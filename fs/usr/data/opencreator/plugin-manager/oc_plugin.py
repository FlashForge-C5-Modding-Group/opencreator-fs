#!/usr/bin/env python3
# OpenCreator plugin manager; documented on the OpenCreator docs site, Plugins page.
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

MANIFEST = "opencreator-plugin.json"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
MODULE_RE = re.compile(r"^[a-z0-9_]+\.py$")
KLIPPER_INCLUDE = "[include plugins/*.cfg]"
MOONRAKER_INCLUDE = "[include plugins/moonraker/*.conf]"
KEEP = "00-oc-plugins.conf"
# The OC_PLUGINS dialog, written into the Klipper plugins folder at every sync. Plugin
# ids can't start with "_", so no plugin's own config can take this name.
MENU = "_oc-plugins.cfg"
MENU_MACROS = """
[gcode_macro OC_PLUGINS]
description: Show the installed OpenCreator plugins
variable_plugins: @PLUGINS@
gcode:
  RESPOND TYPE=command MSG="action:prompt_end"
  RESPOND TYPE=command MSG="action:prompt_begin Plugins ({plugins|length})"
  {% if not plugins %}
    RESPOND TYPE=command MSG="action:prompt_text No plugins are installed. Install one over SSH with: oc-plugin install <git URL>"
  {% else %}
    RESPOND TYPE=command MSG="action:prompt_text Tap a plugin for its details."
    {% for plugin in plugins %}
      RESPOND TYPE=command MSG="action:prompt_button {plugin.label}|OC_PLUGIN_INFO ID={plugin.id}|{plugin.color}"
    {% endfor %}
  {% endif %}
  RESPOND TYPE=command MSG="action:prompt_footer_button Close|_OC_PLUGINS_CLOSE"
  RESPOND TYPE=command MSG="action:prompt_show"

[gcode_macro OC_PLUGIN_INFO]
description: Show one plugin's details (ID=plugin id)
gcode:
  {% set found = printer["gcode_macro OC_PLUGINS"].plugins|selectattr("id", "equalto", params.ID|default("")|lower)|list %}
  {% if not found %}
    { action_raise_error("No plugin with ID " ~ params.ID|default("")) }
  {% endif %}
  {% set plugin = found[0] %}
  RESPOND TYPE=command MSG="action:prompt_end"
  RESPOND TYPE=command MSG="action:prompt_begin {plugin.title}"
  {% for line in plugin.lines %}
    RESPOND TYPE=command MSG="action:prompt_text {line}"
  {% endfor %}
  RESPOND TYPE=command MSG="action:prompt_footer_button Back|OC_PLUGINS"
  RESPOND TYPE=command MSG="action:prompt_footer_button Close|_OC_PLUGINS_CLOSE"
  RESPOND TYPE=command MSG="action:prompt_show"

[gcode_macro _OC_PLUGINS_CLOSE]
gcode:
  RESPOND TYPE=command MSG="action:prompt_end"
"""


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
        # a plugin's own files that survive updates and reinstalls, and the startup items' pid files
        self.data = os.path.join(self.plugins, ".data")
        self.run = os.path.join(self.plugins, ".run")
        self.logs = env("OC_PLUGIN_LOGS") or ("/tmp" if soc else os.path.join(self.plugins, ".logs"))


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


def zmod_config(root):
    """A ZMOD plugin's config: <name>.cfg, or en/<name>.cfg if it's translated."""
    pid = os.path.basename(os.path.normpath(root)).lower()
    for sub in ("", "en"):
        folder = os.path.join(root, sub)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if name.lower() == pid + ".cfg" and os.path.isfile(os.path.join(folder, name)):
                return os.path.join(sub, name) if sub else name
    return None


def zmod_manifest(root):
    """ZMOD plugins have no manifest: a repo named after the plugin, with its .cfg. Only the
    config is used; their install/uninstall/update scripts expect ZMOD and are not run."""
    rel = zmod_config(root)
    if rel is None:
        return None
    pid = os.path.basename(os.path.normpath(root)).lower()
    info = git_info(root)
    return {"id": pid, "name": pid, "version": "git " + info["commit"] if info else "zmod",
            "description": "ZMOD plugin: its Klipper config only", "zmod": True, "klipper_config": rel}


