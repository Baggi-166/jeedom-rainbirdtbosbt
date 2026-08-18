#!/usr/bin/env python3
"""
Rain Bird TBOS-BT — plan de tests interactif sur matériel réel.

Enchaîne une série de tests, chacun soit vérifiable PHYSIQUEMENT (zone qui
se met en route), soit nécessitant une vérification dans l'APP OFFICIELLE
(le script fait alors une pause et demande "conforme / non conforme" avant
de continuer). Objectif : clarifier les points encore incertains du
protocole (lancement de programme B/C, écriture de programme via notre
propre code, budget mensuel en écriture) sans attendre une prochaine
session de reverse engineering.

Chaque test est indépendant : si l'un échoue ou est jugé non conforme, les
suivants s'exécutent quand même (sauf refus explicite de continuer).

Usage :
    python run_tonight_tests.py --address FF:31:C7:36:16:10 --adapter hci0

Nécessite : pip install "bleak==0.21.1"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime

from bleak import BleakScanner

from core import constants as C
from core import protocol as P
from core import ble_client as BLE
import commands as CMD

LOG_FILE = "rainbird_tonight_tests.log"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("rainbird.tonight")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
    fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)

    # "rainbird.ble" (traces WRITE/NOTIF brutes de core/ble_client.py) est un logger FRÈRE
    # de "rainbird.tonight", pas un enfant -- sans ceci, aucune trace brute n'est capturée.
    ble_logger = logging.getLogger("rainbird.ble")
    ble_logger.setLevel(logging.DEBUG)
    ble_logger.addHandler(fh)
    ble_logger.addHandler(ch)

    return logger


LOG = setup_logging()
RESULTS = []


def ask_app_confirmation(question: str) -> str:
    """Met le script en pause, demande à vérifier un point dans l'app officielle."""
    print()
    print("=" * 70)
    print(f"VÉRIFICATION DANS L'APP OFFICIELLE demandée :\n  {question}")
    while True:
        rep = input("  Résultat observé — [c]onforme / [n]on conforme / [s]kip : ").strip().lower()
        if rep in ("c", "conforme"):
            return "conforme"
        if rep in ("n", "non", "non conforme"):
            return "non_conforme"
        if rep in ("s", "skip"):
            return "skip"
        print("  Réponse non reconnue, réessayez (c / n / s).")


def ask_open_question(prompt: str) -> str:
    """Pour les tests exploratoires où il n'y a pas de réponse conforme/non-conforme attendue."""
    print()
    print("=" * 70)
    print(f"OBSERVATION demandée :\n  {prompt}")
    return input("  Réponse : ").strip()


def ask_continue(prompt: str = "Continuer avec le test suivant ? [O/n] ") -> bool:
    rep = input(prompt).strip().lower()
    return rep in ("", "o", "oui", "y", "yes")


def ask_continue_strict(prompt: str) -> bool:
    """Comme ask_continue mais sans défaut : il faut taper explicitement oui."""
    rep = input(prompt).strip().lower()
    return rep in ("o", "oui", "y", "yes")


def record(test_name: str, status: str, detail: str = "") -> None:
    RESULTS.append({"test": test_name, "status": status, "detail": detail, "at": datetime.now().isoformat(timespec="seconds")})
    LOG.info(f"[{test_name}] -> {status} {('- ' + detail) if detail else ''}")


async def run_and_wait_state(address, adapter, timeout, writes, listen_seconds=3.0):
    """Envoie des trames et retourne la dernière trame d'état vue."""
    seen = {"state": None}

    def on_notify(data: bytes):
        if P.classify(data) == "state":
            seen["state"] = P.decode_state(data)

    await BLE.run_session(
        address, writes, on_notify=on_notify, timeout=timeout, listen_seconds=listen_seconds, adapter=adapter
    )
    return seen["state"]


# =========================================================================
# Tests
# =========================================================================

async def test_00_connexion(address, adapter, timeout):
    name = "00_connexion_adaptateur"
    LOG.info(f"--- Test : {name} (adaptateur={adapter or 'défaut'}) ---")
    try:
        state = await run_and_wait_state(address, adapter, timeout, [P.build_read_state()])
        if state:
            record(name, "ok", f"état lu : {state}")
        else:
            record(name, "warning", "connecté mais aucune trame d'état reçue")
    except BLE.RainbirdBLEError as e:
        record(name, "error", str(e))
        print(f"\n/!\\ Connexion impossible ({e}). Vérifiez l'adaptateur ({adapter or 'défaut'}) avant de continuer.")


