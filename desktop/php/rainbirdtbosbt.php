<?php
if (!isConnect('admin')) {
    throw new Exception('{{401 - Accès non autorisé}}');
}
$plugin = plugin::byId('rainbirdtbosbt');
sendVarToJS([
    'eqType' => 'rainbirdtbosbt',
]);
?>

<div class="row row-overflow">
    <div class="col-xs-12 eqLogicThumbnailDisplay">
        <legend><i class="fas fa-tint"></i> {{Mes arroseurs Rain Bird}}</legend>

        <!-- Bouton découverte : prend une MAC en entrée, crée l'équipement -->
        <div class="input-group" style="margin-bottom:15px;max-width:520px;">
            <span class="input-group-addon roundedLeft"><i class="fas fa-search"></i> {{Découverte}}</span>
            <input type="text" id="rainbird_discover_mac" class="form-control" placeholder="{{Adresse MAC (ex. FF:31:C7:36:16:10)}}"/>
            <span class="input-group-btn">
                <a class="btn btn-default roundedRight" id="bt_rainbird_discover"><i class="fas fa-wifi"></i> {{Découvrir}}</a>
            </span>
        </div>

        <div class="eqLogicThumbnailContainer">
            <div class="cursor eqLogicAction logoPrimary" data-action="add">
                <i class="fas fa-plus-circle"></i>
                <br/>
                <span>{{Ajouter}}</span>
            </div>
            <div class="cursor eqLogicAction logoSecondary" data-action="gotoPluginConf">
                <i class="fas fa-cogs"></i>
                <br/>
                <span>{{Configuration}}</span>
            </div>
        </div>

        <div class="input-group" style="margin-top:15px;">
            <span class="input-group-addon roundedLeft">{{Rechercher}}</span>
            <input class="filter form-control roundedRight" placeholder="{{Rechercher un équipement}}"/>
        </div>

        <div id="eqLogicThumbnailContainer">
            <?php
            foreach (eqLogic::byType('rainbirdtbosbt') as $eqLogic) {
                echo '<div class="eqLogicDisplayCard cursor" data-eqLogic_id="' . $eqLogic->getId() . '">';
                echo '<img src="' . $plugin->getPathImgIcon() . '"/>';
                echo '<br/>';
                echo '<span class="name">' . $eqLogic->getHumanName(true, true) . '</span>';
                echo '</div>';
            }
            ?>
        </div>
    </div>

    <div class="col-xs-12 eqLogic" style="display:none;">
        <div class="input-group pull-right" style="display:inline-flex;">
            <a class="btn btn-success btn-sm eqLogicAction" data-action="save"><i class="fas fa-check-circle"></i> {{Sauvegarder}}</a>
            <a class="btn btn-danger btn-sm eqLogicAction" data-action="remove"><i class="fas fa-minus-circle"></i> {{Supprimer}}</a>
            <a class="btn btn-default btn-sm eqLogicAction" data-action="configure"><i class="fas fa-cogs"></i> {{Configuration avancée}}</a>
        </div>

        <ul class="nav nav-tabs" role="tablist">
            <li role="presentation"><a href="#" class="eqLogicAction" data-action="returnToThumbnailDisplay"><i class="fas fa-arrow-circle-left"></i></a></li>
            <li role="presentation"><a href="#eqlogictab" role="tab" data-toggle="tab"><i class="fas fa-tachometer-alt"></i> {{Equipement}}</a></li>
            <li role="presentation"><a href="#commandtab" role="tab" data-toggle="tab"><i class="fas fa-list-alt"></i> {{Commandes}}</a></li>
        </ul>

        <div class="tab-content">
            <!-- Onglet équipement -->
            <div role="tabpanel" class="tab-pane active" id="eqlogictab">
                <form class="form-horizontal">
                    <fieldset>
                        <legend><i class="fas fa-tint"></i> {{Identification du programmateur}}</legend>
                        <div class="form-group">
                            <label class="col-sm-3 control-label">{{Nom de l'équipement}}</label>
                            <div class="col-sm-3">
                                <input type="text" class="eqLogicAttr form-control" data-l1key="name" placeholder="{{Nom}}"/>
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="col-sm-3 control-label">{{Objet parent}}</label>
                            <div class="col-sm-3">
                                <select id="sel_object" class="eqLogicAttr form-control" data-l1key="object_id">
                                    <option value="">{{Aucun}}</option>
                                    <?php
                                    foreach (object::all() as $object) {
                                        echo '<option value="' . $object->getId() . '">' . $object->getName() . '</option>';
                                    }
                                    ?>
                                </select>
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="col-sm-3 control-label">{{Adresse MAC}}</label>
                            <div class="col-sm-3">
                                <input type="text" class="eqLogicAttr form-control" data-l1key="configuration" data-l2key="mac" placeholder="FF:31:C7:36:16:10"/>
                            </div>
                            <div class="col-sm-6">
                                <span class="help-block">{{Adresse MAC du programmateur Rain Bird TBOS-BT (ex. FF:31:C7:36:16:10)}}</span>
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="col-sm-3 control-label">{{Catégorie}}</label>
                            <div class="col-sm-9">
                                <?php
                                foreach (jeedom::getConfiguration('eqLogic:category') as $key => $value) {
                                    echo '<label class="checkbox-inline"><input type="checkbox" class="eqLogicAttr" data-l1key="category" data-l2key="' . $key . '" checked/>{{' . $value['name'] . '}}</label>';
                                }
                                ?>
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="col-sm-3 control-label">{{Options}}</label>
                            <div class="col-sm-9">
                                <label class="checkbox-inline"><input type="checkbox" class="eqLogicAttr" data-l1key="isEnable" checked/>{{Activer}}</label>
                                <label class="checkbox-inline"><input type="checkbox" class="eqLogicAttr" data-l1key="isVisible" checked/>{{Visible}}</label>
                            </div>
                        </div>
                    </fieldset>
                </form>
            </div>

            <!-- Onglet commandes -->
            <div role="tabpanel" class="tab-pane" id="commandtab">
                <a class="btn btn-default btn-sm pull-right cmdAction" data-action="add" style="margin-top:5px;"><i class="fas fa-plus-circle"></i> {{Ajouter une commande}}</a>
                <br/><br/>
                <div class="table-responsive">
                    <table id="table_cmd" class="table table-bordered table-condensed">
                        <thead>
                        <tr>
                            <th>{{Id}}</th>
                            <th>{{Nom}}</th>
                            <th>{{Type}}</th>
                            <th>{{Paramètres}}</th>
                            <th>{{Options}}</th>
                            <th>{{Action}}</th>
                        </tr>
                        </thead>
                        <tbody>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<?php include_file('desktop', 'rainbirdtbosbt', 'js', 'rainbirdtbosbt'); ?>
<?php include_file('core', 'plugin.template', 'js'); ?>
