# Moonraker checkout repair

`startup/moonraker-repo.sh` keeps `/usr/prog/moonraker/moonraker` in a state that Moonraker's update manager accepts, so the Moonraker entry in Mainsail and Fluidd doesn't show **Invalid** ("Failed to detect git branch", "Failed to detect repo url", "Detached HEAD detected").

A copy can get like that if it was cloned from a tag (which leaves it detached, with a fetch for that one tag), set up without an `origin`, or put in place by another mod.

## When it runs

| When | What |
| --- | --- |
| At boot, from `20-msmr.sh`, before Moonraker starts | `repair` |
| Before each Moonraker start, after plugins are synced | `exclude` |
| When the updater installs new startup files | `live`: both, without downloading anything |

It logs to `/tmp/opencreator.log` (or the updater's log), and only when it changes something.

## What it fixes

- **No `origin`, or another one:** `origin` is set to `https://github.com/Arksine/moonraker.git`.
- **A fetch for one tag:** `origin` fetches `master`.
- **Detached HEAD:** `master` is made at the same commit and checked out. No files change.
- **`master` not tracking anything:** it tracks `origin/master`.
- **A checkout with another owner:** it's added to git's `safe.directory`.
- **Not a git checkout at all, or one git can't read:** Moonraker is downloaded again at boot and swapped in, and the timelapse link is made again. If the download fails, the old copy is kept and it tries again at the next boot. Its Python environment is left alone.

A branch other than `master` that someone checked out on purpose is kept. Changed tracked files are left alone too: Moonraker's own **Recover** button can reset those once the remote is valid.

## Untracked files

OpenCreator's components (`opencreator_3mf.py`, `opencreator_machine.py`), timelapse's, and plugins' are links into `moonraker/components`. Moonraker would list them as "untracked source files". `exclude` lists every untracked link there in `.git/info/exclude`, between `# opencreator links begin` and `# opencreator links end`, so they stop showing. Real untracked files still show.
