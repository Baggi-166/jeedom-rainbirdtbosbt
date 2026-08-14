# Rain Bird TBOS-BT — script de pilotage BLE

Pilotage en Bluetooth Low Energy d'un programmateur d'arrosage Rain Bird
TBOS-BT (6 zones), pensé pour être appelé par le plugin Script de Jeedom.

## Installation

```bash
pip install "bleak==0.21.1"   # 0.21.1 pour compatibilité Python 3.9 ; plus récent OK sous 3.10+
```

## Structure

```
rainbird_tbos/
├── core/
│   ├── constants.py   # adresses, UUIDs, tags de protocole
│   ├── protocol.py    # encodage/décodage des trames (testé, sans dépendance BLE)
│   └── ble_client.py  # connexion BLE (bleak), une connexion courte par action
├── commands.py        # get_status(), apply_command()
├── main.py            # CLI
└── tests/
    └── test_protocol.py  # rejoue des trames réellement capturées, sans matériel
```

## Utilisation

```bash
# Lire l'état complet (JSON sur stdout)
python main.py --address FF:31:C7:36:16:10 status

# Envoyer une commande
python main.py command --json '{"power":"off"}'
echo '{"zones":[{"index":1,"action":"start","duration_s":60}]}' | python main.py command

# Vérifier les trames générées SANS se connecter au matériel
python main.py command --json '{"power":"on"}' --dry-run

# Logs de debug aussi visibles en direct (en plus du fichier rainbird_debug.log)
python main.py --verbose status
```

**Important** : seul le JSON (état ou résultat) sort sur stdout — tout le
reste part dans `rainbird_debug.log`. Codes de sortie : 0=succès, 1=erreur.

## Schéma JSON "État" (sortie de `status`)

```json
{
  "fetched_at": "2026-08-12T21:00:00+00:00",
  "controller": {"state": "on", "active_zone": null},
  "zones": {
    "1": {"index": 1, "name": "JARDIN D"},
    "2": {"index": 2, "name": "JARDIN G"}
  },
  "water_budget": {
    "monthly": {"01": 10, "02": 20, "08": 80, "12": 120},
    "current_month_percent": 80
  },
  "programs": {
    "A": {
      "active_days": ["mar", "mer", "jeu", "ven"],
      "enabled": true,
      "start_times": ["06:20"],
      "durations_s": {"1": 900, "2": 900, "3": 900, "5": 1200}
    }
  }
}
```

`controller.state` vaut `"off"`, `"on"` ou `"manual"`.

## Schéma JSON "Commande" (entrée de `command`)

Toutes les clés sont optionnelles — seules celles présentes sont appliquées.

```json
{
  "power": "on",
  "zones": [
    {"index": 1, "action": "start", "duration_s": 60},
    {"index": 2, "action": "stop"}
  ],
  "run_program": "A",
  "stop_all": false,
  "programs": {
    "C": {
      "active_days": ["lun", "mar", "mer", "jeu", "ven"],
      "start_times": ["06:20"],
      "durations_s": {"1": 900, "2": 900, "3": 900, "5": 1200}
    }
  },
  "water_budget": {"monthly": {"08": 90}}
}
```

Notes :
- `zones[].index` : 1 à 6 (numéro physique de station).
- `run_program` : `"A"`, `"B"` ou `"C"` — les trois confirmés par capture réelle.
- `programs` : modifier un programme réécrit les 3 programmes + les noms de
  zone en une salve (c'est le seul mode de fonctionnement observé côté app
  officielle). Les champs non fournis pour un programme gardent leur valeur
  actuelle (lue avant écriture).
- `water_budget.monthly` : dict `{"01": pct, ..., "12": pct}`, un ou
  plusieurs mois. Chaque valeur doit être un multiple de 10 (contrainte de
  l'app). Les mois non mentionnés gardent leur valeur actuelle (lue avant
  écriture, comme pour `programs`). En `--dry-run`, comme il n'y a pas de
  connexion, seuls les mois explicitement fournis dans la commande sont
  utilisés pour construire l'aperçu (pas de fusion avec l'état actuel).

## Tests

```bash
python -m unittest tests.test_protocol -v
```

Ces tests rejouent des trames réellement capturées (documentées dans
`rainbird-tbos-ble-synthese.md`) — ils ne nécessitent aucun matériel et
doivent rester verts après toute modification de `protocol.py`.

## Ce qui n'est PAS confirmé par capture réelle

- La commande STOP (`09-05-15-00-ff-00-00`) semble arrêter toute
  irrigation en cours, pas une zone précise — non vérifié avec plusieurs
  zones actives simultanément (peu probable sur ce modèle de toute façon)
- Le champ durée de la trame d'état semble parfois refléter la durée
  ajustée par le budget mensuel plutôt que la durée brute programmée
  (observé une fois, pas encore confirmé sur plusieurs cas)
