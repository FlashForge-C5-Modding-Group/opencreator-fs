import importlib.util
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "fs" / "usr" / "data" / "opencreator" / "startup" / "opencreator_updater.py"
SPEC = importlib.util.spec_from_file_location("opencreator_updater", MODULE)
up = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(up)

REL = "fs/usr/data/config"
SAVE = b"#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# [extruder]\n#*# pid_kp = 21.0\n"
V1 = b"[a]\nx: 1\n\n[b]\ny: 1\n\n[c]\nz: 1\n"
V2 = b"[a]\nx: 1\n\n[b]\ny: 2\n\n[c]\nz: 1\n"          # the update changes y


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"] + list(args),
                   cwd=str(cwd), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@unittest.skipUnless(shutil.which("git"), "needs git")
class UpdaterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo, self.config = self.tmp / "repo", self.tmp / "config"
        self.config.mkdir()
        (self.repo / REL).mkdir(parents=True)
        git(self.repo, "init", "-q", "-b", "main")

    def commit(self, **files):
        for name, data in files.items():
            (self.repo / REL / (name + ".cfg")).write_bytes(data)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "c")

    def updater(self, repo=None, **kw):
        return up.Updater(self.config, repo or self.repo, REL, log_path=self.tmp / "log", **kw)

    def run_merge(self, u=None):
        u = u or self.updater()
        try:
            return u.merge_configs((u.repo / REL) if u.repo == self.repo else self.repo / REL)
        finally:
            u.cleanup()

    def base(self, name="p"):
        return (self.config / ".opencreator-updater" / "base" / (name + ".cfg")).read_bytes()

    def live(self, name="p"):
        return self.config / (name + ".cfg")

    def test_new_file_and_unchanged(self):
        self.commit(p=V1)
        self.assertEqual(self.run_merge(), (True, []))
        self.assertEqual(self.live().read_bytes(), V1)
        self.assertEqual(self.base(), V1)
        self.updater().record_success([])
        self.assertEqual(self.run_merge(), (False, []))

    def test_edit_and_update_merge(self):
        self.commit(p=V1)
        self.run_merge(); self.updater().record_success([])
        self.live().write_bytes(V1.replace(b"x: 1", b"x: 9") + SAVE)       # user edit + calibration
        self.commit(p=V2)
        self.assertEqual(self.run_merge(), (True, []))
        self.assertEqual(self.live().read_bytes(), V2.replace(b"x: 1", b"x: 9") + SAVE)
        self.assertEqual(self.base(), V2)

    def test_conflict_leaves_live_untouched(self):
        self.commit(p=V1)
        self.run_merge(); self.updater().record_success([])
        edited = V1.replace(b"y: 1", b"y: 5")
        self.live().write_bytes(edited)
        self.commit(p=V2)
        changed, conflicts = self.run_merge()
        self.assertEqual(conflicts, ["p.cfg"])
        self.assertEqual(self.live().read_bytes(), edited)
        self.assertEqual(self.base(), V1)
        self.assertIn(b"<<<<<<< current", (self.config / "p.cfg.conflict").read_bytes())

    def test_crlf_live_merges(self):
        self.commit(p=V1)
        self.run_merge(); self.updater().record_success([])
        self.live().write_bytes(V1.replace(b"\n", b"\r\n"))
        self.commit(p=V2)
        self.assertEqual(self.run_merge(), (True, []))
        self.assertEqual(self.live().read_bytes(), V2)

    def test_missing_base_recovered_from_history(self):
        self.commit(p=V1)
        self.live().write_bytes(V1 + SAVE)            # an unedited old copy, no base yet
        self.commit(p=V2)
        self.assertEqual(self.run_merge(), (True, []))
        self.assertEqual(self.live().read_bytes(), V2 + SAVE)

    def test_missing_base_and_own_edits_left_alone(self):
        self.commit(p=V1)
        mine = V1.replace(b"z: 1", b"z: 7")
        self.live().write_bytes(mine)
        self.commit(p=V2)
        changed, conflicts = self.run_merge()
        self.assertEqual(conflicts, ["p.cfg"])
        self.assertEqual(self.live().read_bytes(), mine)

    def test_current_live_only_syncs_base(self):
        self.commit(p=V2)
        self.live().write_bytes(V2 + SAVE)
        self.assertEqual(self.run_merge(), (False, []))
        self.assertEqual(self.base(), V2)
        self.assertEqual(self.live().read_bytes(), V2 + SAVE)

    def test_migration_fixes_a_wrong_base(self):
        self.commit(p=V1)
        self.live().write_bytes(V1)
        self.commit(p=V2)
        # an earlier updater seeded the base from the new template: the change is lost
        b = self.config / ".opencreator-updater" / "base"
        b.mkdir(parents=True)
        (b / "p.cfg").write_bytes(V2)
        self.assertEqual(self.run_merge(), (True, []))
        self.assertEqual(self.live().read_bytes(), V2)
        u = self.updater(); u.record_success([], "abc")
        self.assertEqual((self.config / ".opencreator-updater" / "merge-version").read_text().strip(), up.MERGE_VERSION)
        self.assertEqual((self.config / ".opencreator-updater" / "applied-commit").read_text().strip(), "abc")

    def test_shallow_checkout_looks_in_full_history(self):
        self.commit(p=V1)
        self.commit(p=V1.replace(b"z: 1", b"z: 2"))
        self.commit(p=V2.replace(b"z: 1", b"z: 2"))
        shallow = self.tmp / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", self.repo.as_uri(), str(shallow)], check=True)
        self.live().write_bytes(V1)                    # matches only the first commit
        u = self.updater(repo=shallow)
        try:
            changed, conflicts = u.merge_configs(shallow / REL)
        finally:
            u.cleanup()
        self.assertEqual(conflicts, [])
        self.assertEqual(self.live().read_bytes(), V2.replace(b"z: 1", b"z: 2"))

    def test_permissions_kept(self):
        self.commit(p=V1)
        self.run_merge(); self.updater().record_success([])
        os.chmod(self.live(), 0o640)
        self.commit(p=V2)
        self.run_merge()
        self.assertEqual(stat.S_IMODE(self.live().stat().st_mode), 0o640)

    def test_conflicted_commit_restarts_once(self):
        self.commit(p=V1)
        s = up.SocUpdater(config_dir=self.config, clone=self.repo, ocdir=self.tmp / "oc",
                          log_path=self.tmp / "log", model_detect=None)
        restarts = []
        s.restart_klipper = restarts.append
        self.assertTrue(s.apply(loopscript=False))
        self.live().write_bytes(V1.replace(b"y: 1", b"y: 9"))
        self.commit(p=V2)
        self.assertFalse(s.apply(loopscript=False))
        self.assertFalse(s.apply(loopscript=False))
        self.assertEqual(restarts, [[], ["p.cfg"]])

    def test_model_file(self):
        self.commit(p=V1, **{"printer.pro": b"[heater_generic chamber_heater]\n"})
        self.run_merge(self.updater(model_detect=lambda: "Creator5"))
        self.assertNotIn(b"include", (self.config / "printer.model.cfg").read_bytes())
        (self.config / "printer.model.cfg").unlink()
        self.run_merge(self.updater(model_detect=lambda: "Creator5Pro"))
        self.assertIn(b"[include printer.pro.cfg]", (self.config / "printer.model.cfg").read_bytes())


class OverlayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_overlay_manifest(self):
        src, dest, manifest = self.tmp / "src", self.tmp / "dest", self.tmp / "m.md5"
        (src / "scripts").mkdir(parents=True)
        (src / "scripts" / "a.sh").write_text("a2")
        dest.mkdir()
        (dest / "dropped.sh").write_text("old")        # we installed it, unchanged: removed
        (dest / "edited.sh").write_text("mine")        # we installed it, user changed it: kept
        (dest / "own.sh").write_text("user's")         # never ours: kept
        manifest.write_text("%s  dropped.sh\n%s  edited.sh\n" % (up.hashlib.md5(b"old").hexdigest(),
                                                                 up.hashlib.md5(b"orig").hexdigest()))
        up.overlay_dir(src, dest, manifest)
        self.assertEqual((dest / "scripts" / "a.sh").read_text(), "a2")
        self.assertFalse((dest / "dropped.sh").exists())
        self.assertTrue((dest / "edited.sh").exists() and (dest / "own.sh").exists())
        self.assertEqual(pathlib.Path(str(manifest) + ".new").read_text(),
                         "%s  scripts/a.sh\n" % up.hashlib.md5(b"a2").hexdigest())

    def test_firmware_exe_not_replaced_over_stock(self):
        s = up.SocUpdater(config_dir=self.tmp / "config", clone=self.tmp / "clone", ocdir=self.tmp / "oc",
                          log_path=self.tmp / "log")
        s.nginx, s.firmware_exe = self.tmp / "nginx", self.tmp / "firmwareExe"
        s.api = lambda *a, **k: None
        launcher = self.tmp / "oc" / "firmware" / "firmwareExe"
        launcher.parent.mkdir(parents=True)
        launcher.write_bytes(b"#!/bin/sh\nnew\n")
        (self.tmp / "clone" / "fs" / "usr" / "data").mkdir(parents=True)
        s.firmware_exe.write_bytes(b"\x7fELF stock binary")
        s.sync_loopscript()
        self.assertEqual(s.firmware_exe.read_bytes(), b"\x7fELF stock binary")
        s.firmware_exe.write_bytes(b"#!/bin/sh\nold\n")
        s.sync_loopscript()
        self.assertEqual(s.firmware_exe.read_bytes(), b"#!/bin/sh\nnew\n")


