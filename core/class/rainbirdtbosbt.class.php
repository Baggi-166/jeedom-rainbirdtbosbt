<?php
/* This file is part of Jeedom.
 *
 * Jeedom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * Jeedom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with Jeedom. If not, see <http://www.gnu.org/licenses/>.
 */

require_once dirname(__FILE__) . '/../../../core/php/core.inc.php';
require_once dirname(__FILE__) . '/rainbirdtbosbtCmd.class.php';

/**
 * Équipement Jeedom représentant un programmateur Rain Bird TBOS-BT.
 *
 * Un équipement = un programmateur physique identifié par son adresse MAC
 * (configuration 'mac'). Toutes les commandes info/action sont créées dans
 * postSave() et exécutées via les scripts Python du dossier scripts/ en
 * appel direct (shell_exec sur main.py).
 *
 * Découverte : discoverByMac($mac) se connecte, lit l'état via main.py status,
 * crée l'équipement portant le nom de la station, et crée les commandes par
 * voie (état/marche/arrêt) avec le nom de chaque voie récupéré.
 */
class rainbirdtbosbt extends eqLogic {

    const NB_ZONES = 6;

    // =====================================================================
    // Cycle de vie de l'équipement
    // =====================================================================

    public function preSave() {
        $this->setDisplay('width', '450px');
    }

    public function postSave() {
        $this->_createCommands();
    }

    public function postUpdate() {
        // Première mise à jour de l'état dès la création de l'équipement.
        $this->refreshStatus();
    }

    // =====================================================================
    // Découverte automatique
    // =====================================================================

    /**
     * Découvre un programmateur à partir de son adresse MAC :
     * se connecte via main.py status, lit le nom de la station + noms des voies,
     * crée l'équipement portant ce nom, et crée les commandes.
     *
     * @param string $mac Adresse MAC du programmateur.
     * @return rainbirdtbosbt L'équipement créé.
     * @throws Exception Si la connexion échoue ou la MAC est vide.
     */
    public static function discoverByMac(string $mac): rainbirdtbosbt {
        $mac = trim($mac);
        if ($mac === '') {
            throw new Exception(__('Adresse MAC vide.', __FILE__));
        }

        // Lecture de l'état via main.py : on récupère notamment les noms de voies.
        $status = self::_fetchStatusRaw($mac);
        $stationName = self::_extractStationName($status);

        // Vérifie si un équipement avec cette MAC existe déjà.
        $eqLogic = self::_findByMac($mac);
        if (!is_object($eqLogic)) {
            $eqLogic = new self();
            $eqLogic->setName($stationName);
        } else {
            $eqLogic->setName($stationName);
        }
        $eqLogic->setEqType_name('rainbirdtbosbt');
        $eqLogic->setConfiguration('mac', $mac);
        $eqLogic->setIsEnable(1);
        $eqLogic->setIsVisible(1);
        $eqLogic->save();

        // Mémorise le nombre de voies détectées + leurs noms.
        $zones = $status['zones'] ?? [];
        $zoneCount = count($zones);
        $eqLogic->setConfiguration('zone_count', $zoneCount);
        foreach ($zones as $idx => $zone) {
            $eqLogic->setConfiguration('zone_name_' . $idx, $zone['name'] ?? ('Zone ' . $idx));
        }
        $eqLogic->save();

        // Crée les commandes et rafraîchit l'état.
        $eqLogic->_createCommands();
        $eqLogic->refreshStatus();

        return $eqLogic;
    }

    /**
     * Extrait le nom de la station depuis le JSON d'état.
     * Le TBOS-BT ne renvoie pas de nom de station explicite ; on construit
     * un nom lisible à partir du nom de la première voie (souvent "JARDIN D",
     * "JARDIN G"...) ou on retombe sur "Rain Bird <MAC>".
     */
    private static function _extractStationName(array $status): string {
        $zones = $status['zones'] ?? [];
        if (!empty($zones)) {
            $first = reset($zones);
            if (!empty($first['name'])) {
                return $first['name'];
            }
        }
        $mac = $status['mac'] ?? '';
        return 'Rain Bird' . ($mac ? ' ' . $mac : '');
    }

    private static function _findByMac(string $mac): ?rainbirdtbosbt {
        foreach (self::byType('rainbirdtbosbt') as $eq) {
            if (strcasecmp(trim($eq->getConfiguration('mac', '')), $mac) === 0) {
                return $eq;
            }
        }
        return null;
    }

