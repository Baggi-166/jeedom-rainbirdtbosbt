"""
Client BLE bas niveau pour le Rain Bird TBOS-BT.

Le programmateur coupe la connexion très rapidement après avoir répondu
(observé : de ~3s à ~40s selon les cas). Ce module part du principe qu'une
connexion sert à UNE action (ou une courte séquence d'actions liées), pas à
une session longue — c'est le comportement qu'on a observé de l'app
officielle elle-même.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Iterable, List, Optional

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from . import constants as C
from . import protocol as P

logger = logging.getLogger("rainbird.ble")


class RainbirdBLEError(Exception):
    pass


async def _connect(address: str, timeout: float, adapter: Optional[str] = None) -> BleakClient:
    try:
        kwargs = {"timeout": 8.0}
        if adapter:
            kwargs["adapter"] = adapter
        device = await BleakScanner.find_device_by_address(address, **kwargs)
    except (BleakError, TypeError):
        # TypeError : bleak plus récent/sur cette plateforme peut ne pas accepter 'adapter' ici
        device = None
    target = device if device else address
    client_kwargs = {"timeout": timeout}
    if adapter:
        client_kwargs["adapter"] = adapter
    client = BleakClient(target, **client_kwargs)
    await client.connect()
    logger.debug(f"Connecté à {address} (adaptateur={adapter or 'défaut'}) : {client.is_connected}")
    return client


async def run_session(
    address: str,
    writes: Iterable[bytes],
    on_notify: Optional[Callable[[bytes], None]] = None,
    listen_seconds: float = 4.0,
    timeout: float = 15.0,
    retries: int = 2,
    adapter: Optional[str] = None,
    sync_clock: bool = True,
) -> bool:
    """
    Connexion unique : abonnement notifications, envoi séquentiel des trames
    de `writes`, écoute des notifications pendant `listen_seconds`,
    déconnexion. Retente jusqu'à `retries` fois en cas de coupure BLE.

    on_notify(data: bytes) est appelé pour chaque notification reçue.
    adapter : nom de l'interface BLE à utiliser (ex. 'hci0', 'hci1'),
    uniquement pertinent sous Linux/BlueZ ; ignoré ailleurs.
    sync_clock : si True (défaut), envoie la trame de synchronisation
    horloge en tout premier, comme le fait l'app officielle à la connexion.
    Retourne True si la session s'est déroulée sans erreur BLE.
    """
    writes = list(writes)
    if sync_clock:
        writes = [P.build_sync_clock()] + writes

    for attempt in range(1, retries + 1):
        client = None
        try:
            client = await _connect(address, timeout, adapter=adapter)

            def _handler(_sender, data):
                raw = bytes(data)
                logger.debug(f"NOTIF {raw.hex('-')}")
                if on_notify:
                    on_notify(raw)

            await client.start_notify(C.CHAR_NOTIFY_UUID, _handler)

            for w in writes:
                logger.debug(f"WRITE {w.hex('-')}")
                await client.write_gatt_char(C.CHAR_WRITE_UUID, w, response=False)
                await asyncio.sleep(0.2)

            await asyncio.sleep(listen_seconds)
            return True

        except BleakError as e:
            logger.warning(f"Erreur BLE (tentative {attempt}/{retries}) : {e}")
            if attempt == retries:
                raise RainbirdBLEError(str(e)) from e
            await asyncio.sleep(1.0)
        finally:
            if client is not None:
                try:
                    if client.is_connected:
                        await client.disconnect()
                        logger.debug("Déconnexion propre effectuée")
                except Exception:
                    pass

    return False


async def read_full_config(
    address: str, timeout: float = 15.0, listen_seconds: float = 15.0, adapter: Optional[str] = None
) -> List[bytes]:
    """
    Connexion, abonnement, envoi des requêtes de lecture connues (état,
    programmes, budget mensuel, noms de zone), collecte de toutes les
    notifications reçues pendant `listen_seconds`. Retourne la liste brute
    des trames reçues (à classifier/décoder ensuite avec protocol.py).
    """
    received: List[bytes] = []

    def collect(data: bytes):
        received.append(data)

    writes = [C.CMD_STATUS_PING, C.CMD_READ_STATE] + C.CMD_READ_EXTRA
    await run_session(
        address, writes, on_notify=collect, listen_seconds=listen_seconds, timeout=timeout, adapter=adapter
    )
    return received
