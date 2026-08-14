"""
Tests de protocol.py à partir de trames RÉELLEMENT CAPTURÉES (pcap + nRF
Connect), documentées dans rainbird-tbos-ble-synthese.md.

Objectif : pouvoir vérifier tout le module sans matériel, et détecter
immédiatement une régression si on modifie l'encodage/décodage plus tard.

Lancer avec : python -m pytest tests/test_protocol.py -v
(ou : python -m unittest tests.test_protocol -v)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import protocol as P


def hx(s: str) -> bytes:
    """Aide : convertit une chaîne 'xx-xx-xx' capturée directement en bytes."""
    return bytes.fromhex(s.replace("-", ""))


class TestBuildCommands(unittest.TestCase):
    def test_manual_run_zone1_1min(self):
        # Confirmé par capture réelle : test zone1/1min du 12/08 22h46
        self.assertEqual(P.build_manual_run(1, 60), hx("09-05-12-01-00-00-3c"))

    def test_manual_run_zone3_2min(self):
        self.assertEqual(P.build_manual_run(3, 120), hx("09-05-12-03-00-00-78"))

    def test_manual_run_zone2_3min(self):
        # Confirmé par capture réelle + recoupement avec la notif de confirmation
        self.assertEqual(P.build_manual_run(2, 180), hx("09-05-12-02-00-00-b4"))

    def test_manual_run_invalid_station(self):
        with self.assertRaises(ValueError):
            P.build_manual_run(7, 60)

    def test_stop(self):
        self.assertEqual(P.build_stop(), hx("09-05-15-00-ff-00-00"))

    def test_power_off(self):
        # Confirmé : c0 = OFF
        self.assertEqual(P.build_power(False), hx("09-05-c0-00-00-00-00"))

    def test_power_on(self):
        # Confirmé : a0 = ON
        self.assertEqual(P.build_power(True), hx("09-05-a0-00-00-00-00"))

    def test_run_program_a(self):
        # Seul programme confirmé par capture réelle
        self.assertEqual(P.build_run_program("A"), hx("09-05-14-00-01-00-00"))

    def test_sync_clock(self):
        import datetime
        dt = datetime.datetime(2026, 8, 12, 22, 14, 9)
        self.assertEqual(P.build_sync_clock(dt), hx("03-06-00-7e-08-0c-16-0e-09"))


class TestBuildProgramRecords(unittest.TestCase):
    def test_program_b_matches_capture(self):
        # Programme B tel que capturé : sam+dim (0x60), départ 7h00, 15/15/15/0/10/0 min
        records = P.build_program_records(
            "B",
            day_mask=0x60,
            start_min=7 * 60,
            durations_s=[900, 900, 900, 0, 600, 0],
        )
        # On ignore la date (dernier champ, dépend du jour d'exécution du test)
        self.assertEqual(records[0][:12], hx("0f-0e-00-11-00-00-00-64-00-60-01-00"))
        self.assertEqual(records[1], hx("0f-12-01-11-01-a4-05-a0-05-a0-05-a0-05-a0-05-a0-05-a0-05-a0"))
        self.assertEqual(records[2], hx("0f-11-02-11-00-03-84-00-03-84-00-03-84-00-00-00-00-02-58"))
        self.assertEqual(records[3], hx("0f-11-03-11-00-00-00-00-00-00-00-00-00-00-00-00-00-00-00"))

    def test_program_a_matches_capture(self):
        records = P.build_program_records(
            "A",
            day_mask=0x1F,
            start_min=6 * 60 + 20,
            durations_s=[900, 900, 900, 0, 1200, 0],
        )
        self.assertEqual(records[1], hx("0f-12-01-10-01-7c-05-a0-05-a0-05-a0-05-a0-05-a0-05-a0-05-a0"))
        self.assertEqual(records[2], hx("0f-11-02-10-00-03-84-00-03-84-00-03-84-00-00-00-00-04-b0"))

    def test_zone_name_record(self):
        self.assertEqual(
            P.build_zone_name_record(0, "JARDIN D"),
            hx("0b-0e-00-00-4a-41-52-44-49-4e-20-44-00-00-00-00"),
        )
        self.assertEqual(
            P.build_zone_name_record(3, "HAIE"),
            hx("0b-0e-00-03-48-41-49-45-00-00-00-00-00-00-00-00"),
        )

    def test_monthly_budget_write_matches_capture(self):
        # Vérifié contre une trame d'écriture réellement capturée (anciennes valeurs, 12/08)
        f1, f2 = P.build_monthly_budget_records({"08": 140, "09": 90, "10": 60, "11": 0, "12": 0})
        self.assertEqual(f2, hx("15-10-01-00-8c-00-5a-00-3c-00-00-00-00-ff-f0-00-ff-ff"))

    def test_monthly_budget_write_matches_capture_13_08(self):
        # Vérifié contre une trame d'écriture réellement capturée avec de NOUVELLES valeurs (13/08)
        monthly = {
            "01": 10, "02": 20, "03": 30, "04": 40, "05": 50, "06": 60, "07": 70,
            "08": 80, "09": 90, "10": 100, "11": 120, "12": 130,
        }
        f1, f2 = P.build_monthly_budget_records(monthly)
        self.assertEqual(f1, hx("15-11-00-02-01-00-0a-00-14-00-1e-00-28-00-32-00-3c-00-46"))
        self.assertEqual(f2, hx("15-10-01-00-50-00-5a-00-64-00-78-00-82-ff-f0-00-ff-ff"))

    def test_monthly_budget_rejects_non_multiple_of_10(self):
        with self.assertRaises(ValueError):
            P.build_monthly_budget_records({"08": 77})

    def test_monthly_budget_accepts_multiple_of_10(self):
        # Ne doit pas lever d'exception
        P.build_monthly_budget_records({"03": 30, "04": 40})


class TestClassify(unittest.TestCase):
    def test_state_frame(self):
        self.assertEqual(P.classify(hx("0a-10-02-42-00-00-00-2a-00-01-4d-13-10-00-3c-10-00-00")), "state")

    def test_program_header(self):
        self.assertEqual(P.classify(hx("12-0e-0b-10-00-00-00-64-00-1e-01-00-0c-08-07-ea")), "program_header")

    def test_program_starts(self):
        self.assertEqual(
            P.classify(hx("12-12-01-10-01-86-05-a0-05-a0-05-a0-05-a0-05-a0-05-a0-05-a0")),
            "program_starts",
        )

    def test_zone_name(self):
        self.assertEqual(
            P.classify(hx("0c-12-00-00-4a-41-52-44-49-4e-20-44-00-00-00-00-00-00-00-00")),
            "zone_name",
        )

    def test_program_durations_1(self):
        self.assertEqual(
            P.classify(hx("12-11-02-10-00-03-84-00-03-84-00-03-84-00-00-00-00-04-b0")),
            "program_durations_1",
        )

    def test_monthly_budget_1(self):
        self.assertEqual(
            P.classify(hx("16-11-00-02-01-00-0a-00-14-00-1e-00-28-00-32-00-3c-00-46")),
            "monthly_budget_1",
        )

    def test_monthly_budget_2(self):
        self.assertEqual(
            P.classify(hx("16-10-00-00-50-00-5a-00-64-00-6e-00-78-ff-f0-00-ff-ff")),
            "monthly_budget_2",
        )


class TestDecode(unittest.TestCase):
    def test_decode_state_manual(self):
        result = P.decode_state(hx("0a-10-02-42-00-00-00-2a-00-01-4d-13-10-00-3c-10-00-00"))
        self.assertEqual(result["state"], "manual")
        self.assertEqual(result["active_zone"], 1)

    def test_decode_state_off(self):
        result = P.decode_state(hx("0a-10-02-00-00-00-00-00-00-00-4d-13-10-00-00-10-00-00"))
        self.assertEqual(result["state"], "off")
        self.assertIsNone(result["active_zone"])

    def test_decode_state_program_running(self):
        # Confirmé par capture réelle : lancement du programme B (13/08)
        result = P.decode_state(hx("0a-10-02-44-00-00-00-26-02-01-4d-13-10-02-d0-10-00-00"))
        self.assertEqual(result["state"], "program_running")
        self.assertEqual(result["active_zone"], 1)

    def test_decode_program_header(self):
        # Programme A après suppression du lundi : jours mar-ven
        result = P.decode_program_header(hx("12-0e-0b-10-00-00-00-64-00-1e-01-00-0c-08-07-ea"))
        self.assertEqual(result["program"], "A")
        self.assertEqual(result["active_days"], ["mar", "mer", "jeu", "ven"])
        self.assertTrue(result["enabled"])
        self.assertEqual(result["device_date"], "12/08/2026")

    def test_decode_program_starts(self):
        result = P.decode_program_starts(hx("12-12-01-10-01-86-05-a0-05-a0-05-a0-05-a0-05-a0-05-a0-05-a0"))
        self.assertEqual(result["program"], "A")
        self.assertEqual(result["start_times"], ["06:30"])

    def test_decode_program_durations(self):
        result = P.decode_program_durations(
            hx("12-11-02-10-00-03-84-00-03-84-00-03-84-00-00-00-00-04-b0"), part=1
        )
        self.assertEqual(result["durations_s"], [900, 900, 900, 0, 1200])

    def test_decode_zone_name(self):
        result = P.decode_zone_name(hx("0c-12-00-00-4a-41-52-44-49-4e-20-44-00-00-00-00-00-00-00-00"))
        self.assertEqual(result, {"index": 0, "name": "JARDIN D"})

    def test_decode_monthly_budget_1(self):
        # Confirmé : mars=30%, avril=40% (Thomas, test réel)
        values = P.decode_monthly_budget_1(hx("16-11-00-02-01-00-0a-00-14-00-1e-00-28-00-32-00-3c-00-46"))
        self.assertEqual(values, [10, 20, 30, 40, 50, 60, 70])

    def test_decode_monthly_budget_2(self):
        values = P.decode_monthly_budget_2(hx("16-10-00-00-50-00-5a-00-64-00-6e-00-78-ff-f0-00-ff-ff"))
        self.assertEqual(values, [80, 90, 100, 110, 120])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCommandsValidation(unittest.TestCase):
    """Valide les garde-fous ajoutés dans commands.py (pas d'appel BLE réel ici)."""

    def test_first_start_to_minutes_valid(self):
        import commands as CMD
        self.assertEqual(CMD._first_start_to_minutes(["06:20"]), 380)
        self.assertEqual(CMD._first_start_to_minutes([]), 0)

    def test_first_start_to_minutes_invalid_format(self):
        import commands as CMD
        with self.assertRaises(ValueError):
            CMD._first_start_to_minutes(["6h20"])

    def test_first_start_to_minutes_out_of_range(self):
        import commands as CMD
        with self.assertRaises(ValueError):
            CMD._first_start_to_minutes(["25:00"])
        with self.assertRaises(ValueError):
            CMD._first_start_to_minutes(["10:60"])
