"""
Constantes matériel et protocole pour le Rain Bird TBOS-BT.

Toutes les valeurs ici viennent de captures réelles (nRF Connect + pcap système
Android), documentées dans rainbird-tbos-ble-synthese.md. Rien n'est deviné :
ce qui n'est pas confirmé est marqué explicitement comme tel.
"""

# --- Matériel -----------------------------------------------------------
DEFAULT_ADDRESS = "FF:31:C7:36:16:10"
SERVICE_UUID = "f4780001-f54b-4c45-b4be-6db9ffb0703f"
CHAR_NOTIFY_UUID = "f4780003-f54b-4c45-b4be-6db9ffb0703f"
CHAR_WRITE_UUID = "f4780002-f54b-4c45-b4be-6db9ffb0703f"

# Noms de zone par défaut (index 0-based = station physique 1-6).
# Le programmateur renvoie ses propres noms en BLE (trames 0x0E/0x12) ;
# ces valeurs ne servent que de repli si la lecture échoue.
DEFAULT_ZONE_NAMES = ["JARDIN D", "JARDIN G", "JARDIN C", "HAIE", "POTAGER", "VALVE 6"]
ZONE_COUNT = 6

# --- États contrôleur -----------------------------------------------------
STATE_OFF = 0x00
STATE_ON_AUTO = 0x40
STATE_MANUAL = 0x42
STATE_PROGRAM_RUNNING = 0x44
STATE_LABELS = {
    STATE_OFF: "off",
    STATE_ON_AUTO: "on",
    STATE_MANUAL: "manual",
    STATE_PROGRAM_RUNNING: "program_running",
}

# --- Programmes -------------------------------------------------------
# Tag "PP" utilisé dans les trames de LECTURE (byte3 des enregistrements programme)
PROGRAM_READ_TAG = {"A": 0x10, "B": 0x11, "C": 0x12}
PROGRAM_LETTER_FROM_TAG = {v: k for k, v in PROGRAM_READ_TAG.items()}

# Tag utilisé dans la commande "lancer un programme" (09-05-14-00-PP-00-00)
# CONFIRMÉ pour A=1 ; B=2 et C=3 sont une extrapolation logique NON TESTÉE.
PROGRAM_RUN_INDEX = {"A": 0x01, "B": 0x02, "C": 0x03}

DAY_LABELS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]  # bit0=lundi ... bit6=dimanche

# --- Commandes confirmées (préfixes fixes) --------------------------------
CMD_READ_STATE = bytes.fromhex("1300")
CMD_STOP = bytes.fromhex("09051500ff0000")  # 09-05-15-00-ff-00-00
CMD_ON = bytes.fromhex("0905a000000000")
CMD_OFF = bytes.fromhex("0905c000000000")

# Requêtes de lecture supplémentaires observées à la connexion (contenu exact
# de leur réponse pas toujours identifié avec certitude, mais l'envoi est sûr)
CMD_READ_EXTRA = [bytes.fromhex("1700"), bytes.fromhex("1100"), bytes.fromhex("0d00")]

# Requête de statut/handshake générique observée (réponse fixe 1a-03-02-88-ee)
CMD_STATUS_PING = bytes.fromhex("1900001900")
