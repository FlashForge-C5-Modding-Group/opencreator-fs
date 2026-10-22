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

The native and tunnel `_SET_MPC_MATERIAL` tables use density in **g/cm³**
and specific heat capacity in **J/(g·K)**. The added defaults below use
representative product densities, not universal values for each polymer.
Generic `PA-CF` and `PA-GF` represent PA6 composites, not every nylon blend.
`PCTG` is already supported in both tables; its existing defaults remain
unchanged at density **1.27** and heat capacity **2.20**.

**All ten additions use estimated heat capacities**, not manufacturer
heat-capacity measurements: PPA, PPA-CF, PPA-GF, PA-CF, PA-GF, PA6-GF and
PA12-CF use the existing PA-family upper-end value **2.50**; PET-CF, PET-GF
and PETG-GF use the PETG-family value **2.20**. [Kalico's MPC guide](https://docs.kalico.gg/MPC.html)
gives PA 2–2.5 and PETG 1.7–2.2 and recommends the base polymer's heat
capacity for CF blends. Extending that approximation to GF, PPA/PA12 and
PET here is our family estimate, not an upstream guarantee.

Density sources for the additions:

| Material | Density (g/cm³) | Representative source |
| --- | --- | --- |
| PPA | 1.21 | [Siraya Tech Fibreheart PPA](https://siraya.tech/pages/siraya-tech-fibreheart-ppa-filament-tds) |
| PPA-CF | 1.22 | [Flashforge PPA-CF TDS](https://after-support.flashforge.jp/uploads/datasheet/tds/PPA_CF_TDS_EN.pdf), midpoint of 1.21–1.23 (10% CF) |
| PPA-GF | 1.27 | [Siraya Tech Fibreheart PPA-GF](https://siraya.tech/pages/fibreheart-ppa-gf-tds) (15% GF) |
| PET-CF | 1.29 | [Bambu Lab PET-CF TDS](https://wiki.bambulab.com/filament-acc/petcf-ppacf/07689de83afd4cc480f136c7697e6de3.pdf) |
| PET-GF | 1.38 | [Raise3D Industrial PET-GF TDS](https://s1.raise3d.com/2023/03/Raise3D-Industrial-PET-GF_TDS_V1.pdf) (15% GF) |
| PETG-GF | 1.30 | [SSSRAY PETG-GF TDS](https://sssray.com/wp-content/uploads/2026/05/PETG-GF-3D-Printing-Filament-Technical-Data-Sheet.pdf) |
| PA-CF | 1.19 | Existing PA6-CF default from [Kalico's MPC table](https://docs.kalico.gg/MPC.html) |
| PA-GF, PA6-GF | 1.20 | [Polymaker PolyMide PA6-GF TDS](https://cdn.polymaker.com.cn/wp-content/uploads/lana-downloads/PolyMide_PA6_GF_TDS_V5.1.pdf) |
| PA12-CF | 1.03 | [Extrudr DuraPro PA12-CF TDS](https://s3.extrudr.com/extrudr-media/datasheets/tds/tds-en/durapro-pa12-cf-TDS-en.pdf) |

These are starting defaults, not hardware-validated settings. Filler ratios
and spool-specific properties vary; customize the table or use
`MPC_SET HEATER=extruder FILAMENT_DENSITY=... FILAMENT_HEAT_CAPACITY=...`
with known material data. Unknown-material fallback behavior is unchanged.

## Temperature waits

MPC models block temperature; the sensor can remain a few degrees off target,
so a stock ±1 °C wait may wait unnecessarily. On MPC hotends, `M109` waits
from 2 °C below to 5 °C above target (`band_below` / `band_above`). With `T`,
it delegates lane selection to AFC using `D4` (±2 °C); an explicit `D` passes
through unchanged. `M190` uses the same −2/+5 °C band only if the bed uses MPC.