    // =====================================================================
    // Appel aux scripts Python existants (JSON sur stdout)
    // =====================================================================

    /**
     * Renvoie l'adapter Bluetooth configuré au niveau du plugin.
     */
    private function _getAdapter(): ?string {
        $a = trim(config::byKey('adapter', 'rainbirdtbosbt', ''));
        return ($a !== '') ? $a : null;
    }

    /**
     * Construit la ligne de commande `python3 main.py ...` avec adapter.
     */
    private function _buildPythonCmd(array $args): string {
        $python = config::byKey('python_path', 'rainbirdtbosbt', 'python3');
        $scriptsDir = config::byKey('scripts_dir', 'rainbirdtbosbt', dirname(__DIR__) . '/scripts');
        $main = $scriptsDir . '/main.py';

        $fullArgs = array();
        $adapter = $this->_getAdapter();
        if ($adapter !== null) {
            $fullArgs[] = '--adapter';
            $fullArgs[] = $adapter;
        }
        foreach ($args as $a) {
            $fullArgs[] = $a;
        }

        $parts = array_map('escapeshellarg', $fullArgs);
        return sprintf(
            '%s %s %s 2>/dev/null',
            escapeshellcmd($python),
            escapeshellarg($main),
            implode(' ', $parts)
        );
    }

    /**
     * Récupère l'adresse MAC configurée sur l'équipement.
     */
    public function getMac(): string {
        $mac = trim($this->getConfiguration('mac', ''));
        if ($mac === '') {
            throw new Exception(__('Adresse MAC non renseignée sur l\'équipement.', __FILE__));
        }
        return $mac;
    }

    /**
     * Appelle statiquement `main.py status` (pour la découverte, sans équipement).
     */
    private static function _fetchStatusRaw(string $mac, float $timeout = 15.0): array {
        $python = config::byKey('python_path', 'rainbirdtbosbt', 'python3');
        $scriptsDir = config::byKey('scripts_dir', 'rainbirdtbosbt', dirname(__DIR__) . '/scripts');
        $adapter = trim(config::byKey('adapter', 'rainbirdtbosbt', ''));

        $args = array();
        $args[] = '--address';
        $args[] = $mac;
        if ($adapter !== '') {
            $args[] = '--adapter';
            $args[] = $adapter;
        }
        $args[] = 'status';

        $parts = array_map('escapeshellarg', $args);
        $cmd = sprintf('%s %s %s 2>/dev/null', escapeshellcmd($python), escapeshellarg($scriptsDir . '/main.py'), implode(' ', $parts));

        $output = shell_exec($cmd);
        $data = json_decode($output, true);
        if (!is_array($data)) {
            log::add('rainbirdtbosbt', 'error', 'discoverByMac réponse non-JSON : ' . substr($output, 0, 200));
            throw new Exception(__('Échec de connexion au programmateur (vérifiez l\'adresse MAC et la portée Bluetooth).', __FILE__));
        }
        $data['mac'] = $mac;
        return $data;
    }

    /**
     * Appelle `main.py status` et retourne le tableau décodé du JSON d'état.
     */
    public function fetchStatus(): array {
        $cmd = $this->_buildPythonCmd(['--address', $this->getMac(), 'status']);
        $output = shell_exec($cmd);
        $data = json_decode($output, true);
        if (!is_array($data)) {
            log::add('rainbirdtbosbt', 'error', 'Réponse non-JSON : ' . substr($output, 0, 200));
            throw new Exception(__('Échec de lecture de l\'état du programmateur.', __FILE__));
        }
        return $data;
    }

    /**
     * Lit l'état via fetchStatus() et met à jour toutes les commandes info.
     */
    public function refreshStatus(): void {
        try {
            $status = $this->fetchStatus();
        } catch (Throwable $e) {
            log::add('rainbirdtbosbt', 'error', 'refreshStatus : ' . $e->getMessage());
            return;
        }

        $controller = $status['controller'] ?? [];
        $activeZone = $controller['active_zone'] ?? null;

        // État global de la station
        $this->checkAndUpdateCmd('controller_state', $controller['state'] ?? '');

        // État par voie : "1" si la voie est active, "0" sinon.
        $zoneCount = $this->_getZoneCount();
        for ($i = 1; $i <= $zoneCount; $i++) {
            $this->checkAndUpdateCmd('zone_state_' . $i, ($activeZone === $i) ? 1 : 0);
        }
    }

