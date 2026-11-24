import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FLASHER = ROOT / "fs" / "usr" / "data" / "opencreator" / "mcu-flash" / "oc-mcu-flash"


@unittest.skipUnless(shutil.which("sh"), "needs sh")
class McuFlashStatusTest(unittest.TestCase):
    """The live flasher proceeds only after Moonraker confirms an idle state."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.control = self.tmp / "control"
        self.hexes = self.tmp / "hexes"
        self.bin = self.tmp / "bin"
        self.control.mkdir()
        self.hexes.mkdir()
        self.bin.mkdir()
        (self.hexes / "mainBoardGD.hex").write_text("fake hex\n")
        self.marker = self.tmp / "flasher-called"
        self.write_tool("IAPCommand", "true\n")
        self.write_tool("ISPCommand", "echo ISPCommand >> \"$FLASH_MARKER\"; echo finished successfully\n")
        self.write_tool("curl", r'''#!/bin/sh
case "$MOONRAKER_STATE" in
    unavailable) exit 1 ;;
esac
case "$*" in
    *printer/info*) printf '%s' '{"result":{"state":"ready"}}' ;;
    *print_stats*) printf '%s' '{"result":{"status":{"print_stats":{"state":"'"$MOONRAKER_STATE"'"}}}}' ;;
    *) printf '%s' '{}' ;;
esac
''')
        for name in ("IAPCommand", "ISPCommand"):
            shutil.copy2(self.bin / name, self.control / name)

    def write_tool(self, name, body):
        path = self.bin / name
        if not body.startswith("#!"):
            body = "#!/bin/sh\n" + body
        path.write_text(body)
        path.chmod(0o755)

    def flash(self, state):
        env = os.environ.copy()
        env.update(
            PATH=str(self.bin) + os.pathsep + env.get("PATH", ""),
            OC_MCU_CONTROL=str(self.control),
            OC_MOONRAKER="http://moonraker.invalid",
            OC_MCU_WORK=str(self.tmp / "work"),
            OC_MCU_LOG=str(self.tmp / "flash.log"),
            MOONRAKER_STATE=state,
            FLASH_MARKER=str(self.marker),
        )
        return subprocess.run(["sh", str(FLASHER), str(self.hexes)], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=20)

    def test_unavailable_status_never_invokes_flasher(self):
        result = self.flash("unavailable")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot confirm printer is idle", result.stderr)
        self.assertFalse(self.marker.exists())

    def test_unknown_status_never_invokes_flasher(self):
        result = self.flash("restarting")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_confirmed_idle_allows_mainboard_flash(self):
        result = self.flash("standby")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.marker.read_text().strip(), "ISPCommand")
        self.assertIn("mainboard: flashed", result.stdout)


if __name__ == "__main__":
    unittest.main()
