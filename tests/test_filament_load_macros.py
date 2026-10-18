import copy
import re
import unittest

from test_mpc_macros import CONFIG_DIR, RaisedError, render


FILAMENT_CONFIG = CONFIG_DIR / "printer.filament.cfg"


class FilamentMacroRunner:
    """Execute real nested templates; model only Klipper/hardware commands.

    Each macro is rendered completely before its commands execute, as in
    Klipper. Heater waits update live status before the next helper renders.
    Hardware purge records the actual heater state at the feed boundary.
    """

    def __init__(self, attached=1, active="extruder1", target=0,
                 can_extrude=True, paused=False, sensor_error=None):
        self.min_extrude_temp = -200 if can_extrude else 170
        self.printer = {
            "creator5_toolchanger": {
                "active_tool": attached, "sensor_error": sensor_error},
            "toolhead": {"extruder": active, "homed_axes": "xyz"},
            "print_stats": {"state": "paused" if paused else "standby"},
            "pause_resume": {"is_paused": paused},
            "heater_bed": {"target": 0},
        }
        for index in range(4):
            heater = "extruder" if index == 0 else "extruder%d" % index
            self.printer[heater] = {
                "target": target if heater == active else 0,
                "temperature": 24., "can_extrude": can_extrude}
        self.macros = set(re.findall(
            r"^\[gcode_macro ([^\]]+)\]", FILAMENT_CONFIG.read_text(
                encoding="utf-8"), re.M))
        self.events = []
        self.gcode_state = {"position": [120., 100., 8., 42.],
                            "absolute_extrude": True}
        self.saved_states = {"PAUSE_STATE": copy.deepcopy(self.gcode_state)}

    def run(self, name="C5_LOAD_FILAMENT", **params):
        params = {key: str(value) for key, value in params.items()}
        # Do not render nested helpers until previous commands have executed.
        lines = render(FILAMENT_CONFIG, "gcode_macro " + name,
                       self.printer, params)
        for line in lines:
            self.execute(line)

    def execute(self, line):
        command, *args = line.split()
        params = dict(arg.split("=", 1) for arg in args if "=" in arg)
        if command in self.macros:
            self.run(command, **params)
            return
        heater = self.printer["toolhead"]["extruder"]
        if command == "C5_CHECK_LOAD_TOOL":
            tc = self.printer["creator5_toolchanger"]
            attached = tc["active_tool"]
            if tc["sensor_error"] or attached is None:
                raise RaisedError("Loading requires valid attached tool sensors")
            expected = "extruder" if attached == 0 else "extruder%d" % attached
            if (heater != expected or
                    int(params.get("T", attached)) != attached):
                raise RaisedError("Active hotend does not match attached tool")
        elif command == "AFC_SELECT_TOOL":
            heater = params["TOOL"]
            self.events.append(("select", heater))
            self.printer["toolhead"]["extruder"] = heater
            self.printer["creator5_toolchanger"]["active_tool"] = (
                0 if heater == "extruder" else int(heater[-1]))
        elif command == "SET_HEATER_TEMPERATURE":
            heater, target = params["HEATER"], float(params["TARGET"])
            self.events.append(("heat", heater, target))
            self.printer[heater]["target"] = target
        elif command == "TEMPERATURE_WAIT":
            heater, minimum = params["SENSOR"], float(params["MINIMUM"])
            self.events.append(("wait", heater, minimum))
            self.printer[heater]["temperature"] = max(
                self.printer[heater]["temperature"], minimum)
            self.printer[heater]["can_extrude"] = minimum >= self.min_extrude_temp
        elif command == "C5_AUTO_NOZZLE_Z":
            self.events.append(("auto_z", int(params["T"]),
                                float(params["HOTEND"])))
        elif command == "C5_TOOL_PURGE":
            self.feed(float(params["LENGTH"]))
        elif command == "C5_COOL_FOR_DOCK":
            self.events.append(("cool", heater, float(params["HOTEND"])))
        elif command == "AFC_UNSELECT_TOOL":
            self.events.append(("dock", heater))
            self.printer["creator5_toolchanger"]["active_tool"] = None
        elif command == "SAVE_GCODE_STATE":
            self.saved_states[params["NAME"]] = copy.deepcopy(self.gcode_state)
        elif command == "RESTORE_GCODE_STATE":
            if params.get("MOVE", "0") != "0":
                self.events.append(("move", line))
            self.gcode_state = copy.deepcopy(self.saved_states[params["NAME"]])
        elif command == "M83":
            self.gcode_state["absolute_extrude"] = False
        elif command == "G1":
            if any(arg[0] in "XYZ" for arg in args):
                self.events.append(("move", line))
            for arg in args:
                if arg.startswith("E"):
                    length = float(arg[1:])
                    if self.gcode_state["absolute_extrude"]:
                        length -= self.gcode_state["position"][3]
                    self.feed(length)
                    self.gcode_state["position"][3] += length
        else:
            raise AssertionError("Unmodeled external command: " + line)

    def feed(self, length):
        heater = self.printer["toolhead"]["extruder"]
        status = self.printer[heater]
        self.events.append(("feed", heater, length, status["temperature"],
                            status["target"]))


