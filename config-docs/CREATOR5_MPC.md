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

## Material defaults

Both native and tunneled installations use the following defaults.
Material names are case-insensitive. Unlisted materials use the heater's
configured defaults: **1.20 g/cm³** and **1.80 J/(g·K)** in the MPC overlay.

| Material | Density (g/cm³) | Heat capacity (J/(g·K)) |
| --- | --- | --- |
| ABS | 1.06 | 2.40 |
| ABS-CF | 1.11 | 2.40 |
| ASA | 1.07 | 2.10 |
| ASA-CF | 1.11 | 2.10 |
| PA | 1.15 | 2.50 |
| PA-CF | 1.19 | 2.50 |
| PA-GF | 1.20 | 2.50 |
| PA6 | 1.12 | 2.50 |
| PA6-CF | 1.19 | 2.50 |
| PA6-GF | 1.20 | 2.50 |
| PA12-CF | 1.03 | 2.50 |
| PC | 1.20 | 1.90 |
| PC+ABS | 1.15 | 2.20 |
| PC+ABS-CF | 1.22 | 2.20 |
| PC+CF | 1.36 | 1.90 |
| PCTG | 1.27 | 2.20 |
| PET-CF | 1.29 | 2.20 |
| PET-GF | 1.38 | 2.20 |
| PETG | 1.27 | 2.20 |
| PETG-CF | 1.30 | 2.20 |
| PETG-GF | 1.30 | 2.20 |
| PLA | 1.25 | 2.20 |
| PLA-CF | 1.29 | 2.20 |
| PPA | 1.21 | 2.50 |
| PPA-CF | 1.22 | 2.50 |
| PPA-GF | 1.27 | 2.50 |
| TPU | 1.21 | 2.00 |
| TPU-90A | 1.15 | 2.00 |
| TPU-95A | 1.22 | 2.00 |

### Estimates and sources

These are starting defaults, not measurements for every brand or
hardware-validated tuning. Density varies with formulation and fiber content.
Heat capacities follow polymer-family estimates: PPA/PA12 and nylon
composites use the PA value; PET composites use the PETG value. PCTG uses
the PETG density/heat-capacity pair. Generic `PA-CF` and `PA-GF` represent
PA6 composites, not every nylon blend.

- [Kalico's MPC reference](https://docs.kalico.gg/MPC.html): common polymer
  densities and heat-capacity ranges; CF blends use the base polymer's heat
  capacity. Using those family estimates for GF, PPA/PA12 and PET is an
  approximation, not a manufacturer heat-capacity measurement.
- Siraya Tech: [PPA](https://siraya.tech/pages/siraya-tech-fibreheart-ppa-filament-tds)
  and [PPA-GF](https://siraya.tech/pages/fibreheart-ppa-gf-tds) density references.
- [Flashforge PPA-CF TDS](https://after-support.flashforge.jp/uploads/datasheet/tds/PPA_CF_TDS_EN.pdf):
  the density default is the midpoint of the published range.
- [Bambu Lab PET-CF](https://wiki.bambulab.com/filament-acc/petcf-ppacf/07689de83afd4cc480f136c7697e6de3.pdf),
  [Raise3D PET-GF](https://s1.raise3d.com/2023/03/Raise3D-Industrial-PET-GF_TDS_V1.pdf)
  and [SSSRAY PETG-GF](https://sssray.com/wp-content/uploads/2026/05/PETG-GF-3D-Printing-Filament-Technical-Data-Sheet.pdf):
  representative composite densities.
- [Polymaker PA6-GF](https://cdn.polymaker.com.cn/wp-content/uploads/lana-downloads/PolyMide_PA6_GF_TDS_V5.1.pdf)
  and [Extrudr PA12-CF](https://s3.extrudr.com/extrudr-media/datasheets/tds/tds-en/durapro-pa12-cf-TDS-en.pdf):
  representative nylon-composite densities.

For spool-specific values, edit `_SET_MPC_MATERIAL`'s `filament_table`.
`MPC_SET HEATER=extruder FILAMENT_DENSITY=... FILAMENT_HEAT_CAPACITY=...`
provides a runtime override; a subsequent material-setting command can replace it.

## Temperature waits

MPC models block temperature; the sensor can remain a few degrees off target,
so a stock ±1 °C wait may wait unnecessarily. On MPC hotends, `M109` waits
from 2 °C below to 5 °C above target (`band_below` / `band_above`). With `T`,
it delegates lane selection to AFC using `D4` (±2 °C); an explicit `D` passes
through unchanged. `M190` uses the same −2/+5 °C band only if the bed uses MPC.
