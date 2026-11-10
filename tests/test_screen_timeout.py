import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest import mock

if os.name == 'nt':
    raise unittest.SkipTest("screen_timeout uses Linux input devices (fcntl)")

PATH = (pathlib.Path(__file__).resolve().parents[1] / "fs" / "usr" / "data"
        / "opencreator" / "screen-timeout" / "screen_timeout.py")
spec = importlib.util.spec_from_file_location("screen_timeout", PATH)
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)

DEVICES = """\
I: Bus=0018 Vendor=0416 Product=1001 Version=0100
N: Name="goodix-ts"
H: Handlers=event2

I: Bus=0019 Vendor=0001 Product=0001 Version=0100
N: Name="md-gpio-keys"
H: Handlers=kbd event1

I: Bus=0003 Vendor=045e Product=028e Version=0110
N: Name="Microsoft X-Box 360 pad"
H: Handlers=event5 js0
"""


class ConfigTest(unittest.TestCase):
    def timeout(self, text):
        with tempfile.NamedTemporaryFile('w', suffix='.conf', delete=False) as f:
            f.write(text)
        self.addCleanup(os.remove, f.name)
        return st.read_timeout(f.name)

    def test_formats(self):
        self.assertEqual(self.timeout("timeout: 120\n"), 120)
        self.assertEqual(self.timeout("timeout=45  # seconds\n"), 45)
        self.assertEqual(self.timeout("# timeout: 9\nTimeout : 60\n"), 60)

    def test_off_negative_and_bad(self):
        self.assertEqual(self.timeout("timeout: 0\n"), 0)
        self.assertEqual(self.timeout("timeout: -5\n"), 0)
        self.assertEqual(self.timeout("timeout: soon\n"), st.DEFAULT_TIMEOUT)
        self.assertEqual(self.timeout("nothing here\n"), st.DEFAULT_TIMEOUT)

    def test_missing_file(self):
        self.assertEqual(st.read_timeout("/nonexistent/screen-timeout.conf"), st.DEFAULT_TIMEOUT)

    def test_default_file_reads_as_default(self):
        self.assertEqual(self.timeout(st.DEFAULT_CONFIG), st.DEFAULT_TIMEOUT)


class GrabCodeTest(unittest.TestCase):
    def test_mips_and_others(self):
        with mock.patch.object(st.os, 'uname', return_value=mock.Mock(machine='mips')):
            self.assertEqual(st.eviocgrab(), 0x80044590)
        with mock.patch.object(st.os, 'uname', return_value=mock.Mock(machine='aarch64')):
            self.assertEqual(st.eviocgrab(), 0x40044590)


class InputsTest(unittest.TestCase):
    def setUp(self):
        real_open = open

        def fake_open(path, *a, **k):
            if path == '/proc/bus/input/devices':
                return mock.mock_open(read_data=DEVICES)()
            return real_open(path, *a, **k)
        patcher = mock.patch('builtins.open', side_effect=fake_open)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_touch_is_the_goodix(self):
        self.assertEqual(st.find_touch(), '/dev/input/event2')

    def test_other_inputs_leave_out_the_touchscreen(self):
        self.assertEqual(st.other_inputs(), ['/dev/input/event1', '/dev/input/event5'])


class InstanceTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.pid_file = os.path.join(d, 'pid')
        patcher = mock.patch.object(st, 'PID_FILE', self.pid_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, pid):
        with open(self.pid_file, 'w') as f:
            f.write('%d\n' % pid)

    def test_no_file_or_own_pid(self):
        self.assertIsNone(st.other_instance())
        self.write(os.getpid())
        self.assertIsNone(st.other_instance())

    def test_reused_pid_is_not_an_instance(self):
        # PID 1 is alive but isn't screen_timeout
        self.write(1)
        self.assertIsNone(st.other_instance())


class LoopTest(unittest.TestCase):
    """The whole cycle with simulated devices: off after the timeout (touch
    grabbed), on at the next touch (released), and on again when it stops."""

    def test_sleep_and_wake(self):
        tmp = tempfile.mkdtemp()
        backlight = os.path.join(tmp, 'brightness')
        open(backlight, 'w').write('1\n')
        cfg = os.path.join(tmp, 'screen-timeout.conf')
        open(cfg, 'w').write('timeout: 1\n')
        touch_r, touch_w = os.pipe()
        os.set_blocking(touch_r, False)
        grabs = []
        events = []

        def fake_select(fds, w, x, wait):
            # sleep through the timeout, then a touch, then stop
            events.append(wait)
            if len(events) == 1:
                fake_now[0] += 2.0
                return [], [], []
            if len(events) == 2:
                self.assertEqual(open(backlight).read().strip(), '0')
                os.write(touch_w, b'x' * 24)
                return [touch_r], [], []
            raise SystemExit(0)

        fake_now = [100.0]
        with mock.patch.multiple(
                st, PID_FILE=os.path.join(tmp, 'pid'), LOG_FILE=os.path.join(tmp, 'log'),
                find_backlight=lambda: (backlight, 1), config_path=lambda: cfg,
                find_touch=lambda: '/dev/input/event2', other_inputs=lambda: [],
                fullscreen_app_running=lambda: False, other_instance=lambda: None), \
                mock.patch.object(st.os, 'open', return_value=touch_r), \
                mock.patch.object(st.os.path, 'exists', return_value=True), \
                mock.patch.object(st.select, 'select', side_effect=fake_select), \
                mock.patch.object(st.fcntl, 'ioctl', side_effect=lambda fd, req, v: grabs.append(v)), \
                mock.patch.object(st.time, 'monotonic', side_effect=lambda: fake_now[0]), \
                mock.patch.object(st.signal, 'signal'):
            with self.assertRaises(SystemExit):
                st.run()
        self.assertEqual(grabs, [1, 0])            # grabbed while dark, released on the touch
        self.assertEqual(open(backlight).read().strip(), '1')
        log = open(os.path.join(tmp, 'log')).read()
        self.assertIn('backlight off', log)
        self.assertIn('backlight on (touch)', log)


if __name__ == '__main__':
    unittest.main()
