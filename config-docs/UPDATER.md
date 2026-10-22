# OpenCreator Updater

One updater keeps every OpenCreator install's configs current:
`fs/usr/data/opencreator/startup/opencreator_updater.py`. The printer SoC runs it
through `startup/scripts/99-opencreator-updater.sh`. Tunnel SBCs run an identical
copy in opencreator-tunnel's `pi/opencreator-updater/`, through `update.py`. Change
it here and copy it there; opencreator-tunnel's tests fail while the two differ.

## What it does

When a new template comes in (an OpenCreator update in Fluidd or Mainsail), it
merges the template's changes into your live config. It keeps:

- **your own edits**, unless the update changes the same lines;
- **the printer's calibration**: the `SAVE_CONFIG` block (input shaper, PID,
  meshes, skew) is never compared or merged, only carried along;
- **line endings**: a config that picked up Windows (CRLF) line endings still
  merges. It's written back with plain line endings.

| | Printer SoC | Tunnel SBC |
| --- | --- | --- |
| Templates | `fs/usr/data/config/*.cfg` in the opencreator-fs checkout (`/usr/data/opencreator/opencreator-fs`) | `pi/config/*.cfg` and `pi/config/.fluidd-theme/*` in the opencreator-tunnel checkout |
| Live config | `/usr/data/opencreator/klipper/config` | `~/printer_data/config` (`OC_UPDATER_CONFIG_DIR`) |
| When | Watches the checkout every 60 s; applies each new commit | Once, each time Moonraker's update manager pulls opencreator-tunnel |
| Also | Updates OpenCreator's own folders (startup scripts, firmwareExe launcher, Moonraker components, Fluidd layout, plugin manager, nginx snippets) | Pulls Klipper (`OC_UPDATER_KLIPPER_DIR`) |
| Log | `/tmp/opencreator-updater.log` | the service's journal (`journalctl -u opencreator-updater`) |

Afterwards it restarts Klipper, but only once nothing is printing or paused, and
only if something changed and nothing conflicted.

## How a config is merged

For each template it keeps a copy of the last version it applied, the **base**
(`<config>/.opencreator-updater/base/`). Then:

1. **No live file:** the template is installed as is.
2. **Template unchanged since the base:** nothing to do. Your edits stay.
3. **Live file already matches the new template:** only the base is updated.
4. **Otherwise:** a three-way merge (`git merge-file`) of base, new template and your
   live file. Changes from both sides are kept, and the same change made on both sides
   is no conflict. The live file and its base are replaced together; if the base can't
   be written, the live file goes back to what it was.
5. **Both changed the same lines:** a conflict. The live file is left exactly as it was,
   and the attempted merge, with `<<<<<<<` markers, goes beside it as `<file>.conflict`.
   Resolve it by hand, copy it over, and restart Klipper.

**No base yet** (an old install, or a file the updater hasn't seen): it looks
through the template's git history for a version your live file is an unedited
copy of, and merges from that. A shallow checkout is looked through first, then a
temporary full clone. Without an exact match, it doesn't guess: the file is a
conflict, and nothing is touched.

A run counts as applied (`.opencreator-updater/applied-commit`) only when every
config merged. A conflict leaves it unapplied, so the next check tries again.

**Migration** (`.opencreator-updater/merge-version`, now 2): some earlier installs
saved bases that weren't really what the live file came from. Once per version
bump, every changed config is checked against git history again before merging.

**`printer.model.cfg`:** `printer.base.cfg` only includes the Creator 5 Pro's
chamber heater and fans through this file. If it's missing, the updater writes it:
for the model in the stock boot script on the SoC (Pro if unknown), and Pro on an
SBC, since installs from before the file existed had that hardware.

## OpenCreator's own folders (SoC)

The first run after install only notes the checkout's commit
(`/usr/data/opencreator/.loopscript-commit`). Each later commit:

- `startup`, `firmware`, `tunneled`, `moonraker`, `fluidd`, `plugin-manager` and `mcu-flash` are
  each copied next to the live folder and the new files laid over the copy. Files you
  added stay. A file an earlier version installed and the new one dropped is removed,
  unless you changed it. `/usr/data/opencreator/.installed/<folder>.md5` lists what was
  installed; the installer writes the same list. The copy is then swapped in.
  Running scripts keep their old copy, so new startup scripts run from the next boot.
- `version.txt` and the nginx snippets in `/usr/data/nginx/conf.d` are updated.
- `/usr/prog/PROGRAM/software/firmwareExe` is updated only while it's the OpenCreator
  launcher, never over FlashForge's own binary, so a rollback to stock stays.

If the opencreator-fs checkout is missing (installs from before it was kept), the
updater clones it, and Moonraker's update manager uses it from then on.

## MCU firmware (SoC)

Every minute the updater also compares `mcu-firmware/` in the checkout with what it last
flashed, and updates the boards live with `oc-mcu-flash` (see `CREATOR5_LIVE_MCU_FLASH.md`)
when they differ.

- `mcu-firmware/` holds any of `eBoard.hex`, `heaterBoard.hex`, `levelBoard.hex` and
  `mainBoardGD.hex`, plus `SHA256SUMS` (`sha256sum *.hex > SHA256SUMS`). If any listed file
  doesn't match its sum, nothing is flashed. An optional `VERSION` holds the Kalico version
  the boards report (`mcu_version`, e.g. `ab62660c7`).
- A board is out of date when its file's sha256 differs from the one recorded after its last
  successful flash (`.opencreator-updater/mcu-flashed.json` in the config folder). With
  `VERSION`, a board already reporting it is only recorded, so a printer that is already
  current isn't flashed again.
- Only the out-of-date boards are flashed, never during a print.
- A failed set of files is noted in `.opencreator-updater/mcu-failed`, reported in the
  console and not retried until the files change. The eBoard and heaterBoard need firmware
  with `c5_reset_bootloader` (flashed once from USB) before they can be updated live.
- `soc --once` flashes too, unless given `--no-mcu`.

## Running it by hand

```sh
# SoC: apply the checkout once and log to the terminal
/usr/data/python-hf/bin/python3 /usr/data/opencreator/startup/opencreator_updater.py soc --once --stdout
# SBC
python3 ~/opencreator-tunnel/pi/opencreator-updater/update.py
```

To try a template update without touching the live config, give it a copy of the
config folder (and of the checkout): `--config-dir COPY --repo CHECKOUT_COPY
--no-restart`. A copied config keeps its `.opencreator-updater` state, so it merges
exactly as the live one would.
