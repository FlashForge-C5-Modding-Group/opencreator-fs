# Login banner and prompt

SSH and ADB logins get a coloured `user@host:folder#` prompt that follows the current folder. The OpenCreator logo is shown next to
the uptime, IP address, free space in `/usr/data` and hostname, with the printer model (Creator 5 or
Creator 5 Pro, from the stock boot script) underneath.

## Files

| File | What it does |
|---|---|
| `startup/scripts/03-login.sh` | Links `login/profile.sh` as `/etc/profile.d/opencreator.sh` at every boot. `/etc` is writable but a stock update could reset it, so the link is put back each time. |
| `startup/login/profile.sh` | Sourced by `/etc/profile` on login. Interactive logins only: sets the prompt, shows the banner once per session, and switches to Entware's `/opt/bin/bash` if it's installed. |
| `startup/login/banner.sh` | Prints the banner. The logo is generated from `OpenCreator/docs/assets/logo.svg`; each line ends in a `\|` marker so its padding survives editors that strip trailing spaces. |

## Behaviour

- `scp`, `sftp` and `ssh printer command` don't read `/etc/profile`, so scripts and file transfers are
  unaffected.
- Without Entware, the login stays in the stock BusyBox `sh`, which shows the same banner and prompt
  (its prompt shows the home folder as a full path instead of `~`). With Entware, bash is only started
  after `/opt/bin/bash -c :` succeeds, so a broken install can't lock the login out.
- With bash, your own `~/.bash_profile` or `~/.bashrc` runs after this and can set a different `PS1`.
- When `$HOME` isn't writable (root's `/root` is on the read-only root), bash history goes to
  `/usr/data/home/root/.bash_history`.
- The logo uses Unicode block characters, so the terminal needs UTF-8 (Windows Terminal, PuTTY,
  macOS and Linux terminals all default to it).

## Reverting to stock

The hook is in `/etc`, outside `/usr/data`, so a revert has to remove it:

- The installer's rollbacks (`install.sh rollback` and the full stock rollback) and the stock 2.0 USB
  restore delete `/etc/profile.d/opencreator.sh`.
- `profile.sh` also checks `firmwareExe` on every login. If it's FlashForge's ELF binary instead of
  OpenCreator's launcher script, OpenCreator isn't running, so the hook deletes its own link and leaves
  the stock login alone. This also covers a FlashForge firmware update.

To turn it off on one printer, remove `/etc/profile.d/opencreator.sh` and
`startup/scripts/03-login.sh`.
