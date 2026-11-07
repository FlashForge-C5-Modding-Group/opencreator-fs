import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "fs" / "usr" / "data" / "opencreator" / "plugin-manager" / "oc_plugin.py"
SPEC = importlib.util.spec_from_file_location("oc_plugin", MODULE)
oc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oc)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class PluginTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        t = self.tmp
        (t / "klipper" / "klippy" / "extras").mkdir(parents=True)
        (t / "klipper" / "klippy" / "plugins").mkdir()
        write(t / "klipper" / "klippy" / "extras" / "probe.py", "")
        (t / "moonraker" / "moonraker" / "components").mkdir(parents=True)
        write(t / "config" / "printer.cfg", "[include printer.base.cfg]\n\n#*# <---------------------- SAVE_CONFIG\n#*# [probe]\n")
        write(t / "config" / "moonraker.conf", "[server]\n")
        env = {"OC_PLUGINS_DIR": str(t / "plugins"), "OC_KLIPPER_DIR": str(t / "klipper"),
               "OC_CONFIG_DIR": str(t / "config"), "OC_MOONRAKER_DIR": str(t / "moonraker"),
               "OC_MOONRAKER_URL": "http://127.0.0.1:1"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.src = t / "src"
        self.make_plugin(self.src)

    def make_plugin(self, root, pid="hello", module="oc_hello.py"):
        write(root / "klippy" / module, "def load_config(config):\n    return None\n")
        write(root / "config" / "hello.cfg", "[oc_hello]\n")
        write(root / "moonraker" / module, "def load_component(config):\n    return None\n")
        write(root / "moonraker" / "hello.conf", "[oc_hello]\n")
        write(root / oc.MANIFEST, json.dumps({
            "id": pid, "name": "Hello", "version": "1.0.0",
            "klippy_extras": ["klippy/" + module], "klipper_config": "config/hello.cfg",
            "moonraker_components": ["moonraker/" + module], "moonraker_config": "moonraker/hello.conf"}))

    def run_cli(self, *args):
        return oc.main(list(args))

    def test_install_links_everything(self):
        self.assertEqual(self.run_cli("install", str(self.src), "--no-restart"), 0)
        t = self.tmp
        link = t / "klipper" / "klippy" / "plugins" / "oc_hello.py"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (t / "plugins" / "hello" / "klippy" / "oc_hello.py").resolve())
        self.assertTrue((t / "moonraker" / "moonraker" / "components" / "oc_hello.py").is_symlink())
        self.assertTrue((t / "config" / "plugins" / "hello.cfg").is_symlink())
        self.assertIn("[oc_hello]", (t / "config" / "plugins" / "moonraker" / "hello.conf").read_text())
        printer = (t / "config" / "printer.cfg").read_text()
        # the include goes before SAVE_CONFIG, once
        self.assertLess(printer.index(oc.KLIPPER_INCLUDE), printer.index("#*# <"))
        self.run_cli("sync")
        self.assertEqual((t / "config" / "printer.cfg").read_text().count(oc.KLIPPER_INCLUDE), 1)
        self.assertIn(oc.MOONRAKER_INCLUDE, (t / "config" / "moonraker.conf").read_text())

    def test_disable_and_remove_unlink(self):
        self.run_cli("install", str(self.src), "--no-restart")
        t = self.tmp
        link = t / "klipper" / "klippy" / "plugins" / "oc_hello.py"
        self.run_cli("disable", "hello", "--no-restart")
        self.assertFalse(os.path.lexists(link))
        self.assertFalse((t / "config" / "plugins" / "hello.cfg").exists())
        self.run_cli("enable", "hello", "--no-restart")
        self.assertTrue(link.is_symlink())
        self.run_cli("remove", "hello", "--no-restart")
        self.assertFalse(os.path.lexists(link))
        self.assertFalse((t / "plugins" / "hello").exists())
        self.assertFalse((t / "config" / "plugins" / "moonraker" / "hello.conf").exists())
        # Moonraker's include must still match a file
        self.assertTrue((t / "config" / "plugins" / "moonraker" / oc.KEEP).is_file())

    def test_refuses_name_of_builtin_module(self):
        other = self.tmp / "clash"
        self.make_plugin(other, pid="clash", module="probe.py")
        self.assertEqual(self.run_cli("install", str(other), "--no-restart"), 1)
        self.assertFalse(os.path.lexists(self.tmp / "klipper" / "klippy" / "plugins" / "probe.py"))
        # rolled back: nothing of it is left
        self.assertFalse((self.tmp / "plugins" / "clash").exists())
        self.assertFalse((self.tmp / "config" / "plugins" / "clash.cfg").exists())

    def test_never_replaces_files_it_did_not_make(self):
        own = self.tmp / "klipper" / "klippy" / "plugins" / "oc_hello.py"
        write(own, "# someone's own module\n")
        self.assertEqual(self.run_cli("install", str(self.src), "--no-restart"), 1)
        self.assertEqual(own.read_text(), "# someone's own module\n")
        self.assertFalse((self.tmp / "plugins" / "hello").exists())

    def test_rejects_paths_outside_the_plugin(self):
        data = json.loads((self.src / oc.MANIFEST).read_text())
        write(self.tmp / "outside.cfg", "")
        data["klipper_config"] = "../outside.cfg"
        (self.src / oc.MANIFEST).write_text(json.dumps(data))
        with self.assertRaisesRegex(oc.PluginError, "outside"):
            oc.load_manifest(str(self.src))

    def test_rejects_bad_id(self):
        data = json.loads((self.src / oc.MANIFEST).read_text())
        data["id"] = "../evil"
        (self.src / oc.MANIFEST).write_text(json.dumps(data))
        self.assertEqual(self.run_cli("install", str(self.src), "--no-restart"), 1)

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_git_install_adds_update_manager_and_updates(self):
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.src)], check=True)
        subprocess.run(g + ["-C", str(self.src), "add", "-A"], check=True)
        subprocess.run(g + ["-C", str(self.src), "commit", "-qm", "1"], check=True)
        self.assertEqual(self.run_cli("install", "file://" + str(self.src), "--no-restart"), 0)
        conf = (self.tmp / "config" / "plugins" / "moonraker" / "hello.conf").read_text()
        self.assertIn("[update_manager oc-plugin-hello]", conf)
        self.assertIn("primary_branch: main", conf)
        self.assertIn("managed_services: klipper moonraker", conf)
        data = json.loads((self.src / oc.MANIFEST).read_text())
        data["version"] = "1.1.0"
        (self.src / oc.MANIFEST).write_text(json.dumps(data))
        subprocess.run(g + ["-C", str(self.src), "commit", "-qam", "2"], check=True)
        self.assertEqual(self.run_cli("update", "hello", "--no-restart"), 0)
        self.assertEqual(oc.load_manifest(str(self.tmp / "plugins" / "hello"))["version"], "1.1.0")

    # ---- ZMOD plugins

    def test_installs_a_zmod_plugin_by_its_cfg(self):
        src = self.tmp / "zsrc" / "g28_tenz"
        write(src / "g28_tenz.cfg", "[gcode_macro G28_TENZ]\ngcode:\n  G28\n")
        write(src / "install.sh", "#!/bin/sh\nexit 1\n")
        self.assertEqual(self.run_cli("install", str(src), "--no-restart"), 0)
        link = self.tmp / "config" / "plugins" / "g28_tenz.cfg"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (self.tmp / "plugins" / "g28_tenz" / "g28_tenz.cfg").resolve())
        _, plugins = self.menu()
        self.assertEqual([(p["id"], p["label"]) for p in plugins], [("g28_tenz", "g28_tenz zmod")])
        self.assertIn("ZMOD plugin: its Klipper config only", plugins[0]["lines"])
        self.run_cli("disable", "g28_tenz", "--no-restart")
        self.assertFalse(os.path.lexists(link))
        self.run_cli("remove", "g28_tenz", "--no-restart")
        self.assertFalse((self.tmp / "plugins" / "g28_tenz").exists())

    def test_translated_zmod_plugin_uses_english(self):
        src = self.tmp / "zsrc" / "Cut_Filament"
        write(src / "en" / "cut_filament.cfg", "[gcode_macro CUT]\ngcode:\n  M400\n")
        write(src / "ru" / "cut_filament.cfg", "[gcode_macro CUT]\ngcode:\n  M400\n")
        self.assertEqual(self.run_cli("install", str(src), "--no-restart"), 0)
        link = self.tmp / "config" / "plugins" / "cut_filament.cfg"
        self.assertEqual(link.resolve(), (self.tmp / "plugins" / "cut_filament" / "en" / "cut_filament.cfg").resolve())

    def test_folder_without_manifest_or_zmod_cfg_is_refused(self):
        src = self.tmp / "zsrc" / "nothing"
        write(src / "other.cfg", "[gcode_macro X]\ngcode:\n  M400\n")
        self.assertEqual(self.run_cli("install", str(src), "--no-restart"), 1)
        self.assertFalse((self.tmp / "plugins" / "nothing").exists())

    # ---- OC_PLUGINS dialog

    def menu(self):
        """The generated config as Klipper reads it: its parser, its literal_eval."""
        import ast
        import configparser
        path = self.tmp / "config" / "plugins" / oc.MENU
        cfg = configparser.RawConfigParser(strict=False, inline_comment_prefixes=(";", "#"))
        cfg.read_string(path.read_text())
        return cfg, ast.literal_eval(cfg.get("gcode_macro OC_PLUGINS", "variable_plugins"))

    def render(self, cfg, section, plugins, **params):
        import jinja2
        import textwrap
        env = jinja2.Environment("{%", "%}", "{", "}")
        tpl = env.from_string(textwrap.dedent(cfg.get(section, "gcode")))
        out = tpl.render(plugins=plugins, params=params,
                         printer={"gcode_macro OC_PLUGINS": {"plugins": plugins}},
                         action_raise_error=lambda msg: (_ for _ in ()).throw(RuntimeError(msg)))
        return [l.strip() for l in out.splitlines() if l.strip()]

    def test_menu_lists_plugins_and_survives_klippers_parser(self):
        manifest = json.loads((self.src / oc.MANIFEST).read_text())
        manifest["description"] = 'Says "hi" #1; a|b'
        manifest["author"] = "Someone"
        (self.src / oc.MANIFEST).write_text(json.dumps(manifest))
        self.run_cli("install", str(self.src), "--no-restart")
        cfg, plugins = self.menu()
        self.assertEqual([p["id"] for p in plugins], ["hello"])
        hello = plugins[0]
        self.assertEqual((hello["label"], hello["color"]), ("Hello 1.0.0", "primary"))
        self.assertIn("Says 'hi' #1; a/b", hello["lines"])
        self.assertIn("By Someone", hello["lines"])
        self.assertIn("Adds: Klipper module oc_hello; Klipper config; Moonraker component oc_hello; "
                      "Moonraker config", hello["lines"])
        lines = self.render(cfg, "gcode_macro OC_PLUGINS", plugins)
        self.assertIn('RESPOND TYPE=command MSG="action:prompt_begin Plugins (1)"', lines)
        self.assertIn('RESPOND TYPE=command MSG="action:prompt_button Hello 1.0.0|OC_PLUGIN_INFO ID=hello|primary"',
                      lines)
        info = self.render(cfg, "gcode_macro OC_PLUGIN_INFO", plugins, ID="hello")
        self.assertIn('RESPOND TYPE=command MSG="action:prompt_begin Hello"', info)
        self.assertIn('RESPOND TYPE=command MSG="action:prompt_text Says \'hi\' #1; a/b"', info)
        self.assertIn('RESPOND TYPE=command MSG="action:prompt_footer_button Back|OC_PLUGINS"', info)
        with self.assertRaises(RuntimeError):
            self.render(cfg, "gcode_macro OC_PLUGIN_INFO", plugins, ID="nope")

    def test_menu_shows_disabled_broken_and_none(self):
        self.run_cli("sync")
        cfg, plugins = self.menu()
        self.assertEqual(plugins, [])
        self.assertTrue(any("No plugins are installed" in l
                            for l in self.render(cfg, "gcode_macro OC_PLUGINS", plugins)))
        self.run_cli("install", str(self.src), "--no-restart")
        self.run_cli("disable", "hello", "--no-restart")
        write(self.tmp / "plugins" / "junk" / oc.MANIFEST, "{not json")
        self.run_cli("sync")
        cfg, plugins = self.menu()
        by_id = {p["id"]: p for p in plugins}
        self.assertEqual((by_id["hello"]["label"], by_id["hello"]["color"]), ("Hello 1.0.0 (disabled)", "secondary"))
        self.assertIn("oc-plugin enable hello", by_id["hello"]["lines"][-1])
        self.assertEqual((by_id["junk"]["label"], by_id["junk"]["color"]), ("junk (broken)", "error"))
        # a regular file, so pruning plugin links leaves it alone
        self.assertFalse((self.tmp / "config" / "plugins" / oc.MENU).is_symlink())


class ExamplePluginTest(unittest.TestCase):
    def test_example_manifest_is_valid(self):
        example = ROOT.parent / "opencreator-plugin-example"
        if not example.is_dir():
            self.skipTest("opencreator-plugin-example is not checked out next to opencreator-fs")
        m = oc.load_manifest(str(example))
        self.assertEqual(m["id"], "hello")


if __name__ == "__main__":
    unittest.main()
