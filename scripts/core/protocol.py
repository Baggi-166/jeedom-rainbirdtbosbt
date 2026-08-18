"""
Encodage et décodage des trames BLE du Rain Bird TBOS-BT.

Convention de nommage : build_* construit une trame à écrire, decode_*
interprète une notification reçue. classify() identifie le type d'une
notification pour pouvoir la router vers le bon decode_*.

IMPORTANT sur le byte 0 des notifications : il varie selon le contexte
(0x0A, 0x14, 0x16, 0x10, 0x12, 0x0C observés) sans qu'on en connaisse le
sens exact (probablement un compteur/tag de session). La classification
se fait donc sur les bytes 1+, jamais sur le byte 0.

Toutes les valeurs et offsets ici sont documentés et confirmés dans
rainbird-tbos-ble-synthese.md, sauf mention contraire explicite dans les
docstrings ("NON CONFIRMÉ" / "extrapolé").
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from . import constants as C


# =========================================================================
# Construction de commandes (écriture)
# =========================================================================

def build_read_state() -> bytes:
    return C.CMD_READ_STATE


def build_sync_clock(dt: Optional[datetime] = None) -> bytes:
    """03-06-00-7e-MM-DD-hh-mm-ss : synchronise l'horloge du programmateur."""
    dt = dt or datetime.now()
    return bytes([0x03, 0x06, 0x00, 0x7E, dt.month, dt.day, dt.hour, dt.minute, dt.second])


def build_manual_run(station: int, duration_s: int) -> bytes:
    """09-05-12-ZZ-00-DD-DD : lance une station en manuel. ZZ=1..6, durée en secondes."""
    if not (1 <= station <= C.ZONE_COUNT):
        raise ValueError(f"station doit être entre 1 et {C.ZONE_COUNT}")
    if not (1 <= duration_s <= 0xFFFFFF):
        raise ValueError("durée invalide")
    return bytes([0x09, 0x05, 0x12, station]) + duration_s.to_bytes(3, "big")


def build_stop() -> bytes:
    return C.CMD_STOP


def build_run_program(program: str) -> bytes:
    """
    09-05-14-00-PP-00-00 : lance un programme complet.
    A=1, B=2, C=3 — les trois CONFIRMÉS par capture réelle (A le 12/08, B et C le 13/08).
    """
    program = program.upper()
    if program not in C.PROGRAM_RUN_INDEX:
        raise ValueError("programme doit être 'A', 'B' ou 'C'")
    pp = C.PROGRAM_RUN_INDEX[program]
    return bytes([0x09, 0x05, 0x14, 0x00, pp, 0x00, 0x00])


def build_power(on: bool) -> bytes:
    return C.CMD_ON if on else C.CMD_OFF


def build_program_records(program: str, day_mask: int, start_min: int, durations_s, budget_percent: int = 100):
    """
    Construit les 4 trames d'écriture d'un programme (A/B/C) :
    en-tête (jours/activation/date/budget), heures de départ, durées (2 trames).

    durations_s : liste de 6 durées en secondes (station 1 à 6).
    budget_percent : budget eau PROPRE à ce programme, 0-255, défaut 100
    (CONFIRMÉ le 15/08 : ce champ varie réellement, ex. 50%, 80%, 127% observés
    sur du matériel réel — ce n'est pas un octet fixe comme on l'a cru longtemps).
    """
    program = program.upper()
    if program not in C.PROGRAM_READ_TAG:
        raise ValueError("programme doit être 'A', 'B' ou 'C'")
    pp = C.PROGRAM_READ_TAG[program]

    if len(durations_s) != C.ZONE_COUNT:
        raise ValueError(f"durations_s doit contenir {C.ZONE_COUNT} valeurs")
    if not (0 <= budget_percent <= 255):
        raise ValueError("budget_percent doit être entre 0 et 255")

    today = datetime.now()
    date_bytes = bytes([today.day, today.month]) + today.year.to_bytes(2, "big")

    rec_header = (
        bytes([0x0F, 0x0E, 0x00, pp])
        + bytes([0, 0, 0, budget_percent, 0])
        + bytes([day_mask & 0x7F, 0x01, 0])
        + date_bytes
    )

    slots = [start_min & 0xFFFF] + [0x05A0] * 7  # 1 heure utilisée + 7 slots "vide" (sentinelle 1440)
    rec_starts = bytes([0x0F, 0x12, 0x01, pp]) + b"".join(s.to_bytes(2, "big") for s in slots)

    durs = durations_s[:5]
    rec_dur1 = bytes([0x0F, 0x11, 0x02, pp]) + b"".join(int(d).to_bytes(3, "big") for d in durs)

    dur6 = int(durations_s[5])
    rec_dur2 = bytes([0x0F, 0x11, 0x03, pp]) + dur6.to_bytes(3, "big") + bytes(12)

    return [rec_header, rec_starts, rec_dur1, rec_dur2]


