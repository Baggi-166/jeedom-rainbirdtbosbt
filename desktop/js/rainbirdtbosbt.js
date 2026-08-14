/* rainbirdtbosbt — script desktop */

/* Bouton découverte : prend la MAC, appelle l'AJAX, recharge la page. */
$(document).on('click', '#bt_rainbird_discover', function () {
    var mac = $('#rainbird_discover_mac').val();
    if (mac === '') {
        $('#div_alert').showAlert({ message: '{{Adresse MAC requise}}', level: 'danger' });
        return;
    }
    $('#div_alert').showAlert({ message: '{{Découverte en cours...}}', level: 'warning' });
    $.ajax({
        type: 'POST',
        url: 'plugins/rainbirdtbosbt/core/ajax/rainbirdtbosbt.ajax.php',
        data: {
            action: 'discover',
            mac: mac
        },
        dataType: 'json',
        error: function (request, status, error) {
            handleAjaxError(request, status, error);
        },
        success: function (data) {
            if (data.state !== 'ok') {
                $('#div_alert').showAlert({ message: data.result, level: 'danger' });
                return;
            }
            $('#div_alert').showAlert({
                message: '{{Équipement créé : }}' + data.result.name,
                level: 'success'
            });
            // Recharge la liste des équipements.
            setTimeout(function () {
                window.location.reload();
            }, 1500);
        }
    });
});

/* Affichage des commandes dans le tableau de l'équipement */
function addCmdToTable(_cmd) {
    if (!isset(_cmd)) {
        var _cmd = { configuration: {} };
    }
    if (!isset(_cmd.configuration)) {
        _cmd.configuration = {};
    }
    var tr = '<tr class="cmd" data-cmd_id="' + init(_cmd.id) + '">';
    tr += '<td style="width:60px;"><span class="cmdAttr" data-l1key="id"></span></td>';
    tr += '<td style="min-width:250px;width:350px;">';
    tr += '<div class="row"><div class="col-xs-7">';
    tr += '<input class="cmdAttr form-control input-sm" data-l1key="name" placeholder="{{Nom de la commande}}">';
    tr += '<select class="cmdAttr form-control input-sm" data-l1key="value" style="display:none;margin-top:5px;" title="{{Commande information liée}}"><option value="">{{Aucune}}</option></select>';
    tr += '</div><div class="col-xs-5">';
    tr += '<a class="cmdAction btn btn-default btn-sm" data-l1key="chooseIcon"><i class="fas fa-flag"></i> {{Icône}}</a>';
    tr += '<span class="cmdAttr" data-l1key="display" data-l2key="icon" style="margin-left:10px;"></span>';
    tr += '</div></div></td>';
    tr += '<td><span class="type" type="' + init(_cmd.type) + '">' + jeedom.cmd.availableType() + '</span>';
    tr += '<span class="subType" subType="' + init(_cmd.subType) + '"></span></td>';
    tr += '<td style="min-width:150px;width:350px;">';
    tr += '<input class="cmdAttr form-control input-sm" data-l1key="configuration" data-l2key="action_type" placeholder="{{Type action}}" title="{{Type d\'action (zone_start/zone_stop/stop_all)}}" style="width:40%;display:inline-block;"/> ';
    tr += '<input class="cmdAttr form-control input-sm" data-l1key="configuration" data-l2key="zone" placeholder="{{Zone}}" title="{{N° zone 1-6}}" style="width:25%;display:inline-block;"/> ';
    tr += '<input class="cmdAttr form-control input-sm" data-l1key="configuration" data-l2key="duration_s" placeholder="{{Durée s}}" title="{{Durée en secondes}}" style="width:25%;display:inline-block;"/>';
    tr += '</td>';
    tr += '<td style="min-width:80px;width:350px;">';
    tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="isVisible" checked/>{{Afficher}}</label>';
    tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="isHistorized"/>{{Historiser}}</label>';
    tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="display" data-l2key="invertBinary"/>{{Inverser}}</label>';
    tr += '</td>';
    tr += '<td style="min-width:80px;width:200px;">';
    if (is_numeric(_cmd.id)) {
        tr += '<a class="btn btn-default btn-xs cmdAction" data-action="configure"><i class="fas fa-cogs"></i></a> ';
        tr += '<a class="btn btn-default btn-xs cmdAction" data-action="test"><i class="fas fa-rss"></i> {{Tester}}</a>';
    }
    tr += '<i class="fas fa-minus-circle pull-right cmdAction cursor" data-action="remove"></i></td>';
    tr += '</tr>';
    $('#table_cmd tbody').append(tr);
    var tr = $('#table_cmd tbody tr').last();
    jeedom.eqLogic.builSelectCmd({
        id: $('.eqLogicAttr[data-l1key=id]').value(),
        filter: { type: 'info' },
        error: function (error) {
            $('#div_alert').showAlert({ message: error.message, level: 'danger' });
        },
        success: function (result) {
            tr.find('.cmdAttr[data-l1key=value]').append(result);
            tr.setValues(_cmd, '.cmdAttr');
            jeedom.cmd.changeType(tr, init(_cmd.subType));
        }
    });
}
