<?php
/* AJAX pour rainbirdtbosbt — découverte automatique et rafraîchissement. */

if (!isConnect('admin')) {
    throw new Exception('{{401 - Accès non autorisé}}');
}

ajax::init();

if (init('action') == 'discover') {
    $mac = trim(init('mac', ''));
    if ($mac === '') {
        throw new Exception(__('Adresse MAC requise pour la découverte.', __FILE__));
    }
    $eqLogic = rainbirdtbosbt::discoverByMac($mac);
    ajax::success(array(
        'id' => $eqLogic->getId(),
        'name' => $eqLogic->getName(),
    ));
}

if (init('action') == 'refreshStatus') {
    $eqLogic = eqLogic::byId(init('id'));
    if (!is_object($eqLogic)) {
        throw new Exception(__('Équipement introuvable', __FILE__));
    }
    $eqLogic->refreshStatus();
    ajax::success();
}

throw new Exception(__('Aucune méthode correspondante', __FILE__));
