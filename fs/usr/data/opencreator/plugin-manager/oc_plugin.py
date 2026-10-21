#!/usr/bin/env python3
# OpenCreator plugin manager; documented on the OpenCreator docs site, Plugins page.
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

MANIFEST = "opencreator-plugin.json"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
MODULE_RE = re.compile(r"^[a-z0-9_]+\.py$")
KLIPPER_INCLUDE = "[include plugins/*.cfg]"
MOONRAKER_INCLUDE = "[include plugins/moonraker/*.conf]"
KEEP = "00-oc-plugins.conf"


class PluginError(Exception):
    pass


class Paths:
    def __init__(self):
        soc = os.path.isdir("/usr/data/opencreator/klipper/config")
        home = os.path.expanduser("~")
        env = os.environ.get
        self.plugins = env("OC_PLUGINS_DIR") or (
            "/usr/data/opencreator/plugins" if soc else os.path.join(home, "opencreator-plugins"))
        self.klipper = env("OC_KLIPPER_DIR") or (
            "/usr/data/opencreator/klipper/klipper" if soc else os.path.join(home, "klipper"))
        self.config = env("OC_CONFIG_DIR") or (
            "/usr/data/opencreator/klipper/config" if soc else os.path.join(home, "printer_data", "config"))
        self.moonraker = env("OC_MOONRAKER_DIR") or (
            "/usr/prog/moonraker/moonraker" if soc else os.path.join(home, "moonraker"))
        self.url = env("OC_MOONRAKER_URL") or "http://127.0.0.1:7125"
        # Kalico loads third-party modules from klippy/plugins (git-ignored, and it refuses names that
        # clash with its own extras); mainline Klipper only has klippy/extras.
        self.builtin = os.path.join(self.klipper, "klippy", "extras")
        kalico = os.path.join(self.klipper, "klippy", "plugins")
        self.extras = kalico if os.path.isdir(kalico) else self.builtin
        self.components = os.path.join(self.moonraker, "moonraker", "components")
        self.klipper_cfg = os.path.join(self.config, "plugins")
        self.moonraker_cfg = os.path.join(self.config, "plugins", "moonraker")
        self.state = os.path.join(self.plugins, "state.json")


# ---- manifests ---------------------------------------------------------------

def _inside(root, rel, what):
    if not isinstance(rel, str) or not rel or os.path.isabs(rel):
        raise PluginError("%s must be a relative path" % what)
    full = os.path.realpath(os.path.join(root, rel))
    if os.path.commonpath([full, os.path.realpath(root)]) != os.path.realpath(root):
        raise PluginError("%s %r points outside the plugin" % (what, rel))
    if not os.path.isfile(full):
        raise PluginError("%s %r does not exist" % (what, rel))
    return full


def load_manifest(root):
    path = os.path.join(root, MANIFEST)
    try:
        with open(path) as f:
            m = json.load(f)
    except FileNotFoundError:
        raise PluginError("no %s in %s" % (MANIFEST, root))
    except ValueError as e:
        raise PluginError("%s is not valid JSON: %s" % (MANIFEST, e))
    if not isinstance(m, dict):
        raise PluginError("%s must be a JSON object" % MANIFEST)
    pid = m.get("id")
    if not isinstance(pid, str) or not ID_RE.match(pid):
        raise PluginError("id must be 2-41 lowercase letters, digits, - or _")
    for key in ("name", "version"):
        if not isinstance(m.get(key), str) or not m[key]:
            raise PluginError("%s is required" % key)
    for key in ("klippy_extras", "moonraker_components"):
        files = m.setdefault(key, [])
        if not isinstance(files, list):
            raise PluginError("%s must be a list" % key)
        for rel in files:
            _inside(root, rel, key)
            if not MODULE_RE.match(os.path.basename(rel)):
                raise PluginError("%s %r: module names are lowercase letters, digits and _ ending in .py"
                                  % (key, rel))
    for key in ("klipper_config", "moonraker_config"):
        if m.get(key) is not None:
            _inside(root, m[key], key)
    services = m.setdefault("restart", [])
    if not isinstance(services, list) or not set(services) <= {"klipper", "moonraker"}:
        raise PluginError("restart must list klipper and/or moonraker")
    return m


# ---- state -------------------------------------------------------------------