class FilamentLoadMacroTests(unittest.TestCase):
    def assert_heated_feed(self, runner, heater, target, length=20):
        feeds = [event for event in runner.events if event[0] == "feed"]
        self.assertEqual(len(feeds), 1, runner.events)
        feed = feeds[0]
        self.assertEqual((feed[1], feed[2], feed[4]),
                         (heater, length, target), runner.events)
        self.assertGreaterEqual(feed[3], target - 2, runner.events)
        heat = ("heat", heater, target)
        wait = ("wait", heater, target - 2)
        self.assertIn(heat, runner.events)
        self.assertIn(wait, runner.events)
        self.assertLess(runner.events.index(heat), runner.events.index(wait))
        self.assertLess(runner.events.index(wait), runner.events.index(feed))

    def test_cold_bare_load_heats_even_when_can_extrude_is_true(self):
        runner = FilamentMacroRunner(can_extrude=True)
        runner.run(LENGTH=20)
        self.assert_heated_feed(runner, "extruder1", 220)
        self.assertNotIn("select", [event[0] for event in runner.events])
        self.assertIn(("auto_z", 1, 220), runner.events)
        self.assertIn(("cool", "extruder1", 220), runner.events)
        self.assertEqual(runner.events[-2:],
                         [("heat", "extruder1", 0), ("dock", "extruder1")])

    def test_cold_bare_load_waits_before_rendering_feed_readiness(self):
        runner = FilamentMacroRunner(can_extrude=False)
        runner.run(LENGTH=20)
        self.assert_heated_feed(runner, "extruder1", 220)

    def test_bare_load_rejects_stale_logical_tool_before_side_effects(self):
        runner = FilamentMacroRunner(attached=1, active="extruder")
        with self.assertRaises(RaisedError):
            runner.run(LENGTH=20)
        self.assertEqual(runner.events, [])

    def test_bare_load_rejects_missing_or_invalid_mount_before_side_effects(self):
        for attached, error in ((None, None), (1, "invalid mount sensors")):
            with self.subTest(attached=attached, sensor_error=error):
                runner = FilamentMacroRunner(attached=attached,
                                             sensor_error=error)
                with self.assertRaises(RaisedError):
                    runner.run(LENGTH=20)
                self.assertEqual(runner.events, [])

    def test_bare_explicit_temp_overrides_existing_target(self):
        runner = FilamentMacroRunner(target=255)
        runner.run(TEMP=235, LENGTH=20)
        self.assert_heated_feed(runner, "extruder1", 235)
        self.assertIn(("cool", "extruder1", 235), runner.events)

    def test_bare_load_reuses_valid_target(self):
        for target in (150, 255, 300):
            with self.subTest(target=target):
                runner = FilamentMacroRunner(target=target)
                runner.run(LENGTH=20)
                self.assert_heated_feed(runner, "extruder1", target)

    def test_bare_load_falls_back_to_220_for_unusable_target(self):
        for target in (149, 301):
            with self.subTest(target=target):
                runner = FilamentMacroRunner(target=target)
                runner.run(LENGTH=20)
                self.assert_heated_feed(runner, "extruder1", 220)

    def test_invalid_explicit_temp_rejected_before_any_side_effect(self):
        for selection, temp in (({}, 149), ({}, 301), ({}, "nan"),
                                ({}, "invalid"), ({"TOOL": 1}, "nan"),
                                ({"TOOLS": "1,2"}, "inf"),
                                ({"TOOLS": "1,2"}, "-inf")):
            with self.subTest(selection=selection, temp=temp):
                runner = FilamentMacroRunner(target=255)
                with self.assertRaises(RaisedError):
                    runner.run(TEMP=temp, LENGTH=20, **selection)
                self.assertEqual(runner.events, [])

    def test_paused_bare_load_heats_and_feeds_in_place_preserving_state(self):
        runner = FilamentMacroRunner(paused=True, can_extrude=False)
        before = copy.deepcopy(runner.gcode_state)
        pause_state = copy.deepcopy(runner.saved_states["PAUSE_STATE"])
        runner.run(TEMP=240, LENGTH=20)
        self.assert_heated_feed(runner, "extruder1", 240)
        self.assertFalse({"select", "move", "auto_z", "cool", "dock"} &
                         {event[0] for event in runner.events}, runner.events)
        self.assertEqual(runner.gcode_state, before)
        self.assertEqual(runner.saved_states["PAUSE_STATE"], pause_state)
        self.assertEqual(runner.printer["creator5_toolchanger"]["active_tool"], 1)
        self.assertTrue(runner.printer["pause_resume"]["is_paused"])

    def test_explicit_tools_load_mounted_first_then_unique_requested_order(self):
        runner = FilamentMacroRunner(attached=2, active="extruder2",
                                     can_extrude=False)
        runner.run(TOOLS="1,2,0,1", TEMP=230, TEMP2=255, TEMP0=215, LENGTH=20)
        self.assertEqual([event for event in runner.events
                          if event[0] == "select"],
                         [("select", "extruder2"), ("select", "extruder1"),
                          ("select", "extruder")])
        feeds = [event for event in runner.events if event[0] == "feed"]
        self.assertEqual([(event[1], event[2], event[4]) for event in feeds],
                         [("extruder2", 20, 255), ("extruder1", 20, 230),
                          ("extruder", 20, 215)])
        previous_dock = -1
        for feed, target in zip(feeds, (255, 230, 215)):
            heater = feed[1]
            heat = runner.events.index(("heat", heater, target))
            wait = runner.events.index(("wait", heater, target - 2))
            feed_index = runner.events.index(feed)
            cool = runner.events.index(("cool", heater, target))
            off = runner.events.index(("heat", heater, 0))
            dock = runner.events.index(("dock", heater))
            self.assertLess(previous_dock, heat)
            self.assertLess(heat, wait)
            self.assertLess(wait, feed_index)
            self.assertGreaterEqual(feed[3], target - 2)
            self.assertLess(feed_index, cool)
            self.assertLess(cool, off)
            self.assertLess(off, dock)
            previous_dock = dock

    def test_explicit_per_tool_invalid_temp_is_validated_before_first_tool(self):
        runner = FilamentMacroRunner()
        with self.assertRaises(RaisedError):
            runner.run(TOOLS="1,2", TEMP1=230, TEMP2="nan", LENGTH=20)
        self.assertEqual(runner.events, [])


if __name__ == "__main__":
    unittest.main()