def build_zone_name_record(index: int, name: str) -> bytes:
    """0b-0e-00-XX-<nom ASCII padded 12 octets>."""
    if not (0 <= index < C.ZONE_COUNT):
        raise ValueError(f"index doit être entre 0 et {C.ZONE_COUNT - 1}")
    name_bytes = name.encode("ascii", errors="replace")[:12].ljust(12, b"\x00")
    return bytes([0x0B, 0x0E, 0x00, index]) + name_bytes


def build_monthly_budget_records(monthly: dict) -> list:
    """
    CONFIRMÉ par capture réelle (13/08) : les 2 trames générées correspondent
    exactement à une écriture réellement observée avec de NOUVELLES valeurs
    (pas seulement l'en-tête comme précédemment) : 10/20/30/40/50/60/70 pour
    jan-jui et 80/90/100/120/130 pour aoû-déc.

    monthly : dict {"01": pct, ..., "12": pct}, mois manquants -> 0.
    Chaque valeur doit être un multiple de 10 (contrainte de l'app officielle).
    """
    values = [int(monthly.get(f"{m:02d}", 0)) for m in range(1, 13)]
    for v in values:
        if not (0 <= v <= 255):
            raise ValueError("chaque valeur doit être entre 0 et 255")
        if v % 10 != 0:
            raise ValueError(f"le budget eau n'accepte que des multiples de 10% (reçu : {v})")

    jan_jul = values[0:7]
    aug_dec = values[7:12]

    frame1 = bytes([0x15, 0x11, 0x00, 0x02, 0x01]) + b"".join(bytes([0x00, v]) for v in jan_jul)

    body = bytearray()
    for i, v in enumerate(aug_dec):
        body.append(v)
        if i < len(aug_dec) - 1:
            body.append(0x00)
    frame2 = bytes([0x15, 0x10, 0x01, 0x00]) + bytes(body) + bytes.fromhex("fff000ffff")

    return [frame1, frame2]


# =========================================================================
# Classification et décodage des notifications
# =========================================================================

def classify(data: bytes) -> str:
    """Identifie le type d'une notification. Ignore le byte 0 (non fiable)."""
    if len(data) < 2:
        return "unknown"

    b1, b2 = data[1], data[2] if len(data) > 2 else None

    if b1 == 0x10 and b2 == 0x02 and len(data) >= 10:
        return "state"
    if b1 == 0x10 and b2 == 0x01:
        return "zone_type_raw"
    if b1 == 0x05:
        return "short_ack_raw"
    if b1 == 0x0E and len(data) >= 4:
        return "program_header"
    if b1 == 0x12 and b2 == 0x01:
        return "program_starts"
    if b1 == 0x12 and b2 == 0x00:
        return "zone_name"
    if b1 == 0x11 and b2 == 0x02:
        return "program_durations_1"
    if b1 == 0x11 and b2 == 0x03:
        return "program_durations_2"
    if b1 == 0x11 and b2 == 0x00:
        return "monthly_budget_1"
    if b1 == 0x10 and b2 == 0x00 and len(data) > 3 and data[3] == 0x00:
        return "monthly_budget_2"
    if b1 == 0x0F and b2 == 0x01:
        return "identity_mac"
    if data.hex() == "1a030288ee":
        return "status_ping_response"
    return "unknown"


