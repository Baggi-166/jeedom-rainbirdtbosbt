# Rain Bird TBOS-BT — Référence du protocole BLE

Rétro-ingénié à partir de captures réelles (nRF Connect + pcap système Android/Windows,
snoop HCI), sur un module BLE TBOS-BT (6 stations, alimenté par pile), entre le
10/08/2026 et le 13/08/2026. Aucune source officielle Rain Bird n'a été utilisée pour
le contenu de ce document — le manuel utilisateur public ne documente pas le protocole
BLE bas niveau.

Le dépôt `maillme/rainbird-esp32` (protocole "SIP" pour ESP-RZXe/BAT-BT) **ne s'applique
pas** à ce matériel : UUIDs différents, opcodes différents, pas de CRC/auth dans les deux
cas mais structures de trame incompatibles. Aucune ligne de ce document n'en est issue.

## Vue d'ensemble

Le protocole est **texte binaire brut, non chiffré, sans authentification ni checksum**
détecté sur aucune des ~15 commandes confirmées. Contrairement au protocole "SIP" d'autres
contrôleurs Rain Bird, les opcodes ne sont pas des octets uniques — ce sont des familles de
trames à préfixe variable (voir "Format des trames").

Le programmateur propose une protection de la connexion par mot de passe (visible dans
l'app officielle), **non activée** sur le matériel de test — donc jamais capturée. Ça
allongerait probablement les trames (échange d'authentification en plus). Toutes les
commandes documentées ici supposent l'absence de mot de passe.

## Service et caractéristiques BLE

**Service UUID** : `f4780001-f54b-4c45-b4be-6db9ffb0703f`

| UUID | Propriétés | CCCD | Rôle |
|---|---|---|---|
| `f4780002-f54b-4c45-b4be-6db9ffb0703f` | Write, Write Without Response | Non | Canal de commande (écriture) |
| `f4780003-f54b-4c45-b4be-6db9ffb0703f` | Notify | Oui (`0x2902`) | Canal de réponse (notifications) |

**Nom BLE (Generic Access `0x2A00`)** : `<MAC sans les ':'>N`, ex. `FF31C7361610N` pour
l'adresse `FF:31:C7:36:16:10`.

**Flux de commande principal** : écrire sur `f4780002`, recevoir la réponse sur `f4780003`.

## Comportement de connexion

Le programmateur **ne maintient jamais une connexion longue**. Observé sur toutes les
captures : connexion → une ou quelques actions → déconnexion, avec des durées de session
allant de ~3s à ~40s avant un `GATT CONN TIMEOUT` côté central. L'app officielle se
reconnecte à chaque action plutôt que de garder une session ouverte. Toute implémentation
doit reproduire ce pattern (connexion courte par action), pas une connexion persistante.

Séquence typique observée à la connexion :
1. Écriture CCCD `01-00` sur la caractéristique notify (abonnement standard BLE)
2. `19-00-00-19-00` → réponse `1a-03-02-88-ee` (requête générique, fonction exacte inconnue)
3. `13-00` → déclenche le trio de notifications d'état (voir plus bas)
4. `03-06-00-7e-MM-DD-hh-mm-ss` → synchronisation de l'horloge du programmateur sur celle du téléphone (CONFIRMÉ, voir plus bas)
5. `17-00`, `11-00`, `0d-00` → toutes identifiées le 14/08 par isolement (une requête à la fois, connexion dédiée). Voir table ci-dessous.

## Format des trames

**Écriture** : pas de préfixe de longueur ni de checksum détecté. Deux familles principales :
- Requêtes de lecture courtes : `[opcode 1 octet] [00]` (ex. `13-00`)
- Commandes d'action : `09-05-[sous-opcode][paramètres...]`, 7 octets au total pour toutes les commandes d'action confirmées

**Notification (réponse/lecture)** : `[byte0][byte1][byte2][données...]`.
**`byte0` n'est PAS un identifiant de type fiable** — il varie (`0x0A`, `0x14`, `0x16`,
`0x10`, `0x12`, `0x0C` observés selon le contexte) sans corrélation claire avec le contenu ;
probablement un compteur ou tag de session non élucidé. **La classification du type de
trame doit se faire sur `byte1` (et souvent `byte2`), jamais sur `byte0`.**

## Commandes de lecture (requêtes courtes)

| Requête | Réponse déclenchée | Statut |
|---|---|---|
| `13-00` | Trio d'état : `xx-10-02-...`, `xx-10-01-...`, `xx-05-00-01-...` | CONFIRMÉ |
| `19-00-00-19-00` | `1a-03-02-88-ee` (fixe) | CONFIRMÉ (envoi + réponse), fonction inconnue |
| `17-00` | Budget mensuel (2 trames, même contenu que via `13-00`/spontané mais tag `18` au lieu de `16`), une trame contenant l'adresse MAC, une trame vide | CONFIRMÉ (isolé le 14/08) |
| `11-00` | Dump complet des 3 programmes A/B/C (jours, heures de départ, durées — mêmes trames que le dump spontané, tag `12` inchangé) | CONFIRMÉ (isolé le 14/08) |
| `0d-00` | Dump des 6 noms de zone (tag `0E` au lieu de `0C` du dump spontané, contenu identique) | CONFIRMÉ (isolé le 14/08) |

## Commandes d'action

Toutes au format `09-05-[sous-opcode][params]`, 7 octets, sans réponse directe autre que
les notifications d'état standard qui suivent.

| Trame | Action | Statut |
|---|---|---|
| `09-05-12-ZZ-00-DD-DD` | Lancer la station `ZZ` (1 octet, 1-based, 1→6) pour `DD-DD` secondes (2 octets big-endian) | CONFIRMÉ, recoupé écriture+lecture |
| `09-05-15-00-ff-00-00` | Arrêter toute irrigation en cours (zone manuelle ou programme) | CONFIRMÉ (3 cas : après zone manuelle, après programme B, après programme C) |
| `09-05-14-00-PP-00-00` | Lancer le programme `PP` (1 octet, 1-based : A=1, B=2, C=3) | CONFIRMÉ pour A, B et C |
| `09-05-c0-00-00-00-00` | Couper l'irrigation (OFF général) | CONFIRMÉ |
| `09-05-a0-00-00-00-00` | Activer l'irrigation (ON/Auto général) | CONFIRMÉ |
| `03-06-00-7e-MM-DD-hh-mm-ss` | Synchroniser l'horloge du programmateur | CONFIRMÉ (2 occurrences, dates/heures réelles recoupées) |

Note : `09-05-12-ZZ-...` (lancer une station) fait 7 octets, avec la durée sur les 2
DERNIERS octets uniquement (`00-DD-DD` sur 3 octets au total après le numéro de station,
mais la valeur elle-même tient sur 2 octets utiles, le premier étant toujours `00` dans
la plage testée). Voir le code (`core/protocol.py::build_manual_run`) pour l'implémentation
exacte, qui encode sur 3 octets big-endian bruts.

## Écriture de configuration (programmes, noms de zone, budget mensuel)

Le programmateur ne semble accepter qu'une **réécriture complète** à chaque modification :
observé systématiquement, l'app réécrit les 3 programmes + les 6 noms de zone en une seule
salve de ~18 trames, même pour changer un seul champ (ex. retirer un jour d'un programme).
Aucune écriture partielle/ciblée n'a été observée.

### Programme (A/B/C) — 4 trames par programme

Tag programme `PP` (4e octet de l'en-tête) : A=`0x10`, B=`0x11`, C=`0x12` — **identique en
lecture et en écriture** (contrairement aux tags d'enregistrement eux-mêmes, voir plus bas).

**En-tête** (jours, activation, date) :
```
Lecture : 12-0E-xx-PP-00-00-00-<budget>-00-<jours>-<actif>-00-<JJ>-<MM>-<AAAA_hi>-<AAAA_lo>
Écriture: 0F-0E-00-PP-00-00-00-<budget>-00-<jours>-<actif>-00-<JJ>-<MM>-<AAAA_hi>-<AAAA_lo>
```
- `<jours>` : masque 1 octet, bit0=lundi ... bit6=dimanche (CONFIRMÉ : 0x1F=lun-ven, 0x60=sam-dim, 0x1E=mar-ven après suppression du lundi, 0x7F=tous les jours — 4 recoupements indépendants)
- `<actif>` : `0x01` = programme activé
- `<budget>` : **budget eau PAR PROGRAMME, CONFIRMÉ le 15/08** par capture réelle via l'app
  officielle — 1 octet, pourcentage brut (pas de contrainte multiple-de-10 contrairement au
  budget mensuel global). Recoupé sur 3 programmes en une seule session : A=`0x32`(50%),
  B=`0x50`(80%), C=`0x64`(100%). Longtemps pris à tort pour un octet fixe (toujours vu à
  100% par défaut dans les captures précédentes, d'où la confusion initiale).
- Date : jour/mois/année, probablement un horodatage de fraîcheur plutôt qu'une donnée de programme

**Heures de départ** (jusqu'à 8 créneaux/jour) :
```
Lecture : 12-12-xx-PP-<8 x 2 octets big-endian, minutes depuis minuit>
Écriture: 0F-12-01-PP-<idem>
```
Sentinelle `0x05A0` (1440) = créneau inutilisé. CONFIRMÉ : 0x0186=6h30, 0x01A4=7h00, 0x017C=6h20 (3 valeurs recoupées avec des changements réels).

**Durées par station** (2 trames, stations 1-5 puis station 6) :
```
Lecture : 12-11-02-PP-<5 x 3 octets big-endian, secondes>   (stations 1 à 5)
          12-11-03-PP-<3 octets station 6>-<12 octets de bourrage>
Écriture: 0F-11-02-PP-<idem>
          0F-11-03-PP-<idem>
```
CONFIRMÉ à de nombreuses reprises : `0x000384`=900s=15min, `0x0004B0`=1200s=20min,
`0x000258`=600s=10min, `0x000000`=station inutilisée.

### Noms de zone — 1 trame par zone (6 au total)

```
Lecture : 0C-12-00-ii-<nom ASCII, padding 0x00 jusqu'à 12 octets utiles>
Écriture: 0B-0E-00-ii-<idem>
```
`ii` = index de zone 0-based (0→5), correspond à la station physique `ii+1`. CONFIRMÉ,
y compris via une écriture de test (renommage réussi, vérifié dans l'app puis annulé).

Noms lus sur le matériel de test : `JARDIN D`, `JARDIN G`, `JARDIN C`, `HAIE`, `POTAGER`,
`VALVE 6` (index 0 à 5).

### Budget eau mensuel — 2 trames

**CONFIRMÉ en lecture ET en écriture**, avec deux jeux de valeurs réelles indépendants
recoupés exactement (12/08 : mars=30%, avril=40% ; 13/08 : jan→déc = 10 à 130% par
paliers, dont un pallier non linéaire 100→120 confirmant qu'il ne s'agit pas d'une simple
formule mais bien de valeurs individuelles lues/écrites).

```
Lecture  frame 1 (jan-jui) : 16-11-00-02-01-<7 x (00,valeur)>
Écriture frame 1 (jan-jui) : 15-11-00-02-01-<idem>

Lecture  frame 2 (aoû-déc) : 16-10-00-00-<5 x (valeur,00) sauf la dernière non suivie de 00>-FF-F0-00-FF-FF
Écriture frame 2 (aoû-déc) : 15-10-01-00-<idem>
```
- Chaque valeur = 1 octet, pourcentage brut (ex. `0x1E`=30)
- **Contrainte de l'app** : valeurs multiples de 10 uniquement (0, 10, 20, ... 130+ observé)
- Le flag `0x01` en tête de la frame 1 et les 5 octets `FF-F0-00-FF-FF` en fin de frame 2 sont fixes dans toutes les captures — probablement des limites min/max d'interface, jamais des données de budget
- Frame 1 : octet utile en position IMPAIRE du payload (`(00,valeur)`)
- Frame 2 : octet utile en position PAIRE du payload (`(valeur,00)`) — **ordre inversé entre les deux trames**, confirmé par les données réelles des deux côtés

## États du contrôleur

Trame d'état générale (18 octets), déclenchée par `13-00` ou en notification spontanée
après une action — préfixe `byte1-byte2 = 10-02` :

```
[byte0][10][02][état][00][00][00][2A][00][zone][4D][xx][10][00][durée_hi][durée_lo][10][00][00]
```

| Offset | Champ | Détail |
|---|---|---|
| 3 | État | voir table ci-dessous |
| 9 | Station active | 1-based (1→6), `0x00`=aucune. CONFIRMÉ recoupé écriture/lecture |
| 13-14 | Champ "durée" | Position instable selon les captures (voir "Points non résolus") — parfois brut, parfois potentiellement ajusté par le budget mensuel, pas encore confirmé avec certitude |

| Valeur état | Libellé | Statut |
|---|---|---|
| `0x00` | Off | CONFIRMÉ |
| `0x40` | On / Auto (attente) | CONFIRMÉ |
| `0x42` | Manuel actif (une seule zone lancée manuellement) | CONFIRMÉ |
| `0x44` | Programme actif | CONFIRMÉ (13/08, lancement réel de B et C) — nouveau, non documenté avant cette session |

## Comportement zones simultanées

**CONFIRMÉ (14/08)** : lancer une deuxième zone manuellement pendant qu'une première est
déjà active **remplace** la première — les deux ne coulent jamais en parallèle, même via
deux connexions séparées. Vérifié par observation physique directe.

## Trame "zone_type" (non décodée en détail)

Préfixe `byte1-byte2 = 10-01`, 18 octets, accompagne systématiquement la trame d'état.
Contenu largement constant (`10-00-00-10-00-00-10-00-00-10-00-00-00-00-00`), sauf un octet
qui varie selon le contexte sans qu'on ait identifié son rôle précis (probablement lié au
type/à la config de chaque station). Non bloquant pour le pilotage.

## Trames d'identité (vues à la connexion, une fois)

- `02-0F-01-<adresse MAC en clair>-...` : trame d'identité incluant l'adresse MAC du device
- `02-10-00-<nom du site en ASCII>` : nom personnalisé donné au contrôleur dans l'app (ex. "JARDIN BGY")

## Points non résolus

- **Position du champ "durée"** dans la trame d'état : vu à l'offset 14 pour certains
  lancements manuels, à l'offset 17 pour d'autres — pas de règle claire identifiée. Un
  test dédié (`run_tonight_tests.py`, test 9) compare ce champ à budget 100% vs 50% pour
  vérifier l'hypothèse d'un ajustement par le budget mensuel (un seul point de comparaison
  disponible à ce jour, insuffisant pour conclure).
- **Rôle exact du `0x01` flag et des octets `4D-xx-10` en fin de trame d'état** : ce
  dernier ressemble à un compteur lent (tick), sans lien apparent avec un CRC.
- **STOP (`09-05-15-...`) arrête-t-il une zone précise ou tout ?** : le format ne contient
  pas de champ zone visible (`ff` fixe) — comportement observé cohérent avec "arrête tout",
  jamais testé avec 2 zones actives en parallèle avant l'ajout du test dédié (7a/7b/7c).
- **Rain Delay** (report de pluie 1-14 jours, mentionné au manuel) : jamais capturé, aucune
  piste protocole.
- **Batterie et qualité de connexion** : l'app officielle affiche les deux, jamais décodés
  avec certitude côté protocole. **La trame candidate `04-06-00-7E-...` initialement
  suspectée est en réalité l'écho de la synchronisation horloge** (confirmé le 14/08 :
  chaque écriture `03-06-00-7E-MM-DD-hh-mm-ss` est immédiatement suivie d'une notification
  `04-06-00-7E-MM-DD-hh-mm-ss` avec le même payload) — donc pas une piste batterie/signal.
  **Test RSSI fait le 14/08** via `bleak` (mesure indépendante du protocole) : -78 dBm
  proche vs -89 dBm loin (cohérent), mais l'app affichait "1/4" barre dans les deux cas et
  aucun octet des trames reçues ne corrèle avec cet écart — inconclusif, contraste
  peut-être insuffisant ou indicateur app trop grossier pour cette comparaison. Batterie :
  toujours aucune piste, nécessite un contraste sur plusieurs semaines (décharge réelle).
- **Modèle et version firmware** : jamais capturés. Aucune requête identifiée comme
  "ModelAndVersion" (contrairement au protocole SIP d'autres contrôleurs Rain Bird, qui a
  une commande dédiée `0x02`/`0x82` pour ça — rien d'équivalent trouvé ici à ce jour).
  Recherche ASCII systématique effectuée (chaîne "TBOS" + toutes séquences imprimables
  ≥4 caractères) sur les 5 pcap disponibles : aucune occurrence du modèle ni du nombre de
  voies, contrairement au nom du site et aux noms de zone qui eux sont bien en clair. Piste
  à considérer comme épuisée sauf découverte d'un nouvel opcode de requête dédié.
  Version de l'app officielle notée pour référence : 5.2.41 (côté app, pas forcément
  présente dans les trames émises par le device lui-même).
- **Stabilité de connexion** : déconnexions fréquentes ("Not connected") observées les
  14 et 15/08. Hypothèse initiale (rafale de notifications) **infirmée le 15/08** :
  augmenter le délai entre écritures à 1s a fait échouer la connexion encore plus tôt
  (dès la 2e écriture), pas plus tard. Le délai entre connexion et coupure semble
  constant (~1 à 2s après le `connect()`) indépendamment de ce qui est envoyé — ça
  ressemble à une coupure qui survient d'elle-même plutôt qu'à une conséquence de nos
  écritures. Pistes non protocolaires à explorer : stack Bluetooth Windows/WinRT qui
  coupe avant la fin de la renégociation des paramètres de connexion (observée dans les
  tout premiers logs nRF : l'app renégocie l'intervalle quelques secondes après connexion),
  ou interférence RF (Wi-Fi 2.4GHz, distance, obstacle) ce soir-là. Délai entre écritures
  ramené à 0.2s (revert), et la synchronisation horloge automatique désactivée par défaut
  dans `ble_client.run_session()` pour laisser plus de marge à la commande utile dans la
  fenêtre de connexion, très courte et imprévisible.

## Journal des captures ayant servi à ce document

| Date | Ce qui a été confirmé |
|---|---|
| 10/08/2026 | UUIDs, premier décodage état/zone/durée (test zone1) |
| 11/08/2026 | Programmes A/B (jours, heures, durées), noms de zone, dates |
| 12/08/2026 (soir) | Écritures : lancement zone, stop, ON/OFF, lancement programme A, sync horloge, réécriture programme (suppression lundi), budget global (140→100%) |
| 13/08/2026 | Lancement programme B et C confirmés en conditions réelles (état `0x44` découvert), écriture budget mensuel confirmée avec 12 nouvelles valeurs réelles |
| 14/08/2026 | `17-00`/`11-00`/`0d-00` isolées et identifiées, comportement zones simultanées confirmé (remplacement, pas parallèle), écho horloge clarifié (pas batterie/signal), RSSI mesuré (inconclusif), piste budget par programme identifiée, instabilité de connexion diagnostiquée |
| 15/08/2026 | Budget eau PAR PROGRAMME confirmé (A=50%, B=80%, C=100%, recoupé exactement) ; découverte critique et corrigée : une écriture avec lecture préalable incomplète (connexion coupée en cours de route) peut écraser un programme avec des valeurs vides — garde-fou ajouté ; hypothèse "délai plus long = plus stable" infirmée par les données réelles ; app officielle 100% fiable sur la même session où notre script échouait, pointant vers un problème côté stack BLE Windows plutôt que protocole |
