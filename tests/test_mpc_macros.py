import ast
import pathlib
import re
import textwrap
import unittest

import jinja2


CONFIG_DIR = (pathlib.Path(__file__).resolve().parents[1] / "fs" / "usr" /
              "data" / "config")
MPC_CONFIG = CONFIG_DIR / "printer.mpc.cfg"
START_CONFIG = CONFIG_DIR / "printer.creator5.cfg"


class RaisedError(Exception):
    pass


def section(path, name):
    text = path.read_text(encoding="utf-8")
    body = text.split("[%s]\n" % name, 1)[1]
    return body.split("\n[", 1)[0]


def variables(body):
    found = {}
    for match in re.finditer(r"^variable_(\w+):(.*?)(?=^\S)", body + "\nx",
                             re.M | re.S):
        lines = [re.sub(r"\s+#.*$", "", line)
                 for line in match.group(2).splitlines()]
        lines = [line for line in lines if not line.strip().startswith("#")]
        found[match.group(1)] = ast.literal_eval("\n".join(lines).strip())
    return found


def render(path, name, printer, params, rawparams=""):
    body = section(path, name)
    gcode = textwrap.dedent(body.split("\ngcode:\n", 1)[1])
    template = jinja2.Environment("{%", "%}", "{", "}").from_string(gcode)

    def fail(message):
        raise RaisedError(message)

    out = template.render(printer=printer, params=params, rawparams=rawparams,
                          action_raise_error=fail,
                          action_respond_info=lambda m: "",
                          **variables(body))
    return [line.strip() for line in out.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def printer_state(kalico=True, control="mpc", bed_control="pid",
                  active="extruder"):
    heaters = ["extruder", "extruder1", "extruder2", "extruder3"]
    printer = {
        "toolhead": {"extruder": active, "homed_axes": "xyz"},
        "configfile": {"settings": {h: {"control": control} for h in heaters}},
    }
    printer["configfile"]["settings"]["heater_bed"] = {"control": bed_control}
    for heater in heaters + ["heater_bed"]:
        printer[heater] = {"pid_profile": "default"} if kalico else {}
    return printer


class M109Tests(unittest.TestCase):

    def m109(self, printer, params, raw):
        return render(MPC_CONFIG, "gcode_macro M109", printer, params, raw)

    def test_stock_klipper_passes_through(self):
        self.assertEqual(self.m109(printer_state(kalico=False), {"S": "220"},
                                   "S220"), ["M109.1 S220"])

    def test_kalico_pid_passes_through(self):
        self.assertEqual(self.m109(printer_state(control="pid"), {"S": "220"},
                                   "S220"), ["M109.1 S220"])

    def test_mpc_waits_for_band_on_active_tool(self):
        self.assertEqual(
            self.m109(printer_state(active="extruder1"), {"S": "220"}, "S220"),
            ["M104 S220",
             "TEMPERATURE_WAIT SENSOR=extruder1 MINIMUM=218.0 MAXIMUM=225.0"])

    def test_mpc_with_tool_uses_afc_deadband(self):
        self.assertEqual(
            self.m109(printer_state(), {"S": "220", "T": "2"}, "S220 T2"),
            ["M109.1 S220 T2 D4"])

    def test_zero_target_passes_through(self):
        self.assertEqual(self.m109(printer_state(), {"S": "0"}, "S0"),
                         ["M109.1 S0"])


class M190Tests(unittest.TestCase):

    def test_pid_bed_passes_through(self):
        self.assertEqual(render(MPC_CONFIG, "gcode_macro M190", printer_state(),
                                {"S": "60"}, "S60"), ["M190.1 S60"])

    def test_mpc_bed_waits_for_band(self):
        self.assertEqual(
            render(MPC_CONFIG, "gcode_macro M190",
                   printer_state(bed_control="mpc"), {"S": "60"}, "S60"),
            ["M140 S60",
             "TEMPERATURE_WAIT SENSOR=heater_bed MINIMUM=58.0 MAXIMUM=65.0"])


class MaterialTests(unittest.TestCase):

    def material(self, printer, params):
        return render(MPC_CONFIG, "gcode_macro _SET_MPC_MATERIAL", printer,
                      params)

    def test_known_material_for_tool(self):
        out = self.material(printer_state(), {"TOOL": "2", "MATERIAL": "petg"})
        self.assertEqual(out[-1], "MPC_SET HEATER=extruder2 "
                                  "FILAMENT_DENSITY=1.27 FILAMENT_HEAT_CAPACITY=2.2")

    def test_unknown_material_uses_defaults(self):
        out = self.material(printer_state(), {"MATERIAL": "PVB"})
        self.assertIn("Unknown material 'PVB'", out[0])
        self.assertEqual(out[-1], "MPC_SET HEATER=extruder "
                                  "FILAMENT_DENSITY=1.2 FILAMENT_HEAT_CAPACITY=1.8")

    def test_stock_klipper_does_nothing(self):
        self.assertEqual(self.material(printer_state(kalico=False),
                                       {"MATERIAL": "PLA"}), [])


class CalibrateTests(unittest.TestCase):

    def test_refuses_stock_klipper(self):
        with self.assertRaisesRegex(RaisedError, "Kalico"):
            render(MPC_CONFIG, "gcode_macro C5_MPC_CALIBRATE",
                   printer_state(kalico=False), {})

    def test_refuses_pid_heater(self):
        with self.assertRaisesRegex(RaisedError, "control: mpc"):
            render(MPC_CONFIG, "gcode_macro C5_MPC_CALIBRATE",
                   printer_state(control="pid"), {"TOOL": "1"})

    def test_calibrates_requested_tool(self):
        out = render(MPC_CONFIG, "gcode_macro C5_MPC_CALIBRATE",
                     printer_state(), {"TOOL": "1", "TARGET": "230"})
        self.assertIn("MPC_CALIBRATE HEATER=extruder1 TARGET=230.0 "
                      "FAN_BREAKPOINTS=10", out)

    def test_calibrates_over_purge_bucket(self):
        for path, name in ((MPC_CONFIG, "gcode_macro C5_MPC_CALIBRATE"),
                           (CONFIG_DIR / "printer.macro.cfg",
                            "gcode_macro C5_PID_CALIBRATE")):
            out = render(path, name, printer_state(), {})
            calibrate = [i for i, line in enumerate(out)
                         if line.startswith(("MPC_CALIBRATE", "PID_CALIBRATE"))]
            self.assertEqual(len(calibrate), 4)
            for i in calibrate:
                self.assertEqual(out[i - 1], "C5_MOVE_TO_PURGE_BUCKET")
                self.assertEqual(out[i + 2], "G1 X250.0 Y250.0 F6000")


class PrintStartMaterialTests(unittest.TestCase):

    def start(self, params):
        printer = {
            "output_pin flow_calibration": {"value": 0.},
            "output_pin purge": {"value": 0.},
            "output_pin bed_leveling": {"value": 0.},
            "bed_mesh": {"profiles": {}},
        }
        for heater in ("extruder", "extruder1", "extruder2", "extruder3"):
            printer["filament_switch_sensor %s_tool_start" % heater] = {
                "filament_detected": True}
        return [line for line in render(START_CONFIG,
                                        "gcode_macro C5_PRINT_START",
                                        printer, params)
                if line.startswith("_SET_MPC_MATERIAL")]

    def test_per_tool_materials(self):
        self.assertEqual(
            self.start({"TOOL": "1", "TOOLS": "1,3", "HOTEND": "220",
                        "MATERIAL": "PLA", "MATERIAL3": "PETG"}),
            ['_SET_MPC_MATERIAL TOOL=1 MATERIAL="PLA"',
             '_SET_MPC_MATERIAL TOOL=3 MATERIAL="PETG"'])

    def test_no_material_no_call(self):
        self.assertEqual(self.start({"TOOL": "0", "HOTEND": "220"}), [])


class PrintStartPlateCheckTests(unittest.TestCase):

    def start(self, params):
        printer = {
            "output_pin flow_calibration": {"value": 0.},
            "output_pin purge": {"value": 0.},
            "output_pin bed_leveling": {"value": 0.},
            "bed_mesh": {"profiles": {}},
            "filament_switch_sensor extruder_tool_start": {
                "filament_detected": True},
        }
        return render(START_CONFIG, "gcode_macro C5_PRINT_START", printer,
                      dict({"TOOL": "0", "HOTEND": "220"}, **params))

    def test_checks_plate_right_after_homing(self):
        out = self.start({})
        home = out.index("C5_HOME_FOR_PRINT")
        self.assertEqual(out[home + 1], "C5_CHECK_BUILD_PLATE")
        self.assertLess(home + 1, out.index("M140 S0.0"))

    def test_can_be_skipped(self):
        self.assertNotIn("C5_CHECK_BUILD_PLATE",
                         self.start({"BUILDPLATE_CHECK": "0"}))

    def test_rejects_bad_value(self):
        with self.assertRaisesRegex(RaisedError, "BUILDPLATE_CHECK"):
            self.start({"BUILDPLATE_CHECK": "2"})


if __name__ == "__main__":
    unittest.main()
