# Creator 5 MCU startup and wake

## SoC coprocessor

`firmware/firmwareExe` loads and boots the SoC's coprocessor before anything else, the same way stock `klipper/start.sh` does:

```sh
cmd_mcu write_firmware /usr/prog/libmcu-bare.bin
cmd_mcu bootup
```

## Boot-stage wake: `startup/scripts/08-mcu-wake.sh`

The heaterboard, eboard and levelboard come up in a resident boot stage after power-on and after every reset, including `FIRMWARE_RESTART`. Klipper can't connect until they are released. This script does that on the SoC. It is a shell port of the wake in `opencreator-tunnel/printer/c5_bridge.py`.

- It follows `/usr/data/opencreator/klipper/logs/printer.log`. When Klipper logs `mcu '<name>': Timeout on connect` for one of the boards, the identify went unanswered and the board needs waking.
- It pauses Klipper (`SIGSTOP`) so the two don't share the UART, saves the port settings, runs the wake and puts the settings back. Then it resumes Klipper (`SIGCONT`), and Klipper's next connect attempt succeeds.
- Wake handshake, per parity in order: switch to 115200 8N1 or 8E1, wait up to 4 s for `Ready`, send `A` up to three times, wait for `0x06`. If the banner came but the ACK was lost, it sends an identify at the Klipper baud and accepts any reply frame.
- A board isn't woken again within 7 s of its last wake. That skips the stale timeout Klipper logs right after resuming.
- Only one copy runs (lock `/tmp/c5-mcu-wake.lock`).
- Log: `/usr/data/logs/c5-mcu-wake.log`.

| MCU | UART | Klipper baud | Parity order |
|---|---|---|---|
| `eheaterboard` (or `heaterboard`) | `/dev/ttyS4` | 230400 | N, E |
| `eboard` | `/dev/ttyS5` | 460800 | E, N |
| `levelboard` | `/dev/ttyS7` | 230400 | N, E |

The mainboard (`mcu`, `/dev/ttyS2`) has no boot stage and is left alone.

In tunneled mode `firmwareExe` hands off to `tunneled/tunneled.sh` (when it is executable) instead of `startup.sh`. This script doesn't run there; the socat bridge (`/usr/prog/c5-tunnel-socat/c5_socat.py`) does the wake.

## Startup

`firmwareExe` runs `startup.sh` once. `startup.sh` starts every script in `startup/scripts/` in the background and returns. `firmwareExe` then stays alive, because `app_startup.sh` puts the stock binary back if no `firmwareExe` process is running. `10-klipper.sh` restarts Klippy 3 s after it exits.
