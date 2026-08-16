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
                        <option value="set_budget">{{Modifier budget eau}}</option>
                        <option value="set_program">{{Modifier programme}}</option>
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
            <div class="form-group">
                <label class="col-sm-3 control-label">{{Mois (budget eau)}}</label>
                <div class="col-sm-3">
                    <select class="cmdAttr form-control" data-l1key="configuration" data-l2key="month">
                        <option value="">{{Aucun}}</option>
                        <option value="01">{{Janvier}}</option>
                        <option value="02">{{Février}}</option>
                        <option value="03">{{Mars}}</option>
                        <option value="04">{{Avril}}</option>
                        <option value="05">{{Mai}}</option>
                        <option value="06">{{Juin}}</option>
                        <option value="07">{{Juillet}}</option>
                        <option value="08">{{Août}}</option>
                        <option value="09">{{Septembre}}</option>
                        <option value="10">{{Octobre}}</option>
                        <option value="11">{{Novembre}}</option>
                        <option value="12">{{Décembre}}</option>
                    </select>
                </div>
                <div class="col-sm-6">
                    <span class="help-block">{{Mois concerné par la modification du budget eau (pour l'action "Modifier budget eau").}}</span>
                </div>
            </div>
            <div class="form-group">
                <label class="col-sm-3 control-label">{{Valeur budget (%)}}</label>
                <div class="col-sm-3">
                    <input type="number" min="0" max="200" step="10" class="cmdAttr form-control" data-l1key="configuration" data-l2key="budget_value" placeholder="100"/>
                </div>
                <div class="col-sm-6">
                    <span class="help-block">{{Pourcentage du budget eau (multiple de 10, 0-200). Défaut : 100.}}</span>
                </div>
            </div>
            <div class="form-group">
                <label class="col-sm-3 control-label">{{Programme}}</label>
                <div class="col-sm-3">
                    <select class="cmdAttr form-control" data-l1key="configuration" data-l2key="program">
                        <option value="">{{Aucun}}</option>
                        <option value="A">{{Programme A}}</option>
                        <option value="B">{{Programme B}}</option>
                        <option value="C">{{Programme C}}</option>
                    </select>
                </div>
                <div class="col-sm-6">
                    <span class="help-block">{{Programme à modifier (pour l'action "Modifier programme").}}</span>
                </div>
            </div>
            <div class="form-group">
                <label class="col-sm-3 control-label">{{Jours actifs}}</label>
                <div class="col-sm-3">
                    <input type="text" class="cmdAttr form-control" data-l1key="configuration" data-l2key="active_days" placeholder="lun,mar,mer,jeu,ven"/>
                </div>
                <div class="col-sm-6">
                    <span class="help-block">{{Jours d'arrosage séparés par virgules (lun,mar,mer,jeu,ven,sam,dim).}}</span>
                </div>
            </div>
            <div class="form-group">
                <label class="col-sm-3 control-label">{{Heure de départ}}</label>
                <div class="col-sm-3">
                    <input type="text" class="cmdAttr form-control" data-l1key="configuration" data-l2key="start_time" placeholder="06:20"/>
                </div>
                <div class="col-sm-6">
                    <span class="help-block">{{Heure de départ du programme (format HH:MM, ex. 06:20).}}</span>
                </div>
            </div>
            <div class="form-group">
                <label class="col-sm-3 control-label">{{Durées par voie (s)}}</label>
                <div class="col-sm-9">
                    <input type="text" class="cmdAttr form-control" data-l1key="configuration" data-l2key="durations" placeholder="1:900,2:900,3:0,4:0,5:1200,6:0"/>
                    <span class="help-block">{{Durées en secondes par voie (voie:secondes, séparées par virgules). Les voies non mentionnées gardent leur valeur actuelle.}}</span>
                </div>
            </div>
        <?php } ?>
    </fieldset>
</form>
