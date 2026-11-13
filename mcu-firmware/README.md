# MCU firmware for live updates

The SoC updater keeps the four boards on the firmware in this folder: `eBoard.hex`, `heaterBoard.hex`,
`levelBoard.hex` and `mainBoardGD.hex`, their `SHA256SUMS`, and `VERSION` (the `mcu_version` the boards
report). It all comes from Kalico's update maker, `scripts/build_c5_update.py all` (see
`docs/Creator5_Updates.md` in Kalico): copy the files in its `live/` folder here. The same run makes the
stock-style update packages the installer and tunneled printers use.

Only boards whose file changed since their last flash are updated, never during a print. Details:
`config-docs/UPDATER.md` (MCU firmware) and `config-docs/CREATOR5_LIVE_MCU_FLASH.md`.
