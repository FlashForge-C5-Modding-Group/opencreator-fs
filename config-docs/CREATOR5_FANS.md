# Creator 5 mainboard and power supply fans

Two fans on the mainboard are run by `_PCB_FAN_TICK` in `printer.base.cfg`, every 2 seconds. Both are
`fan_generic` fans; GrumpyScreen shows them as sliders, but the macro sets them again within 2 s.

## Mainboard fan (`pcb_fan`, pin PD14)

It cools the mainboard and the X/Y/Z motor drivers, and follows the mainboard MCU's own temperature
(`temperature_sensor mainboard_mcu`), only while X, Y or Z is powered or a hotend has a target:

| Mainboard MCU | Speed |
| --- | --- |
| below `on_temp` (54.5 °C) | off |
| `on_temp` to `max_temp` (54.5–62 °C) | `min_speed` (30%) rising in a straight line to 100% |
| `max_temp` and up | 100% |

Once on, it stays at `min_speed` until the MCU is `hysteresis` (2 °C) under `on_temp`. While X, Y or Z is
powered it runs at least `motor_min` (40%), for the motor drivers.

## Power supply fan (`heat_ctl_fan`, pin PE14)

The higher of two speeds:

- **The mainboard fan's speed**, so a hot board also speeds this one up.
- **The power supply's estimated load**: `heater_watts` (45 W) per hotend at its heater's duty, plus
  `motor_watts` (30 W) while X, Y or Z is powered, reaching 100% at `full_watts` (120 W). At least
  `min_speed` (30%) while there is any load, and `heating_min` (50%) while any hotend has a target.

Once the load is gone it keeps its speed, at most `runon_speed` (80%), for `runon` (60 s), then stops.

## During calibration

Input shaper calibration (`CALIBRATE_INPUT_SHAPER`, `CALIBRATE_INPUT_SHAPER_GRAPH`) and VFA calibration
(`STEPPER_RESONANCE_FACTORY_CALIBRATE`, which `VFA_COMPENSATION` and the stock VFA button run) hold both fans
at 50%, so their vibration stays the same through the measurement. `_FANS_HOLD SPEED=…` and `_FANS_RELEASE`
do it by hand. A calibration stopped part way leaves the hold on until the next print start or restart.

## Settings

The numbers are variables of `_PCB_FAN` and `_PSU_FAN`. Change them in `printer.base.cfg`, or try them
until the next restart:

```
SET_GCODE_VARIABLE MACRO=_PCB_FAN VARIABLE=max_temp VALUE=62
SET_GCODE_VARIABLE MACRO=_PSU_FAN VARIABLE=heating_min VALUE=0.5
```

## Needs

- The mainboard firmware with the MCU temperature sensor (`ADC_TEMPERATURE` on the GD32H737, Kalico
  `33d27fc5` or later). The SoC updater flashes it from `mcu-firmware/`; tunneled printers get it from the
  OpenCreator USB update.
- Kalico with the `gd32h7` entry in `temperature_mcu.py`. The SoC updater brings Kalico up to date with each
  OpenCreator update (see `UPDATER.md`).
