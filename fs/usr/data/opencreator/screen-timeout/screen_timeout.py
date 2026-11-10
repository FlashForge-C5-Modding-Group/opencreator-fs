#!/usr/bin/env python3
"""Turns the touchscreen's backlight off after a while without a touch, and on
again at the next touch. That waking touch is kept from the screen app, so it
doesn't press anything. Runs beside GrumpyScreen (or any screen app) and
doesn't change it. Settings: screen-timeout.conf in the config folder.

Exit status 3: nothing to do here (already running, or no backlight), so the
startup script stops restarting it."""
import fcntl
import glob
import os
import select
import signal
import sys
import time

CONFIG_DIR = '/usr/data/opencreator/klipper/config'
CONFIG_NAME = 'screen-timeout.conf'
PID_FILE = '/tmp/screen-timeout.pid'
LOG_FILE = '/tmp/screen-timeout.log'
LOG_MAX = 100000
DEFAULT_TIMEOUT = 300
# Programs that use the screen without its touch input (games played with a
# gamepad): the screen stays on while they run
FULLSCREEN_APPS = ('RSDKv5U', 'c5doom')
POLL_S = 5.0          # how often settings, inputs and apps are looked at again
RESCAN_S = 10.0       # how often new keyboards and gamepads are looked for
NOTHING_TO_DO = 3

DEFAULT_CONFIG = """\
# Touchscreen backlight timeout, read by screen-timeout (beside the screen app).
# Seconds without a touch before the backlight turns off; 0 keeps it on.
# The next touch turns it on again (and doesn't press anything).
# Changes are picked up within a few seconds.
timeout: %d
""" % DEFAULT_TIMEOUT


def log(msg):
    try:
        if os.path.getsize(LOG_FILE) > LOG_MAX:
            os.replace(LOG_FILE, LOG_FILE + '.old')
    except OSError:
        pass
    try:
        with open(LOG_FILE, 'a') as f:
            f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except OSError:
        pass


def eviocgrab():
    # _IOW('E', 0x90, int). The direction bits differ: MIPS (the printer)
    # has 3 of them at bit 29, write = 4; most others 2 at bit 30, write = 1
    write = (4 << 29) if os.uname().machine.startswith('mips') else (1 << 30)
    return write | (4 << 16) | (ord('E') << 8) | 0x90


def config_path():
    if os.path.isdir(CONFIG_DIR):
        return os.path.join(CONFIG_DIR, CONFIG_NAME)
    # A tunneled SoC has no config folder: next to this script instead
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_NAME)


def read_timeout(path):
    """Seconds, from `timeout: N` or `timeout=N`; 0 means never. A missing
    or unreadable file gives the default."""
    try:
        with open(path) as f:
            for line in f:
                line = line.split('#', 1)[0].strip()
                for sep in (':', '='):
                    key, found, value = line.partition(sep)
                    if found and key.strip().lower() == 'timeout':
                        try:
                            return max(0, int(float(value.strip())))
                        except ValueError:
                            return DEFAULT_TIMEOUT
    except OSError:
        pass
    return DEFAULT_TIMEOUT


def input_devices():
    """(name, handler event nodes) for each input device."""
    devices, name = [], ''
    try:
        with open('/proc/bus/input/devices') as f:
            for line in f:
                if line.startswith('N: Name='):
                    name = line.split('=', 1)[1].strip().strip('"').lower()
                elif line.startswith('H: Handlers='):
                    nodes = ['/dev/input/' + h for h in line.split('=', 1)[1].split()
                             if h.startswith('event')]
                    devices.append((name, nodes))
    except OSError:
        pass
    return devices


def is_touch(name):
    return 'goodix' in name or 'touch' in name


def find_touch():
    for name, nodes in input_devices():
        if is_touch(name) and nodes:
            return nodes[0]
    return '/dev/input/event2' if os.path.exists('/dev/input/event2') else None


def other_inputs():
    """Keyboards and gamepads: activity on them keeps the screen on."""
    return [nodes[0] for name, nodes in input_devices()
            if nodes and not is_touch(name)]


def find_backlight():
    for path in sorted(glob.glob('/sys/class/backlight/*/brightness')):
        try:
            with open(os.path.join(os.path.dirname(path), 'max_brightness')) as f:
                on = int(f.read().strip() or 1)
        except (OSError, ValueError):
            on = 1
        return path, max(on, 1)
    return None, 1


def fullscreen_app_running():
    for cmdline in glob.glob('/proc/[0-9]*/cmdline'):
        try:
            with open(cmdline, 'rb') as f:
                args = f.read().split(b'\0')
        except OSError:
            continue
        if args and os.path.basename(args[0].decode('utf-8', 'replace')) in FULLSCREEN_APPS:
            return True
    return False


