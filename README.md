# opencreator-fs
Utilities and Scripts for OpenCreator CFW, also including filesystem changes

## What's this repo for?
File system injection such as putting stuff in printer-data (like config files and such)<br>
Helper scripts for installation of OCR CFW (such as moving around gcodes and stuff)<br>
Detecting mods and dealing with them<br>
Anything else important to the installation of CFW onto the Creator5/5Pro

You probably shouldn't git clone it directly on the printer, as it will be downloaded from releases / mirrors.

## Config updates

`opencreator_updater.py` (run by `99-opencreator-updater.sh`) merges config
template updates into the live config after an OpenCreator update in Fluidd,
keeping your edits and the printer's `SAVE_CONFIG` calibration, and keeps
OpenCreator's own startup files current. Tunnel SBCs run the same file. A
conflict never touches the live config: the merge attempt goes beside it as
`<file>.conflict`. USB reinstalls keep existing configs; the updater reconciles
them. Updated startup scripts take effect after a printer reboot. Details:
[config-docs/UPDATER.md](config-docs/UPDATER.md).

## Releases

Every commit pushed to `main` gets its own GitHub release, numbered `0.1.x` in
order (`v0.1.0`, `v0.1.1`, ...), with the commit message as its notes. A push
with several commits gets one release per commit, oldest first; a merge counts
as one commit. A new branch or a force push only releases the new head. Other
branches get no releases, and neither does a commit with `-nover` in its
message (as its own word, e.g. `fix typo -nover`).
`.github/workflows/release.yml` runs `.github/scripts/release-per-commit.sh`
for this.
