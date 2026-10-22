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

No Orca start-G-code edits are needed for automatic virtual-SD start with
updated shared Kalico: it passes `MATERIAL=` for **only the initial tool**.
Enable and calibrate MPC first. An explicit `C5_PRINT_START` in the startup
header bypasses automatic start and material injection completely.

The hook reads `; filament_type = PLA;PETG;...` in the bounded startup
prefix or last 64 KiB; trailer metadata wins. T0–T3 index list slots 0–3.
Missing, empty, malformed or unavailable slots, including metadata outside
these windows, pass `MATERIAL=UNKNOWN`. Known materials use the macro's
density/heat-capacity table; unknown materials use the heater's configured
defaults (1.20 / 1.80 in the overlay). PID ignores material updates.
This reads slicer metadata; it does not sense the filament actually loaded.

An explicit start owns `MATERIAL=` (shared) or `MATERIAL0=`–`MATERIAL3=`
(per tool). With no material arguments, it leaves material settings unchanged.
Multi-tool preparation still requires explicit `TOOLS=` and appropriate
materials; metadata slots do not select tools. For example:

```
C5_PRINT_START TOOL=0 TOOLS=0,1 BED=60 HOTEND=220 MATERIAL0=PLA MATERIAL1=PETG
```

## Temperature waits

MPC models block temperature; the sensor can remain a few degrees off target,
so a stock ±1 °C wait may wait unnecessarily. On MPC hotends, `M109` waits
from 2 °C below to 5 °C above target (`band_below` / `band_above`). With `T`,
it delegates lane selection to AFC using `D4` (±2 °C); an explicit `D` passes
through unchanged. `M190` uses the same −2/+5 °C band only if the bed uses MPC.
