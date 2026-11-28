# Creator 5 notower

Notower replaces the slicer's prime tower on multi-tool prints. After every tool
change during the print, the new tool goes to the purge bucket, purges a set
weight of filament there, then AFC takes it back to the print. Slice with the
prime tower off. It needs a poop bucket fitted on the printer for the purged
filament to drop into; a nozzle brush is recommended, so the purge doesn't
trail back onto the print.

## Turning it on

There is no switch. A print uses notower when its G-code has a `poop=<grams>`
line (`; poop=2`, the `;` is optional) and it uses more than one tool.

- `poop=` without a number is 2 g; `poop=0` turns it off.
- Kalico's print dispatcher (`creator5_start_command` in `virtual_sdcard.py`)
  turns the line into `POOP=<grams>` on the `C5_PRINT_START` it builds. It also
  adds `DENSITY<n>` for each used tool, from Orca's `filament_density`.
- A file with its own `C5_PRINT_START` line ignores the `poop=` line. Put
  `POOP=<grams>` (and `DENSITY0`..`DENSITY3` if you like) on that line instead.
- OpenCreator Send's **Notower** box does both: it writes `; poop=<grams>` at
  the top of the file and adds `DENSITY<n>`/`POOP` to its own `C5_PRINT_START`
  line, or to one already in the file.

## What happens

1. `C5_PRINT_START` clears notower, then arms it at the very end of print start,
   after the purge lines and the first tool's pickup. It's armed only with
   `POOP` and more than one tool in `TOOLS` and the slicer's `USED_TOOLS`. Print
   start keeps each head's print temperature (`HOTEND`, `HOTEND0..3`) and
   density for it. Like the other per-tool values, `DENSITY<n>` follows AFC's
   colour-to-head map.
2. AFC's `custom_tool_swap` is `_OC_TOOL_SWAP T=<n>` in
   `printer.afc-standalone.cfg`. It runs `C5_TOOL_SELECT`, then
   `_OC_NOTOWER_PURGE` when notower is armed and the print is running (not
   paused).
3. `_OC_NOTOWER_PURGE`:
   - goes to the bucket with `C5_MOVE_TO_PURGE_BUCKET`, at `travel_speed` and
     `travel_accel`. The bucket is on the frame and the head only moves in XY,
     so the print position is kept; the move only ever raises Z (to `safe_z`
     when lower), never brings the bed up;
   - heats the tool to its print temperature, or its current target if
     higher, and waits until it's within 2 °C. It heats at the bucket, so ooze
     lands there;
   - purges `grams / density / filament area` mm, in moves of at most 100 mm
     (`max_extrude_only_distance` is 500), at `flow` mm³/s;
   - retracts `retract` mm, against oozing on the way back.

   AFC then moves back to the print.
4. `C5_PRINT_STOP` (the end of the print, and a cancel) clears notower.

Print start's own tool selections (priming, purge lines, the first tool) come
before it's armed, so they never purge. Tool changes by hand while paused don't
purge either.

## Settings

In `[gcode_macro _OC_NOTOWER]` in `printer.creator5.cfg`:

| Variable | Default | |
| --- | --- | --- |
| `variable_travel_speed` | 300 | trip to the bucket, mm/s (`C5_MOVE_TO_PURGE_BUCKET SPEED`) |
| `variable_travel_accel` | 20000 | trip to the bucket, mm/s² (`ACCEL`) |
| `variable_flow` | 10.0 | purge flow, mm³/s |
| `variable_retract` | 1.0 | retract after the purge, mm |
| `variable_default_density` | 1.24 | g/cm³ when the slicer gives no density (PLA) |

`_OC_NOTOWER` on its own prints whether notower is armed and how much it purges.

## Time

2 g of PLA is about 670 mm of 1.75 mm filament. At 10 mm³/s that's about
2 min 40 s of purging per tool change, plus heating and the trip to the bucket.