def other_instance():
    """The PID in the PID file, if it's another screen_timeout still running
    (a PID reused by something else doesn't count)."""
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            return None
        with open('/proc/%d/cmdline' % pid, 'rb') as f:
            if b'screen_timeout' in f.read():
                return pid
    except (OSError, ValueError):
        pass
    return None


class Screen:
    def __init__(self, backlight, on_value):
        self.backlight, self.on_value = backlight, on_value
        self.lit = None

    def set(self, lit):
        if lit == self.lit:
            return
        try:
            with open(self.backlight, 'w') as f:
                f.write('%d\n' % (self.on_value if lit else 0))
            self.lit = lit
        except OSError as e:
            log('backlight write failed: %s' % e)


def drain(fd):
    """Read what's waiting; False when the device is gone."""
    try:
        return bool(os.read(fd, 4096))
    except BlockingIOError:
        return True
    except OSError:
        return False


def run():
    other = other_instance()
    if other:
        log('already running as %d' % other)
        return NOTHING_TO_DO
    backlight, on_value = find_backlight()
    if not backlight:
        log('no backlight found under /sys/class/backlight')
        return NOTHING_TO_DO

    cfg = config_path()
    if not os.path.exists(cfg) and os.path.isdir(os.path.dirname(cfg)):
        try:
            with open(cfg, 'w') as f:
                f.write(DEFAULT_CONFIG)
        except OSError:
            pass

    touch_path = find_touch()
    while not touch_path or not os.path.exists(touch_path):
        time.sleep(2)
        touch_path = find_touch()
    touch = None
    while touch is None:
        try:
            touch = os.open(touch_path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            time.sleep(2)

    with open(PID_FILE, 'w') as f:
        f.write('%d\n' % os.getpid())

    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    grab = eviocgrab()
    screen = Screen(backlight, on_value)
    screen.set(True)
    grabbed = False
    others = {}          # path -> fd
    next_rescan = 0.
    timeout, cfg_mtime = DEFAULT_TIMEOUT, None
    last_activity = time.monotonic()
    log('started: touch %s, backlight %s, %s' % (touch_path, backlight, cfg))

    try:
        while True:
            now = time.monotonic()
            # Settings, picked up when the file changes
            try:
                mtime = os.path.getmtime(cfg)
            except OSError:
                mtime = None
            if mtime != cfg_mtime:
                cfg_mtime = mtime
                new = read_timeout(cfg)
                if new != timeout or mtime is None:
                    log('timeout %s' % ('off' if new == 0 else '%d s' % new))
                timeout = new
                last_activity = now
            # Keyboards and gamepads, plugged in or out
            if now >= next_rescan:
                next_rescan = now + RESCAN_S
                wanted = set(other_inputs())
                for path in list(others):
                    if path not in wanted:
                        os.close(others.pop(path))
                for path in wanted - set(others):
                    try:
                        others[path] = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                    except OSError:
                        pass
            app = fullscreen_app_running()
            if app:
                last_activity = now
            if not screen.lit and (app or not timeout):
                # A game started, or the timeout was turned off, while dark
                if grabbed:
                    try:
                        fcntl.ioctl(touch, grab, 0)
                    except OSError:
                        pass
                    grabbed = False
                screen.set(True)
                log('backlight on (%s)' % ('app' if app else 'timeout off'))

            asleep = not screen.lit
            if timeout and not asleep and now - last_activity >= timeout:
                screen.set(False)
                try:
                    fcntl.ioctl(touch, grab, 1)
                    grabbed = True
                except OSError as e:
                    log('grab failed: %s' % e)
                log('backlight off')
                asleep = True

            wait = POLL_S
            if timeout and not asleep:
                wait = min(wait, max(0.05, timeout - (now - last_activity)))
            fds = [touch] + list(others.values())
            ready, _, _ = select.select(fds, [], [], wait)
            if not ready:
                continue
            now = time.monotonic()
            for fd in ready:
                if fd == touch:
                    if not drain(touch):
                        log('touch device gone')
                        return 1
                else:
                    if not drain(fd):
                        for path, other_fd in list(others.items()):
                            if other_fd == fd:
                                os.close(others.pop(path))
                        continue
                last_activity = now
                if not screen.lit:
                    if grabbed:
                        try:
                            fcntl.ioctl(touch, grab, 0)
                        except OSError:
                            pass
                        grabbed = False
                    screen.set(True)
                    log('backlight on (%s)' % ('touch' if fd == touch else 'input'))
    finally:
        # Never leave the screen dark or its touch input held
        if grabbed:
            try:
                fcntl.ioctl(touch, grab, 0)
            except OSError:
                pass
        screen.set(True)
        try:
            if other_instance() is None:
                os.remove(PID_FILE)
        except OSError:
            pass


if __name__ == '__main__':
    sys.exit(run())
