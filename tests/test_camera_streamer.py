"""30-camera.sh picks its streamer from camera.conf, downloads ustreamer, and falls
back to mjpg_streamer.

Runs a copy of the script with its paths pointed at a temp folder, a fake curl, and
fake streamers that record how they were started."""
import hashlib
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile
import time
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "fs/usr/data/opencreator/startup/scripts/30-camera.sh"
RUNNING = "echo ustreamer \"$@\" >> $RUNS; sleep 60"


def executable(path, body):
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class CameraStreamer(unittest.TestCase):
    def run_script(self, conf, release=RUNNING, installed=None, curl_works=True, seconds=2.0,
                   short_run=30, installed_exec=True, pin=None):
        """release: the ustreamer the download gives. installed: one already on the printer.
        pin: the checksum the script expects, the release's own by default."""
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for d in ("mjpg", "config", "logs", "bin", "camera"):
            (root / d).mkdir()
        (root / "video0").touch()
        runs = root / "runs"
        runs.touch()
        executable(root / "mjpg/mjpg_streamer", "echo mjpg \"$@\" >> " + str(runs) + "; sleep 60")
        published = root / "release-ustreamer"
        executable(published, release.replace("$RUNS", str(runs)))
        pinned = pin or hashlib.sha256(published.read_bytes()).hexdigest()
        if installed is not None:
            executable(root / "camera/ustreamer", installed.replace("$RUNS", str(runs)))
            if not installed_exec:
                (root / "camera/ustreamer").chmod(0o644)
        # curl -fsSL -m N -o FILE URL: copies the published file, or fails
        executable(root / "bin/curl", 'echo curl >> %s\n%s' % (
            root / "curl-calls",
            'while [ $# -gt 0 ]; do [ "$1" = -o ] && { cp %s "$2"; exit 0; }; shift; done; exit 1' % published
            if curl_works else "exit 7"))
        if conf is not None:
            (root / "config/camera.conf").write_text(conf)
        text = SCRIPT.read_text()
        for name, value in (("MJPG_DIR", root / "mjpg"), ("USTREAMER", root / "camera/ustreamer"),
                            ("CAMERA_CONF", root / "config/camera.conf"), ("DEVICE", root / "video0"),
                            ("LOGS", root / "logs"), ("SHORT_RUN_S", short_run),
                            ("USTREAMER_SHA256", pinned), ("FETCH_TRIES", 2), ("FETCH_WAIT_S", 0),
                            ("LAUNCHER_LOG", '"%s"' % (root / "launcher.log"))):
            text, n = re.subn(r"^%s=\S+" % name, "%s=%s" % (name, value), text, flags=re.M)
            self.assertEqual(n, 1, name)
        # no real sleeps of a few seconds between restarts, and no wget to a real camera
        text = text.replace("sleep 3\n  done", "sleep 0.2\n  done").replace("apply_controls &\n", ":\n")
        text = "PATH=%s:$PATH\n" % (root / "bin") + text
        script = root / "30-camera.sh"
        script.write_text(text)
        subprocess.run(["sh", str(script)], timeout=10, check=True)
        time.sleep(seconds)
        subprocess.run(["pkill", "-f", str(root)], check=False)  # the loop runs in the background
        read = lambda p: p.read_text() if p.exists() else ""
        return {"runs": read(runs).splitlines(), "log": read(root / "launcher.log"),
                "conf": read(root / "config/camera.conf"), "curl": len(read(root / "curl-calls").splitlines()),
                "binary": root / "camera/ustreamer", "pinned": pinned}

    def test_default_is_mjpg_and_writes_the_setting(self):
        r = self.run_script(None)
        self.assertTrue(r["runs"] and all(x.startswith("mjpg") for x in r["runs"]), r["runs"])
        self.assertIn("streamer: mjpg_streamer", r["conf"])
        self.assertEqual(r["curl"], 0)

    def test_first_choice_downloads_it(self):
        r = self.run_script("streamer: ustreamer\n")
        self.assertEqual(len(r["runs"]), 1, r["runs"])
        self.assertTrue(r["runs"][0].startswith("ustreamer"))
        for arg in ("--encoder=HW", "--port=8080", "--host=0.0.0.0", "--allow-origin=*",
                    "--white-balance=4800", "--saturation=100", "--contrast=33", "--hue=-20"):
            self.assertIn(arg, r["runs"][0])
        self.assertEqual(r["curl"], 1)
        self.assertTrue(r["binary"].stat().st_mode & stat.S_IEXEC)
        self.assertIn("downloaded ustreamer", r["log"])
        self.assertIn("using ustreamer", r["log"])

    def test_the_pinned_copy_isnt_downloaded_again(self):
        r = self.run_script("streamer: ustreamer\n", installed=RUNNING)
        self.assertEqual(r["curl"], 0)
        self.assertTrue(r["runs"] and r["runs"][0].startswith("ustreamer"))

    def test_without_execute_bit_still_runs(self):
        r = self.run_script("streamer: ustreamer\n", installed=RUNNING, installed_exec=False)
        self.assertTrue(r["runs"] and r["runs"][0].startswith("ustreamer"), r["runs"])

    def test_spelling_variants(self):
        for conf in ("streamer = ustreamer\n", "  streamer:ustreamer  # comment\n"):
            r = self.run_script(conf, seconds=1.0)
            self.assertTrue(r["runs"] and r["runs"][0].startswith("ustreamer"), (conf, r["runs"]))

    def test_no_network_uses_mjpg(self):
        r = self.run_script("streamer: ustreamer\n", curl_works=False)
        self.assertTrue(r["runs"] and r["runs"][0].startswith("mjpg"), r["runs"])
        self.assertEqual(r["curl"], 2)  # FETCH_TRIES
        self.assertIn("couldn't be downloaded", r["log"])
        self.assertFalse(r["binary"].exists())

    def test_wrong_checksum_is_not_used(self):
        r = self.run_script("streamer: ustreamer\n", pin="0" * 64)
        self.assertTrue(r["runs"] and r["runs"][0].startswith("mjpg"), r["runs"])
        self.assertIn("didn't match its checksum", r["log"])
        self.assertEqual(r["curl"], 1)  # a bad download isn't retried
        self.assertFalse(r["binary"].exists())

    def test_failed_update_keeps_the_old_copy(self):
        r = self.run_script("streamer: ustreamer\n", installed=RUNNING + "\n# an older build", curl_works=False)
        self.assertTrue(r["runs"] and r["runs"][0].startswith("ustreamer"), r["runs"])
        self.assertIn("using the copy already here", r["log"])

    def test_ustreamer_that_keeps_stopping_falls_back(self):
        r = self.run_script("streamer: ustreamer\n", release="echo ustreamer >> $RUNS; exit 1", seconds=3.0)
        streamers = [x.split()[0] for x in r["runs"]]
        self.assertEqual(streamers[:3], ["ustreamer"] * 3, streamers)
        self.assertEqual(streamers[3:4], ["mjpg"], streamers)
        self.assertIn("keeps stopping", r["log"])

    def test_long_runs_reset_the_count(self):
        r = self.run_script("streamer: ustreamer\n", release="echo ustreamer >> $RUNS; sleep 1.1; exit 1",
                            seconds=4.0, short_run=1)
        self.assertGreaterEqual(len(r["runs"]), 3)
        self.assertTrue(all(x.startswith("ustreamer") for x in r["runs"]), r["runs"])
        self.assertNotIn("keeps stopping", r["log"])


if __name__ == "__main__":
    unittest.main()
