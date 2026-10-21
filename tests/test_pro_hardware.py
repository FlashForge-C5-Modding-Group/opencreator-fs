import pathlib
import re
import textwrap
import unittest

import jinja2

CONFIG = pathlib.Path(__file__).resolve().parents[1] / "fs" / "usr" / "data" / "config"
PRO_ONLY = ("heater_generic chamber_heater", "verify_heater chamber_heater", "fan_generic chamber_fan",
            "heater_fan_throttled chamber_heat_fan", "fan_generic chamber_loop_fan", "fan_generic chamber_cool_fan")


def sections(name):
    return re.findall(r"(?m)^\[([^\]]+)\]", (CONFIG / name).read_text(encoding="utf-8"))


def macro(name):
    text = (CONFIG / "printer.macro.cfg").read_text(encoding="utf-8")
    gcode = text.split("[gcode_macro %s]\n" % name, 1)[1].split("\n[", 1)[0].split("gcode:\n", 1)[1]
    return jinja2.Environment("{%", "%}", "{", "}").from_string(textwrap.dedent(gcode))


def printer(pro):
    p = {"output_pin chamber_wait": {"value": 1.}}
    if pro:
        p.update({"heater_generic chamber_heater": {"target": 0.}, "fan_generic chamber_fan": {},
                  "fan_generic chamber_loop_fan": {}, "fan_generic chamber_cool_fan": {}})
    return p


def run(name, pro, **params):
    lines = []
    out = macro(name).render(params=params, printer=printer(pro),
                             action_respond_info=lambda msg: lines.append("INFO " + msg) or "")
    return [l.strip() for l in out.splitlines() if l.strip() and not l.strip().startswith("#")] + lines


class ProHardwareTest(unittest.TestCase):
    def test_pro_hardware_only_in_pro_file(self):
        base, pro = sections("printer.base.cfg"), sections("printer.pro.cfg")
        for s in PRO_ONLY:
            self.assertNotIn(s, base)
            self.assertIn(s, pro)
        self.assertIn("include printer.model*.cfg", base)

    def test_fans_skip_missing_hardware_on_creator5(self):
        for macro_name, params in (("M106", {"P": "2", "S": "255"}), ("M106", {"P": "3"}),
                                   ("M107", {"P": "2"}), ("M107", {"P": "3"})):
            self.assertEqual(run(macro_name, False, **params), [], (macro_name, params))

    def test_fans_still_work_on_pro(self):
        self.assertEqual(run("M106", True, P="3", S="255"), ["SET_FAN_SPEED FAN=chamber_fan SPEED=1.0"])
        self.assertIn("SET_FAN_SPEED FAN=chamber_loop_fan SPEED=0.0", run("M107", True, P="2"))
        self.assertEqual(run("M106", False, S="255"), ["SET_FAN_SPEED FAN=fanM106 SPEED=1.0"])

    def test_m191(self):
        self.assertEqual(run("M191", False, S="50"), ["INFO No chamber heater on a Creator 5; M191 ignored"])
        self.assertEqual(run("M191", False, S="0"), [])
        self.assertEqual(run("M191", True, S="50")[0], "SET_HEATER_TEMPERATURE HEATER=chamber_heater TARGET=50")


if __name__ == "__main__":
    unittest.main()
