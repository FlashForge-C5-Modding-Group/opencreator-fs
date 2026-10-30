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
    gcode = textwrap.dedent(body.split("gcode:\n", 1)[1])
    template = jinja2.Environment("{%", "%}", "{", "}").from_string(gcode)

    def fail(message):
        raise RaisedError(message)

    out = template.render(printer=printer, params=params, rawparams=rawparams,
                          action_raise_error=fail,
                          action_respond_info=lambda m: "",
                          **variables(body))
    return [line.strip() for line in out.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def render_print_start(printer, params):
    output = []
    for line in render(START_CONFIG, "gcode_macro _C5_PRINT_START_AFTER_BOOT",
                       printer, params):
        if line.split()[0] == "_OC_PRINT_START_REST":
            output.extend(render(START_CONFIG, "gcode_macro _OC_PRINT_START_REST",
                                 printer, params))
        else:
            output.append(line)
    return output


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

    def commands(self, params):
        printer = {
            "output_pin flow_calibration": {"value": 0.},
            "output_pin purge": {"value": 0.},
            "output_pin bed_leveling": {"value": 0.},
            "bed_mesh": {"profiles": {}},
            "creator5_toolchanger": {"build_plate_detected": True},
        }
        for heater in ("extruder", "extruder1", "extruder2", "extruder3"):
            printer["filament_switch_sensor %s_tool_start" % heater] = {
                "filament_detected": True}
        return render_print_start(printer, params)

    def start(self, params):
        return [line for line in self.commands(params)
                if line.startswith("_SET_MPC_MATERIAL")]

    def test_per_tool_materials(self):
        self.assertEqual(
            self.start({"TOOL": "1", "TOOLS": "1,3", "HOTEND": "220",
                        "MATERIAL": "PLA", "MATERIAL3": "PETG"}),
            ['_SET_MPC_MATERIAL TOOL=1 MATERIAL="PLA"',
             '_SET_MPC_MATERIAL TOOL=3 MATERIAL="PETG"'])

    def test_all_tool_materials_do_not_expand_physical_preparation(self):
        out = self.commands({
            "TOOL": "0", "HOTEND": "220", "FLOW_CALIBRATION": "1", "PURGE": "1",
            "MATERIAL0": "PLA", "MATERIAL1": "PETG",
            "MATERIAL2": "ABS", "MATERIAL3": "UNKNOWN",
        })
        self.assertEqual(
            [line for line in out if line.startswith("_SET_MPC_MATERIAL")],
            ['_SET_MPC_MATERIAL TOOL=0 MATERIAL="PLA"',
             '_SET_MPC_MATERIAL TOOL=1 MATERIAL="PETG"',
             '_SET_MPC_MATERIAL TOOL=2 MATERIAL="ABS"',
             '_SET_MPC_MATERIAL TOOL=3 MATERIAL="UNKNOWN"'])
        self.assertEqual(
            [line for line in out if line.startswith("SET_HEATER_TEMPERATURE")],
            ["SET_HEATER_TEMPERATURE HEATER=extruder TARGET=100.0",
             "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=220.0",
             "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=100.0",
             "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=220.0"])
        self.assertEqual(
            [line for line in out if line.startswith("AFC_SELECT_TOOL")],
            ["AFC_SELECT_TOOL TOOL=extruder", "AFC_SELECT_TOOL TOOL=extruder"])
        self.assertEqual(
            [line for line in out if line.startswith("C5_AUTO_NOZZLE_Z")],
            ["C5_AUTO_NOZZLE_Z T=0 HOTEND=220.0 BED=0.0 FIRST_LAYER_HEIGHT=0.2",
             "C5_AUTO_NOZZLE_Z T=0 HOTEND=220.0 BED=0.0 FIRST_LAYER_HEIGHT=0.2"])
        self.assertEqual(out.count("C5_FLOW_CALIBRATION"), 1)
        self.assertEqual(out.count("C5_TOOL_PURGE"), 1)

    def test_shared_material_only_updates_selected_tools(self):
        self.assertEqual(
            self.start({"TOOL": "1", "TOOLS": "1,3", "HOTEND": "220",
                        "MATERIAL": "PLA"}),
            ['_SET_MPC_MATERIAL TOOL=1 MATERIAL="PLA"',
             '_SET_MPC_MATERIAL TOOL=3 MATERIAL="PLA"'])

    def test_unselected_per_tool_material_overrides_shared_without_heating(self):
        out = self.commands({"TOOL": "0", "HOTEND": "220",
                             "MATERIAL": "PLA", "MATERIAL2": "PETG"})
        self.assertEqual(
            [line for line in out if line.startswith("_SET_MPC_MATERIAL")],
            ['_SET_MPC_MATERIAL TOOL=0 MATERIAL="PLA"',
             '_SET_MPC_MATERIAL TOOL=2 MATERIAL="PETG"'])
        self.assertEqual(
            [line for line in out if line.startswith("SET_HEATER_TEMPERATURE")],
            ["SET_HEATER_TEMPERATURE HEATER=extruder TARGET=100.0",
             "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=100.0",
             "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=220.0"])

    def test_empty_per_tool_material_suppresses_shared_fallback(self):
        self.assertEqual(
            self.start({"TOOL": "0", "HOTEND": "220",
                        "MATERIAL": "PLA", "MATERIAL0": " ", "MATERIAL2": ""}),
            [])

    def test_no_material_no_call(self):
        self.assertEqual(self.start({"TOOL": "0", "HOTEND": "220"}), [])


class PrintStartChamberTests(unittest.TestCase):

    def commands(self, params, pro=True):
        printer = {
            "output_pin flow_calibration": {"value": 0.},
            "output_pin purge": {"value": 0.},
            "output_pin bed_leveling": {"value": 0.},
            "bed_mesh": {"profiles": {}},
            "creator5_toolchanger": {"build_plate_detected": True},
            "configfile": {"settings": {}},
        }
        if pro:
            printer["heater_generic chamber_heater"] = {}
            printer["configfile"]["settings"]["heater_generic chamber_heater"] = {
                "max_temp": 65.}
        for heater in ("extruder", "extruder1", "extruder2", "extruder3"):
            printer["filament_switch_sensor %s_tool_start" % heater] = {
                "filament_detected": True}
        return render_print_start(printer, params)

    def test_print_z_plan_runs_before_any_tool_is_selected(self):
        out = self.commands({"TOOL": "1", "BED": "100", "HOTEND": "240",
                             "FIRST_LAYER_HEIGHT": "0.1"})
        plan = [i for i, line in enumerate(out) if "C5_PRINT_Z_PLAN" in line]
        select = [i for i, line in enumerate(out) if "AFC_SELECT_TOOL" in line]
        self.assertEqual(len(plan), 1)
        self.assertLess(plan[0], select[0])
        self.assertIn("HOTEND1=240.0", out[plan[0]])
        self.assertIn("BED=100.0", out[plan[0]])
        self.assertIn("FIRST_LAYER_HEIGHT=0.1", out[plan[0]])

    def chamber(self, out):
        return [line for line in out if "chamber_heater" in line]

    def test_pro_heats_chamber_with_the_bed_without_waiting(self):
        out = self.commands({"TOOL": "0", "HOTEND": "260", "BED": "100",
                             "CHAMBER": "60"})
        self.assertEqual(self.chamber(out),
                         ["SET_HEATER_TEMPERATURE HEATER=chamber_heater TARGET=60.0"])
        bed = out.index("M140 S100.0")
        self.assertEqual(out[bed + 1],
                         "SET_HEATER_TEMPERATURE HEATER=chamber_heater TARGET=60.0")

    def test_chamber_target_is_capped_at_max_temp(self):
        out = self.commands({"TOOL": "0", "HOTEND": "260", "CHAMBER": "80"})
        self.assertEqual(self.chamber(out),
                         ["SET_HEATER_TEMPERATURE HEATER=chamber_heater TARGET=65.0"])

    def test_no_chamber_heater_or_no_target_leaves_it_alone(self):
        self.assertEqual(self.chamber(self.commands(
            {"TOOL": "0", "HOTEND": "260", "CHAMBER": "60"}, pro=False)), [])
        self.assertEqual(self.chamber(self.commands(
            {"TOOL": "0", "HOTEND": "220"})), [])


class PrintStartPurgeLineTests(unittest.TestCase):

    def lines(self, purge, purge_line, params=None):
        printer = {
            "output_pin flow_calibration": {"value": 0.},
            "output_pin purge": {"value": purge},
            "output_pin bed_leveling": {"value": 0.},
            "bed_mesh": {"profiles": {}},
            "creator5_toolchanger": {"build_plate_detected": True},
        }
        if purge_line is not None:
            printer["output_pin purge_line"] = {"value": purge_line}
        for heater in ("extruder", "extruder1", "extruder2", "extruder3"):
            printer["filament_switch_sensor %s_tool_start" % heater] = {
                "filament_detected": True}
        start = {"TOOL": "0", "HOTEND": "220"}
        start.update(params or {})
        return render_print_start(printer, start).count("LINE_PURGE")

    def test_purge_line_has_its_own_switch(self):
        self.assertEqual(self.lines(purge=0., purge_line=1.), 1)
        self.assertEqual(self.lines(purge=1., purge_line=0.), 0)

    def test_param_overrides_switch(self):
        self.assertEqual(self.lines(0., 1., {"PURGE_LINE": "0"}), 0)
        self.assertEqual(self.lines(0., 0., {"PURGE_LINE": "1"}), 1)

    def test_without_the_switch_follows_purge(self):
        self.assertEqual(self.lines(purge=1., purge_line=None), 1)
        self.assertEqual(self.lines(purge=0., purge_line=None), 0)


class PrintStartPreheatTests(unittest.TestCase):

    def test_preheats_before_homing_and_waits_before_meshing(self):
        printer = {
            "output_pin flow_calibration": {"value": 0.},
            "output_pin purge": {"value": 0.},
            "output_pin bed_leveling": {"value": 1.},
            "bed_mesh": {"profiles": {}},
            "creator5_toolchanger": {"build_plate_detected": True},
        }
        for heater in ("extruder", "extruder1", "extruder2", "extruder3"):
            printer["filament_switch_sensor %s_tool_start" % heater] = {
                "filament_detected": True}
        out = render_print_start(printer, {
            "TOOL": "1", "TOOLS": "1,3", "HOTEND": "220", "HOTEND3": "90"})
        home = out.index("C5_HOME_FOR_PRINT")
        mesh = out.index("BED_MESH_CALIBRATE ADAPTIVE=1")
        self.assertEqual(out[home - 2:home], [
            "SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=100.0",
            "SET_HEATER_TEMPERATURE HEATER=extruder3 TARGET=90.0"])
        waits = [line for line in out[home:mesh]
                 if line.startswith("TEMPERATURE_WAIT SENSOR=extruder")]
        self.assertEqual(waits, [
            "TEMPERATURE_WAIT SENSOR=extruder1 MINIMUM=98.0",
            "TEMPERATURE_WAIT SENSOR=extruder3 MINIMUM=88.0"])

    def test_other_tools_wait_at_idle_temperature_or_100(self):
        printer = {
            "output_pin flow_calibration": {"value": 0.},
            "output_pin purge": {"value": 0.},
            "output_pin bed_leveling": {"value": 0.},
            "bed_mesh": {"profiles": {}},
            "creator5_toolchanger": {"build_plate_detected": True},
        }
        for heater in ("extruder", "extruder1", "extruder2", "extruder3"):
            printer["filament_switch_sensor %s_tool_start" % heater] = {
                "filament_detected": True}
        # T0 from TOOLS, T2 and T3 only from the slicer's used tools; the
        # first tool (T1) is not set to idle.
        out = render_print_start(printer, {
            "TOOL": "1", "TOOLS": "0,1", "HOTEND": "220",
            "USED_TOOLS": "1,3,2", "IDLE0": "150", "IDLE1": "160", "IDLE3": "170"})
        park = out.index("SMART_PARK")
        self.assertEqual(out[park + 1:park + 5], [
            "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=150.0",
            "SET_HEATER_TEMPERATURE HEATER=extruder2 TARGET=100.0",
            "SET_HEATER_TEMPERATURE HEATER=extruder3 TARGET=170.0",
            "SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=220.0"])

    def test_unused_tools_get_no_idle_or_fallback_temperature(self):
        printer = {
            "output_pin flow_calibration": {"value": 0.},
            "output_pin purge": {"value": 0.},
            "output_pin bed_leveling": {"value": 0.},
            "bed_mesh": {"profiles": {}},
            "creator5_toolchanger": {"build_plate_detected": True},
            "filament_switch_sensor extruder_tool_start": {"filament_detected": True},
        }
        out = render_print_start(printer, {"TOOL": "0", "HOTEND": "220",
                                           "USED_TOOLS": "0,1", "IDLE2": "150"})
        park = out.index("SMART_PARK")
        self.assertEqual(out[park + 1:park + 3], [
            "SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=100.0",
            "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=220.0"])
        self.assertFalse(any("extruder2" in line or "extruder3" in line for line in out))

    def test_single_tool_print_sets_no_idle_temperature(self):
        printer = {
            "output_pin flow_calibration": {"value": 0.},
            "output_pin purge": {"value": 0.},
            "output_pin bed_leveling": {"value": 0.},
            "bed_mesh": {"profiles": {}},
            "creator5_toolchanger": {"build_plate_detected": True},
            "filament_switch_sensor extruder_tool_start": {"filament_detected": True},
        }
        out = render_print_start(printer, {"TOOL": "0", "HOTEND": "220",
                                           "USED_TOOLS": "0", "IDLE0": "150"})
        park = out.index("SMART_PARK")
        self.assertEqual(out[park + 1], "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=220.0")


class PrintStartPlateCheckTests(unittest.TestCase):

    def start(self, params):
        printer = {
            "output_pin flow_calibration": {"value": 0.},
            "output_pin purge": {"value": 0.},
            "output_pin bed_leveling": {"value": 0.},
            "bed_mesh": {"profiles": {}},
            "creator5_toolchanger": {"build_plate_detected": True},
            "filament_switch_sensor extruder_tool_start": {
                "filament_detected": True},
        }
        return render_print_start(
            printer, dict({"TOOL": "0", "HOTEND": "220"}, **params))

    def test_checks_plate_right_after_homing(self):
        out = self.start({})
        home = out.index("C5_HOME_FOR_PRINT")
        self.assertTrue(out[home + 1].startswith("C5_CHECK_BUILD_PLATE "))
        self.assertLess(home + 1, out.index("M140 S0.0"))

    def test_can_be_skipped(self):
        self.assertFalse(any(
            line.startswith("C5_CHECK_BUILD_PLATE")
            for line in self.start({"BUILDPLATE_CHECK": "0"})))

    def test_rejects_bad_value(self):
        with self.assertRaisesRegex(RaisedError, "BUILDPLATE_CHECK"):
            self.start({"BUILDPLATE_CHECK": "2"})


if __name__ == "__main__":
    unittest.main()