def read_state(p):
    try:
        with open(p.state) as f:
            s = json.load(f)
    except (FileNotFoundError, ValueError):
        s = {}
    s.setdefault("disabled", [])
    return s


def write_state(p, s):
    _write(p.state, json.dumps(s, indent=2, sort_keys=True) + "\n")


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".oc-")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def installed(p):
    out = []
    if not os.path.isdir(p.plugins):
        return out
    for name in sorted(os.listdir(p.plugins)):
        root = os.path.join(p.plugins, name)
        if os.path.isfile(os.path.join(root, MANIFEST)):
            out.append(root)
    return out


# ---- git ---------------------------------------------------------------------

def git(*args, cwd=None):
    env = dict(os.environ)
    env["PATH"] = env.get("PATH", "") + ":/opt/bin"
    env["GIT_TERMINAL_PROMPT"] = "0"
    r = subprocess.run(["git"] + list(args), cwd=cwd, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    if r.returncode:
        raise PluginError("git %s failed: %s" % (args[0], r.stdout.strip()))
    return r.stdout.strip()


def git_info(root):
    if not os.path.isdir(os.path.join(root, ".git")):
        return None
    try:
        return {"origin": git("remote", "get-url", "origin", cwd=root),
                "branch": git("rev-parse", "--abbrev-ref", "HEAD", cwd=root),
                "commit": git("rev-parse", "--short", "HEAD", cwd=root)}
    except PluginError:
        return None


# ---- linking -----------------------------------------------------------------

def _owned(link, p):
    """A symlink this manager made: it points into the plugins folder."""
    if not os.path.islink(link):
        return False
    target = os.path.realpath(link)
    plugins = os.path.realpath(p.plugins)
    return os.path.commonpath([target, plugins]) == plugins


def _link(target, link, p):
    if os.path.lexists(link) and not _owned(link, p):
        raise PluginError("%s already exists and is not a plugin link; not replacing it" % link)
    if os.path.islink(link) and os.readlink(link) == target:
        return
    tmp = link + ".oc-new"
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, link)


def _prune(folder, wanted, p):
    if not os.path.isdir(folder):
        return
    for name in os.listdir(folder):
        link = os.path.join(folder, name)
        if link not in wanted and _owned(link, p):
            os.unlink(link)


def _ensure_include(path, line):
    """Add LINE to a config that doesn't include it yet (before Klipper's SAVE_CONFIG block)."""
    if not os.path.isfile(path):
        return False
    with open(path) as f:
        text = f.read()
    if any(l.strip() == line for l in text.splitlines()):
        return False
    mark = text.find("#*# <")
    if mark < 0:
        text = text.rstrip("\n") + "\n\n" + line + "\n"
    else:
        text = text[:mark].rstrip("\n") + "\n\n" + line + "\n\n" + text[mark:]
    _write(path, text)
    return True


def update_manager_section(root, m):
    info = git_info(root)
    if not info or info["branch"] == "HEAD":
        return ""
    services = ["klipper"] + (["moonraker"] if m["moonraker_components"] else [])
    return ("[update_manager oc-plugin-%s]\ntype: git_repo\npath: %s\norigin: %s\n"
            "primary_branch: %s\nmanaged_services: %s\nis_system_service: False\n"
            % (m["id"], root, info["origin"], info["branch"], " ".join(services)))


