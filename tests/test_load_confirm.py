import ast
import pathlib
import textwrap
import unittest

import jinja2

CONFIG = pathlib.Path(__file__).resolve().parents[1] / "fs" / "usr" / "data" / "config" / "printer.filament.cfg"


def render(macro, printer=None, **params):
    text = CONFIG.read_text(encoding="utf-8")
    gcode = text.split("[gcode_macro %s]\n" % macro, 1)[1].split("\n[", 1)[0].split("gcode:\n", 1)[1]
    gcode = "\n".join(l for l in gcode.splitlines() if not l.startswith("#"))
    env = jinja2.Environment("{%", "%}", "{", "}")
    out = env.from_string(textwrap.dedent(gcode)).render(params=params, printer=printer or {})
    return [l.strip() for l in out.splitlines() if l.strip() and not l.strip().startswith("#")]


def idle(active=None):
    return {"print_stats": {"state": "standby"}, "pause_resume": {"is_paused": False},
            "creator5_toolchanger": {"sensor_error": None, "active_tool": active}}


def queue_value(lines):
    line = next(l for l in lines if "VARIABLE=tools" in l)
    return ast.literal_eval(line.split("VALUE=", 1)[1])


class LoadCheckTest(unittest.TestCase):
    def test_prompt_buttons(self):
        text = "\n".join(render("_C5_LOAD_CHECK", TOOL="2", HOTEND="240", LENGTH="20"))
        self.assertIn("prompt_begin Filament loaded?", text)
        self.assertIn("T2 nozzle", text)
        self.assertIn("|_C5_LOAD_AGAIN TOOL=2 HOTEND=240.0 LENGTH=20.0\"", text)
        self.assertIn("|_C5_LOAD_CONFIRMED TOOL=2 HOTEND=240.0 LENGTH=20.0|primary", text)
        self.assertTrue(text.endswith('prompt_show"'))

    def test_again_reheats_purges_and_asks(self):
        lines = render("_C5_LOAD_AGAIN", TOOL="1", HOTEND="240.0", LENGTH="20.0")
        self.assertEqual(lines[1:], [
            "C5_CHECK_LOAD_TOOL T=1",
            "SET_HEATER_TEMPERATURE HEATER=extruder1 TARGET=240.0",
            "TEMPERATURE_WAIT SENSOR=extruder1 MINIMUM=238.0",
            "C5_TOOL_PURGE LENGTH=20.0",
            "_C5_LOAD_CHECK TOOL=1 HOTEND=240.0 LENGTH=20.0",
        ])

    def test_confirmed_cools_docks_then_next(self):
        lines = render("_C5_LOAD_CONFIRMED", TOOL="0", HOTEND="220.0", LENGTH="20.0")
        self.assertEqual(lines[1:], [
            "C5_COOL_FOR_DOCK HOTEND=220.0",
            "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=0",
            "AFC_UNSELECT_TOOL",
            "_C5_LOAD_NEXT",
        ])


class LoadQueueTest(unittest.TestCase):
    def test_multi_tool_starts_first_and_queues_rest(self):
        lines = render("C5_LOAD_FILAMENT", idle(active=2), TOOLS="0,2,3", TEMP="220", TEMP3="255", LENGTH="20")
        self.assertEqual(queue_value(lines), [[0, 220.0], [3, 255.0]])
        self.assertEqual(lines[-1], "C5_LOAD_SELECTED_TOOL TOOL=2 TEMP=220.0 LENGTH=20.0")

    def test_single_tool_queues_nothing(self):
        lines = render("C5_LOAD_FILAMENT", idle(), TOOL="1")
        self.assertEqual(queue_value(lines), [])
        self.assertEqual(lines[-1], "C5_LOAD_SELECTED_TOOL TOOL=1 TEMP=220.0 LENGTH=80.0")

    def test_next_pops_queue(self):
        printer = {"gcode_macro _C5_LOAD_QUEUE": {"tools": [[0, 220.0], [3, 255.0]], "length": 20.0}}
        lines = render("_C5_LOAD_NEXT", printer)
        self.assertEqual(queue_value(lines), [[3, 255.0]])
        self.assertEqual(lines[-1], "C5_LOAD_SELECTED_TOOL TOOL=0 TEMP=220.0 LENGTH=20.0")

    def test_next_empty_does_nothing(self):
        printer = {"gcode_macro _C5_LOAD_QUEUE": {"tools": [], "length": 20.0}}
        self.assertEqual(render("_C5_LOAD_NEXT", printer), [])

    def test_selected_tool_keeps_queue(self):
        lines = render("C5_LOAD_SELECTED_TOOL", TOOL="3", TEMP="255", LENGTH="20")
        self.assertTrue(lines[-1].endswith("QUEUED=1"))


if __name__ == "__main__":
    unittest.main()
