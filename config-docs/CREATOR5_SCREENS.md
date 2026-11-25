# Touchscreen: GrumpyScreen or HelixScreen

The installer puts one touchscreen UI on the printer, GrumpyScreen or HelixScreen. Both can be
installed, but only one runs: `startup/scripts/40-grumpyscreen.sh` and `41-helixscreen.sh` each start
their screen only when its binary is executable, so the other one is kept on the printer, not
executable.

## Switching

Over SSH on the printer:

```sh
oc-switchscreen            # which screen is on, and whether it's running
oc-switchscreen grumpy     # GrumpyScreen on, HelixScreen off
oc-switchscreen helix      # HelixScreen on, GrumpyScreen off
```

It switches right away, no reboot needed, and the choice stays after a reboot. It:

1. refuses while a print is running or paused (HelixScreen needs about 60 MB more memory);
2. makes the chosen screen's binary executable and the other's not;
3. stops both screens and their startup loops, then starts the chosen one's startup script;
4. records the choice in `/usr/data/opencreator/install.json` (`"touchscreen"`), so a later install or
   update keeps it.

A screen that was never installed can't be switched to: install it with the OpenCreator Installer's
touchscreen setting. Each screen's installer also adds it to Moonraker's update manager.

`startup/scripts/10-klipper.sh` (SoC) and `tunneled/tunneled.sh` (tunneled) link the command into
`/opt/bin` at boot. Until a printer has booted once with it, run it as
`sh /usr/data/opencreator/startup/commands/oc-switchscreen`.
