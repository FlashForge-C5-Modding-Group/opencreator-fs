# Creator 5 screen timeout

The touchscreen's backlight turns off after a while without a touch, and on
again at the next touch. That waking touch doesn't press anything on the
screen. It runs as its own service beside the screen app (GrumpyScreen, or
HelixScreen) and doesn't change it.

## Settings

`screen-timeout.conf` in the config folder, editable from Fluidd or Mainsail.
It's written with the default the first time the service starts:

```
timeout: 300
```

Seconds without a touch before the backlight turns off; `0` keeps it on.
Changes are picked up within a few seconds, with nothing to restart. A
tunneled SoC has no config folder and keeps the file next to the daemon,
`/usr/data/opencreator/screen-timeout/screen-timeout.conf`.

## What keeps the screen on

- A touch.
- A keyboard or gamepad on the printer's USB: any key, button or stick.
- A full-screen app that doesn't use touch running: Sonic Mania (`RSDKv5U`) or
  DOOM (`c5doom`). Starting one also turns a dark screen back on.

Web and Wi-Fi activity (Fluidd, Mainsail) don't count: they don't use the
screen.

## How it works

`startup/scripts/45-screen-timeout.sh` starts
`screen-timeout/screen_timeout.py` with the first Python it finds (python-hf,
then Klippy's) and restarts it 5 seconds after it stops. When the daemon has
nothing to do (another copy is running, or there's no backlight), it exits with
status 3 and the script stops too.

The daemon:

- finds the backlight under `/sys/class/backlight/*/brightness` (on the C5 a
  plain on/off, `max_brightness` 1);
- finds the touchscreen in `/proc/bus/input/devices` (`goodix` or `touch` in
  its name, else `/dev/input/event2`), and the other input devices;
- waits for input with `select()`, waking every few seconds to pick up setting
  changes, new USB devices and full-screen apps;
- after `timeout` seconds without activity, turns the backlight off and grabs
  the touchscreen (`EVIOCGRAB`), so it's the only reader;
- at the next touch, reads it, releases the grab and turns the backlight on.
  The screen app never sees that touch.

`EVIOCGRAB`'s code depends on the CPU: `0x80044590` on MIPS (the printer),
`0x40044590` on ARM and x86.

When it stops for any reason (SIGTERM, a lost device, an error), it releases
the grab and turns the backlight on, so it can't leave the screen dark or the
touchscreen held.

Only one copy runs. A copy checks `/tmp/screen-timeout.pid` and leaves if that
PID is another `screen_timeout`; a PID reused by some other process doesn't
count, so a stale file can't stop it from starting.

Log: `/tmp/screen-timeout.log`, rotated at 100 KB to `.old`. The startup
script's own output goes to `/tmp/45-screen-timeout.sh.log`.