async def test_02_run_program_b(address, adapter, timeout):
    name = "02_lancement_programme_B"
    LOG.info(f"--- Test : {name} (opcode confirmé le 13/08) ---")
    status = await CMD.get_status(address, timeout=timeout, adapter=adapter)
    if not CMD.program_is_configured(status["programs"].get("B", {})):
        print("Le programme B n'a aucune station >= 1 min configurée — test annulé (rien à vérifier).")
        record(name, "skip", "programme B vide ou stations < 1min")
        return
    print("\nTest de routine (opcode déjà confirmé) : vérifie que c'est toujours cohérent.")
    try:
        await BLE.run_session(address, [P.build_run_program("B")], timeout=timeout, listen_seconds=2.0, adapter=adapter)
        rep = ask_app_confirmation(
            "Le programme B est-il affiché comme actif dans l'app (et PAS A ou C) ?"
        )
        record(name, rep)
        print("Arrêt de sécurité...")
        await BLE.run_session(address, [P.build_stop()], timeout=timeout, listen_seconds=1.0, adapter=adapter)
    except BLE.RainbirdBLEError as e:
        record(name, "error", str(e))


async def test_05_program_c_write(address, adapter, timeout):
    name = "05_ecriture_programme_C"
    LOG.info(f"--- Test : {name} ---")
    print("\nCe test réécrit le programme C avec une config de test (mardi seul, 5h55, station1=1min).")
    print("(Durée à 60s car l'app impose un minimum d'1 min par station.)")
    if not ask_continue("Lancer ce test ? [O/n] "):
        record(name, "skip")
        return
    try:
        result = await CMD.apply_command(
            {
                "programs": {
                    "C": {
                        "active_days": ["mar"],
                        "start_times": ["05:55"],
                        "durations_s": {"1": 60, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0},
                    }
                }
            },
            address,
            timeout=timeout,
            adapter=adapter,
        )
        LOG.info(f"Résultat apply_command: {result}")
        rep = ask_app_confirmation(
            "Le programme C affiche-t-il bien : mardi uniquement, départ 5h55, station 1 = 1 min ?"
        )
        record(name, rep)
    except Exception as e:
        record(name, "error", str(e))


async def test_06_monthly_budget_write(address, adapter, timeout):
    name = "06_ecriture_budget_mensuel"
    LOG.info(f"--- Test : {name} (structure confirmée le 13/08) ---")
    print("\nÉcriture du budget mensuel — structure confirmée par capture réelle avec de")
    print("nouvelles valeurs (10 à 130%). Test de routine pour vérifier que ça reste cohérent.")
    if not ask_continue("Lancer ce test ? [O/n] "):
        record(name, "skip")
        return

    current = await CMD.get_status(address, timeout=timeout, adapter=adapter)
    current_month = f"{datetime.now().month:02d}"
    before = current["water_budget"]["monthly"].get(current_month)
    print(f"Valeur actuelle du mois en cours ({current_month}) : {before}%")

    test_value = 90  # valeur multiple de 10 (contrainte de l'app), facilement reconnaissable
    monthly = dict(current["water_budget"]["monthly"])
    monthly[current_month] = test_value

    try:
        frames = P.build_monthly_budget_records(monthly)
        await BLE.run_session(address, frames, timeout=timeout, listen_seconds=2.0, adapter=adapter)
        rep = ask_app_confirmation(f"Le budget du mois en cours affiche-t-il {test_value}% dans l'app ?")
        record(name, rep, f"avant={before}, tenté={test_value}")

        if rep == "conforme" and before is not None and ask_continue(
            f"Remettre l'ancienne valeur ({before}%) maintenant ? [O/n] "
        ):
            monthly[current_month] = before
            revert_frames = P.build_monthly_budget_records(monthly)
            await BLE.run_session(address, revert_frames, timeout=timeout, listen_seconds=2.0, adapter=adapter)
            record(name + "_revert", "ok")
    except Exception as e:
        record(name, "error", str(e))


