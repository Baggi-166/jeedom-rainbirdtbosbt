"""
Fonctions haut niveau pour piloter le Rain Bird TBOS-BT.

get_status()   -> construit le JSON "État" en lisant le programmateur
apply_command() -> applique un JSON "Commande" et retourne un JSON "Résultat"

Le budget eau mensuel (lecture ET écriture) est pleinement supporté — les
deux confirmés par capture réelle (build_monthly_budget_records).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core import constants as C
from core import protocol as P
from core import ble_client as BLE


# =========================================================================
# État
# =========================================================================

async def get_status(
    address: str = C.DEFAULT_ADDRESS, timeout: float = 15.0, adapter: Optional[str] = None
) -> Dict[str, Any]:
    frames = await BLE.read_full_config(address, timeout=timeout, adapter=adapter)

    status: Dict[str, Any] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "controller": {"state": None, "active_zone": None},
        "zones": {i: {"index": i, "name": C.DEFAULT_ZONE_NAMES[i - 1]} for i in range(1, C.ZONE_COUNT + 1)},
        "water_budget": {"monthly": {}},
        "programs": {},
    }

    programs: Dict[str, Dict[str, Any]] = {}
    monthly: Dict[str, int] = {}

    for data in frames:
        kind = P.classify(data)

        if kind == "state":
            d = P.decode_state(data)
            status["controller"]["state"] = d["state"]
            status["controller"]["active_zone"] = d["active_zone"]

        elif kind == "zone_name":
            d = P.decode_zone_name(data)
            zone_idx = d["index"] + 1  # 0-based en BLE -> 1-based pour l'API
            if zone_idx in status["zones"]:
                status["zones"][zone_idx]["name"] = d["name"]

        elif kind == "program_header":
            d = P.decode_program_header(data)
            programs.setdefault(d["program"], {})
            programs[d["program"]].update(
                {"active_days": d["active_days"], "enabled": d["enabled"], "budget_percent": d["budget_percent"]}
            )

        elif kind == "program_starts":
            d = P.decode_program_starts(data)
            programs.setdefault(d["program"], {})
            programs[d["program"]]["start_times"] = d["start_times"]

        elif kind in ("program_durations_1", "program_durations_2"):
            d = P.decode_program_durations(data, part=1 if kind == "program_durations_1" else 2)
            programs.setdefault(d["program"], {})
            durations = programs[d["program"]].setdefault("durations_s", {})
            base = 0 if d["part"] == 1 else 5
            for i, val in enumerate(d["durations_s"]):
                station = base + i + 1
                if station <= C.ZONE_COUNT:
                    durations[str(station)] = val

        elif kind == "monthly_budget_1":
            values = P.decode_monthly_budget_1(data)
            for i, v in enumerate(values):
                monthly[f"{i + 1:02d}"] = v  # janvier..juillet

        elif kind == "monthly_budget_2":
            values = P.decode_monthly_budget_2(data)
            for i, v in enumerate(values):
                monthly[f"{i + 8:02d}"] = v  # août..décembre

    status["programs"] = programs
    status["water_budget"]["monthly"] = monthly
    current_month = f"{datetime.now().month:02d}"
    status["water_budget"]["current_month_percent"] = monthly.get(current_month)

    return status


# =========================================================================
# Commandes
# =========================================================================

async def apply_command(
    command: Dict[str, Any],
    address: str = C.DEFAULT_ADDRESS,
    timeout: float = 15.0,
    adapter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    command : voir le schéma dans README.md. Chaque clé est optionnelle ;
    seules celles présentes sont appliquées.
    """
    result: Dict[str, Any] = {"applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "actions": []}

    if "water_budget" in command:
        try:
            monthly_changes = command["water_budget"].get("monthly", {})
            current = await get_status(address, timeout=timeout, adapter=adapter)
            monthly = dict(current["water_budget"]["monthly"])
            monthly.update(monthly_changes)

            frames = P.build_monthly_budget_records(monthly)
            await BLE.run_session(address, frames, timeout=timeout, listen_seconds=2.0, adapter=adapter)
            result["actions"].append(
                {"action": "water_budget", "updated_months": list(monthly_changes.keys()), "status": "ok"}
            )
        except (BLE.RainbirdBLEError, ValueError) as e:
            result["actions"].append({"action": "water_budget", "status": "error", "error": str(e)})

    # --- ON / OFF général --------------------------------------------------
    if command.get("power") in ("on", "off"):
        on = command["power"] == "on"
        try:
            await BLE.run_session(
                address, [P.build_power(on)], timeout=timeout, listen_seconds=1.5, adapter=adapter
            )
            result["actions"].append({"action": "power", "value": command["power"], "status": "ok"})
        except BLE.RainbirdBLEError as e:
            result["actions"].append({"action": "power", "status": "error", "error": str(e)})

    # --- Zones (start/stop) -------------------------------------------------
    for zone_cmd in command.get("zones", []):
        idx = zone_cmd.get("index")
        action = zone_cmd.get("action")
        try:
            if not isinstance(idx, int):
                raise ValueError(f"index de zone invalide ou manquant : {idx!r}")

            if action == "start":
                duration = int(zone_cmd.get("duration_s", 60))
                await BLE.run_session(
                    address,
                    [P.build_manual_run(idx, duration)],
                    timeout=timeout,
                    listen_seconds=1.5,
                    adapter=adapter,
                )
                result["actions"].append(
                    {"action": "zone_start", "index": idx, "duration_s": duration, "status": "ok"}
                )
            elif action == "stop":
                await BLE.run_session(
                    address, [P.build_stop()], timeout=timeout, listen_seconds=1.5, adapter=adapter
                )
                result["actions"].append({"action": "zone_stop", "index": idx, "status": "ok"})
            else:
                result["actions"].append(
                    {"action": "zone", "index": idx, "status": "error", "error": f"action inconnue: {action!r}"}
                )
        except (BLE.RainbirdBLEError, ValueError, TypeError) as e:
            result["actions"].append({"action": "zone", "index": idx, "status": "error", "error": str(e)})

    # --- Lancer un programme -------------------------------------------------
    if command.get("run_program"):
        program = command["run_program"].upper()
        try:
            status = await get_status(address, timeout=timeout, adapter=adapter)
            if not program_is_configured(status["programs"].get(program, {})):
                result["actions"].append(
                    {
                        "action": "run_program",
                        "program": program,
                        "status": "error",
                        "error": f"le programme {program} n'a aucune station configurée pour au moins 1 min — envoi annulé",
                    }
                )
            else:
                await BLE.run_session(
                    address, [P.build_run_program(program)], timeout=timeout, listen_seconds=1.5, adapter=adapter
                )
                entry = {"action": "run_program", "program": program, "status": "ok"}
                result["actions"].append(entry)
        except (BLE.RainbirdBLEError, ValueError) as e:
            result["actions"].append({"action": "run_program", "status": "error", "error": str(e)})

    # --- Arrêt général --------------------------------------------------
    if command.get("stop_all"):
        try:
            await BLE.run_session(address, [P.build_stop()], timeout=timeout, listen_seconds=1.5, adapter=adapter)
            result["actions"].append({"action": "stop_all", "status": "ok"})
        except BLE.RainbirdBLEError as e:
            result["actions"].append({"action": "stop_all", "status": "error", "error": str(e)})

    # --- Modification de programme(s) ----------------------------------------
    if command.get("programs"):
        try:
            await _apply_program_changes(address, command["programs"], timeout, adapter, result)
        except (BLE.RainbirdBLEError, ValueError) as e:
            result["actions"].append({"action": "programs", "status": "error", "error": str(e)})

    return result


async def _apply_program_changes(
    address: str,
    changes: Dict[str, Dict[str, Any]],
    timeout: float,
    adapter: Optional[str],
    result: Dict[str, Any],
) -> None:
    """
    Le programmateur ne semble accepter que la réécriture complète des 3
    programmes + noms de zone en une salve (c'est ce que fait l'app
    officielle à chaque modification, observé sur toutes les captures).
    On lit donc l'état courant, on fusionne les changements demandés, et on
    réécrit l'ensemble.
    """
    current = await get_status(address, timeout=timeout, adapter=adapter)

    # Garde-fou CRITIQUE : si la lecture de l'état courant a été interrompue (connexion
    # coupée en cours de dump), certains champs de programme peuvent être manquants plutôt
    # que réellement vides. Écrire ces "trous" comme s'ils étaient l'état réel écraserait
    # la config actuelle avec des zéros. On vérifie que chaque programme a bien les 3 clés
    # attendues -- si ce n'est pas le cas, on retente UNE fois une lecture propre avant
    # d'abandonner sans rien écrire.
    required_keys = {"active_days", "start_times", "durations_s", "budget_percent"}

    def _missing_fields(status: Dict[str, Any]) -> Dict[str, list]:
        return {
            letter: sorted(required_keys - set(status["programs"].get(letter, {}).keys()))
            for letter in ("A", "B", "C")
            if required_keys - set(status["programs"].get(letter, {}).keys())
        }

    missing = _missing_fields(current)
    if missing:
        current = await get_status(address, timeout=timeout, adapter=adapter)
        missing = _missing_fields(current)
    if missing:
        raise ValueError(
            f"Lecture incomplète après 2 tentatives (champs manquants : {missing}) "
            f"— écriture ANNULÉE pour éviter d'écraser la config actuelle avec des valeurs "
            f"vides. Probablement une connexion instable. Réessayez plus tard."
        )

    writes: List[bytes] = []
    for letter in ("A", "B", "C"):
        prog = dict(current["programs"].get(letter, {}))
        prog.update(changes.get(letter, {}))

        day_mask = _days_to_mask(prog.get("active_days", []))
        start_min = _first_start_to_minutes(prog.get("start_times", []))
        durations = prog.get("durations_s", {})
        durations_list = [int(durations.get(str(i), 0)) for i in range(1, C.ZONE_COUNT + 1)]
        budget_percent = int(prog.get("budget_percent", 100))

        writes.extend(P.build_program_records(letter, day_mask, start_min, durations_list, budget_percent))

    for i, name in enumerate(C.DEFAULT_ZONE_NAMES):
        zone = current["zones"].get(i + 1, {})
        writes.append(P.build_zone_name_record(i, zone.get("name", name)))

    await BLE.run_session(address, writes, timeout=timeout, listen_seconds=2.0, adapter=adapter)
    result["actions"].append({"action": "programs", "updated": list(changes.keys()), "status": "ok"})


def program_is_configured(program: Dict[str, Any]) -> bool:
    """Un programme n'est 'lançable' que s'il a au moins une station avec une durée >= 1 min (60s)."""
    durations = program.get("durations_s", {})
    return any(int(v) >= 60 for v in durations.values())


def _days_to_mask(day_labels: List[str]) -> int:
    mask = 0
    for i, label in enumerate(C.DAY_LABELS):
        if label in day_labels:
            mask |= 1 << i
    return mask


def _first_start_to_minutes(start_times: List[str]) -> int:
    if not start_times:
        return 0
    raw = start_times[0]
    try:
        h_str, m_str = raw.split(":")
        h, m = int(h_str), int(m_str)
    except (ValueError, AttributeError):
        raise ValueError(f"heure de départ invalide, format attendu 'HH:MM' : {raw!r}")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"heure de départ hors plage (00:00-23:59) : {raw!r}")
    return h * 60 + m
