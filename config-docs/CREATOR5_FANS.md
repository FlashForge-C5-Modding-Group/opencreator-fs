# Creator 5 mainboard and power supply fans

`[c5_board_fans]` in `printer.base.cfg` (Kalico's `klippy/extras/c5_board_fans.py`) runs two fans on the
mainboard, every second. It runs on its own timer, like Klipper's `controller_fan`, so long commands
(`PID_CALIBRATE`, heat-up waits, homing) don't stop it. Both fans are `fan_generic` fans; GrumpyScreen
shows them as sliders, but it sets them again within a second.

## Mainboard fan (`pcb_fan`, pin PD14)

It cools the mainboard and the X/Y/Z motor drivers, and follows the mainboard MCU's own temperature
(`temperature_sensor mainboard_mcu`), only while X, Y or Z is powered or a hotend has a target:

| Mainboard MCU | Speed |
| --- | --- |
| below `on_temp` (54.5 °C) | off |
| `on_temp` to `max_temp` (54.5–65 °C) | `min_speed` (30%) rising in a straight line to 100% |
| `max_temp` and up | 100% |

Once on, it stays at `min_speed` until the MCU is `hysteresis` (2 °C) under `on_temp`. While X, Y or Z is
powered it runs at least `motor_min` (40%), for the motor drivers.

## Power supply fan (`heat_ctl_fan`, pin PE14)

The higher of two speeds:

- **The mainboard fan's speed**, so a hot board also speeds this one up.
- **The power supply's estimated load**: `heater_watts` (45 W) per hotend at its heater's duty, plus
  `motor_watts` (30 W) while X, Y or Z is powered, reaching 100% at `full_watts` (120 W). At least
  `psu_min_speed` (30%) while there is any load, and `heating_min` (50%) while any hotend has a target.

Once the load is gone it keeps its speed, at most `runon_speed` (80%), for `runon` (60 s), then stops.

## During calibration

Input shaper calibration (`CALIBRATE_INPUT_SHAPER`, `CALIBRATE_INPUT_SHAPER_GRAPH`) and VFA calibration
(`STEPPER_RESONANCE_FACTORY_CALIBRATE`, which `VFA_COMPENSATION` and the stock VFA button run) hold both fans
at 50% (`_FANS_HOLD`, then `_FANS_RELEASE`), so their vibration stays the same through the measurement. A
calibration stopped part way leaves the hold on until the next print start or restart.

## Commands and settings

```
C5_BOARD_FANS                      # both speeds, the MCU temperature and the estimated load
C5_BOARD_FANS HOLD=0.5             # hold both fans at 50%; HOLD=-1 releases
C5_BOARD_FANS MAX_TEMP=65 HEATING_MIN=0.5   # change settings until restart
```

Every option of `[c5_board_fans]` can be given that way (upper case). To keep a change, edit
`printer.base.cfg`. `printer.c5_board_fans` in Moonraker has the speeds, the temperature, the load, the
hold and the settings.

Other options, with their defaults: `mainboard_fan: pcb_fan`, `psu_fan: heat_ctl_fan`,
`sensor: temperature_sensor mainboard_mcu`, `steppers: stepper_x, stepper_y, stepper_z`,
`heaters: extruder, extruder1, extruder2, extruder3`.

## Needs

- The mainboard firmware with the MCU temperature sensor (`ADC_TEMPERATURE` on the GD32H737, Kalico
  `33d27fc5` or later). The SoC updater flashes it from `mcu-firmware/`; tunneled printers get it from the
  OpenCreator USB update.
- Kalico with `c5_board_fans.py` and the `gd32h7` entry in `temperature_mcu.py`. The SoC updater brings
  Kalico up to date with each OpenCreator update (see `UPDATER.md`).
