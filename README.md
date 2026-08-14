# Plugin Jeedom — Rain Bird TBOS-BT

Pilotage en Bluetooth Low Energy d'un programmateur d'arrosage Rain Bird
TBOS-BT (6 zones), via les scripts Python du dossier `scripts/`.

## Principe

Le plugin appelle directement les scripts Python existants (`main.py`,
`commands.py`, `core/`) par `shell_exec`. Aucun démon. Les scripts
communiquent en JSON sur stdout.

- `main.py status --address <MAC> --adapter <hci0>` → JSON d'état lu et
  ventilé dans les commandes info Jeedom.
- `main.py command --address <MAC> --adapter <hci0> --json '{...}'` →
  applique une commande et renvoie un JSON de résultat.

## Configuration globale

Page **Plugins → Gestion des plugins → Rain Bird TBOS-BT** :

- **Exécutable Python** : chemin de `python3` (défaut `python3`).
- **Dossier des scripts** : dossier contenant `main.py` et `core/`
  (défaut : `scripts/` à côté du plugin).
- **Carte Bluetooth** : liste déroulante des interfaces détectées
  (`hci0`, `hci1`...). Transmise aux scripts via `--adapter`.

## Découverte automatique

Sur la page principale du plugin, un champ **Découverte** permet de saisir
l'adresse MAC du programmateur. Au clic sur **Découvrir** :

1. Le plugin se connecte via `main.py status`.
2. Il lit le nom de la station et les noms des 6 voies.
3. Il crée automatiquement l'équipement portant le nom de la station.
4. Les commandes par voie sont créées avec le nom de chaque voie.

## Commandes créées automatiquement

**État global** : `controller_state` (off / on / manual).

**Par voie (1 à 6)**, nommées avec le nom récupéré depuis le programmateur :

- `zone_state_N` (info binaire) : 1 si la voie est en cours d'arrosage, 0 sinon.
- `zone_start_N` (action) : démarre la voie N (durée configurable, défaut 60 s).
- `zone_stop_N` (action) : arrête la voie N.

> Note : le TBOS-BT ne dispose que d'un STOP global (`09-05-15-00-ff-00-00`).
> La commande `zone_stop_N` envoie ce STOP global — elle arrête donc toute
> irrigation en cours, pas seulement la voie N.

**Arrêt général** : `stop_all` (action) — arrête toute irrigation.

**Budget eau mensuel** :
- `budget_month_01` à `budget_month_12` (info numeric) : pourcentage du budget
  eau pour chaque mois (0-200%, multiple de 10). Mis à jour à chaque rafraîchissement.
- `budget_current_month` (info numeric) : pourcentage du budget du mois courant.
- `set_budget` (action) : modifie le budget d'un mois. Paramètres : `month` (01-12)
  et `budget_value` (multiple de 10, 0-200). Le plugin force le multiple de 10 et
  borne la valeur entre 0 et 200.

## Rafraîchissement automatique

`cron15()` relit l'état de tous les équipements actifs toutes les 15 minutes
et met à jour l'état global + l'état de chaque voie.

## Structure

```
rainbirdtbosbt/
├── plugin_info/
│   ├── info.json                 # id, name, category, hasDependency=1
│   ├── install.php               # install/update/remove
│   └── configuration.php         # config globale (python3, scripts, carte BLE)
├── core/
│   ├── class/
│   │   ├── rainbirdtbosbt.class.php       # eqLogic : discoverByMac(), refreshStatus(), cron15()
│   │   └── rainbirdtbosbtCmd.class.php    # execute() → switch sur action_type
│   ├── php/rainbirdtbosbt.inc.php
│   └── ajax/rainbirdtbosbt.ajax.php        # discover + refreshStatus
├── desktop/
│   ├── php/rainbirdtbosbt.php              # page équipements + bouton découverte
│   ├── js/rainbirdtbosbt.js                # handler découverte + addCmdToTable()
│   └── modal/modal.rainbirdtbosbt.php      # config action_type/zone/durée
├── resources/
│   └── install_apt.sh                      # deps système + pip bleak
└── scripts/                               # scripts Python (réutilisés)
    ├── main.py                            # CLI : --address, --adapter, status, command
    ├── commands.py
    ├── core/
    └── tests/
```

## Installation

1. Copier le dossier `rainbirdtbosbt/` dans `var/www/html/plugins/`.
2. Activer le plugin dans Jeedom (il installe les dépendances Python via
   `resources/install_apt.sh`).
3. Configurer la carte Bluetooth (Plugins → Gestion des plugins →
   Rain Bird TBOS-BT).
4. Saisir l'adresse MAC du programmateur dans le champ **Découverte** et
   cliquer sur **Découvrir**. L'équipement est créé avec le nom de la station.
