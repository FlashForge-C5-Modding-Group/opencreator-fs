import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "plugins" / "orca-filament-profiles" / "oc_orca_filament_profiles.py"
SPEC = importlib.util.spec_from_file_location("oc_orca_filament_profiles", PATH)
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)


class OrcaFilamentProfilesTest(unittest.TestCase):
    def setUp(self):
        self.published = []
        self.events = {}
        self.client = SimpleNamespace(send_lane_data=self.published.append)
        self.afc = SimpleNamespace(moonraker=self.client)
        self.printer = SimpleNamespace(
            lookup_object=lambda name, default: self.afc,
            register_event_handler=self.events.__setitem__,
        )

    def configure(self, mapping):
        return plugin.load_config(SimpleNamespace(
            get_printer=lambda: self.printer,
            get=lambda name, default: mapping,
            error=ValueError,
        ))

    def test_publish_adds_id_to_matching_lanes_without_mutating_afc_record(self):
        self.configure("PLA: OFJ3F2jm\nTPU-90A: OFwlZ7gH")
        self.events["afc:moonraker_connect"]()
        for key in ("T0", "T1", "T2", "T3"):
            record = {"namespace": "lane_data", "key": key,
                      "value": {"material": " tpu_90a ", "color": "#AA11BB"}}
            self.client.send_lane_data(record)
            self.assertEqual(self.published[-1], dict(
                record, value=dict(record["value"], filament_id="OFwlZ7gH")))
            self.assertNotIn("filament_id", record["value"])

    def test_missing_mapping_empty_lane_and_existing_id_pass_through(self):
        self.configure("PLA: OFJ3F2jm")
        self.events["afc:moonraker_connect"]()
        for record in (
            {"namespace": "lane_data", "value": {"material": "PA"}},
            {"namespace": "lane_data", "value": {"material": ""}},
            {"namespace": "lane_data",
             "value": {"material": "PLA", "filament_id": "OFMkAW6r"}},
            {"namespace": "other", "value": {"material": "PLA"}},
        ):
            self.client.send_lane_data(record)
            self.assertIs(self.published[-1], record)

    def test_connect_wraps_each_client_once(self):
        self.configure("PLA: OFJ3F2jm")
        connect = self.events["afc:moonraker_connect"]
        connect()
        publisher = self.client.send_lane_data
        connect()
        self.assertIs(self.client.send_lane_data, publisher)
        self.afc.moonraker = SimpleNamespace(send_lane_data=self.published.append)
        connect()
        self.afc.moonraker.send_lane_data({"namespace": "lane_data", "value": {"material": "PLA"}})
        self.assertEqual(self.published[-1]["value"]["filament_id"], "OFJ3F2jm")

    def test_empty_config_and_errors(self):
        self.configure("")
        self.assertEqual(self.events, {})
        with self.assertRaisesRegex(ValueError, "Expected a material and filament ID"):
            self.configure("PLA OFJ3F2jm")
        with self.assertRaisesRegex(ValueError, "Duplicate material"):
            self.configure("TPU-90A: OFwlZ7gH\ntpu_90a: OFx0WlzS")
