# Motion guard: skipped steps and stalls on X, Y and Z

The X, Y and Z motors are not on TMC drivers. FlashForge's motor controller ("mclib", `kalico/src/c5_mclib.c`)
drives them from the mainboard and estimates where each rotor really is from its currents, with no encoder.
The motion guard reads two things from that:

- **Skipped steps.** The gap between where a motor was told to be and where it is. A jump of a whole
  electrical cycle (4 full steps, 0.8 mm on X/Y) is a lost or gained cycle.
- **Stalls (StallGuard-like).** The load torque falling under `stall_threshold` in `[mclib stepper_*]` while the
  motor runs. Only counted on the axes in `stall_axes`, once their threshold is calibrated.

Stalls only count while a motor moves fast enough for the estimate. Prints watch skipped steps in fast moves
only. In test mode, `slip_watch` can widen that: `holding` (also while a motor holds still, so pulling the
carriage by hand counts) or `always` (whenever the motor is enabled). Both counted false slips while printing
(Z especially), so a real print always goes back to fast moves only. Windows that overlap a toolchange are ignored, since docking pushes the carriage into
the dock on purpose.

## Needs

- The mainboard firmware with `mclib_query_status` (MCU update built from Kalico with the motion guard).
  On older firmware the guard stays idle and `C5_MOTION_STATUS` says to flash.
- Kalico with `klippy/extras/c5_motion_guard.py`.

## Config

```ini
[c5_motion_guard]
action: warn       # warn: error message in the console; pause: PAUSE the print
slip_limit: 1      # net cycles lost on one axis in one print before it trips
# slip_watch: moving  # test mode only: moving, holding or always
# stall_axes: z    # axes whose stall flag counts (calibrate first)
# poll_time: 0.5
# enabled: True
```

## Commands

| Command | What it does |
| --- | --- |
| `C5_MOTION_STATUS` | Skipped cycles and stalls this print per axis, the live stall flag and threshold |
| `C5_MOTION_RECORD` / `C5_MOTION_RECORD STOP=1` | Record the torque range while moving and suggest a `stall_threshold` |
| `C5_MOTION_GUARD ENABLE=0/1 ACTION=warn/pause WATCH=moving/holding/always RESET=1 TEST=0/1` | Turn it on or off, change the action and when skipped steps are watched, clear the counts; `TEST=1` also watches outside prints |
| `MCLIB_SET_STALL STEPPER=stepper_x THRESHOLD=…` | Try a stall threshold until restart |

## Trying it out

1. Flash the MCU update, update Kalico and the config, restart.
2. `C5_MOTION_STATUS` should list stepper_x, stepper_y and stepper_z.
3. **Skipped steps.** Home, run `C5_MOTION_GUARD TEST=1 RESET=1`, then move X back and forth fast
   (`G1 X50 F30000`, `G1 X250 F30000`). Clean moves should stay at 0 in `C5_MOTION_STATUS`. Then, with a
   gloved hand, briefly hold the carriage back during a move so the motor slips: the console should show
   `Motion guard: stepper_x skipped steps`. `C5_MOTION_GUARD TEST=0` when done (it also stops on restart).
   To try it by hand without moving: `C5_MOTION_GUARD TEST=1 RESET=1 WATCH=holding`, then pull the carriage
   until the motor gives. Leave it idle for a minute first: it should count nothing on its own.
4. **Stall thresholds.** Run `C5_MOTION_RECORD`, print something normal for a few minutes, then
   `C5_MOTION_RECORD STOP=1`. It gives the torque range per axis and a threshold at about half the lowest
   normal torque. Try it with `MCLIB_SET_STALL`, check a normal print never shows a stall, and that holding
   the carriage does. Then put it in `[mclib stepper_x]` / `[mclib stepper_y]` as `stall_threshold` and add
   the axis to `stall_axes`.
5. Once a few prints run clean, `action: pause` makes a crash or skipped steps pause the print.

X and Y currently have no `stall_threshold`, so it defaults to the bus voltage (24). That is far above any real
torque, so their stall flag is set on nearly every move; leave them out of `stall_axes` until calibrated.
