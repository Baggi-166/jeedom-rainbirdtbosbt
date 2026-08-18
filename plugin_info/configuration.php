<?php
/* Configuration globale du plugin (page Plugins → Gestion des plugins → Rain Bird TBOS-BT). */

if (!isConnect('admin')) {
    throw new Exception('{{401 - Accès non autorisé}}');
}

// Valeurs par défaut : venv dédié au plugin si présent, sinon python3 système.
$venvPython = dirname(__DIR__) . '/resources/venv/bin/python3';
$defaultPython = is_executable($venvPython) ? $venvPython : 'python3';
$pythonPath = config::byKey('python_path', 'rainbirdtbosbt', $defaultPython);
$scriptsDir = config::byKey('scripts_dir', 'rainbirdtbosbt', dirname(__DIR__) . '/scripts');
$adapter = config::byKey('adapter', 'rainbirdtbosbt', '');
$refreshStrategy = config::byKey('refresh_strategy', 'rainbirdtbosbt', 'on_demand');
$refreshAfterAction = config::byKey('refresh_after_action', 'rainbirdtbosbt', 0);

// Scan des interfaces Bluetooth disponibles (hci0, hci1, ...).
$adapters = array();
exec('hciconfig 2>/dev/null', $output, $rc);
if ($rc === 0) {
    foreach ($output as $line) {
        if (preg_match('/^(hci\d+)/', $line, $m)) {
            $adapters[] = $m[1];
        }
    }
}
// Fallback : /sys/class/bluetooth
if (empty($adapters) && is_dir('/sys/class/bluetooth')) {
    foreach (scandir('/sys/class/bluetooth') as $entry) {
        if (strpos($entry, 'hci') === 0) {
            $adapters[] = $entry;
        }
    }
}

$strategies = [
    'on_demand'      => '{{À la demande (aucun refresh auto)}}',
    'during_program' => '{{Pendant un programme en cours}}',
    'daily_05h'      => '{{Journalier vers 05h00}}',
    'every_15min'    => '{{Toutes les 15 min (historique)}}',
];
?>
<form class="form-horizontal">
    <fieldset>
        <legend><i class="fas fa-cog"></i> {{Configuration du moteur}}</legend>
        <div class="form-group">
            <label class="col-sm-3 control-label">{{Exécutable Python}}</label>
            <div class="col-sm-4">
                <input type="text" class="configKey form-control" data-l1key="python_path" value="<?php echo $pythonPath; ?>" placeholder="python3"/>
            </div>
            <div class="col-sm-5">
                <span class="help-block">{{Chemin de l'exécutable Python. Par défaut : le venv dédié du plugin (resources/venv/bin/python3) s'il a été créé par l'installation des dépendances, sinon python3 du système.}}</span>
            </div>
        </div>
        <div class="form-group">
            <label class="col-sm-3 control-label">{{Dossier des scripts}}</label>
            <div class="col-sm-4">
                <input type="text" class="configKey form-control" data-l1key="scripts_dir" value="<?php echo $scriptsDir; ?>" placeholder="/var/www/html/plugins/rainbirdtbosbt/scripts"/>
            </div>
            <div class="col-sm-5">
                <span class="help-block">{{Dossier contenant main.py et core/. Par défaut : scripts/ à côté du plugin.}}</span>
            </div>
        </div>
        <div class="form-group">
            <label class="col-sm-3 control-label">{{Carte Bluetooth}}</label>
            <div class="col-sm-4">
                <select class="configKey form-control" data-l1key="adapter">
                    <?php if (empty($adapters)) { ?>
                        <option value="">{{Aucune carte détectée}}</option>
                    <?php } else { ?>
                        <?php if ($adapter === '') { ?><option value="">{{Par défaut}}</option><?php } ?>
                        <?php foreach ($adapters as $hci) { ?>
                            <option value="<?php echo $hci; ?>" <?php echo ($adapter === $hci) ? 'selected' : ''; ?>><?php echo $hci; ?></option>
                        <?php } ?>
                    <?php } ?>
                </select>
            </div>
            <div class="col-sm-5">
                <span class="help-block">{{Carte Bluetooth à utiliser pour communiquer avec le programmateur.}}</span>
            </div>
        </div>
    </fieldset>

    <fieldset>
        <legend><i class="fas fa-sync"></i> {{Rafraîchissement (préserve la pile)}}</legend>
        <div class="form-group">
            <label class="col-sm-3 control-label">{{Stratégie de refresh}}</label>
            <div class="col-sm-4">
                <select class="configKey form-control" data-l1key="refresh_strategy">
                    <?php foreach ($strategies as $value => $label) { ?>
                        <option value="<?php echo $value; ?>" <?php echo ($refreshStrategy === $value) ? 'selected' : ''; ?>><?php echo $label; ?></option>
                    <?php } ?>
                </select>
            </div>
            <div class="col-sm-5">
                <span class="help-block">{{Fréquence de relire de l'état du programmateur via cron15. Le TBOS-BT est alimenté par pile : privilégier une stratégie peu fréquente. Défaut : à la demande.}}</span>
            </div>
        </div>
        <div class="form-group">
            <label class="col-sm-3 control-label">{{Refresh après chaque action}}</label>
            <div class="col-sm-4">
                <input type="checkbox" class="configKey" data-l1key="refresh_after_action" <?php echo $refreshAfterAction ? 'checked' : ''; ?>/>
            </div>
            <div class="col-sm-5">
                <span class="help-block">{{Mode debug : relit l'état complet juste après chaque commande (déclenche une seconde connexion BLE). Désactivé par défaut pour limiter l'usure de la pile.}}</span>
            </div>
        </div>
    </fieldset>
</form>
