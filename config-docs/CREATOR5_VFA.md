# Creator 5 VFA compensation

`VFA_COMPENSATION` is the MCLib calibration button for the custom Klipper
configuration. It mirrors the stock `firmwareExe.i64` VFA path: home, move to
Z100 and X130/Y130, then run `STEPPER_RESONANCE_FACTORY_CALIBRATE`.

Run it only with a clear build area and all toolheads docked. The macro rejects
an active or paused print and an attached toolhead. Calibration measures X and
Y with the configured LIS2DW accelerometer, stages the resulting `td1`, `td2`,
and `td4` amplitude/phase values in the `[mclib stepper_x]` and
`[mclib stepper_y]` sections, then runs `SAVE_CONFIG`. That command writes the
values and restarts Klipper.

`C5_PRINT_START` calls `STEPPER_RESONANCE_DAMP_ENABLE` before print motion.
That macro now invokes `MCLIB_APPLY_CALIBRATION` for X and Y, restoring the
saved MCLib values instead of fixed factory numbers. The Klipper host must be
updated along with these config files because the restore command is new.

`AXIS=X` or `AXIS=Y` (on `VFA_COMPENSATION` and `VFA_COMPENSATION_GRAPH`)
calibrates and graphs only that motor. The other motor's damping isn't touched,
and its saved values stay as they are.

## How it compensates during a print

The host only sends numbers; the cancelling runs in the mainboard firmware
(`kalico/src/c5_mclib.c`).

- At Klipper start, `[mclib stepper_x]` / `[mclib stepper_y]` send their saved
  `td*_amp` / `td*_phase1` / `td*_phase2` to the mainboard
  (`mclib_set_resonance_damp`). At print start, `C5_PRINT_START` runs
  `STEPPER_RESONANCE_DAMP_ENABLE`, which sends them again with
  `MCLIB_APPLY_CALIBRATION`. `C5_PRINT_STOP` (print end) and `CANCEL_PRINT` run
  `STEPPER_RESONANCE_DAMP_DISABLE`, which sets all of them to 0.
- The mainboard runs field-oriented current control for each motor every PWM
  cycle (20 kHz, from the current samples TIMER2/TIMER4 trigger). For X and Y (`nonfast_control`), it subtracts
  `sum(amp_k * sin(k * angle + phase))` for k = 1, 2, 4 from the d-axis
  current reference. Here `angle` is the commanded electrical angle (it
  advances with each step), and `phase` is `phase1` while the motor turns
  forward and `phase2` while it turns backward. So the compensation follows the
  motor's position at any speed, with no per-move work on the host.
- It's added only while the step period is at least 2468 timer ticks. The motor
  timer runs at 100 MHz (TIMER22, prescaler 3), so that's 24.68 µs per step,
  about 510 mm/s of belt travel at 0.012625 mm per step (40.4 mm, 200 steps,
  16 microsteps). Faster than about 560 mm/s (period under
  `crossover_threshold - 100`, 2243 ticks), the motor switches to
  `fast_control`, the observer-based high-speed mode, which has no
  compensation. On CoreXY a pure X or Y move turns both motors at the toolhead
  speed, and a 45 degree move turns one at 1.41 times it. So compensation holds
  up to roughly 360 to 510 mm/s of toolhead speed, depending on direction.

## Finding each motor's resonance

Before calibrating, each motor's resonance frequency is measured rather than
assumed. With compensation off, the toolhead makes test moves across the
`vel_range` speeds, 20 to 300 mm/s, each about 8% faster than the last
(`sweep_spacing`). That keeps the steps fine at low speed, where resonance
peaks are narrow. It then takes finer steps around each of the three
strongest high points, since a narrow peak can fall between two speeds and
look smaller than a wide one. Where the main (2x) ripple peaks gives the
motor's resonances. A peak counts when it's clear (inside the swept speeds and
at least 1.5 times the typical level) and at least half as strong as the
strongest; at most two are kept.

Calibration runs each harmonic at the speed that puts it on the resonance's
frequency. With one resonance, that's it. With two, it calibrates at each,
sweeps the speeds again with each result, and keeps the one that leaves less
vibration overall (`STEPPER_RESONANCE_AUTO_CALIBRATE`). The strongest peak isn't
always the best: the best cancelling setting depends on the speed it's tuned
at. On one C5, X calibrated at its stronger 84 Hz resonance (12 to 48 mm/s)
left 3 to 5 times more vibration from 30 to 120 mm/s than calibrated at its
285 Hz one (41 to 162 mm/s). `SAVE_CONFIG` keeps the frequency used as
`stepper_x_freq` / `stepper_y_freq`.

With no clear resonance, the configured frequency (200 Hz unless saved) is
used, and the console says so.

The accelerometer (LIS2DW, 1600 samples/s) can't measure vibration above
about 700 Hz. A ripple faster than that is left out at that speed, shown as
`--` in the console and not used to find the resonance: the 4x ripple above
about 100 mm/s and the 2x above about 200 mm/s. The 1x ripple is measured all
the way to 300 mm/s (525 Hz). Test moves faster than `fast_move_speed`
(150 mm/s) accelerate at `fast_move_accel` (10000 mm/s², capped at the
printer's own `max_accel`), so even a 300 mm/s move has some steady speed to
measure.

## Graphs

`VFA_COMPENSATION_GRAPH` (or **VFA + Graphs** in the touchscreen and Fluidd
menus) does the same calibration, then repeats the speed sweep with
compensation on, and draws one picture per motor to `config/vfa/`
(`vfa_stepper_x.png`, `vfa_stepper_y.png`). It takes longer than
`VFA_COMPENSATION`, by one more sweep per motor.

Each picture explains itself:

- The top chart shows how hard the toolhead shakes at each print speed, for
  each of the three ripples it corrects (1x, 2x and 4x per motor cycle).
  Dotted lines are before compensation and solid lines after, so lower is
  better. Peaks are the speeds where a ripple matches the frame's resonance,
  and a marker shows the speed each ripple was tuned at.
- The bottom chart shows each ripple at its worst speed, before and after,
  with how much less it shakes, or that it was left off because it didn't
  help.

## How each harmonic is calibrated

For each of `td1`, `td2` and `td4`, in each direction, the search measures the
vibration with no compensation, then finds the phase and amplitude that cancel
it. Each measurement uses the whole steady-speed part of the test move, found
from the move's own timing, not just a slice of it.

The two directions share one amplitude (the MCU keeps a phase per direction
but one amplitude), so the amplitude used is the one that gives the least
vibration over both, not the larger of the two. The result is then measured
as it will run and compared with no compensation: a harmonic that doesn't
lower the vibration by at least 5% is left off (amplitude 0) rather than
saved.

Afterwards the printer's own acceleration and minimum cruise ratio are put
back. If calibration stops with an error, the motors go back to their saved
damping. With `SAVE=0`, the new values are what print start restores until
Klipper restarts. A CSV of every measurement is written to
`/tmp/stepper_x_search_calibrate-<time>.csv` (and `stepper_y`).

This workflow is implemented but still needs on-printer validation. Confirm
homing, test travel, accelerometer readings, saved values, and subsequent print
motion before using it unattended.
