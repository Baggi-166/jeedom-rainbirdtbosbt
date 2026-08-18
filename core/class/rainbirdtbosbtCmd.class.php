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
 * (zone_start, zone_stop, power_on, power_off, stop_all, set_budget,
 * set_program). La zone concernée est dans la configuration 'zone'.
 * La durée (en secondes) pour zone_start est dans la configuration
 * 'duration_s' (défaut 60).
 * Pour set_budget : 'month' (01-12) et 'budget_value' (multiple de 10, 0-200).
 * Pour set_program : 'program' (A/B/C), 'active_days' (lun,mar,...),
 * 'start_time' (HH:MM), 'durations' (voie:secondes,voie:secondes,...),
 * 'program_budget' (0-255, budget propre au programme, sans contrainte
 * multiple-de-10 contrairement au budget mensuel global).
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

            case 'power_on':
                // power:on active l'automatisme (état 0x40 = On/Auto).
                // Distinct de stop_all : OFF (power:off, état 0x00) désactive
                // l'automatisme lui-même, STOP (stop_all) ne coupe que
                // l'irrigation en cours. Voir PROTOCOL.md.
                $command['power'] = 'on';
                break;

            case 'power_off':
                $command['power'] = 'off';
                break;

            case 'stop_all':
                $command['stop_all'] = true;
                break;

            case 'power_on':
                $command['power'] = 'on';
                break;

            case 'power_off':
                $command['power'] = 'off';
                break;

            case 'set_budget':
                $month = $this->getConfiguration('month', '');
                $value = (int) $this->getConfiguration('budget_value', 100);
                if ($month === '' || !preg_match('/^(0[1-9]|1[0-2])$/', $month)) {
                    log::add('rainbirdtbosbt', 'error', 'set_budget : mois invalide (01-12 attendu) : ' . $month);
                    return null;
                }
                // Le programmateur n'accepte que des multiples de 10% (0-200).
                $value = max(0, min(200, $value));
                $value = (int) round($value / 10) * 10;
                $command['water_budget'] = array('monthly' => array($month => $value));
                break;

            case 'set_program':
                $program = strtoupper($this->getConfiguration('program', ''));
                if (!in_array($program, ['A', 'B', 'C'])) {
                    log::add('rainbirdtbosbt', 'error', 'set_program : programme invalide (A/B/C) : ' . $program);
                    return null;
                }
                $progConfig = array();

                // Jours actifs : "lun,mar,mer,jeu,ven" → tableau
                $rawDays = trim($this->getConfiguration('active_days', ''));
                if ($rawDays !== '') {
                    $validDays = ['lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim'];
                    $days = array_filter(array_map('trim', explode(',', $rawDays)));
                    $cleanDays = [];
                    foreach ($days as $d) {
                        $dl = strtolower($d);
                        if (in_array($dl, $validDays)) {
                            $cleanDays[] = $dl;
                        }
                    }
                    if (!empty($cleanDays)) {
                        $progConfig['active_days'] = $cleanDays;
                    }
                }

                // Heure de départ : "HH:MM"
                $rawStart = trim($this->getConfiguration('start_time', ''));
                if ($rawStart !== '' && preg_match('/^([01]?\d|2[0-3]):([0-5]\d)$/', $rawStart)) {
                    $progConfig['start_times'] = array($rawStart);
                }

                // Durées par voie : "1:900,2:900,3:0,4:0,5:1200,6:0" → dict
                $rawDurations = trim($this->getConfiguration('durations', ''));
                if ($rawDurations !== '') {
                    $durParts = array_filter(array_map('trim', explode(',', $rawDurations)));
                    $durations = array();
                    foreach ($durParts as $part) {
                        if (preg_match('/^(\d+):(\d+)$/', $part, $m)) {
                            $durations[$m[1]] = (int) $m[2];
                        }
                    }
                    if (!empty($durations)) {
                        $progConfig['durations_s'] = $durations;
                    }
                }

                // Budget propre à ce programme (distinct du budget mensuel global) :
                // pas de contrainte multiple-de-10 ici, contrairement à set_budget --
                // CONFIRMÉ par capture réelle (ex. 127% observé). Voir PROTOCOL.md.
                $rawProgBudget = trim($this->getConfiguration('program_budget', ''));
                if ($rawProgBudget !== '') {
                    $progBudget = (int) $rawProgBudget;
                    if ($progBudget < 0 || $progBudget > 255) {
                        log::add('rainbirdtbosbt', 'error', sprintf(
                            'set_program : budget programme hors plage (0-255 attendu) pour %s : %d',
                            $program,
                            $progBudget
                        ));
                        return null;
                    }
                    $progConfig['budget_percent'] = $progBudget;
                }

                if (empty($progConfig)) {
                    log::add('rainbirdtbosbt', 'warning', 'set_program : aucun paramètre fourni pour le programme ' . $program);
                    return null;
                }
                $command['programs'] = array($program => $progConfig);
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
