<?php
/* Configuration globale du plugin (page Plugins → Gestion des plugins → Rain Bird TBOS-BT). */

if (!isConnect('admin')) {
    throw new Exception('{{401 - Accès non autorisé}}');
}

// Valeurs par défaut : python3 et scripts à côté du plugin.
$pythonPath = config::byKey('python_path', 'rainbirdtbosbt', 'python3');
$scriptsDir = config::byKey('scripts_dir', 'rainbirdtbosbt', dirname(__DIR__) . '/scripts');
$adapter = config::byKey('adapter', 'rainbirdtbosbt', '');

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
                <span class="help-block">{{Chemin de l'exécutable Python (python3 par défaut).}}</span>
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
</form>
