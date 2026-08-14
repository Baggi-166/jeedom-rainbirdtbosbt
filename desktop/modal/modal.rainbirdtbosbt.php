<?php
/* Modal de configuration d'une commande rainbirdtbosbt. */
if (!isConnect('admin')) {
    throw new Exception('{{401 - Accès non autorisé}}');
}

$cmd = cmd::byId(init('id'));
if (!is_object($cmd)) {
    throw new Exception(__('Commande introuvable', __FILE__));
}
sendVarToJS('cmd');
?>
<form class="form-horizontal">
    <fieldset>
        <legend><i class="fas fa-cog"></i> {{Configuration de la commande}}</legend>
        <?php if ($cmd->getType() == 'action') { ?>
            <div class="form-group">
                <label class="col-sm-3 control-label">{{Type d'action}}</label>
                <div class="col-sm-3">
                    <select class="cmdAttr form-control" data-l1key="configuration" data-l2key="action_type">
                        <option value="zone_start">{{Démarrer zone}}</option>
                        <option value="zone_stop">{{Arrêter zone}}</option>
                        <option value="stop_all">{{Arrêt général}}</option>
                    </select>
                </div>
                <div class="col-sm-6">
                    <span class="help-block">{{Action à exécuter sur le programmateur.}}</span>
                </div>
            </div>
            <div class="form-group">
                <label class="col-sm-3 control-label">{{Zone (1-6)}}</label>
                <div class="col-sm-3">
                    <input type="number" min="1" max="6" class="cmdAttr form-control" data-l1key="configuration" data-l2key="zone" placeholder="1"/>
                </div>
                <div class="col-sm-6">
                    <span class="help-block">{{Numéro de zone concernée par les commandes de démarrage/arrêt.}}</span>
                </div>
            </div>
            <div class="form-group">
                <label class="col-sm-3 control-label">{{Durée (secondes)}}</label>
                <div class="col-sm-3">
                    <input type="number" min="1" class="cmdAttr form-control" data-l1key="configuration" data-l2key="duration_s" placeholder="60"/>
                </div>
                <div class="col-sm-6">
                    <span class="help-block">{{Durée d'arrosage en secondes (défaut : 60).}}</span>
                </div>
            </div>
        <?php } ?>
    </fieldset>
</form>