def sync(p, klipper=True, moonraker=True):
    """Make the links and config includes match the enabled plugins. Safe to run any time."""
    disabled = set(read_state(p)["disabled"])
    extras, components, kcfg, mcfg = set(), set(), set(), set()
    problems = []
    for root in installed(p):
        try:
            m = load_manifest(root)
        except PluginError as e:
            problems.append("%s: %s" % (os.path.basename(root), e))
            continue
        if m["id"] in disabled:
            continue
        try:
            if klipper:
                if os.path.isdir(p.extras):
                    for rel in m["klippy_extras"]:
                        name = os.path.basename(rel)
                        if p.extras != p.builtin and os.path.lexists(os.path.join(p.builtin, name)):
                            raise PluginError("Klippy already has a module called %s" % name)
                        link = os.path.join(p.extras, name)
                        _link(os.path.join(root, rel), link, p)
                        extras.add(link)
                if m.get("klipper_config"):
                    link = os.path.join(p.klipper_cfg, m["id"] + ".cfg")
                    os.makedirs(p.klipper_cfg, exist_ok=True)
                    _link(os.path.join(root, m["klipper_config"]), link, p)
                    kcfg.add(link)
            if moonraker:
                if os.path.isdir(p.components):
                    for rel in m["moonraker_components"]:
                        link = os.path.join(p.components, os.path.basename(rel))
                        _link(os.path.join(root, rel), link, p)
                        components.add(link)
                text = ""
                if m.get("moonraker_config"):
                    with open(os.path.join(root, m["moonraker_config"])) as f:
                        text = f.read().rstrip("\n") + "\n\n"
                text += update_manager_section(root, m)
                if text:
                    path = os.path.join(p.moonraker_cfg, m["id"] + ".conf")
                    _write(path, "# Written by oc-plugin from %s; edits are replaced.\n%s" % (root, text))
                    mcfg.add(path)
        except PluginError as e:
            problems.append("%s: %s" % (m["id"], e))
    if klipper:
        _prune(p.extras, extras, p)
        _prune(p.klipper_cfg, kcfg, p)
        _ensure_include(os.path.join(p.config, "printer.cfg"), KLIPPER_INCLUDE)
    if moonraker:
        _prune(p.components, components, p)
        if os.path.isdir(p.moonraker_cfg):
            for name in os.listdir(p.moonraker_cfg):
                path = os.path.join(p.moonraker_cfg, name)
                if name.endswith(".conf") and name != KEEP and path not in mcfg:
                    os.unlink(path)
        # Moonraker refuses an include that matches no files (Klipper doesn't)
        keep = os.path.join(p.moonraker_cfg, KEEP)
        if not os.path.isfile(keep):
            _write(keep, "# Keeps [include plugins/moonraker/*.conf] matching while no plugin has Moonraker config.\n")
        _ensure_include(os.path.join(p.config, "moonraker.conf"), MOONRAKER_INCLUDE)
    return problems


# ---- restarts ----------------------------------------------------------------

