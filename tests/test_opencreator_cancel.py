import asyncio
import importlib.util
import pathlib
import unittest
from unittest import mock

PATH = (pathlib.Path(__file__).resolve().parents[1] / "fs" / "usr" / "data"
        / "opencreator" / "moonraker" / "opencreator_cancel.py")
spec = importlib.util.spec_from_file_location("opencreator_cancel", PATH)
component = importlib.util.module_from_spec(spec)
spec.loader.exec_module(component)


class CancelComponentTest(unittest.TestCase):
    def make(self, run_gcode=None):
        handlers = {}
        klippy_apis = mock.Mock()
        klippy_apis.run_gcode = run_gcode or mock.AsyncMock(return_value="ok")
        server = mock.Mock()
        server.register_event_handler.side_effect = (
            lambda name, cb: handlers.setdefault(name, cb))
        server.lookup_component.return_value = klippy_apis
        config = mock.Mock()
        config.get_server.return_value = server
        component.load_component(config)
        return handlers, klippy_apis

    def test_sends_the_interrupt_when_a_cancel_is_announced(self):
        handlers, klippy_apis = self.make()
        self.assertIn("klippy_apis:cancel_requested", handlers)
        asyncio.run(handlers["klippy_apis:cancel_requested"]())
        klippy_apis.run_gcode.assert_awaited_once_with(
            "_OC_START_CANCEL_INTERRUPT", None)

    def test_a_failure_never_stops_the_cancel(self):
        handlers, _ = self.make(mock.AsyncMock(side_effect=RuntimeError("klippy")))
        with self.assertLogs(level="ERROR"):
            asyncio.run(handlers["klippy_apis:cancel_requested"]())


if __name__ == "__main__":
    unittest.main()