async def test_07_zones_meme_connexion(address, adapter, timeout):
    name = "07_zones_meme_connexion"
    LOG.info(f"--- Test : {name} ---")
    print("\nZone 1 puis zone 3, UNE SEULE connexion, sans déconnexion entre les deux,")
    print("avec une lecture d'état finale. Comportement déjà connu via connexions séparées")
    print("(la 2e remplace la 1ère) — ce test vérifie si le résultat est identique en connexion unique.")
    if not ask_continue("Lancer ce test ? [O/n] "):
        record(name, "skip")
        return
    try:
        seen = {"states": []}

        def on_notify(data: bytes):
            if P.classify(data) == "state":
                seen["states"].append(P.decode_state(data))

        await BLE.run_session(
            address,
            [P.build_manual_run(1, 30), P.build_manual_run(3, 30), P.build_read_state()],
            on_notify=on_notify,
            timeout=timeout,
            listen_seconds=3.0,
            adapter=adapter,
        )
        LOG.info(f"États vus pendant la connexion unique : {seen['states']}")
        rep_physique = ask_open_question(
            "Combien de zones coulent physiquement maintenant (1 seule, laquelle, ou les deux) ?"
        )
        record(name, "observed", f"états={seen['states']}, physique='{rep_physique}'")

        print("Arrêt de sécurité...")
        await BLE.run_session(address, [P.build_stop()], timeout=timeout, listen_seconds=1.5, adapter=adapter)
        rep_stop = ask_open_question("Après l'arrêt : plus aucune zone ne coule, c'est bien ça ?")
        record(name + "_stop", "observed", rep_stop)
    except BLE.RainbirdBLEError as e:
        record(name, "error", str(e))



async def test_09_budget_vs_duree(address, adapter, timeout):
    name = "09_budget_vs_duree"
    LOG.info(f"--- Test : {name} ---")
    print("\nCe test vérifie si le champ durée de la trame d'état est ajusté par le budget mensuel.")
    print("Il compare : programme B à 100% vs 50%, puis zone 1 manuelle (15min) à 50% vs 100%.")
    print("Le budget du mois en cours sera modifié temporairement puis restauré à la fin.")

    status = await CMD.get_status(address, timeout=timeout, adapter=adapter)
    if not CMD.program_is_configured(status["programs"].get("B", {})):
        print("Le programme B n'a aucune station >= 1 min configurée — test annulé.")
        record(name, "skip", "programme B non configuré")
        return

    if not ask_continue("Lancer ce test ? [O/n] "):
        record(name, "skip")
        return

    current_month = f"{datetime.now().month:02d}"
    original_monthly = dict(status["water_budget"]["monthly"])
    original_value = original_monthly.get(current_month)
    print(f"Budget actuel du mois en cours ({current_month}) : {original_value}%  (sera restauré à la fin)")

    async def set_budget(pct):
        monthly = dict(original_monthly)
        monthly[current_month] = pct
        await BLE.run_session(
            address, P.build_monthly_budget_records(monthly), timeout=timeout, listen_seconds=1.5, adapter=adapter
        )

    async def capture_duration_field(writes):
        """Envoie les trames et retourne le champ 'durée' brut (offset 13-14) de la 1ère trame d'état vue."""
        seen = {"value": None}

        def on_notify(data: bytes):
            if P.classify(data) == "state" and len(data) >= 15 and seen["value"] is None:
                seen["value"] = (data[13] << 8) | data[14]

        await BLE.run_session(
            address, writes, on_notify=on_notify, timeout=timeout, listen_seconds=2.5, adapter=adapter
        )
        return seen["value"]

    results = {}
    try:
        print("\n-- Programme B à 100% --")
        await set_budget(100)
        results["programme_100"] = await capture_duration_field([P.build_run_program("B")])
        await BLE.run_session(address, [P.build_stop()], timeout=timeout, listen_seconds=1.0, adapter=adapter)

        print("-- Programme B à 50% --")
        await set_budget(50)
        results["programme_50"] = await capture_duration_field([P.build_run_program("B")])
        await BLE.run_session(address, [P.build_stop()], timeout=timeout, listen_seconds=1.0, adapter=adapter)

        print("-- Zone 1 manuelle (15min) à 50% (budget inchangé) --")
        results["manuel_50"] = await capture_duration_field([P.build_manual_run(1, 900)])
        await BLE.run_session(address, [P.build_stop()], timeout=timeout, listen_seconds=1.0, adapter=adapter)

        print("-- Zone 1 manuelle (15min) à 100% --")
        await set_budget(100)
        results["manuel_100"] = await capture_duration_field([P.build_manual_run(1, 900)])
        await BLE.run_session(address, [P.build_stop()], timeout=timeout, listen_seconds=1.0, adapter=adapter)

        print("\nRésultats bruts (secondes, valeur brute station1 = 900s) :")
        for k, v in results.items():
            print(f"  {k:18s} : {v}")

        record(name, "observed", str(results))

    except BLE.RainbirdBLEError as e:
        record(name, "error", str(e))
    finally:
        if original_value is not None:
            print(f"\nRestauration du budget d'origine ({original_value}%)...")
            await set_budget(original_value)
            record(name + "_restore", "ok", f"budget remis à {original_value}%")


