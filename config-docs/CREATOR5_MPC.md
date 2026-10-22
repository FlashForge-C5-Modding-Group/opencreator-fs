# MPC hotend control (Kalico only)

MPC replaces hotend PID on Kalico only. It needs both the MPC overlay and
`printer.mpc.cfg` macros; PID/stock Klipper retain their normal behavior.

## Enable and calibrate

1. Copy `kalico/printer.kalico_mpc.cfg` next to `printer.cfg` (Kalico only).
   It enables `control: mpc` on all four hotends with `heater_power: 50`.
   Enable `[include printer.mpc.cfg]` and `[include printer.kalico_mpc*.cfg]`
   if commented out. Keep the macros after `AFC/AFC.cfg` so they wrap AFC's
   `M109`; the native layout already enables these includes.
2. Remove each extruder's `control = pid` from the `SAVE_CONFIG` block:
   saved values override includes. The saved PID coefficients can stay.
3. Restart and run `C5_MPC_CALIBRATE` (all tools) or
   `C5_MPC_CALIBRATE TOOL=n` (`n` = 0–3). It picks up each requested tool,
   calibrates over the bucket, then docks and runs `SAVE_CONFIG` once.
   `TARGET=` defaults to **250 °C**; `T0=`–`T3=` override it per tool.
   `SAVE=0` skips saving; run `SAVE_CONFIG` yourself to persist the results.

Calibration refuses stock Klipper or heaters still using PID. To return to
PID, remove the overlay, restore `control = pid` for each extruder, restart
and run `C5_PID_CALIBRATE`.

## Filament material from Orca

With updated Kalico **and** Creator 5 config macros, automatic virtual-SD
startup sets MPC material properties for **all four tools**, including tools
selected later in the print. No Orca start-G-code edits are needed. Enable
and calibrate MPC first.

The hook reads `; filament_type = PLA;PETG;...` in the bounded startup
prefix or last 64 KiB; trailer metadata wins. Slots 0–3 become
`MATERIAL0=`–`MATERIAL3=`. Missing, empty or malformed slots become
`UNKNOWN`, restoring that hotend's configured density/heat-capacity defaults
(1.20 / 1.80 in the overlay). Known materials use the macro's table.
PID ignores these updates. This reads slicer metadata, not loaded filament.

Material setup does **not** select, heat or purge extra tools. Automatic
startup still prepares only the initial tool; `TOOL`/`TOOLS` control physical
preparation independently of MPC material properties.

An explicit `C5_PRINT_START` in the startup header bypasses all automatic
start/material injection. Supply `MATERIAL=` for the tools in `TOOLS`, or
`MATERIAL0=`–`MATERIAL3=` for individual tools regardless of `TOOLS`.
Per-tool values override the shared value; no material arguments leave
existing settings unchanged. To prepare two tools explicitly, for example:

```
C5_PRINT_START TOOL=0 TOOLS=0,1 BED=60 HOTEND=220 MATERIAL0=PLA MATERIAL1=PETG
```

## Temperature waits

MPC models block temperature; the sensor can remain a few degrees off target,
so a stock ±1 °C wait may wait unnecessarily. On MPC hotends, `M109` waits
from 2 °C below to 5 °C above target (`band_below` / `band_above`). With `T`,
it delegates lane selection to AFC using `D4` (±2 °C); an explicit `D` passes
through unchanged. `M190` uses the same −2/+5 °C band only if the bed uses MPC.