def _api(p, path, method="GET"):
    req = urllib.request.Request(p.url + path, method=method, data=b"" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def restart(p, services):
    if not services:
        return
    try:
        state = _api(p, "/printer/objects/query?print_stats=state")["result"]["status"]["print_stats"]["state"]
    except Exception:
        state = None
    if state in ("printing", "paused"):
        print("Printer is %s: restart %s yourself when it's done." % (state, " and ".join(services)))
        return
    for s in ("klipper", "moonraker"):
        if s in services:
            try:
                _api(p, "/machine/services/restart?service=" + s, "POST")
                print("Restarting %s" % s)
            except Exception as e:
                print("Couldn't restart %s (%s); restart it yourself." % (s, e))


def services_for(m):
    out = set(m["restart"])
    if m["klippy_extras"] or m.get("klipper_config"):
        out.add("klipper")
    if m["moonraker_components"] or m.get("moonraker_config"):
        out.add("moonraker")
    return out


# ---- commands ----------------------------------------------------------------

def find(p, pid):
    for root in installed(p):
        try:
            if load_manifest(root)["id"] == pid:
                return root
        except PluginError:
            if os.path.basename(root) == pid:
                return root
    raise PluginError("%s is not installed" % pid)


def cmd_list(p, a):
    disabled = set(read_state(p)["disabled"])
    roots = installed(p)
    if not roots:
        print("No plugins installed (%s)" % p.plugins)
    for root in roots:
        try:
            m = load_manifest(root)
        except PluginError as e:
            print("%-20s BROKEN  %s" % (os.path.basename(root), e))
            continue
        info = git_info(root)
        print("%-20s %-10s %-9s %s%s" % (m["id"], m["version"], "disabled" if m["id"] in disabled else "enabled",
                                         m["name"], "  [%s@%s]" % (info["branch"], info["commit"]) if info else ""))
    return 0


def cmd_install(p, a):
    os.makedirs(p.plugins, exist_ok=True)
    work = tempfile.mkdtemp(dir=p.plugins, prefix=".install-")
    try:
        src = a.source
        if os.path.isdir(src):
            stage = os.path.join(work, "plugin")
            shutil.copytree(src, stage, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        else:
            stage = os.path.join(work, "plugin")
            # full history: Moonraker's update manager doesn't like shallow clones
            args = ["clone"] + (["--branch", a.ref] if a.ref else []) + [src, stage]
            git(*args)
        m = load_manifest(stage)
        dest = os.path.join(p.plugins, m["id"])
        if os.path.exists(dest):
            raise PluginError("%s is already installed; use oc-plugin update %s" % (m["id"], m["id"]))
        os.rename(stage, dest)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    s = read_state(p)
    if m["id"] in s["disabled"]:
        s["disabled"].remove(m["id"])
        write_state(p, s)
    problems = sync(p)
    mine = [msg for msg in problems if msg.startswith(m["id"] + ":")]
    if mine:   # half-linked is worse than not installed
        shutil.rmtree(dest)
        sync(p)
        raise PluginError("not installed: " + "; ".join(msg.split(": ", 1)[1] for msg in mine))
    for msg in problems:
        print("warning: " + msg)
    print("Installed %s %s" % (m["name"], m["version"]))
    if not a.no_restart:
        restart(p, services_for(m))
    return 0


def cmd_update(p, a):
    roots = installed(p) if a.id is None else [find(p, a.id)]
    services = set()
    for root in roots:
        if not git_info(root):
            print("%s: not a git checkout, reinstall it to update" % os.path.basename(root))
            continue
        before = git("rev-parse", "HEAD", cwd=root)
        git("pull", "--ff-only", cwd=root)
        if git("rev-parse", "HEAD", cwd=root) != before:
            m = load_manifest(root)
            print("Updated %s to %s" % (m["id"], m["version"]))
            services |= services_for(m)
        else:
            print("%s is up to date" % os.path.basename(root))
    for msg in sync(p):
        print("warning: " + msg)
    if not a.no_restart:
        restart(p, services)
    return 0


def cmd_remove(p, a):
    root = find(p, a.id)
    try:
        services = services_for(load_manifest(root))
    except PluginError:
        services = {"klipper", "moonraker"}
    shutil.rmtree(root)
    s = read_state(p)
    if a.id in s["disabled"]:
        s["disabled"].remove(a.id)
        write_state(p, s)
    sync(p)
    print("Removed %s" % a.id)
    if not a.no_restart:
        restart(p, services)
    return 0


def cmd_enable(p, a, enable=True):
    m = load_manifest(find(p, a.id))
    s = read_state(p)
    if enable and m["id"] in s["disabled"]:
        s["disabled"].remove(m["id"])
    elif not enable and m["id"] not in s["disabled"]:
        s["disabled"].append(m["id"])
    write_state(p, s)
    for msg in sync(p):
        print("warning: " + msg)
    print("%s %s" % ("Enabled" if enable else "Disabled", m["id"]))
    if not a.no_restart:
        restart(p, services_for(m))
    return 0


def cmd_sync(p, a):
    problems = sync(p, klipper=a.only != "moonraker", moonraker=a.only != "klipper")
    for msg in problems:
        print("warning: " + msg)
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="oc-plugin", description="Install and manage OpenCreator plugins.")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="show installed plugins")
    i = sub.add_parser("install", help="install from a git URL or a local folder")
    i.add_argument("source")
    i.add_argument("--ref", help="branch or tag to install")
    u = sub.add_parser("update", help="pull the newest version of one or all plugins")
    u.add_argument("id", nargs="?")
    r = sub.add_parser("remove", help="uninstall a plugin")
    r.add_argument("id")
    for name in ("enable", "disable"):
        e = sub.add_parser(name, help="%s a plugin without removing it" % name)
        e.add_argument("id")
    s = sub.add_parser("sync", help="redo the links and includes (run at every Klippy/Moonraker start)")
    s.add_argument("--only", choices=("klipper", "moonraker"))
    for parser in (i, u, r) + tuple(sub.choices[n] for n in ("enable", "disable")):
        parser.add_argument("--no-restart", action="store_true", help="don't restart Klipper/Moonraker")
    a = ap.parse_args(argv)
    p = Paths()
    cmds = {"list": cmd_list, "install": cmd_install, "update": cmd_update, "remove": cmd_remove,
            "enable": cmd_enable, "disable": lambda p, a: cmd_enable(p, a, False), "sync": cmd_sync}
    if a.cmd not in cmds:
        ap.print_help()
        return 2
    try:
        return cmds[a.cmd](p, a)
    except PluginError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
