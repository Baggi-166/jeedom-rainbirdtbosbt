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

- **Exécutable Python** : chemin de l'exécutable Python. Par défaut, le venv
  dédié au plugin (`resources/venv/bin/python3`) créé par l'installation des
  dépendances ; sinon `python3` du système.
- **Dossier des scripts** : dossier contenant `main.py` et `core/`
  (défaut : `scripts/` à côté du plugin).
- **Carte Bluetooth** : liste déroulante des interfaces détectées
  (`hci0`, `hci1`...). Transmise aux scripts via `--adapter`.
- **Stratégie de refresh** : fréquence de relire de l'état via cron15, pour
  préserver la pile du contrôleur (voir ci-dessous).
- **Refresh après chaque action** : mode debug, relit l'état après chaque
  commande (désactivé par défaut).

## Environnement Python dédié

Le TBOS-BT étant alimenté par pile et la stack BLE (bleak) évolutive, le
plugin crée un **venv Python isolé** dans `resources/venv/` lors de
l'installation des dépendances (`resources/install_apt.sh`). Cela évite tout
conflit de version de `bleak` ou de Python avec d'autres plugins ou avec
l'environnement système du Pi. Le `python_path` par défaut pointe
automatiquement sur ce venv s'il est présent.

## Découverte automatique

Sur la page principale du plugin, un champ **Découverte** permet de saisir
l'adresse MAC du programmateur. Au clic sur **Découvrir** :

1. Le plugin se connecte via `main.py status`.
2. Il lit le nom de la station et les noms des 6 voies.
3. Il crée automatiquement l'équipement portant le nom de la station.
4. Les commandes par voie sont créées avec le nom de chaque voie.

## Commandes créées automatiquement

**État global** : `controller_state` (off / on / manual / program_running).

**Par voie (1 à 6)**, nommées avec le nom récupéré depuis le programmateur :

- `zone_state_N` (info binaire) : 1 si la voie est en cours d'arrosage, 0 sinon.
- `zone_start_N` (action) : démarre la voie N (durée configurable, défaut 60 s).
- `zone_stop_N` (action) : arrête la voie N.

> Note : le TBOS-BT ne dispose que d'un STOP global (`09-05-15-00-ff-00-00`).
> La commande `zone_stop_N` envoie ce STOP global — elle arrête donc toute
> irrigation en cours, pas seulement la voie N.

**Marche / Arrêt général (automatisme)** :

- `power_on` (action) : active l'automatisme (`power: "on"`, état `0x40`).
- `power_off` (action) : désactive l'automatisme lui-même (`power: "off"`,
  état `0x00`) — coupe les programmes automatiques programmés.

> Important (voir `scripts/PROTOCOL.md`) : **STOP et OFF sont deux actions
> distinctes**. `stop_all` (STOP, `09-05-15`) coupe l'irrigation en cours
> sans désactiver les programmes auto ; `power_off` (OFF) désactive
> l'automatisme lui-même. Sans `power_off`, il est impossible de couper les
> arrosages programmés depuis Jeedom.

**Arrêt irrigation (STOP)** : `stop_all` (action) — arrête toute irrigation en
cours, les programmes auto restent intacts.

**Budget eau mensuel** :
- `budget_month_01` à `budget_month_12` (info numeric) : pourcentage du budget
  eau pour chaque mois (0-200%, multiple de 10). Mis à jour à chaque rafraîchissement.
- `budget_current_month` (info numeric) : pourcentage du budget du mois courant.
- `set_budget` (action) : modifie le budget d'un mois. Paramètres : `month` (01-12)
  et `budget_value` (multiple de 10, 0-200). Le plugin force le multiple de 10 et
  borne la valeur entre 0 et 200.

**Programmes A/B/C** :
- `program_A_days`, `program_B_days`, `program_C_days` (info string) : jours
  actifs (ex. `lun,mar,mer,jeu,ven`).
- `program_A_start`, `program_B_start`, `program_C_start` (info string) : heure
  de départ (ex. `06:20`).
- `program_A_durations`, `program_B_durations`, `program_C_durations` (info
  string) : durées par voie (ex. `1:900,2:900,3:0,4:0,5:1200,6:0`). Une voie
  non lue est marquée `z:?` pour signaler une lecture incomplète.
- `set_program_A`, `set_program_B`, `set_program_C` (action) : modifie un
  programme. Paramètres : `program` (A/B/C), `active_days` (`lun,mar,...`),
  `start_time` (`HH:MM`), `durations` (`voie:secondes,...`).
  Les champs non fournis gardent leur valeur actuelle (lue avant écriture).
  > Note : modifier un programme réécrit les 3 programmes + noms de zone en une
  > salve (comportement du programmateur observé sur l'app officielle).

## Rafraîchissement automatique

`cron15()` relit l'état des équipements actifs selon la **stratégie de
refresh** configurée (page de config du plugin), afin de préserver la pile du
contrôleur :

- **À la demande** (défaut) : aucun refresh automatique, uniquement via la
  commande manuelle ou à la création de l'équipement.
- **Pendant un programme en cours** : ne rafraîchit qu'à la minute d'un départ
  de programme connu (start_times + durées lues), pendant la fenêtre d'arrosage.
- **Journalier vers 05h00** : un seul refresh par jour.
- **Toutes les 15 min** (historique) : refresh à chaque passage du cron.

Par ailleurs, le refresh après chaque action est désactivé par défaut (une
action déclenche déjà une connexion BLE ; un refresh immédiat en ajouterait
une seconde). Il peut être réactivé en mode debug via l'option
**Refresh après chaque action**.

Garde-fou lecture incomplète : si le JSON renvoyé par le script Python manque
une section clé (controller, water_budget, programs), le plugin ne réécrit pas
les commandes d'affichage avec des valeurs par défaut (0 / vide) et conserve
l'état précédent plutôt que d'afficher un faux « 00:00 » ou une durée à 0
résultant d'une lecture ratée.

## Structure

```
rainbirdtbosbt/
├── plugin_info/
│   ├── info.json                 # id, name, category, hasDependency=1
│   ├── install.php               # install/update/remove
│   └── configuration.php         # config globale (python, scripts, BLE, refresh)
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
│   ├── install_apt.sh                      # deps système + venv dédié + bleak
│   └── venv/                               # venv Python isolé (non commité)
└── scripts/                               # scripts Python (réutilisés)
    ├── main.py                            # CLI : --address, --adapter, status, command
    ├── commands.py
    ├── core/
    └── tests/
```

## Installation

1. Copier le dossier `rainbirdtbosbt/` dans `var/www/html/plugins/`.
2. Activer le plugin dans Jeedom (il installe les dépendances Python via
   `resources/install_apt.sh` : paquets système + venv dédié + bleak).
3. Configurer la carte Bluetooth et la stratégie de refresh (Plugins →
   Gestion des plugins → Rain Bird TBOS-BT).
4. Saisir l'adresse MAC du programmateur dans le champ **Découverte** et
   cliquer sur **Découvrir**. L'équipement est créé avec le nom de la station.
