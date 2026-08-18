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

    /** @var array<string,bool>|null Commandes créées/gérées par _createCommands() au passage courant. */
    private static $_managedLogicalIds = null;

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
     * Helper statique commun : construit la ligne de commande `python3 main.py ...`
     * avec --address et --adapter. Centralise la logique partagée par l'appel
     * d'instance (sendCommand / fetchStatus) et l'appel statique de découverte,
     * afin qu'un changement de paramétrage se fasse en un seul endroit.
     *
     * @param string $mac  Adresse MAC du programmateur.
     * @param array  $args Args spécifiques au sous-mode (ex. ['status']
     *                    ou ['command', '--json', $json]).
     * @return string Ligne de commande prête à exécuter (stdout parsé, stderr masqué).
     */
    private static function _buildPythonCmd(string $mac, array $args = []): string {
        $python = config::byKey('python_path', 'rainbirdtbosbt', self::_defaultPythonPath());
        $scriptsDir = config::byKey('scripts_dir', 'rainbirdtbosbt', dirname(__DIR__) . '/scripts');
        $main = $scriptsDir . '/main.py';

        $fullArgs = ['--address', $mac];
        $adapter = self::_adapterConfig();
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
     * Renvoie l'adapter Bluetooth configuré au niveau du plugin (null si non défini).
     */
    private static function _adapterConfig(): ?string {
        $a = trim(config::byKey('adapter', 'rainbirdtbosbt', ''));
        return ($a !== '') ? $a : null;
    }

    /**
     * Chemin de l'exécutable Python par défaut : le binaire du venv dédié au
     * plugin s'il existe, sinon 'python3' du système.
     */
    private static function _defaultPythonPath(): string {
        $venvPython = dirname(__DIR__, 2) . '/resources/venv/bin/python3';
        return is_executable($venvPython) ? $venvPython : 'python3';
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
        $cmd = self::_buildPythonCmd($mac, ['status']);
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
     * Appelle `main.py status` et retorne le tableau décodé du JSON d'état.
     */
    public function fetchStatus(): array {
        $cmd = self::_buildPythonCmd($this->getMac(), ['status']);
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
     *
     * Garde-fou lecture incomplète : si le JSON renvoyé par le script Python
     * manque une section clé (controller, water_budget, programs), on considère
     * la lecture comme ratée et on n'écrase PAS les commandes d'affichage avec
     * des valeurs par défaut (0 / vide). On logge un warning et on conserve
     * l'état précédent, plutôt que d'afficher un "00:00" ou une durée à 0 qui
     * laisserait croire à un état réel alors que c'est une lecture échouée.
     */
    public function refreshStatus(): void {
        try {
            $status = $this->fetchStatus();
        } catch (Throwable $e) {
            log::add('rainbirdtbosbt', 'error', 'refreshStatus : ' . $e->getMessage());
            return;
        }

        // --- Garde-fou : valider la cohérence minimale du payload reçu ---
        $controller = $status['controller'] ?? null;
        $waterBudget = $status['water_budget'] ?? null;
        $programs = $status['programs'] ?? null;
        $incomplete = false;
        if (!is_array($controller)) {
            $incomplete = true;
        } elseif (!array_key_exists('state', $controller)) {
            // 'state' peut légitimement valoir null (décodeur BLE) mais la clé
            // doit être présente : son absence signifie une trame d'état non reçue.
            $incomplete = true;
        }
        if (!is_array($waterBudget)) {
            $incomplete = true;
        }
        if (!is_array($programs)) {
            $incomplete = true;
        }
        if ($incomplete) {
            log::add(
                'rainbirdtbosbt',
                'warning',
                'refreshStatus : lecture incomplète (sections manquantes), état conservé inchangé.'
            );
            return;
        }

        $activeZone = $controller['active_zone'] ?? null;

        // État global de la station
        $this->checkAndUpdateCmd('controller_state', $controller['state'] ?? '');

        // État par voie : "1" si la voie est active, "0" sinon.
        $zoneCount = $this->_getZoneCount();
        for ($i = 1; $i <= $zoneCount; $i++) {
            $this->checkAndUpdateCmd('zone_state_' . $i, ($activeZone === $i) ? 1 : 0);
        }

        // Budget eau mensuel : 12 valeurs (01-12) + mois courant
        $monthly = $waterBudget['monthly'] ?? [];
        for ($m = 1; $m <= 12; $m++) {
            $key = sprintf('%02d', $m);
            // On ne met à jour que les mois effectivement présents dans la réponse :
            // un mois manquant = lecture partielle, on conserve la valeur précédente.
            if (array_key_exists($key, $monthly)) {
                $this->checkAndUpdateCmd('budget_month_' . $key, $monthly[$key]);
            }
        }
        $this->checkAndUpdateCmd('budget_current_month', $waterBudget['current_month_percent'] ?? 0);

        // Programmes A/B/C : jours actifs, heure de départ, durées par voie, budget propre
        foreach (['A', 'B', 'C'] as $prog) {
            $p = $programs[$prog] ?? [];
            $days = $p['active_days'] ?? [];
            $this->checkAndUpdateCmd('program_' . $prog . '_days', implode(',', $days));
            $starts = $p['start_times'] ?? [];
            $this->checkAndUpdateCmd('program_' . $prog . '_start', $starts[0] ?? '');
            $durations = $p['durations_s'] ?? [];
            $durParts = [];
            $zoneCount = $this->_getZoneCount();
            for ($z = 1; $z <= $zoneCount; $z++) {
                $val = $durations[$z] ?? $durations[(string)$z] ?? null;
                // Si la durée d'une voie est absente du payload, on ne fabrique
                // pas un "z:0" qui ressemblerait à un état réel ; on marque le
                // créneau comme non lu via '?' pour signaler une lecture incomplète.
                $durParts[] = $z . ':' . ($val === null ? '?' : $val);
            }
            $this->checkAndUpdateCmd('program_' . $prog . '_durations', implode(',', $durParts));
            // Budget propre au programme (distinct du budget mensuel global) :
            // on ne met à jour que si la clé est effectivement présente, pour ne
            // pas écraser une valeur réelle par un 0 en cas de lecture partielle.
            if (array_key_exists('budget_percent', $p)) {
                $this->checkAndUpdateCmd('program_' . $prog . '_budget', $p['budget_percent']);
            }
        }
    }

    /**
     * Envoie une commande JSON au programmateur via `main.py command`.
     *
     * Le rafraîchissement automatique après action est optionnel (mode debug)
     * pour éviter une seconde connexion BLE complète juste après celle de l'action.
     * Activé par la configuration 'refresh_after_action' (défaut : désactivé).
     */
    public function sendCommand(array $command): array {
        $json = json_encode($command, JSON_UNESCAPED_UNICODE);
        $cmd = self::_buildPythonCmd($this->getMac(), ['command', '--json', $json]);
        $output = shell_exec($cmd);
        $data = json_decode($output, true);
        if (!is_array($data)) {
            log::add('rainbirdtbosbt', 'error', 'sendCommand réponse non-JSON : ' . substr($output, 0, 200));
            throw new Exception(__('Échec d\'envoi de la commande.', __FILE__));
        }
        // Rafraîchissement optionnel après action (mode debug, défaut off).
        if (config::byKey('refresh_after_action', 'rainbirdtbosbt', 0)) {
            $this->refreshStatus();
        }
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
        // Réinitialise la liste des commandes gérées à ce passage : sert ensuite
        // à supprimer les commandes devenues obsolètes (nb de voies modifié).
        self::$_managedLogicalIds = [];

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


        // --- Marche/Arrêt général (power on/off) ---
        // Distinct de stop_all : STOP (09-05-15) coupe l'irrigation en cours
        // sans désactiver les programmes auto ; OFF (power:off, état 0x00)
        // désactive l'automatisme lui-même. Voir PROTOCOL.md.
        $this->_addActionCmd('power_on', __('Marche auto (ON)', __FILE__), 'power_on');
        $this->_addActionCmd('power_off', __('Arrêt auto (OFF)', __FILE__), 'power_off');

        // --- Arrêt général (stop irrigation en cours, programmes intacts) ---
        $this->_addActionCmd('stop_all', __('Arrêt irrigation (STOP)', __FILE__), 'stop_all');


        // --- Budget eau mensuel ---
        $months = [
            '01' => 'Janvier', '02' => 'Février', '03' => 'Mars',
            '04' => 'Avril', '05' => 'Mai', '06' => 'Juin',
            '07' => 'Juillet', '08' => 'Août', '09' => 'Septembre',
            '10' => 'Octobre', '11' => 'Novembre', '12' => 'Décembre',
        ];
        foreach ($months as $num => $label) {
            $this->_addInfoCmd('budget_month_' . $num, sprintf('Budget %s', $label), 'numeric');
        }
        $this->_addInfoCmd('budget_current_month', __('Budget mois courant', __FILE__), 'numeric');
        $this->_addActionCmd('set_budget', __('Modifier budget', __FILE__), 'set_budget');

        // --- Programmes A/B/C (lecture + écriture) ---
        foreach (['A', 'B', 'C'] as $prog) {
            $this->_addInfoCmd('program_' . $prog . '_days', sprintf(__('Programme %s — jours', __FILE__), $prog), 'string');
            $this->_addInfoCmd('program_' . $prog . '_start', sprintf(__('Programme %s — heure départ', __FILE__), $prog), 'string');
            $this->_addInfoCmd('program_' . $prog . '_durations', sprintf(__('Programme %s — durées', __FILE__), $prog), 'string');
            $this->_addInfoCmd('program_' . $prog . '_budget', sprintf(__('Programme %s — budget', __FILE__), $prog), 'numeric');
            $this->_addActionCmd('set_program_' . $prog, sprintf(__('Programme %s — modifier', __FILE__), $prog), 'set_program', ['program' => $prog]);
        }

        // --- Nettoyage des commandes obsolètes ---
        // Si le nombre de voies change entre deux sauvegardes (rare), les anciennes
        // commandes zone_state_N/zone_start_N/zone_stop_N au-delà du nouveau
        // nombre deviendraient orphelines. On supprime celles qui ne sont plus
        // gérées par _createCommands().
        $this->_removeObsoleteCommands();
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
        self::$_managedLogicalIds[$logicalId] = true;
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
        self::$_managedLogicalIds[$logicalId] = true;
    }

    /**
     * Supprime les commandes de cet équipement dont le logicalId n'est plus
     * géré par _createCommands(). Évite l'accumulation de commandes orphelines
     * (zone_state_N / zone_start_N / zone_stop_N) si le nombre de voies diminue.
     */
    private function _removeObsoleteCommands(): void {
        $managed = self::$_managedLogicalIds;
        if ($managed === null) {
            return; // Sécurité : ne rien faire si la liste gérée n'a pas été peuplée.
        }
        foreach ($this->getCmd() as $cmd) {
            $lid = $cmd->getLogicalId();
            if ($lid !== '' && !isset($managed[$lid])) {
                $cmd->remove();
                log::add('rainbirdtbosbt', 'info', sprintf(
                    'Commande obsolète supprimée : %s (équipement %s)',
                    $lid,
                    $this->getName()
                ));
            }
        }
    }

    // =====================================================================
    // Cron : rafraîchissement périodique des équipements actifs
    // =====================================================================

    /**
     * Cron toutes les 15 minutes.
     *
     * Stratégie de rafraîchissement configurable au niveau du plugin
     * (clé 'refresh_strategy') pour préserver la pile du contrôleur :
     *  - 'on_demand' (défaut) : aucun rafraîchissement automatique, uniquement
     *    via la commande manuelle ou postUpdate.
     *  - 'during_program' : rafraîchit seulement à la minute si un programme
     *    est susceptible d'être en cours (on connaît la programmation lue).
     *  - 'daily_05h' : un rafraîchissement par jour, vers 05h00.
     *  - 'every_15min' : rafraîchit à chaque appel (comportement historique).
     */
    public static function cron15() {
        $strategy = config::byKey('refresh_strategy', 'rainbirdtbosbt', 'on_demand');

        foreach (self::byType('rainbirdtbosbt', true) as $eqLogic) {
            try {
                if (!self::_shouldRefresh($eqLogic, $strategy)) {
                    continue;
                }
                $eqLogic->refreshStatus();
            } catch (Throwable $e) {
                log::add('rainbirdtbosbt', 'error', 'cron15 ' . $eqLogic->getName() . ' : ' . $e->getMessage());
            }
        }
    }

    /**
     * Détermine si un équipement doit être rafraîchi lors du passage courant
     * du cron15, selon la stratégie configurée.
     */
    private static function _shouldRefresh(rainbirdtbosbt $eq, string $strategy): bool {
        switch ($strategy) {
            case 'every_15min':
                return true;

            case 'daily_05h':
                // Une seule fenêtre par jour : slot 04:45 -> 05:00 (cron15),
                // on tolère un petit décalage en incluant 05:00.
                $h = (int) date('G');
                $m = (int) date('i');
                return ($h === 4 && $m >= 45) || ($h === 5 && $m === 0);

            case 'during_program':
                // Rafraîchit à la minute précise d'un départ de programme
                // (start_times lu), pendant la durée d'arrosage d'au moins une
                // voie du programme concerné. Évite les lectures inutiles le
                // reste du temps et préserve la pile.
                return self::_isProgramRunningNow($eq);

            case 'on_demand':
            default:
                return false;
        }
    }

    /**
     * Indique si un programme de l'équipement est censé être en cours à
     * l'heure courante (heure de départ atteinte, dans la fenêtre de durée
     * d'au moins une voie). Utilise la programmation lue et stockée dans les
     * commandes info (program_X_start / program_X_durations).
     */
    private static function _isProgramRunningNow(rainbirdtbosbt $eq): bool {
        $nowMin = (int) date('G') * 60 + (int) date('i');
        // Étiquette du jour (lun..dim) pour filtrer les jours actifs connus.
        $todayLabel = ['dim', 'lun', 'mar', 'mer', 'jeu', 'ven', 'sam'][(int) date('w')];

        foreach (['A', 'B', 'C'] as $prog) {
            $startCmd = $eq->getCmd(null, 'program_' . $prog . '_start');
            if (!is_object($startCmd)) {
                continue;
            }
            $startStr = trim($startCmd->execCmd());
            if (!preg_match('/^([01]?\d|2[0-3]):([0-5]\d)$/', $startStr, $m)) {
                continue;
            }
            $startMin = ((int) $m[1]) * 60 + (int) $m[2];

            $daysCmd = $eq->getCmd(null, 'program_' . $prog . '_days');
            if (is_object($daysCmd)) {
                $days = array_filter(array_map('trim', explode(',', (string) $daysCmd->execCmd())));
                if (!empty($days) && !in_array($todayLabel, $days, true)) {
                    continue; // Programme non planifié aujourd'hui.
                }
            }

            // Durée max d'une voie = fenêtre pendant laquelle un arrosage est actif.
            $durCmd = $eq->getCmd(null, 'program_' . $prog . '_durations');
            if (!is_object($durCmd)) {
                continue;
            }
            $maxDuration = 0;
            foreach (explode(',', (string) $durCmd->execCmd()) as $part) {
                if (preg_match('/^\d+:(\d+)$/', $part, $dm)) {
                    $maxDuration = max($maxDuration, (int) $dm[1]);
                }
            }
            if ($maxDuration <= 0) {
                continue;
            }
            if ($nowMin >= $startMin && $nowMin < $startMin + $maxDuration) {
                return true;
            }
        }
        return false;
    }
}