    /**
     * Envoie une commande JSON au programmateur via `main.py command`.
     */
    public function sendCommand(array $command): array {
        $json = json_encode($command, JSON_UNESCAPED_UNICODE);
        $cmd = $this->_buildPythonCmd(['--address', $this->getMac(), 'command', '--json', $json]);
        $output = shell_exec($cmd);
        $data = json_decode($output, true);
        if (!is_array($data)) {
            log::add('rainbirdtbosbt', 'error', 'sendCommand réponse non-JSON : ' . substr($output, 0, 200));
            throw new Exception(__('Échec d\'envoi de la commande.', __FILE__));
        }
        // Après une action, on rafraîchit l'état pour refléter le changement.
        $this->refreshStatus();
        return $data;
    }

    // =====================================================================
    // Nombre de voies (dynamique, depuis la configuration)
    // =====================================================================

    /**
     * Renvoie le nombre de voies de l'équipement.
     * Défini lors de la découverte à partir des voies réellement
     * renvoyées par le programmateur (1, 2, 4, 6...). Défaut : 6.
     */
    private function _getZoneCount(): int {
        $count = (int) $this->getConfiguration('zone_count', 0);
        return $count > 0 ? $count : self::NB_ZONES;
    }

    // =====================================================================
    // Création des commandes Jeedom
    // =====================================================================

    private function _createCommands(): void {
        // --- État global de la station ---
        $this->_addInfoCmd('controller_state', __('État station', __FILE__), 'string');

        // --- Par voie (état + marche + arrêt), nombre dynamique ---
        $zoneCount = $this->_getZoneCount();
        for ($i = 1; $i <= $zoneCount; $i++) {
            $name = $this->getConfiguration('zone_name_' . $i, sprintf(__('Zone %d', __FILE__), $i));
            $this->_addInfoCmd('zone_state_' . $i, sprintf('%s — %s', $name, __('état', __FILE__)), 'binary');
            $this->_addActionCmd('zone_start_' . $i, sprintf('%s — %s', $name, __('Marche', __FILE__)), 'zone_start', ['zone' => $i]);
            $this->_addActionCmd('zone_stop_' . $i, sprintf('%s — %s', $name, __('Arrêt', __FILE__)), 'zone_stop', ['zone' => $i]);
        }

        // --- Arrêt général ---
        $this->_addActionCmd('stop_all', __('Arrêt général', __FILE__), 'stop_all');
    }

    private function _addInfoCmd(string $logicalId, string $name, string $subType): void {
        $cmd = $this->getCmd(null, $logicalId);
        if (!is_object($cmd)) {
            $cmd = new rainbirdtbosbtCmd();
            $cmd->setName($name);
        }
        $cmd->setEqLogic_id($this->getId());
        $cmd->setLogicalId($logicalId);
        $cmd->setType('info');
        $cmd->setSubType($subType);
        $cmd->save();
    }

    /**
     * Ajoute une commande action.
     * $actionType : logicalId du type d'action (zone_start, zone_stop, stop_all, ...)
     *               transmis à rainbirdtbosbtCmd::execute() via la configuration.
     * $configuration : configuration par défaut (zone, duration_s, program, ...).
     */
    private function _addActionCmd(string $logicalId, string $name, string $actionType, array $configuration = []): void {
        $cmd = $this->getCmd(null, $logicalId);
        if (!is_object($cmd)) {
            $cmd = new rainbirdtbosbtCmd();
            $cmd->setName($name);
        }
        $cmd->setEqLogic_id($this->getId());
        $cmd->setLogicalId($logicalId);
        $cmd->setType('action');
        $cmd->setSubType('other');
        $cmd->setConfiguration('action_type', $actionType);
        foreach ($configuration as $k => $v) {
            $cmd->setConfiguration($k, $v);
        }
        $cmd->save();
    }

    // =====================================================================
    // Cron : rafraîchissement périodique de tous les équipements actifs
    // =====================================================================

    public static function cron15() {
        foreach (self::byType('rainbirdtbosbt', true) as $eqLogic) {
            try {
                $eqLogic->refreshStatus();
            } catch (Throwable $e) {
                log::add('rainbirdtbosbt', 'error', 'cron15 ' . $eqLogic->getName() . ' : ' . $e->getMessage());
            }
        }
    }
}
