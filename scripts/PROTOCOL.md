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
5. `17-00`, `11-00`, `0d-00` → autres lectures observées, contenu de leur réponse non identifié avec certitude

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
| `17-00` | non identifiée | envoi confirmé, réponse non décodée |
| `11-00` | non identifiée | envoi confirmé, réponse non décodée |
| `0d-00` | non identifiée | envoi confirmé, réponse non décodée |

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
Lecture : 12-0E-xx-PP-00-00-00-64-00-<jours>-<actif>-00-<JJ>-<MM>-<AAAA_hi>-<AAAA_lo>
Écriture: 0F-0E-00-PP-00-00-00-64-00-<jours>-<actif>-00-<JJ>-<MM>-<AAAA_hi>-<AAAA_lo>
```
- `<jours>` : masque 1 octet, bit0=lundi ... bit6=dimanche (CONFIRMÉ : 0x1F=lun-ven, 0x60=sam-dim, 0x1E=mar-ven après suppression du lundi — 3 recoupements indépendants)
- `<actif>` : `0x01` = programme activé
- Le `0x64` fixe après les 3 premiers octets n'est PAS le budget eau (voir plus bas) — rôle exact inconnu, toujours vu à 100 quel que soit le budget réel
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
- **Réponses aux requêtes `17-00`, `11-00`, `0d-00`** : envoi confirmé, contenu de la
  réponse jamais isolé avec certitude parmi les autres notifications reçues au même moment.
- **STOP (`09-05-15-...`) arrête-t-il une zone précise ou tout ?** : le format ne contient
  pas de champ zone visible (`ff` fixe) — comportement observé cohérent avec "arrête tout",
  jamais testé avec 2 zones actives en parallèle avant l'ajout du test dédié (7a/7b/7c).
- **Ajustement saisonnier PAR PROGRAMME** (distinct du budget mensuel global) : le manuel
  utilisateur officiel mentionne un réglage "0 à 300%" à la fois par programme et global
  mensuel — seul le mensuel global a été localisé dans le protocole à ce jour.
- **Rain Delay** (report de pluie 1-14 jours, mentionné au manuel) : jamais capturé, aucune
  piste protocole.
- **Batterie et qualité de connexion** : l'app officielle affiche les deux, jamais décodés
  avec certitude côté protocole. Une trame candidate a été repérée tôt dans l'investigation
  — `04-06-00-7E-08-0B-16-16-2D` (notification) / `03-06-00-7E-...` (écriture, à ne pas
  confondre avec la sync horloge qui partage le même préfixe `03-06-00-7E` mais une longueur
  différente) — sans qu'aucun octet ne corresponde clairement à un pourcentage batterie
  (60-70% annoncé par l'app à ce moment) ni à un niveau de signal (1 barre/4). Nécessite une
  capture dédiée avec contraste net (proche/loin du device, ou avant/après décharge de la
  pile) pour isoler quel(s) octet(s) bouge(nt).
- **Modèle et version firmware** : jamais capturés. Aucune requête identifiée comme
  "ModelAndVersion" (contrairement au protocole SIP d'autres contrôleurs Rain Bird, qui a
  une commande dédiée `0x02`/`0x82` pour ça — rien d'équivalent trouvé ici à ce jour).
  Recherche ASCII systématique effectuée (chaîne "TBOS" + toutes séquences imprimables
  ≥4 caractères) sur les 5 pcap disponibles : aucune occurrence du modèle ni du nombre de
  voies, contrairement au nom du site et aux noms de zone qui eux sont bien en clair. Piste
  à considérer comme épuisée sauf découverte d'un nouvel opcode de requête dédié.

## Journal des captures ayant servi à ce document

| Date | Ce qui a été confirmé |
|---|---|
| 10/08/2026 | UUIDs, premier décodage état/zone/durée (test zone1) |
| 11/08/2026 | Programmes A/B (jours, heures, durées), noms de zone, dates |
| 12/08/2026 (soir) | Écritures : lancement zone, stop, ON/OFF, lancement programme A, sync horloge, réécriture programme (suppression lundi), budget global (140→100%) |
| 13/08/2026 | Lancement programme B et C confirmés en conditions réelles (état `0x44` découvert), écriture budget mensuel confirmée avec 12 nouvelles valeurs réelles |
