import pathlib
import textwrap
import unittest

import jinja2


CONFIG = (pathlib.Path(__file__).resolve().parents[1] / "fs" / "usr" /
          "data" / "config" / "printer.creator5.cfg")
FILAMENT_CONFIG = CONFIG.with_name("printer.filament.cfg")


def print_start_template():
    text = CONFIG.read_text(encoding="utf-8")
    section = text.split("[gcode_macro C5_PRINT_START]\n", 1)[1]
    section = section.split("\n[", 1)[0]
    gcode = section.split("\ngcode:\n", 1)[1]
    return jinja2.Environment("{%", "%}", "{", "}").from_string(
        textwrap.dedent(gcode))


def render_start(tool, tools, present, absent_sensors=()):
    printer = {
        "save_variables": {"variables": {"c5_bed_leveling": 1}},
        "filament_switch_sensor flow_calibration": {"enabled": False},
        "filament_switch_sensor purge": {"enabled": False},
    }
    for index in range(4):
        extruder = "extruder" if index == 0 else "extruder%d" % index
        if index not in absent_sensors:
            printer["filament_switch_sensor %s_tool_start" % extruder] = {
                "filament_detected": index in present}
    messages = []
    def raise_error(message):
        raise ValueError(message)
    output = print_start_template().render({
        "printer": printer,
        "params": {"TOOL": str(tool), "TOOLS": tools, "HOTEND": "220",
                   "FLOW_CALIBRATION": "0", "PURGE": "0"},
        "action_raise_error": raise_error,
        "action_respond_info": lambda message: messages.append(message) or "",
    })
    return output, messages


class PrintStartFilamentTests(unittest.TestCase):
    def test_wheel_failure_routes_to_clog_handler_without_preemptive_pause(self):
        text = FILAMENT_CONFIG.read_text(encoding="utf-8")
        self.assertIn("clog_detection_default: False",
                      CONFIG.read_text(encoding="utf-8"))
        for tool in range(4):
            section = text.split(
                "[filament_motion_sensor fm_ex%d]\n" % tool, 1)[1]
            section = section.split("\n[", 1)[0]
            self.assertIn("pause_on_runout: False", section)
            self.assertIn("C5_WHEEL_CLOG TOOL=%d" % tool, section)

    def test_missing_selected_tool_cancels_before_motion_and_heat(self):
        output, messages = render_start(3, "3", set())
        self.assertIn("CANCEL_PRINT", output)
        self.assertNotIn("C5_HOME_FOR_PRINT", output)
        self.assertNotIn("SET_HEATER_TEMPERATURE", output)
        self.assertIn("T3", messages[0])

    def test_unused_empty_tools_do_not_block_print(self):
        output, messages = render_start(3, "3", {3})
        self.assertIn("C5_HOME_FOR_PRINT", output)
        self.assertNotIn("CANCEL_PRINT", output)
        self.assertEqual(messages, [])
        self.assertLess(output.index("RESET_AFC_MAPPING RUNOUT=no"),
                        output.index("AFC_SELECT_TOOL TOOL=extruder3"))

    def test_cancel_does_not_change_afc_mapping(self):
        output, _ = render_start(3, "3", set())
        self.assertNotIn("RESET_AFC_MAPPING", output)

    def test_all_selected_tools_must_have_filament(self):
        output, messages = render_start(3, "0,3", {3})
        self.assertIn("CANCEL_PRINT", output)
        self.assertIn("T0", messages[0])
        self.assertNotIn("T3", messages[0])

    def test_missing_sensor_fails_closed(self):
        output, messages = render_start(3, "3", {3}, absent_sensors={3})
        self.assertIn("CANCEL_PRINT", output)
        self.assertNotIn("C5_HOME_FOR_PRINT", output)
        self.assertIn("T3", messages[0])


if __name__ == "__main__":
    unittest.main()
