#!/usr/bin/env python3
"""
Rain Bird TBOS-BT — CLI.

IMPORTANT pour l'intégration Jeedom : seul le JSON (état ou résultat) est
imprimé sur stdout. Tout le reste (logs de debug) part dans le fichier
rainbird_debug.log — jamais sur stdout, pour ne pas polluer ce que Jeedom
va parser.

Usage :
    # Lire l'état
    python main.py --address FF:31:C7:36:16:10 status

    # Envoyer une commande (JSON en argument ou via stdin)
    python main.py command --json '{"power":"off"}'
    echo '{"zones":[{"index":1,"action":"start","duration_s":60}]}' | python main.py command

    # Vérifier les trames générées sans se connecter au matériel
    python main.py command --json '{"power":"on"}' --dry-run

Codes de sortie : 0 = succès, 1 = erreur.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from core import constants as C
from core import protocol as P
import commands as CMD

LOG_FILE = "rainbird_debug.log"


def setup_logging(verbose: bool) -> None:
    root = logging.getLogger("rainbird")
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")

    fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if verbose:
        # En mode verbose, le debug va sur stderr (jamais stdout, réservé au JSON)
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(fmt)
        root.addHandler(ch)


def cmd_status(args) -> int:
    status = asyncio.run(CMD.get_status(args.address, timeout=args.timeout, adapter=args.adapter))
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0


def cmd_command(args) -> int:
    if args.json:
        raw = args.json
    else:
        raw = sys.stdin.read()

    try:
        command = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON invalide : {e}"}, ensure_ascii=False))
        return 1

    if args.dry_run:
        preview = _preview_command(command)
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        return 0

    result = asyncio.run(CMD.apply_command(command, args.address, timeout=args.timeout, adapter=args.adapter))
    print(json.dumps(result, indent=2, ensure_ascii=False))

    had_error = any(a.get("status") == "error" for a in result.get("actions", []))
    return 1 if had_error else 0


def _preview_command(command: dict) -> dict:
    """Construit les trames sans se connecter — pour vérifier une commande avant de l'envoyer."""
    frames = []

    if command.get("power") in ("on", "off"):
        frames.append({"action": "power", "frame": P.build_power(command["power"] == "on").hex("-")})

    for zone_cmd in command.get("zones", []):
        if zone_cmd.get("action") == "start":
            f = P.build_manual_run(zone_cmd["index"], int(zone_cmd.get("duration_s", 60)))
            frames.append({"action": "zone_start", "index": zone_cmd["index"], "frame": f.hex("-")})
        elif zone_cmd.get("action") == "stop":
            frames.append({"action": "zone_stop", "index": zone_cmd["index"], "frame": P.build_stop().hex("-")})

    if command.get("run_program"):
        frames.append({"action": "run_program", "frame": P.build_run_program(command["run_program"]).hex("-")})

    if command.get("stop_all"):
        frames.append({"action": "stop_all", "frame": P.build_stop().hex("-")})

    if "water_budget" in command:
        monthly = command["water_budget"].get("monthly", {})
        try:
            f1, f2 = P.build_monthly_budget_records(monthly)
            frames.append({"action": "water_budget", "frames": [f1.hex("-"), f2.hex("-")]})
        except ValueError as e:
            frames.append({"action": "water_budget", "status": "error", "error": str(e)})

    return {"dry_run": True, "frames": frames}


def main() -> int:
    parser = argparse.ArgumentParser(description="Rain Bird TBOS-BT — pilotage BLE")
    parser.add_argument("--address", default=C.DEFAULT_ADDRESS, help="Adresse MAC du programmateur")
    parser.add_argument("--adapter", default=None, help="Interface BLE à utiliser (ex. hci0, hci1) — Linux/BlueZ uniquement")
    parser.add_argument("--timeout", type=float, default=15.0, help="Timeout de connexion (s)")
    parser.add_argument("--verbose", action="store_true", help="Logs de debug aussi sur stderr")

    sub = parser.add_subparsers(dest="mode", required=True)

    p_status = sub.add_parser("status", help="Lire l'état du programmateur (JSON sur stdout)")
    p_status.set_defaults(func=cmd_status)

    p_command = sub.add_parser("command", help="Envoyer une commande (JSON en argument ou stdin)")
    p_command.add_argument("--json", help="Commande JSON (sinon lue sur stdin)")
    p_command.add_argument("--dry-run", action="store_true", help="Construit les trames sans se connecter")
    p_command.set_defaults(func=cmd_command)

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        return args.func(args)
    except Exception as e:
        logging.getLogger("rainbird").exception("Erreur inattendue")
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
