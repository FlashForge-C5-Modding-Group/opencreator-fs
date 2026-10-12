# MPC hotend control (Kalico only)

Kalico's Model Predictive Control replaces PID for the four hotends. Stock
Klipper (klipper-c5) has no MPC, so it is split in two:

- `printer.mpc.cfg` (always installed) holds MPC-aware macros. Each one checks
  that the heater reports Kalico's `pid_profile` status **and** is configured
  with `control: mpc`. Otherwise it behaves exactly like the stock command or
  does nothing, so stock Klipper is unaffected.
- `kalico/printer.kalico_mpc.cfg` (repo root, not in `fs/`) switches
  `[extruder]`–`[extruder3]` to `control: mpc`. Only copy it onto Kalico
  installs; it is picked up by `[include printer.kalico_mpc*.cfg]`, which
  matches nothing when the file is absent.

## Enabling on Kalico

1. Copy `kalico/printer.kalico_mpc.cfg` next to `printer.cfg`. It sets
   `heater_power: 50` (the hotend heater wattage).
2. In the `SAVE_CONFIG` block at the bottom of `printer.cfg`, delete the
   `control = pid` line under each of `[extruder]`–`[extruder3]`. Saved
   values override included files, so these lines otherwise keep PID active.
   The leftover `pid_kp`/`pid_ki`/`pid_kd` lines can stay.
3. Restart Klipper and run `C5_MPC_CALIBRATE` (all tools) or
   `C5_MPC_CALIBRATE TOOL=n`. It picks up each tool, calibrates, and runs
   `SAVE_CONFIG`. `TARGET=` sets the calibration temperature (default 210).

`C5_MPC_CALIBRATE` refuses to run on stock Klipper or on a heater still using
PID.

To go back to PID, remove `printer.kalico_mpc.cfg`, restore
`control = pid` for each extruder and run `C5_PID_CALIBRATE`.

## Waiting for temperature

MPC controls the modelled block temperature, so the sensor can sit a few
degrees from target for a while and a stock wait (±1 °C) stalls.

- `M109` on an MPC hotend waits until the sensor is between 2 °C below and
  5 °C above the target (`band_below`/`band_above` variables). With a `T`
  parameter it hands off to AFC's `M109` (which maps `T` to a lane) with
  `D4`, a ±2 °C band. An explicit `D` is passed through untouched.
- `M190` does the same for the bed, only if the bed itself uses MPC.

AFC already replaces `M109`. `printer.mpc.cfg` must stay included after
`AFC/AFC.cfg` (it is, via `printer.cfg`) so its `M109.1` is AFC's command.

## Filament material from the slicer

MPC's filament feed-forward needs the material's density and heat capacity.
`C5_PRINT_START` accepts `MATERIAL=` for all tools, or `MATERIAL0=`–
`MATERIAL3=` per tool, and calls `_SET_MPC_MATERIAL` for each tool in the
print. The table in `_SET_MPC_MATERIAL` covers PLA, PETG, ABS, ASA, PA, PC,
TPU and common CF blends; unknown materials use the heater's configured
defaults. On stock Klipper the call does nothing.

OrcaSlicer start G-code example:

```
C5_PRINT_START TOOL=[initial_tool] BED=[bed_temperature_initial_layer_single] HOTEND=[nozzle_temperature_initial_layer] MATERIAL=[filament_type[initial_tool]]
```

The automatic virtual-SD start hook does not pass a material, so prints
without an explicit `C5_PRINT_START` line use the defaults from
`printer.kalico_mpc.cfg`. `_SET_MPC_MATERIAL TOOL=n MATERIAL=PETG` can also
be run by hand.
