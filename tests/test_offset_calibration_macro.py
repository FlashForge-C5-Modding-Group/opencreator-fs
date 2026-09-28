import pathlib
import textwrap
import unittest

import jinja2


CONFIG = (pathlib.Path(__file__).resolve().parents[1] / 'fs' / 'usr' /
          'data' / 'config' / 'printer.creator5.cfg')


def render_calibration(params):
    text = CONFIG.read_text(encoding='utf-8')
    section = text.split('[gcode_macro C5_CALIBRATE_OFFSETS]\n', 1)[1]
    section = section.split('\n[', 1)[0]
    template = jinja2.Environment('{%', '%}', '{', '}').from_string(
        textwrap.dedent(section.split('\ngcode:\n', 1)[1]))

    def fail(message):
        raise ValueError(message)

    printer = {
        'configfile': {'settings': {'creator5_toolchanger': {}}},
        'toolhead': {'homed_axes': 'xyz'},
    }
    return template.render(printer=printer, params=params,
                           action_raise_error=fail)


class OffsetCalibrationMacroTests(unittest.TestCase):
    def test_single_can_skip_reference_without_skipping_plate_confirmation(self):
        output = render_calibration({
            'TOOL': '2', 'Z': '1', 'SAVE': '0', 'LEVELBOARD': '0',
            'BUILDPLATE_REMOVED': '1'})
        self.assertIn('C5_TOOL_OFFSET_CALIBRATE T=2 Z=1 SAVE=0 '
                      'LEVELBOARD=0', output)

    def test_all_cannot_skip_levelboard_reference(self):
        with self.assertRaisesRegex(ValueError, 'always calibrates'):
            render_calibration({'TOOL': 'ALL', 'LEVELBOARD': '0',
                                'BUILDPLATE_REMOVED': '1'})

    def test_single_requires_plate_confirmation_even_without_reference(self):
        with self.assertRaisesRegex(ValueError, 'Remove the build plate'):
            render_calibration({'TOOL': '2', 'LEVELBOARD': '0'})


if __name__ == '__main__':
    unittest.main()