def load_manifest(root):
    path = os.path.join(root, MANIFEST)
    try:
        with open(path) as f:
            m = json.load(f)
    except FileNotFoundError:
        m = zmod_manifest(root)
        if m is None:
            raise PluginError("no %s (or ZMOD %s.cfg) in %s"
                              % (MANIFEST, os.path.basename(os.path.normpath(root)), root))
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
    items = m.setdefault("startup", [])
    if not isinstance(items, list):
        raise PluginError("startup must be a list")
    names = set()
    for item in items:
        if not isinstance(item, dict):
            raise PluginError("each startup item must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not ID_RE.match(name) or name in names:
            raise PluginError("startup item names are unique, 2-41 lowercase letters, digits, - or _")
        names.add(name)
        _inside(root, item.get("exec"), "startup %s exec" % name)
        item.setdefault("type", "service")
        if item["type"] not in ("service", "once"):
            raise PluginError("startup %s: type is service or once" % name)
        args = item.setdefault("args", [])
        if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
            raise PluginError("startup %s: args must be a list of strings" % name)
        delay = item.setdefault("delay", 0)
        if not isinstance(delay, int) or not 0 <= delay <= 600:
            raise PluginError("startup %s: delay is 0-600 seconds" % name)
    scripts = m.setdefault("scripts", {})
    if not isinstance(scripts, dict) or not set(scripts) <= {"install", "update", "uninstall"}:
        raise PluginError("scripts can have install, update and uninstall")
    for which, rel in scripts.items():
        _inside(root, rel, "scripts %s" % which)
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
        if name.startswith("."):
            continue
        if os.path.isfile(os.path.join(root, MANIFEST)) or zmod_config(root):
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


# ---- OC_PLUGINS dialog ---------------------------------------------------------

def _prompt_text(value):
    """Text safe inside RESPOND MSG="..." and an action:prompt button."""
    return " ".join(str(value).replace('"', "'").replace("|", "/").split())


def _parts(m):
    out = []
    names = [os.path.splitext(os.path.basename(r))[0] for r in m["klippy_extras"]]
    if names:
        out.append("Klipper module %s" % ", ".join(names))
    if m.get("klipper_config"):
        out.append("Klipper config")
    names = [os.path.splitext(os.path.basename(r))[0] for r in m["moonraker_components"]]
    if names:
        out.append("Moonraker component %s" % ", ".join(names))
    if m.get("moonraker_config"):
        out.append("Moonraker config")
    for item in m.get("startup", []):
        out.append("%s %s" % ("service" if item["type"] == "service" else "boot task", item["name"]))
    if m.get("scripts"):
        out.append("%s script" % "/".join(sorted(m["scripts"])))
    return out


def plugin_summaries(p):
    """Each installed plugin as the OC_PLUGINS dialog shows it."""
    disabled = set(read_state(p)["disabled"])
    out = []
    for root in installed(p):
        folder = os.path.basename(root)
        try:
            m = load_manifest(root)
        except PluginError as e:
            out.append({"id": folder.lower(), "label": "%s (broken)" % folder, "color": "error",
                        "title": folder, "lines": ["This plugin's manifest is broken: %s" % e,
                                                   "Fix or remove it over SSH: oc-plugin remove %s" % folder]})
            continue
        enabled = m["id"] not in disabled
        lines = ["Version %s, %s" % (m["version"], "enabled" if enabled else "disabled")]
        if m.get("author"):
            lines.append("By %s" % m["author"])
        if m.get("description"):
            lines.append(m["description"])
        parts = _parts(m)
        if parts:
            lines.append("Adds: %s" % "; ".join(parts))
        info = git_info(root)
        if info:
            lines.append("From %s (%s@%s)" % (info["origin"], info["branch"], info["commit"]))
        else:
            lines.append("Installed from a local folder")
        if m.get("homepage") and (not info or m["homepage"] not in info["origin"]):
            lines.append(m["homepage"])
        lines.append("ID %s. Manage it over SSH: oc-plugin %s %s, update, remove"
                     % (m["id"], "disable" if enabled else "enable", m["id"]))
        out.append({"id": m["id"], "label": "%s %s%s" % (m["name"], m["version"], "" if enabled else " (disabled)"),
                    "color": "primary" if enabled else "secondary", "title": m["name"], "lines": lines})
    for s in out:
        s["label"], s["title"] = _prompt_text(s["label"]), _prompt_text(s["title"])
        s["lines"] = [_prompt_text(l) for l in s["lines"]]
    return out


def menu_config(p):
    # Klipper reads variable_ values with ast.literal_eval, but its config parser cuts a
    # line at # or ;. Both only occur inside strings here, so escaping them is safe.
    literal = repr(plugin_summaries(p)).replace("#", "\\x23").replace(";", "\\x3b")
    return ("# Written by oc-plugin at every sync; edits are replaced. OC_PLUGINS shows the plugins.\n"
            + MENU_MACROS.replace("@PLUGINS@", literal))


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
        _write(os.path.join(p.klipper_cfg, MENU), menu_config(p))
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


# ---- install scripts and startup items -------------------------------------------
#
# Both run with the plugin folder as the working directory and these in the environment:
#   OC_PLUGIN_ID, OC_PLUGIN_DIR, OC_PLUGIN_DATA (kept across updates and reinstalls),
#   OC_CONFIG_DIR, OC_KLIPPER_DIR, OC_MOONRAKER_URL, and /opt/bin on the PATH.

def plugin_env(p, m, root):
    env = dict(os.environ)
    data = os.path.join(p.data, m["id"])
    os.makedirs(data, exist_ok=True)
    env.update(OC_PLUGIN_ID=m["id"], OC_PLUGIN_DIR=root, OC_PLUGIN_DATA=data, OC_CONFIG_DIR=p.config,
               OC_KLIPPER_DIR=p.klipper, OC_MOONRAKER_URL=p.url, PATH=env.get("PATH", "/usr/bin:/bin") + ":/opt/bin")
    return env


def _command(root, rel, args=()):
    path = os.path.join(root, rel)
    return (["sh", path] if path.endswith(".sh") or not os.access(path, os.X_OK) else [path]) + list(args)


def run_script(p, m, root, which, required=True):
    """Run the plugin's install / update / uninstall script. True when there is none or it worked."""
    rel = m.get("scripts", {}).get(which)
    if not rel:
        return True
    print("Running %s script" % which)
    try:
        r = subprocess.run(_command(root, rel), cwd=root, env=plugin_env(p, m, root), timeout=900,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    except subprocess.TimeoutExpired:
        msg = "%s script took longer than 15 minutes" % which
    else:
        for line in r.stdout.splitlines():
            print("  " + line)
        if r.returncode == 0:
            return True
        msg = "%s script failed (exit %d)" % (which, r.returncode)
    if required:
        raise PluginError(msg)
    print("warning: " + msg)
    return False


def _pidfile(p, pid, name):
    return os.path.join(p.run, "%s.%s.pid" % (pid, name))


def _marker(pid, name):
    return "oc-plugin:%s:%s" % (pid, name)


def item_pid(p, pid, name):
    """The running item's process (group) id, or None. Checks the process is still ours, not a reused pid."""
    try:
        with open(_pidfile(p, pid, name)) as f:
            proc = int(f.read().strip())
        with open("/proc/%d/cmdline" % proc, "rb") as f:
            if _marker(pid, name).encode() in f.read():
                return proc
    except (OSError, ValueError):
        pass
    return None


# The shell that runs a startup item: a service is started again 5 s after it exits (up to a minute
# apart if it keeps failing quickly); a boot task runs once. $0 carries the marker item_pid() looks for.
RUNNER = r"""
sleep "$OC_ITEM_DELAY"
wait=5
while true; do
    echo "=== $(date) starting: $*"
    start=$(date +%s)
    "$@"
    code=$?
    [ "$OC_ITEM_TYPE" = once ] && { echo "=== $(date) done (exit $code)"; exit "$code"; }
    [ $(( $(date +%s) - start )) -gt 60 ] && wait=5
    echo "=== $(date) exited ($code), starting again in $wait s"
    sleep $wait
    [ $wait -lt 60 ] && wait=$((wait * 2))
done
"""


def start_items(p, m, root, only=None):
    for item in m.get("startup", []):
        if only and item["name"] != only:
            continue
        if item_pid(p, m["id"], item["name"]):
            continue
        os.makedirs(p.run, exist_ok=True)
        os.makedirs(p.logs, exist_ok=True)
        env = plugin_env(p, m, root)
        env.update(OC_ITEM_TYPE=item["type"], OC_ITEM_DELAY=str(item["delay"]))
        log = open(os.path.join(p.logs, "oc-plugin-%s-%s.log" % (m["id"], item["name"])), "ab")
        proc = subprocess.Popen(["sh", "-c", RUNNER, _marker(m["id"], item["name"])] + _command(root, item["exec"], item["args"]),
                                cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        log.close()
        _write(_pidfile(p, m["id"], item["name"]), "%d\n" % proc.pid)
        print("Started %s %s" % (m["id"], item["name"]))


def stop_items(p, pid, only=None):
    if not os.path.isdir(p.run):
        return
    for fname in sorted(os.listdir(p.run)):
        if not (fname.startswith(pid + ".") and fname.endswith(".pid")):
            continue
        name = fname[len(pid) + 1:-4]
        if only and name != only:
            continue
        proc = item_pid(p, pid, name)
        if proc:
            for sig, wait in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0)):
                try:
                    os.killpg(proc, sig)
                except OSError:
                    break
                end = time.time() + wait
                while time.time() < end and item_pid(p, pid, name):
                    time.sleep(0.2)
                if not item_pid(p, pid, name):
                    break
            print("Stopped %s %s" % (pid, name))
        try:
            os.unlink(os.path.join(p.run, fname))
        except OSError:
            pass


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
        # named like the source: a ZMOD plugin's id is its repo name
        name = os.path.basename(src.rstrip("/\\"))
        name = (name[:-4] if name.endswith(".git") else name) or "plugin"
        stage = os.path.join(work, name)
        if os.path.isdir(src):
            shutil.copytree(src, stage, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        else:
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
    try:
        run_script(p, load_manifest(dest), dest, "install")
    except PluginError as e:   # a plugin whose install script failed isn't installed
        shutil.rmtree(dest, ignore_errors=True)
        raise PluginError("not installed: %s" % e)
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
    scripts = [s for s in ("install.sh", "uninstall.sh", "update.sh") if os.path.isfile(os.path.join(dest, s))]
    if m.get("zmod") and scripts:
        print("note: ZMOD plugin; its %s were not run (they expect ZMOD)" % ", ".join(scripts))
    if not a.no_restart:
        restart(p, services_for(m))
    start_items(p, m, dest)
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
            stop_items(p, m["id"])
            run_script(p, m, root, "update", required=False)
            if m["id"] not in read_state(p)["disabled"]:
                start_items(p, m, root)
        else:
            print("%s is up to date" % os.path.basename(root))
    for msg in sync(p):
        print("warning: " + msg)
    if not a.no_restart:
        restart(p, services)
    return 0


def cmd_remove(p, a):
    root = find(p, a.id)
    stop_items(p, a.id)
    try:
        m = load_manifest(root)
        services = services_for(m)
        run_script(p, m, root, "uninstall", required=False)
    except PluginError:
        services = {"klipper", "moonraker"}
    shutil.rmtree(root)
    if not a.keep_data:
        shutil.rmtree(os.path.join(p.data, a.id), ignore_errors=True)
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
    if enable:
        start_items(p, m, find(p, a.id))
    else:
        stop_items(p, m["id"])
    return 0


def _with_items(p, a):
    """(id, root, manifest) for a.id, or every enabled plugin with startup items."""
    disabled = set(read_state(p)["disabled"])
    out = []
    for root in ([find(p, a.id)] if a.id else installed(p)):
        try:
            m = load_manifest(root)
        except PluginError as e:
            print("warning: %s: %s" % (os.path.basename(root), e))
            continue
        if m.get("startup") and (a.id or m["id"] not in disabled):
            out.append((m["id"], root, m))
    return out


def cmd_start(p, a):
    for pid, root, m in _with_items(p, a):
        start_items(p, m, root, a.item)
    return 0


def cmd_stop(p, a):
    for pid, root, m in _with_items(p, a):
        stop_items(p, pid, a.item)
    return 0


def cmd_restart(p, a):
    for pid, root, m in _with_items(p, a):
        stop_items(p, pid, a.item)
        start_items(p, m, root, a.item)
    return 0


def cmd_status(p, a):
    rows = _with_items(p, a)
    if not rows:
        print("No plugin has startup items")
    for pid, root, m in rows:
        for item in m["startup"]:
            proc = item_pid(p, pid, item["name"])
            print("%-20s %-12s %-8s %s  log: %s" % (pid, item["name"], item["type"],
                                                    "running (%d)" % proc if proc else "stopped",
                                                    os.path.join(p.logs, "oc-plugin-%s-%s.log" % (pid, item["name"]))))
    return 0


def cmd_boot(p, a):
    """At boot (startup.sh): start every enabled plugin's startup items."""
    a.id, a.item = None, None
    return cmd_start(p, a)


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
    for name, text in (("start", "start startup items"), ("stop", "stop startup items"),
                       ("restart", "restart startup items"), ("status", "show startup items")):
        c = sub.add_parser(name, help="%s (one plugin, or all enabled ones)" % text)
        c.add_argument("id", nargs="?")
        if name != "status":
            c.add_argument("item", nargs="?", help="only this startup item")
    sub.add_parser("boot", help="start every enabled plugin's startup items (run by startup.sh at boot)")
    r.add_argument("--keep-data", action="store_true", help="keep the plugin's data folder")
    for parser in (i, u, r) + tuple(sub.choices[n] for n in ("enable", "disable")):
        parser.add_argument("--no-restart", action="store_true", help="don't restart Klipper/Moonraker")
    a = ap.parse_args(argv)
    p = Paths()
    cmds = {"list": cmd_list, "install": cmd_install, "update": cmd_update, "remove": cmd_remove,
            "enable": cmd_enable, "disable": lambda p, a: cmd_enable(p, a, False), "sync": cmd_sync,
            "start": cmd_start, "stop": cmd_stop, "restart": cmd_restart, "status": cmd_status, "boot": cmd_boot}
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