async def test_11_rssi_bleak(address, adapter, timeout):
    name = "11_rssi_bleak"
    LOG.info(f"--- Test : {name} ---")
    print("\nCe test mesure le RSSI (force du signal) via le scan bleak — une donnée de")
    print("référence indépendante de tout décodage — pour la comparer à ce qu'affiche")
    print("l'app, et pour chercher une corrélation avec les octets bruts reçus.")
    print("Il capture aussi le dump complet des notifications, proche puis loin.")
    if not ask_continue("Lancer ce test ? [O/n] "):
        record(name, "skip")
        return

    async def scan_rssi(label):
        input(f"\nPositionnez-vous '{label}' du programmateur, puis appuyez sur Entrée...")
        try:
            devices = await BleakScanner.discover(timeout=5.0, return_adv=True)
        except TypeError:
            # Anciennes versions de bleak : return_adv non supporté
            devices = None
        rssi = None
        if devices and address in devices:
            _dev, adv = devices[address]
            rssi = getattr(adv, "rssi", None)
        LOG.info(f"RSSI mesuré ({label}) : {rssi}")
        return rssi

    async def dump_session(label):
        frames = []

        def on_notify(data: bytes, _frames=frames):
            _frames.append(data.hex("-"))

        try:
            await BLE.run_session(
                address,
                [C.CMD_STATUS_PING, C.CMD_READ_STATE],
                on_notify=on_notify,
                timeout=timeout,
                listen_seconds=5.0,
                adapter=adapter,
            )
        except BLE.RainbirdBLEError as e:
            LOG.warning(f"Erreur BLE pendant le dump ({label}) : {e}")
        LOG.info(f"Dump ({label}) : {frames}")
        return frames

    rssi_pres = await scan_rssi("proche (~1m)")
    dump_pres = await dump_session("proche")

    rssi_loin = await scan_rssi("loin (~15-20m ou derrière un mur)")
    dump_loin = await dump_session("loin")

    rep_app = ask_open_question("Qu'affiche l'app officielle comme qualité de signal, proche puis loin ?")

    print(f"\nRSSI bleak : proche={rssi_pres} dBm, loin={rssi_loin} dBm")
    print("Comparez les deux dumps dans le log pour repérer un octet qui varie entre les deux.")

    record(
        name,
        "observed",
        f"rssi_proche={rssi_pres}, rssi_loin={rssi_loin}, app='{rep_app}', "
        f"dump_proche={dump_pres}, dump_loin={dump_loin}",
    )


TESTS = [
    ("Connexion + adaptateur", test_00_connexion),
    ("Lancement programme B (app requise)", test_02_run_program_b),
    ("Écriture programme C via notre code (app requise) — à rejouer, non conforme la dernière fois", test_05_program_c_write),
    ("Écriture budget mensuel (app requise) — à rejouer, avait planté", test_06_monthly_budget_write),
    ("Zones 1 et 3, même connexion (exploratoire) — à rejouer, avait planté", test_07_zones_meme_connexion),
    ("Budget vs durée : programme et manuel, 100% vs 50% (exploratoire) — à rejouer, avait planté", test_09_budget_vs_duree),
    ("RSSI via bleak, proche/loin (optionnel, déjà fait mais inconclusif)", test_11_rssi_bleak),
]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Plan de tests interactif Rain Bird TBOS-BT")
    parser.add_argument("--address", default=C.DEFAULT_ADDRESS)
    parser.add_argument("--adapter", default=None, help="ex. hci0, hci1")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    LOG.info("=" * 70)
    LOG.info(f"Session de tests — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Cible : {args.address}  |  Adaptateur : {args.adapter or 'défaut'}")
    print(f"{len(TESTS)} tests prévus. Gardez le téléphone avec l'app officielle à portée, Bluetooth ACTIVÉ")
    print("(contrairement aux tests précédents, ici on en a besoin pour vérifier).\n")

    for label, fn in TESTS:
        print("\n" + "-" * 70)
        print(f"TEST : {label}")
        if not ask_continue("Lancer ce test ? [O/n] "):
            continue
        try:
            await fn(args.address, args.adapter, args.timeout)
        except Exception as e:
            LOG.exception(f"Erreur inattendue pendant le test '{label}' — on passe au suivant")
            record(label, "crashed", str(e))
            print(f"\n/!\\ Le test a planté ({e}) — on continue avec le test suivant.")

    print("\n" + "=" * 70)
    print("RÉSUMÉ DE LA SESSION")
    for r in RESULTS:
        print(f"  {r['test']:45s} {r['status']}")
    with open("rainbird_tonight_results.json", "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)
    print("\nDétail sauvegardé dans rainbird_tonight_results.json et rainbird_tonight_tests.log")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
