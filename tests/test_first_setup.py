import pathlib
import re
import textwrap
import unittest

import jinja2

CONFIG = pathlib.Path(__file__).resolve().parents[1] / "fs" / "usr" / "data" / "config" / "printer.misc.cfg"


def render(**params):
    text = CONFIG.read_text(encoding="utf-8")
    gcode = text.split("[gcode_macro _OC_FIRST_SETUP]\n", 1)[1].split("\n[", 1)[0].split("gcode:\n", 1)[1]
    template = jinja2.Environment("{%", "%}", "{", "}").from_string(textwrap.dedent(gcode))
    printer = {"save_variables": {"variables": {"c5_first_setup_step": 0}}}
    out = template.render(params=params, printer=printer)
    return [l.strip() for l in out.splitlines() if l.strip()]


def buttons(lines):
    return re.findall(r"prompt_footer_button ([^|]+)\|([^|\"]+)", "\n".join(lines))


class FirstSetupTest(unittest.TestCase):
    def test_welcome_says_settings_were_imported(self):
        text = " ".join(render(STEP="0"))
        self.assertIn("previous settings have been imported", text)

    def test_pages_and_their_switches(self):
        pages = {1: ("FLOW", "flow_calibration"), 2: ("PURGE", "purge"), 3: ("CLOG", "clog_detection"), 4: ("SOAK", "bed_soak")}
        for step, (param, pin) in pages.items():
            with self.subTest(step=step):
                b = dict(buttons(render(STEP=str(step))))
                self.assertEqual(b["Yes"], "_OC_FIRST_SETUP STEP=%d %s=1" % (step + 1, param))
                self.assertEqual(b["No"], "_OC_FIRST_SETUP STEP=%d %s=0" % (step + 1, param))
                self.assertIn("SET_PIN PIN=%s VALUE=1" % pin, render(STEP=str(step + 1), **{param: "1"}))

    def test_pressure_advance_page(self):
        self.assertIn("action:prompt_begin Pressure Advance Calibration", " ".join(render(STEP="1")))

    def test_offsets_page_leads_to_vfa(self):
        self.assertEqual(dict(buttons(render(STEP="5")))["Next"], "_OC_FIRST_SETUP STEP=6")

    def test_vfa_page_recommends_recalibrating(self):
        lines = render(STEP="6")
        text = " ".join(lines)
        self.assertIn("action:prompt_begin VFA compensation", text)
        self.assertIn("recommend recalibrating VFA", text)
        self.assertEqual(dict(buttons(lines)), {"Next": "_OC_FIRST_SETUP STEP=7"})
        # Only a recommendation: nothing runs and setup isn't finished yet
        self.assertFalse(any("VFA_COMPENSATION" in line and "prompt" not in line for line in lines))
        self.assertNotIn("SAVE_VARIABLE VARIABLE=c5_first_setup_done VALUE=1", lines)

    def test_last_page_thanks_and_finishes(self):
        lines = render(STEP="7")
        self.assertIn("SAVE_VARIABLE VARIABLE=c5_first_setup_done VALUE=1", lines)
        self.assertIn("first version of OpenCreator", " ".join(lines))
        self.assertEqual(dict(buttons(lines))["Finish"], "_OC_FIRST_SETUP STEP=8")
        self.assertIn("action:prompt_end", " ".join(render(STEP="8")))


if __name__ == "__main__":
    unittest.main()
