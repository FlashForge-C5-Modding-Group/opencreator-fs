import pathlib
import textwrap
import unittest

import jinja2

CONFIG = pathlib.Path(__file__).resolve().parents[1] / "fs" / "usr" / "data" / "config" / "printer.afc-standalone.cfg"


def render(macro, state="idle", homed="xyz", **params):
    text = CONFIG.read_text(encoding="utf-8")
    gcode = text.split("[gcode_macro %s]\n" % macro, 1)[1].split("\n[", 1)[0].split("gcode:\n", 1)[1]
    # comments between sections belong to the next macro
    gcode = "\n".join(l for l in gcode.splitlines() if not l.startswith("#"))
    template = jinja2.Environment("{%", "%}", "{", "}").from_string(textwrap.dedent(gcode))
    printer = {"print_stats": {"state": state}, "toolhead": {"homed_axes": homed}}
    out = template.render(params=params, printer=printer, rawparams=" ".join("%s=%s" % kv for kv in params.items()))
    return [l.strip() for l in out.splitlines() if l.strip()]


class ToolLoadTest(unittest.TestCase):
    def test_idle_loads_with_c5(self):
        self.assertEqual(render("TOOL_LOAD", LANE="extruder1"), ["_C5_REQUIRE_HOMED", "C5_LOAD_FILAMENT TOOL=1"])

    def test_print_or_pause_stays_afc(self):
        for state in ("printing", "paused"):
            self.assertEqual(render("TOOL_LOAD", state=state, LANE="extruder1"), ["_AFC_TOOL_LOAD LANE=extruder1"])

    def test_bad_lane_stays_afc(self):
        self.assertEqual(render("TOOL_LOAD", LANE="foo"), ["_AFC_TOOL_LOAD LANE=foo"])
        self.assertEqual(render("TOOL_LOAD"), ["_AFC_TOOL_LOAD"])


class ChangeToolTest(unittest.TestCase):
    def test_idle_loads_with_c5(self):
        lines = render("CHANGE_TOOL", LANE="extruder2", NEW_EXTRUDER_TEMP="255", PURGE_LENGTH="20")
        self.assertEqual(lines, ["_C5_REQUIRE_HOMED", "C5_LOAD_FILAMENT TOOL=2 TEMP=255 LENGTH=20"])

    def test_print_stays_afc(self):
        self.assertEqual(render("CHANGE_TOOL", state="printing", LANE="extruder2"), ["_AFC_CHANGE_TOOL LANE=extruder2"])


class RequireHomedTest(unittest.TestCase):
    def test_homed_does_nothing(self):
        self.assertEqual(render("_C5_REQUIRE_HOMED", homed="xyz"), [])

    def test_unhomed_prompts_then_aborts(self):
        for homed in ("", "x", "y", "z"):
            self.assertEqual(render("_C5_REQUIRE_HOMED", homed=homed), ["_C5_HOME_PROMPT", "_C5_HOME_ABORT"])

    def test_prompt_buttons(self):
        text = "\n".join(render("_C5_HOME_PROMPT"))
        self.assertIn("prompt_begin Home required", text)
        self.assertIn("Home now|_C5_HOME_GO", text)
        self.assertIn("prompt_show", text)

    def test_home_go(self):
        self.assertEqual(render("_C5_HOME_GO")[-1], "G28")


if __name__ == "__main__":
    unittest.main()
