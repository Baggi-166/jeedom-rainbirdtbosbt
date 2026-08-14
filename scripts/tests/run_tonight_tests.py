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


async def test_01_manual_run_visible(address, adapter, timeout):
    name = "01_lancement_zone1_visible"
    LOG.info(f"--- Test : {name} ---")
    try:
        state = await run_and_wait_state(address, adapter, timeout, [P.build_manual_run(1, 10)])
        ok = state and state["state"] == "manual" and state["active_zone"] == 1
        record(name, "ok" if ok else "warning", f"état={state}")
        print("Vérifiez PHYSIQUEMENT : la zone 1 (station 1) doit couler pendant 10s.")
        rep = ask_app_confirmation("La zone 1 a-t-elle bien démarré physiquement ?")
        record(name + "_physique", rep)
        await asyncio.sleep(11)  # laisse le temps que ça s'arrête tout seul
        await BLE.run_session(address, [P.build_stop()], timeout=timeout, listen_seconds=1.0, adapter=adapter)
    except BLE.RainbirdBLEError as e:
        record(name, "error", str(e))


async def test_02_run_program_b(address, adapter, timeout):
    name = "02_lancement_programme_B"
    LOG.info(f"--- Test : {name} (opcode extrapolé, NON confirmé) ---")
    status = await CMD.get_status(address, timeout=timeout, adapter=adapter)
    if not CMD.program_is_configured(status["programs"].get("B", {})):
        print("Le programme B n'a aucune station >= 1 min configurée — test annulé (rien à vérifier).")
        record(name, "skip", "programme B vide ou stations < 1min")
        return
    print("\nATTENTION : opcode du programme B extrapolé, jamais testé avant.")
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


async def test_03_run_program_c(address, adapter, timeout):
    name = "03_lancement_programme_C"
    LOG.info(f"--- Test : {name} (opcode extrapolé, NON confirmé) ---")
    status = await CMD.get_status(address, timeout=timeout, adapter=adapter)
    if not CMD.program_is_configured(status["programs"].get("C", {})):
        print("Le programme C n'a aucune station >= 1 min configurée — test annulé (rien à vérifier).")
        record(name, "skip", "programme C vide ou stations < 1min")
        return
    print("\nATTENTION : opcode du programme C extrapolé, jamais testé avant.")
    try:
        await BLE.run_session(address, [P.build_run_program("C")], timeout=timeout, listen_seconds=2.0, adapter=adapter)
        rep = ask_app_confirmation(
            "Le programme C est-il affiché comme actif dans l'app (et PAS A ou B) ?"
        )
        record(name, rep)
        print("Arrêt de sécurité...")
        await BLE.run_session(address, [P.build_stop()], timeout=timeout, listen_seconds=1.0, adapter=adapter)
    except BLE.RainbirdBLEError as e:
        record(name, "error", str(e))


async def test_04_rename_zone(address, adapter, timeout):
    name = "04_renommage_zone6"
    LOG.info(f"--- Test : {name} ---")
    test_label = "TEST-BLE"
    try:
        frame = P.build_zone_name_record(5, test_label)  # zone 6 = index 5, la moins critique
        await BLE.run_session(address, [frame], timeout=timeout, listen_seconds=2.0, adapter=adapter)
        rep = ask_app_confirmation(f"La zone 6 s'appelle-t-elle maintenant '{test_label}' dans l'app ?")
        record(name, rep)
        if rep != "skip" and ask_continue("Remettre l'ancien nom 'VALVE 6' maintenant ? [O/n] "):
            revert = P.build_zone_name_record(5, "VALVE 6")
            await BLE.run_session(address, [revert], timeout=timeout, listen_seconds=2.0, adapter=adapter)
            record(name + "_revert", "ok")
    except BLE.RainbirdBLEError as e:
        record(name, "error", str(e))


async def test_05_program_c_write(address, adapter, timeout):
    name = "05_ecriture_programme_C"
    LOG.info(f"--- Test : {name} ---")
    print("\nCe test réécrit le programme C avec une config de test (mardi seul, 5h55, station1=30s).")
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
                        "durations_s": {"1": 30, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0},
                    }
                }
            },
            address,
            timeout=timeout,
            adapter=adapter,
        )
        LOG.info(f"Résultat apply_command: {result}")
        rep = ask_app_confirmation(
            "Le programme C affiche-t-il bien : mardi uniquement, départ 5h55, station 1 = 30s ?"
        )
        record(name, rep)
    except Exception as e:
        record(name, "error", str(e))


async def test_06_monthly_budget_write_experimental(address, adapter, timeout):
    name = "06_ecriture_budget_mensuel_EXPERIMENTAL"
    LOG.info(f"--- Test : {name} ---")
    print("\n" + "!" * 70)
    print("TEST EXPÉRIMENTAL : écriture du budget mensuel.")
    print("La structure est basée sur une trame RÉELLEMENT ÉCRITE par l'app")
    print("(en-tête confirmé), mais avec de nouvelles valeurs jamais testées.")
    print("!" * 70)
    if not ask_continue_strict("Confirmez : lancer le test budget mensuel (expérimental) ? [o/N] "):
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
        frames = P.build_monthly_budget_records_experimental(monthly)
        await BLE.run_session(address, frames, timeout=timeout, listen_seconds=2.0, adapter=adapter)
        rep = ask_app_confirmation(f"Le budget du mois en cours affiche-t-il {test_value}% dans l'app ?")
        record(name, rep, f"avant={before}, tenté={test_value}")

        if rep == "conforme" and before is not None and ask_continue(
            f"Remettre l'ancienne valeur ({before}%) maintenant ? [O/n] "
        ):
            monthly[current_month] = before
            revert_frames = P.build_monthly_budget_records_experimental(monthly)
            await BLE.run_session(address, revert_frames, timeout=timeout, listen_seconds=2.0, adapter=adapter)
            record(name + "_revert", "ok")
    except Exception as e:
        record(name, "error", str(e))


TESTS = [
    ("Connexion + adaptateur", test_00_connexion),
    ("Lancement zone 1 (visible physiquement)", test_01_manual_run_visible),
    ("Lancement programme B (app requise)", test_02_run_program_b),
    ("Lancement programme C (app requise)", test_03_run_program_c),
    ("Renommage zone 6 (app requise)", test_04_rename_zone),
    ("Écriture programme C via notre code (app requise)", test_05_program_c_write),
    ("Écriture budget mensuel EXPÉRIMENTAL (app requise)", test_06_monthly_budget_write_experimental),
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
        await fn(args.address, args.adapter, args.timeout)

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