@unittest.skipUnless(shutil.which("sh"), "needs sh")
class RestartTest(unittest.TestCase):
    """restart_klipper only logs for now; Klipper is restarted by hand."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.calls = []
        self.u = up.Updater(self.tmp / "config", self.tmp / "repo", REL, log_path=self.tmp / "log")
        self.u.printing = lambda: False
        self.u.api = lambda path, method="GET", body=None, timeout=10: self.calls.append((path, method))

    def test_does_not_restart(self):
        self.u.restart_klipper([])
        self.assertEqual(self.calls, [])
        self.assertIn("restart Klipper to load it", (self.tmp / "log").read_text())

    def test_logs_conflicts(self):
        self.u.restart_klipper(["printer.cfg"])
        self.assertEqual(self.calls, [])
        self.assertIn("CONFLICTS in: printer.cfg", (self.tmp / "log").read_text())


class McuSyncTest(unittest.TestCase):
    """SocUpdater.sync_mcu with a stand-in oc-mcu-flash that logs what it was given."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fw = self.tmp / "clone" / up.MCU_FIRMWARE_DIR
        self.fw.mkdir(parents=True)
        self.flasher = self.tmp / "oc" / "mcu-flash" / "oc-mcu-flash"
        self.flasher.parent.mkdir(parents=True)
        self.calls = self.tmp / "calls"
        self.flash_result = "ok"
        self.state, self.versions = "standby", {}
        self.s = up.SocUpdater(config_dir=self.tmp / "config", clone=self.tmp / "clone",
                               ocdir=self.tmp / "oc", log_path=self.tmp / "log")
        self.s.api = self.api

    def api(self, path, method="GET", body=None, timeout=10):
        if "print_stats" in path:
            return {"result": {"status": {"print_stats": {"state": self.state}}}}
        if "mcu_version" in path:
            return {"result": {"status": {mcu: {"mcu_version": self.versions.get(name)}
                                          for name, mcu in up.MCU_BOARDS.items()}}}
        return {}

    def hexes(self, version=None, **files):
        for name, data in files.items():
            (self.fw / name).write_bytes(data)
        sums = "".join("%s  %s\n" % (up.hashlib.sha256((self.fw / n).read_bytes()).hexdigest(), n)
                       for n in sorted(up.MCU_BOARDS) if (self.fw / n).is_file())
        (self.fw / "SHA256SUMS").write_text(sums)
        if version:
            (self.fw / "VERSION").write_text(version + "\n")

    def set_flasher(self, ok=True):
        names = {"eBoard.hex": "eboard", "heaterBoard.hex": "eheaterboard",
                 "levelBoard.hex": "levelboard", "mainBoardGD.hex": "mainboard"}
        lines = ["#!/bin/sh", 'ls "$1" | sort | tr "\n" " " >> "%s"; echo >> "%s"' % (self.calls, self.calls)]
        for f, board in names.items():
            lines.append('[ -f "$1/%s" ] && echo "%s: %s"' % (f, board, "flashed" if ok else "FAILED"))
        lines.append("exit %d" % (0 if ok else 1))
        self.flasher.write_text("\n".join(lines) + "\n")

    def flashed_sets(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_no_folder_does_nothing(self):
        shutil.rmtree(self.fw)
        self.set_flasher()
        self.s.sync_mcu()
        self.assertEqual(self.flashed_sets(), [])

    def test_checksum_mismatch_never_flashes(self):
        self.hexes(**{"eBoard.hex": b"e1"})
        (self.fw / "eBoard.hex").write_bytes(b"tampered")
        self.set_flasher()
        self.s.sync_mcu()
        self.assertEqual(self.flashed_sets(), [])

    def test_boards_already_on_version_are_only_recorded(self):
        self.hexes("abc", **{"eBoard.hex": b"e1", "mainBoardGD.hex": b"m1"})
        self.versions = {"eBoard.hex": "abc", "mainBoardGD.hex": "old"}
        self.set_flasher()
        self.s.sync_mcu()
        self.assertEqual(self.flashed_sets(), ["mainBoardGD.hex "])
        self.s.sync_mcu()
        self.assertEqual(len(self.flashed_sets()), 1)

    def test_only_changed_boards_flash(self):
        self.hexes(**{"eBoard.hex": b"e1", "levelBoard.hex": b"l1"})
        self.set_flasher()
        self.s.sync_mcu()
        self.hexes(**{"levelBoard.hex": b"l2"})
        self.s.sync_mcu()
        self.assertEqual(self.flashed_sets(), ["eBoard.hex levelBoard.hex ", "levelBoard.hex "])

    def test_failure_is_not_retried_until_the_files_change(self):
        self.hexes(**{"heaterBoard.hex": b"h1"})
        self.set_flasher(ok=False)
        self.s.sync_mcu()
        self.s.sync_mcu()
        self.assertEqual(len(self.flashed_sets()), 1)
        self.set_flasher()
        self.hexes(**{"heaterBoard.hex": b"h2"})
        self.s.sync_mcu()
        self.assertEqual(len(self.flashed_sets()), 2)
        self.assertFalse((self.s.state / "mcu-failed").exists())

    def stock_tools(self):
        control = self.tmp / "control" / "2.0.8"
        control.mkdir(parents=True)
        for tool in ("IAPCommand", "ISPCommand"):
            (control / tool).write_text("#!/bin/sh\n")
        self.s.control = control.parent

    def test_failed_boards_are_staged_for_startup(self):
        self.hexes(**{"eBoard.hex": b"e1", "heaterBoard.hex": b"h1"})
        self.flasher.write_text('#!/bin/sh\necho "eboard: flashed"\necho "eheaterboard: FAILED"\nexit 1\n')
        self.stock_tools()
        self.s.sync_mcu()
        pending = self.tmp / "oc" / "mcu-flash-pending"
        self.assertEqual(sorted(p.name for p in pending.iterdir()),
                         ["IAPCommand", "ISPCommand", "SHA256SUMS", "flash.sh", "heaterBoard.hex"])
        self.assertIn("heaterBoard.hex", (pending / "SHA256SUMS").read_text())
        self.assertIn("mcu-flash-pending", (pending / "flash.sh").read_text())

    def test_installer_pending_flash_is_left_alone(self):
        self.hexes(**{"eBoard.hex": b"e1"})
        self.set_flasher(ok=False)
        self.stock_tools()
        pending = self.tmp / "oc" / "mcu-flash-pending"
        pending.mkdir(parents=True)
        (pending / "flash.sh").write_text("installer\n")
        self.s.sync_mcu()
        self.assertEqual((pending / "flash.sh").read_text(), "installer\n")
        self.assertFalse((pending / "eBoard.hex").exists())

    def test_not_during_a_print(self):
        self.hexes(**{"eBoard.hex": b"e1"})
        self.set_flasher()
        self.state = "printing"
        self.s.sync_mcu()
        self.assertEqual(self.flashed_sets(), [])
        self.state = "standby"
        self.s.sync_mcu()
        self.assertEqual(self.flashed_sets(), ["eBoard.hex "])


if __name__ == "__main__":
    unittest.main()