def decode_state(data: bytes) -> dict:
    """État général / zone manuelle. classify()=='state'."""
    return {
        "state_byte": data[3],
        "state": C.STATE_LABELS.get(data[3], f"unknown_0x{data[3]:02x}"),
        "active_zone": data[9] if data[9] else None,
    }


def decode_program_header(data: bytes) -> dict:
    """classify()=='program_header'. Jours de la semaine + activation + date + budget."""
    pp = data[3]
    budget_percent = data[7]
    day_mask = data[9]
    active_days = [C.DAY_LABELS[i] for i in range(7) if day_mask & (1 << i)]
    enabled = bool(data[10])
    date = None
    if len(data) >= 16:
        day, month, year = data[12], data[13], (data[14] << 8) | data[15]
        date = f"{day:02d}/{month:02d}/{year:04d}"
    return {
        "program": C.PROGRAM_LETTER_FROM_TAG.get(pp, f"tag_0x{pp:02x}"),
        "budget_percent": budget_percent,
        "day_mask": day_mask,
        "active_days": active_days,
        "enabled": enabled,
        "device_date": date,
    }


def decode_program_starts(data: bytes) -> dict:
    """classify()=='program_starts'. Jusqu'à 8 heures de départ, sentinelle 1440=inutilisé."""
    pp = data[3]
    payload = data[4:]
    starts = []
    for i in range(0, len(payload) - 1, 2):
        val = (payload[i] << 8) | payload[i + 1]
        if val != 0x05A0:
            h, m = divmod(val, 60)
            starts.append(f"{h:02d}:{m:02d}")
    return {"program": C.PROGRAM_LETTER_FROM_TAG.get(pp, f"tag_0x{pp:02x}"), "start_times": starts}


def decode_program_durations(data: bytes, part: int) -> dict:
    """classify() in {'program_durations_1','program_durations_2'}. part=1 -> stations 1-5, part=2 -> station 6."""
    pp = data[3]
    payload = data[4:]
    durations = []
    for i in range(0, len(payload) - 2, 3):
        val = (payload[i] << 16) | (payload[i + 1] << 8) | payload[i + 2]
        durations.append(val)
    return {
        "program": C.PROGRAM_LETTER_FROM_TAG.get(pp, f"tag_0x{pp:02x}"),
        "part": part,
        "durations_s": durations,
    }


def decode_zone_name(data: bytes) -> dict:
    """classify()=='zone_name'."""
    index = data[3]
    raw = bytes(data[4:])
    name = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
    return {"index": index, "name": name}


def decode_monthly_budget_1(data: bytes) -> list:
    """
    classify()=='monthly_budget_1'. Trame '16-11-00-02-[01]-<7 valeurs>'.
    Retourne les valeurs janvier à juillet (7 valeurs).
    Le premier octet du payload (0x01) est un flag fixe, PAS une valeur de mois.
    """
    payload = data[5:]  # en-tête (4) + flag (1)
    return [payload[i] for i in range(1, len(payload), 2)]


def decode_monthly_budget_2(data: bytes) -> list:
    """
    classify()=='monthly_budget_2'. Trame '16-10-00-00-<5 valeurs>-FF-F0-00-FF-FF'.
    Retourne les valeurs août à décembre (5 valeurs). Les 5 derniers octets
    (FF-F0-00-FF-FF) sont des limites fixes d'interface, jamais des données.
    """
    payload = data[4:-5]
    return [payload[i] for i in range(0, len(payload), 2)]
