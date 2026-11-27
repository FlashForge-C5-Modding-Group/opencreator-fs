# Creator 5 early boot: `firmware/driver.sh`

Stock's rootfs runs `/etc/init.d/S11module_driver_default` at every boot. It runs `/usr/prog/module/driver.sh` if that file exists. FlashForge never ships one, and their updates only overwrite the files in their own `module.tar`, so the file survives updates. S11 runs after `/usr/prog` is mounted (S09) and long before `app_startup.sh` (S99), which FlashForge updates do overwrite. The rootfs is read-only while the printer runs, but an update can ship a new one (squashfs); the stock one calls `driver.sh`, and a new one dropping that is unlikely. Without the call, `app_startup.sh` boots OpenCreator the old way.

The updater installs `firmware/driver.sh` there whenever it differs. It takes effect at the next boot.

## What it does

1. Mounts `/usr/data` with the same command S21 uses (`mount_mmc_ext4.sh userdata /usr/data/`). S21 then finds it mounted and leaves it alone.
2. USB stick: if one is plugged in, it runs `runRecovery.sh` from its root (as root, from the stick's folder, `RECOVERY_DIR` set to the stick, output appended to `runRecovery.log` on the stick). It also notes a FlashForge update on the stick (`Creator5*.tgz` or `runFirmwareExe.sh`).
3. In the background, starts OpenCreator: it waits for `app_startup.sh` to bind-mount `/usr/prog/etc` over `/etc`, or does that itself after 60 s, loads the modules `app_startup.sh` would (`soc_mcu`, `8821cu`, `gt9xx_touch`; loading one twice just fails with "File exists"), sets the same `LD_LIBRARY_PATH`, and runs `firmwareExe`.

It doesn't start OpenCreator when:

| Condition | Why |
|---|---|
| `firmwareExe` is FlashForge's ELF | stock was flashed or rolled back |
| a FlashForge update is on the stick | `app_startup.sh` flashes it first |
| the control `Update` flag is set | `app_startup.sh` updates the boards first |
| `firmwareExe` has no boot lock | it would start OpenCreator a second time |
| `firmwareExe` is already running | already started |

Then `app_startup.sh` boots it the old way, or boots stock.

Log: `/tmp/early.log`.

## Boot lock

`firmwareExe` starts with `mkdir /tmp/opencreator.boot`. Whichever gets there first, `driver.sh` or `app_startup.sh`, starts OpenCreator. The other one only stays alive: `app_startup.sh` puts FlashForge's `firmwareExe` back when none is running 5 s after it starts it.

## Wi-Fi

After starting Wi-Fi, `firmwareExe` waits until `wlan0` has an address, at most 15 s, then starts OpenCreator (`/tmp/opencreator.log`: `FE: Wi-Fi address after N s`, or `no Wi-Fi address after 15 s, starting anyway`). It doesn't wait when no network is saved.

## Recovery stick

`runRecovery.sh` in the root of a USB stick runs at every boot while the stick is in, before OpenCreator starts:

- as root, with `sh`, from the stick's folder; `RECOVERY_DIR` is the stick;
- even if `/usr/data` didn't mount;
- output is appended to `runRecovery.log` on the stick and goes to `/tmp/early.log`;
- the stick is mounted at `/tmp/recovery-usb` (not `/mnt`, which stock's USB update uses), read-only until a `runRecovery.sh` is found, then read-write;
- the first of `/dev/sda1`..`sda4`, then `/dev/sda`, that has one is used; it waits up to 3 s for a stick to appear.

OpenCreator boots afterwards as usual. A FlashForge update on the same stick still stops the early start.

## Files on the printer

| File | Installed by |
|---|---|
| `/usr/prog/module/driver.sh` | installer (activation step), then the updater from `firmware/driver.sh` (only where `/usr/prog/module` exists); the installer's rollbacks remove it |
| `/usr/prog/PROGRAM/software/firmwareExe` | installer and updater, from `firmware/firmwareExe` (never over FlashForge's ELF) |
| `/usr/data/opencreator/firmware/{driver.sh,firmwareExe}` | updater, the copies it installs from |

User docs: [Early boot and recovery stick](https://github.com/FlashForge-C5-Modding-Group/OpenCreator/blob/main/docs/early-boot.md).
