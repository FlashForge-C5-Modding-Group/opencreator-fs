# MCU firmware for live updates

The SoC updater keeps the four boards on the firmware in this folder. Put the loose `.hex` files from a Kalico
build here (any of `eBoard.hex`, `heaterBoard.hex`, `levelBoard.hex`, `mainBoardGD.hex`), then:

```sh
sha256sum *.hex > SHA256SUMS
echo ab62660c7 > VERSION   # the mcu_version the boards will report (optional)
```

Only boards whose file changed since their last flash are updated, never during a print. Details:
`config-docs/UPDATER.md` (MCU firmware) and `config-docs/CREATOR5_LIVE_MCU_FLASH.md`.
