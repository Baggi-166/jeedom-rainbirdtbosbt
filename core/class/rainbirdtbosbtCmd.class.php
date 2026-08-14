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

/**
 * Commande Jeedom pour le plugin Rain Bird TBOS-BT.
 *
 * Le type d'action est stocké dans la configuration 'action_type'
 * (zone_start, zone_stop, stop_all). La zone concernée est dans la
 * configuration 'zone'. La durée (en secondes) pour zone_start est dans
 * la configuration 'duration_s' (défaut 60).
 */
class rainbirdtbosbtCmd extends cmd {

    public function execute($_options = array()) {
        $eqLogic = $this->getEqLogic();
        if (!is_object($eqLogic) || $eqLogic->getIsEnable() != 1) {
            return null;
        }

        $actionType = $this->getConfiguration('action_type', '');
        $command = array();

        switch ($actionType) {
            case 'zone_start':
                $zone = (int) $this->getConfiguration('zone', 1);
                $duration = (int) $this->getConfiguration('duration_s', 60);
                $command['zones'] = array(array(
                    'index' => $zone,
                    'action' => 'start',
                    'duration_s' => $duration,
                ));
                break;

            case 'zone_stop':
                $zone = (int) $this->getConfiguration('zone', 1);
                $command['zones'] = array(array(
                    'index' => $zone,
                    'action' => 'stop',
                ));
                break;

            case 'stop_all':
                $command['stop_all'] = true;
                break;

            default:
                log::add('rainbirdtbosbt', 'warning', 'Type d\'action inconnu : ' . $actionType);
                return null;
        }

        try {
            $result = $eqLogic->sendCommand($command);
            // Journalise les erreurs éventuelles par action.
            foreach ($result['actions'] ?? array() as $action) {
                if (($action['status'] ?? '') === 'error') {
                    log::add('rainbirdtbosbt', 'error', sprintf(
                        'Action %s en erreur : %s',
                        $action['action'] ?? '?',
                        $action['error'] ?? 'inconnue'
                    ));
                }
            }
        } catch (Throwable $e) {
            log::add('rainbirdtbosbt', 'error', 'execute(' . $actionType . ') : ' . $e->getMessage());
        }

        return null;
    }
}
