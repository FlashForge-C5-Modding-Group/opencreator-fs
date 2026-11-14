# X2600 RISC-V core as a Klipper MCU

The X2600 SoC has a small RV32IMC core next to the MIPS CPUs. Stock firmware runs a FlashForge image on it (`/usr/prog/libmcu-bare.bin`, loaded by `firmwareExe`) that nothing in OpenCreator uses. On this branch it runs Kalico instead and shows up as `[mcu soc]`.

## Pieces

- `rvmcu/x2600rv.bin`: Kalico built for the core (`MACH_X2600RV`, branch `x2600-riscv` of the Kalico fork). It runs at 576 MHz with no interrupts and talks over the shared-memory rings of the stock `soc_mcu` driver.
- `rvmcu/rvmcu`: static MIPS host tool (source in Kalico `scripts/x2600rv/rvmcu.c`).
  - `rvmcu load FILE` loads an image through `/dev/mcu` and starts the core.
  - `rvmcu stop` holds the core in reset.
  - `rvmcu bridge [PATH]` exposes the core as a pty, `/tmp/klipper_host_soc` by default.
- `startup/scripts/09-riscv.sh`: at boot, waits for `/dev/mcu`, loads the image over the stock one, then keeps the bridge running (restarted if it exits). Log: `/usr/data/logs/rvmcu.log`.
- `printer.base.cfg`: `[mcu soc]` on `/tmp/klipper_host_soc`, `is_non_critical: True`, so Klipper still starts if the core or bridge is missing.

## Notes

- The core has no GPIO, ADC or temperature sensor wired up yet; it only answers the basic Klipper protocol (clock, uptime, config).
- If `[mcu soc]` ends up shut down, `FIRMWARE_RESTART` resets it.
- To go back to the stock image: `rvmcu stop`, then `cmd_mcu write_firmware /usr/prog/libmcu-bare.bin && cmd_mcu bootup`.
