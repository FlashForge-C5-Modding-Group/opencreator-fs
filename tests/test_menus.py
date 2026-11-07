import pathlib
import re
import textwrap
import unittest

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[1] / "fs" / "usr" / "data"
CONFIG = ROOT / "config"
MENUS = CONFIG / "printer.macro.cfg"
SCREENS = (CONFIG / "grumpyscreen.cfg", ROOT / "grumpyscreen" / "grumpyscreen.cfg")
# Commands that come from Python modules rather than gcode_macro sections, and
# OC_PLUGINS, which oc-plugin sync writes into config/plugins/ on the printer.
NATIVE = {"DOCK_EXISTING_TOOL", "C5_BED_SOAK", "OC_PLUGINS"}


def all_macros():
    names = set()
    for cfg in CONFIG.rglob("*.cfg"):
        names.update(re.findall(r"(?m)^\[gcode_macro ([^\]]+)\]", cfg.read_text(encoding="utf-8")))
    return names


def macro(name):
    text = MENUS.read_text(encoding="utf-8")
    gcode = text.split("[gcode_macro %s]\n" % name, 1)[1].split("\n[", 1)[0].split("gcode:\n", 1)[1]
    return jinja2.Environment("{%", "%}", "{", "}").from_string(textwrap.dedent(gcode))


class Raised(Exception):
    pass


def raise_error(msg):
    raise Raised(msg)


def printer(pins=None, state="standby", homed="xyz", saved=None):
    p = {"print_stats": {"state": state}, "toolhead": {"homed_axes": homed},
         "save_variables": {"variables": saved or {}}}
    for pin, value in (pins or {}).items():
        p["output_pin " + pin] = {"value": value}
    return p


def run(name, p, **params):
    out = macro(name).render(params=params, printer=p, action_raise_error=raise_error)
    return [l.strip() for l in out.splitlines() if l.strip() and not l.strip().startswith("#")]


class MenusTest(unittest.TestCase):
    def test_macro_file_is_included(self):
        main = (CONFIG / "printer.cfg").read_text(encoding="utf-8")
        self.assertIn("[include printer.macro.cfg]", main)

    def test_every_screen_button_has_a_macro(self):
        known = all_macros() | NATIVE
        for screen in SCREENS:
            buttons = re.findall(r'(?m)^\[macro "([^"]+)"\]', screen.read_text(encoding="utf-8"))
            self.assertTrue(buttons, screen)
            for name in buttons:
                self.assertIn(name, known, "%s: %s" % (screen, name))

    def test_screens_list_the_same_buttons(self):
        lists = [re.findall(r'(?m)^\[macro "([^"]+)"\]', s.read_text(encoding="utf-8")) for s in SCREENS]
        self.assertEqual(lists[0], lists[1])

    def test_every_prompt_button_runs_a_known_command(self):
        known = all_macros() | NATIVE
        text = MENUS.read_text(encoding="utf-8")
        for target in re.findall(r"prompt_(?:footer_)?button [^|]+\|([A-Z0-9_]+)", text):
            self.assertIn(target, known, target)
        for cmd in re.findall(r"_MENU_RUN CMD=([A-Z0-9_]+)", text):
            self.assertIn(cmd, known, cmd)
        for menu in re.findall(r"MENU=([A-Z0-9_]+)", text):
            self.assertIn(menu, known, menu)

    def test_tool_menus_offer_homing(self):
        for name, axes in (("LOAD_MENU", "z"), ("CAL_DOCK_MENU", "z"), ("TOOL_OFFSETS_MENU", "xy")):
            lines = run(name, printer(homed=axes))
            self.assertEqual(len(lines), 1, name)
            self.assertTrue(lines[0].startswith("_MENU_NEED_HOME MENU=%s" % name), lines)
        self.assertEqual(run("LOAD_MENU", printer(homed=""), TEMP="250"), ["_MENU_NEED_HOME MENU=LOAD_MENU TEMP=250"])
        for name in ("LOAD_MENU", "CAL_DOCK_MENU"):
            self.assertIn('RESPOND TYPE=command MSG="action:prompt_show"', run(name, printer()))
        self.assertEqual(run("TOOL_OFFSETS_MENU", printer()), ["C5_CALIBRATE_OFFSETS"])

    def test_home_prompt_reopens_the_menu(self):
        prompt = run("_MENU_NEED_HOME", printer(), MENU="LOAD_MENU", TEMP="250")
        self.assertIn('RESPOND TYPE=command MSG="action:prompt_footer_button Home|'
                      '_MENU_HOME_THEN MENU=LOAD_MENU TEMP=250|primary"', prompt)
        self.assertEqual(run("_MENU_HOME_THEN", printer(), MENU="CAL_DOCK_MENU")[1:], ["G28", "CAL_DOCK_MENU"])
        self.assertEqual(run("_MENU_HOME_THEN", printer(), MENU="LOAD_MENU", TEMP="250")[-1], "LOAD_MENU TEMP=250")

    def test_load_menu_passes_temperature(self):
        lines = run("LOAD_MENU", printer(), TEMP="250")
        self.assertIn('RESPOND TYPE=command MSG="action:prompt_button T2|_LOAD_PICK T=2 TEMP=250|primary"', lines)
        self.assertIn("C5_LOAD_FILAMENT TOOL=3 TEMP=220", run("_LOAD_PICK", printer(), T="3"))

    def test_calibration_menus_refuse_while_printing(self):
        for name in ("SHAPER_MENU", "SHAPER_GRAPH_MENU", "VFA_MENU", "LEVEL_SAVE_MENU",
                     "TOOL_OFFSETS_MENU"):
            with self.assertRaises(Raised):
                run(name, printer(state="printing"))
            if name != "TOOL_OFFSETS_MENU":
                self.assertIn('RESPOND TYPE=command MSG="action:prompt_show"', run(name, printer()), name)


if __name__ == "__main__":
    unittest.main()
