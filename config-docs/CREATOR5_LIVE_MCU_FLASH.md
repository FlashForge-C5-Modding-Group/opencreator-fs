# Live MCU firmware updates

`oc-mcu-flash` updates the four boards from the running SoC, with no USB stick and no power cycle. It uses
FlashForge's own flashing tools from `/usr/prog/PROGRAM/control/<version>/`, the same ones the USB update's
`run.sh` runs at boot.

```sh
/usr/data/opencreator/mcu-flash/oc-mcu-flash DIR
```

`DIR` holds any of `eBoard.hex`, `heaterBoard.hex`, `levelBoard.hex` and `mainBoardGD.hex` (the loose files
from a Kalico build); only the boards with a file are flashed. Not during a print. Log:
`/usr/data/logs/oc-mcu-flash.log`.

## How each board gets flashed

| Board | UART | Tool | How it gets into its bootloader |
|---|---|---|---|
| mainboard | `/dev/ttyS2` | `ISPCommand` | GPIO 50 (BOOT0) high and a reset pulse on GPIO 49, into the chip's ROM bootloader. Afterwards BOOT0 goes low and another reset boots the new firmware. |
| eBoard | `/dev/ttyS5` | `IAPCommand` | `C5_MCU_BOOTLOADER` sends `c5_reset_bootloader`, which resets without the `0x1234` backup register flag, so FlashForge's boot stage stays resident as after power-on. |
| heaterBoard | `/dev/ttyS4` | `IAPCommand` | Same as the eBoard. |
| levelboard | `/dev/ttyS7` | `IAPCommand` | Its boot stage stays resident after every reset. |

`IAPCommand` speaks an XMODEM-like protocol to the boot stage (`C` at 115200 8E1, 1 KB frames with CRC16,
`EOT`). The normal `reset` on the eBoard and heaterBoard sets the flag, which is why a `FIRMWARE_RESTART`
skips their boot stage while a power-on doesn't.

## Steps

1. Pause `08-mcu-wake.sh` (`SIGSTOP`), or it would release the boards from their boot stage.
2. `C5_MCU_BOOTLOADER BOARDS=…` through Moonraker for the IAP boards; Klipper shuts down.
3. Pause Klippy (`SIGSTOP`) so it leaves the UARTs alone, saving each port's settings.
4. `IAPCommand` per board (3 tries, like `run.sh`), then `ISPCommand` for the mainboard.
5. Restore the port settings, kill Klippy (`10-klipper.sh` starts it again) and resume the wake script,
   which releases the boards still in their boot stage. A trap does this on any exit.

## Needs

- The eBoard, heaterBoard and levelboard firmware with `c5_reset_bootloader` (Kalico `ab62660c` or later),
  flashed once from USB. Until then `C5_MCU_BOOTLOADER` stops with an error and nothing is touched. A run
  with only `mainBoardGD.hex` works on any firmware.
- `[c5_mcu_flash]` in the config (`printer.base.cfg`) and Kalico with `klippy/extras/c5_mcu_flash.py`.

## Recovery

- The mainboard bootloader is in ROM and can't be overwritten. If `ISPCommand` fails it leaves BOOT0 high;
  run `oc-mcu-flash` again, or update from USB.
- The other boards' boot stage isn't touched by a flash. A board left in it is released by the wake script,
  or reflashed by running `oc-mcu-flash` again or from USB.

Tested live on a Creator 5 Pro: levelboard and mainboard reflashed with Klipper paused, and back to ready.
SoC installs only; tunneled installs reach the boards through the socat bridge instead.
