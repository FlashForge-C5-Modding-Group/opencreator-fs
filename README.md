# opencreator-fs
Utilities and Scripts for OpenCreator CFW, also including filesystem changes

## What's this repo for?
File system injection such as putting stuff in printer-data (like config files and such)<br>
Helper scripts for installation of OCR CFW (such as moving around gcodes and stuff)<br>
Detecting mods and dealing with them<br>
Anything else important to the installation of CFW onto the Creator5/5Pro

You probably shouldn't git clone it directly on the printer, as it will be downloaded from releases / mirrors.

## Config updates

`99-opencreator-updater.sh` merges config templates after an OpenCreator update
in Fluidd, or downloads them at boot when no persistent checkout is installed.
USB reinstalls keep existing configs; the boot updater reconciles them.
Updated startup scripts take effect after a printer reboot.

The updater automatically migrates old installs whose missing or incorrectly
seeded baselines left configs stale. No manual version bump or baseline deletion
is required. It identifies old templates from Git history, ignoring line endings
and the printer's `SAVE_CONFIG` calibration block. Shallow/archive installs may
need network access to obtain that history in a temporary checkout.
Recovery also covers an incorrectly seeded baseline from an intermediate release.
If history is unavailable, affected files stay untouched; checkout installs retry
on the next 60-second poll once networking is available.

Normal merges preserve non-conflicting user edits and live calibration data.
Recovery cannot distinguish a stale config from an intentional exact copy of an
older template; that copy is updated during migration. If a missing baseline
cannot be identified safely, the live file is left untouched and a conflict is
logged in `/tmp/opencreator-updater.log`. Resolve those files manually without
discarding printer-specific settings or calibration, then restart Klipper.
Conflicted updates are not marked as applied and remain eligible for retry.
The log includes diff errors, failed patch output, and publication errors.
