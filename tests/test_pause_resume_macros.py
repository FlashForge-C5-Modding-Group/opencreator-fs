import ast
import pathlib
import re
import textwrap
import unittest

import jinja2

CONFIG = pathlib.Path(__file__).resolve().parents[1] / "fs" / "usr" / "data" / "config" / "mainsail.cfg"

PAUSED_STATE = {"reason": "", "tool": 1, "temps": [0., 220., 0., 150.], "fan": .5,
                "x": 120., "y": 100.}


def macro(name):
    section = CONFIG.read_text(encoding="utf-8").split("[gcode_macro %s]\n" % name, 1)[1].split("\n[", 1)[0]
    head, gcode = section.split("gcode:\n", 1)
    variables = {}
    for line in head.splitlines():
        if line.startswith("variable_"):
            key, value = line[len("variable_"):].split(":", 1)
            variables[key.strip()] = ast.literal_eval(value.strip())
    return textwrap.dedent(gcode), variables


def raise_error(message):
    raise RuntimeError(message)


def render(name, printer, params=None, **overrides):
    gcode, variables = macro(name)
    variables.update(overrides)
    template = jinja2.Environment("{%", "%}", "{", "}").from_string(gcode)
    out = template.render(printer=printer, params=params or {}, rawparams="",
                          action_raise_error=raise_error, **variables)
    return [line.strip() for line in out.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def make_printer(paused=False, homed="xyz", tool=1, x=120., sensor_error=None,
                 busy=False, temps=(0., 220., 0., 150.), fan=.5, can_extrude=True,
                 z=5.4, by_object=False, max_z=0.):
    printer = {
        "pause_resume": {"is_paused": paused},
        "virtual_sdcard": {"print_by_object": by_object, "print_max_z": max_z},
        "toolhead": {"homed_axes": homed, "axis_maximum": {"z": 270.},
                     "extruder": "extruder%d" % tool if tool else "extruder"},
        "creator5_toolchanger": {
            "active_tool": tool, "sensor_error": sensor_error, "busy": busy,
            "purge_x": 276.5, "purge_y": 257., "prep_approach_x": 250.,
            "prep_approach_y": 250., "purge_retract": 5., "travel_speed": 600.},
        "gcode_move": {"gcode_position": {"x": x, "y": 100., "z": z},
                       "homing_origin": {"z": 1.5}},
        "fan_generic fanM106": {"speed": fan},
        "configfile": {"settings": {
            "printer": {"max_z_velocity": 20.},
            "afc": {"z_hop": .4},
            "idle_timeout": {"timeout": 600.},
            "pause_resume": {"recover_velocity": 50.}}},
    }
    for index, target in enumerate(temps):
        printer["extruder" if index == 0 else "extruder%d" % index] = {
            "target": target, "can_extrude": can_extrude}
    return printer


def saved_state(lines):
    line = next(line for line in lines if "VARIABLE=state" in line)
    return ast.literal_eval(re.search(r'VALUE="(.*)"', line).group(1))


def z_moves(lines):
    return [line for line in lines if line.startswith("G1") and "Z" in line]


class PauseMacroTest(unittest.TestCase):
    def test_manual_pause_saves_retracts_cools_then_parks(self):
        lines = render("PAUSE", make_printer())
        self.assertEqual(saved_state(lines), PAUSED_STATE)
        retract = "G1 E-2.0 F2100"
        for line in ("PAUSE_BASE", retract, "M107", "SET_IDLE_TIMEOUT TIMEOUT=36000",
                     "SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=40",
                     "SET_HEATER_TEMPERATURE HEATER=extruder3 TARGET=40",
                     "C5_MOVE_TO_PURGE_BUCKET",
                     "SET_GCODE_VARIABLE MACRO=RESUME VARIABLE=parked VALUE=True"):
            self.assertIn(line, lines)
        # Cold tools stay cold
        self.assertNotIn("SET_HEATER_TEMPERATURE HEATER=extruder TARGET=40", lines)
        # Saved before PAUSE_BASE, retract before cooling, cooling before the park
        self.assertLess(lines.index("PAUSE_BASE"), lines.index(retract))
        self.assertLess(lines.index(retract), lines.index("M107"))
        self.assertLess(lines.index("M107"), lines.index("C5_MOVE_TO_PURGE_BUCKET"))
        # Paused at Z5.0, AFC's 0.4 mm hop already done: down to 2 mm below
        lower = "G1 Z7.000 F1200.0"
        self.assertEqual(z_moves(lines), [lower])
        self.assertLess(lines.index(retract), lines.index(lower))
        self.assertLess(lines.index(lower), lines.index("C5_MOVE_TO_PURGE_BUCKET"))

    def test_without_afc_hop_still_goes_down_2_mm(self):
        printer = make_printer()
        del printer["configfile"]["settings"]["afc"]
        self.assertEqual(z_moves(render("PAUSE", printer)), ["G1 Z7.400 F1200.0"])

    def test_without_z_homed_does_not_move_z(self):
        self.assertEqual(z_moves(render("PAUSE", make_printer(homed="xy"))), [])

    def test_runout_leaves_the_move_and_heaters_to_the_runout_macro(self):
        lines = render("PAUSE", make_printer(), {"REASON": "runout"})
        self.assertEqual(saved_state(lines)["reason"], "runout")
        self.assertIn("PAUSE_BASE", lines)
        self.assertIn("G1 E-2.0 F2100", lines)
        for absent in ("C5_MOVE_TO_PURGE_BUCKET", "M107", "SET_HEATER_TEMPERATURE"):
            self.assertFalse([line for line in lines if line.startswith(absent)], absent)

    def test_motion_pause_cools_in_place(self):
        lines = render("PAUSE", make_printer(), {"REASON": "motion"})
        self.assertIn("M107", lines)
        self.assertIn("SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=40", lines)
        self.assertNotIn("C5_MOVE_TO_PURGE_BUCKET", lines)
        self.assertIn('RESPOND MSG="Paused in place: skipped steps, X/Y not trusted"', lines)

    def test_park_is_skipped_when_it_is_not_safe(self):
        cases = {
            "not homed": dict(homed="xy"),
            "no tool attached": dict(tool=None),
            "tool sensor error": dict(sensor_error="Conflicting dock/grab"),
            "toolchanger busy": dict(busy=True),
            "head is beside the docks": dict(x=260.),
        }
        for why, kwargs in cases.items():
            with self.subTest(why=why):
                lines = render("PAUSE", make_printer(**kwargs))
                self.assertNotIn("C5_MOVE_TO_PURGE_BUCKET", lines)
                self.assertIn('RESPOND MSG="Paused in place: %s"' % why, lines)
                self.assertIn("M107", lines)

    def test_no_tool_is_saved_as_minus_one(self):
        lines = render("PAUSE", make_printer(tool=None))
        self.assertEqual(saved_state(lines)["tool"], -1)

    def test_cold_nozzle_is_not_retracted(self):
        lines = render("PAUSE", make_printer(can_extrude=False))
        self.assertFalse([line for line in lines if line.startswith("G1 E")])

    def test_second_pause_does_nothing(self):
        self.assertEqual(render("PAUSE", make_printer(paused=True)), [])

    def test_by_object_lowers_the_bed_below_the_tallest_object_first(self):
        lines = render("PAUSE", make_printer(by_object=True, max_z=30.2))
        lower = "G1 Z32.200 F1200.0"
        self.assertEqual(z_moves(lines), [lower])
        # After the retract, before the park
        self.assertLess(lines.index("G1 E-2.0 F2100"), lines.index(lower))
        self.assertLess(lines.index(lower), lines.index("C5_MOVE_TO_PURGE_BUCKET"))
        self.assertLess(lines.index("G90"), lines.index(lower))
        self.assertIn("RESTORE_GCODE_STATE NAME=C5_PAUSE_CLEAR MOVE=0", lines)

    def test_by_object_lowers_before_runout_and_motion_travel(self):
        for reason in ("runout", "motion"):
            with self.subTest(reason=reason):
                lines = render("PAUSE", make_printer(by_object=True, max_z=30.2),
                               {"REASON": reason})
                self.assertEqual(z_moves(lines), ["G1 Z32.200 F1200.0"])

    def test_by_object_on_the_tallest_object_uses_the_normal_2_mm(self):
        lines = render("PAUSE", make_printer(by_object=True, max_z=5., z=5.4))
        self.assertEqual(z_moves(lines), ["G1 Z7.000 F1200.0"])

    def test_by_object_stops_short_of_the_z_limit(self):
        lines = render("PAUSE", make_printer(by_object=True, max_z=268.))
        # 270 limit - 1.5 tool offset - 1 margin
        self.assertEqual(z_moves(lines), ["G1 Z267.500 F1200.0"])

    def test_never_raises_the_bed_near_the_z_limit(self):
        self.assertEqual(z_moves(render("PAUSE", make_printer(z=268.5))), [])

    def test_by_object_without_z_homed_does_not_move_z(self):
        lines = render("PAUSE", make_printer(by_object=True, max_z=30.2, homed="xy"))
        self.assertEqual(z_moves(lines), [])


class ResumeMacroTest(unittest.TestCase):
    def resume(self, params=None, state=None, parked=True, **printer):
        printer.setdefault("paused", True)
        return render("RESUME", make_printer(**printer), params,
                      state=dict(PAUSED_STATE, **(state or {})), parked=parked)

    def test_parked_pause_reheats_purges_and_returns(self):
        lines = self.resume()
        expected = [
            "SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=220.0",
            "SET_HEATER_TEMPERATURE HEATER=extruder3 TARGET=150.0",
            "TEMPERATURE_WAIT SENSOR=extruder1 MINIMUM=218.0",
            "TEMPERATURE_WAIT SENSOR=extruder3 MINIMUM=148.0",
            "C5_TOOL_PURGE LENGTH=20.0",
            "_C5_RESUME_FAN_BLAST",
            "C5_LEAVE_PURGE_BUCKET",
            "G1 E5.0 F300",
            "SET_FAN_SPEED FAN=fanM106 SPEED=0.5",
            "SET_IDLE_TIMEOUT TIMEOUT=600.0",
            # Back to the print at tool-change travel speed
            "RESUME_BASE VELOCITY=600.0",
            'SET_GCODE_VARIABLE MACRO=RESUME VARIABLE=state VALUE="{}"',
        ]
        self.assertEqual([line for line in lines if line in expected], expected)
        self.assertNotIn("G28 X Y", lines)
        self.assertNotIn("C5_MOVE_TO_PURGE_BUCKET", lines)
        self.assertNotIn("HEATER=extruder TARGET", " ".join(lines))
        self.assertEqual(z_moves(lines), [])

    def test_refuses_when_z_is_lost(self):
        with self.assertRaisesRegex(RuntimeError, "Z lost"):
            self.resume(homed="xy")

    def test_refuses_without_the_paused_tool(self):
        with self.assertRaisesRegex(RuntimeError, "Pick up T1"):
            self.resume(tool=None)
        with self.assertRaisesRegex(RuntimeError, "T2 is attached but the print paused with T1"):
            self.resume(tool=2)
        with self.assertRaisesRegex(RuntimeError, "Tool sensors report an error"):
            self.resume(sensor_error="Conflicting dock/grab")

    def test_motion_pause_rehomes_xy_and_reheats_at_the_bucket(self):
        lines = self.resume(state={"reason": "motion"}, parked=False)
        self.assertLess(lines.index("G28 X Y"), lines.index("C5_MOVE_TO_PURGE_BUCKET"))
        self.assertLess(lines.index("C5_MOVE_TO_PURGE_BUCKET"),
                        lines.index("SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=220.0"))

    def test_lost_xy_rehomes_then_goes_back_to_the_bucket(self):
        lines = self.resume(homed="z")
        self.assertLess(lines.index("G28 X Y"), lines.index("C5_MOVE_TO_PURGE_BUCKET"))

    def test_unparked_pause_moves_to_the_bucket_before_reheating(self):
        lines = self.resume(parked=False)
        self.assertNotIn("G28 X Y", lines)
        self.assertLess(lines.index("C5_MOVE_TO_PURGE_BUCKET"),
                        lines.index("SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=220.0"))

    def test_runout_resume_purges_the_load_length_where_runout_left_it(self):
        lines = self.resume({"PURGE_LENGTH": "120", "PURGE_SPEED": "8"},
                            state={"reason": "runout"}, parked=False)
        self.assertIn("C5_TOOL_PURGE LENGTH=120.0 SPEED=8.0", lines)
        self.assertNotIn("C5_MOVE_TO_PURGE_BUCKET", lines)

    def test_by_layer_resume_goes_straight_back(self):
        self.assertFalse([line for line in self.resume()
                          if line.startswith("G1 X")])

    def test_by_object_crosses_at_the_clear_height_before_lowering(self):
        lines = self.resume(by_object=True, max_z=30.2)
        cross = "G1 X120.000 Y100.000 F36000.0"
        self.assertLess(lines.index("C5_LEAVE_PURGE_BUCKET"), lines.index(cross))
        self.assertLess(lines.index("G1 E5.0 F300"), lines.index(cross))
        self.assertLess(lines.index(cross), lines.index("RESUME_BASE VELOCITY=600.0"))
        self.assertIn("RESTORE_GCODE_STATE NAME=C5_RESUME_CROSS MOVE=0", lines)
        self.assertEqual(z_moves(lines), [])

    def test_velocity_can_be_overridden(self):
        self.assertIn("RESUME_BASE VELOCITY=80.0", self.resume({"VELOCITY": "80"}))

    def test_not_paused_just_calls_resume_base(self):
        self.assertEqual(self.resume(paused=False), ["RESUME_BASE VELOCITY=50.0"])

    def test_pause_without_saved_state_falls_back_to_resume_base(self):
        lines = render("RESUME", make_printer(paused=True), state={}, parked=False)
        self.assertEqual(lines, ["RESUME_BASE VELOCITY=50.0"])


class FanBlastMacroTest(unittest.TestCase):
    def test_full_fan_for_three_seconds(self):
        self.assertEqual(render("_C5_RESUME_FAN_BLAST", make_printer()),
                         ["SET_FAN_SPEED FAN=fanM106 SPEED=1", "G4 P3000"])


if __name__ == "__main__":
    unittest.main()
