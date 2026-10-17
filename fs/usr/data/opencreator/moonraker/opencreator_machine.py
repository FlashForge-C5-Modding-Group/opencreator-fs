# Machine provider for OpenCreator on the printer SoC.
#
# Moonraker treats any system whose PID 1 isn't "init"/"systemd" as an LXC
# container (FlashForge's busybox init isn't), which blocks host reboot and
# shutdown, and with "provider: none" it can't restart Klipper or itself.
# This replaces the provider before Moonraker initializes it: reboot and
# poweroff run busybox's commands (Moonraker already runs as root, there is
# no sudo), and services are restarted the way LoopScript runs them: klippy
# is stopped and 10-klipper.sh starts it again; Moonraker restarts itself.
from __future__ import annotations
import asyncio
import logging
import os
import signal
from typing import TYPE_CHECKING, Any, Dict

from .machine import BaseProvider

if TYPE_CHECKING:
    from ..confighelper import ConfigHelper

SERVICES = ("klipper", "moonraker")


class OpenCreatorProvider(BaseProvider):
    async def initialize(self) -> None:
        self.available_services = {
            name: {"active_state": "active", "sub_state": "running"}
            for name in SERVICES
        }

    async def _run(self, *cmd: str) -> None:
        proc = await asyncio.create_subprocess_exec(*cmd)
        await proc.wait()

    async def shutdown(self) -> None:
        await self._run("/sbin/" + self.shutdown_action)

    async def reboot(self) -> None:
        await self._run("/sbin/reboot")

    async def do_service_action(self, action: str, service_name: str) -> None:
        if service_name not in SERVICES:
            raise self.server.error(f"Service '{service_name}' not available")
        if action != "restart":
            raise self.server.error(
                f"Only restart is available for {service_name} on OpenCreator")
        if service_name == "moonraker":
            self.server.restart(delay=0.5)
            return
        stopped = 0
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmdline = f.read()
            except OSError:
                continue
            if b"klippy.py" in cmdline:
                os.kill(int(pid), signal.SIGTERM)
                stopped += 1
        if not stopped:
            raise self.server.error("Klipper is not running")
        logging.info("OpenCreator: restarting Klipper (LoopScript starts it again)")

    async def check_virt_status(self) -> Dict[str, Any]:
        return {"virt_type": "none", "virt_identifier": "none"}


class OpenCreatorMachine:
    def __init__(self, config: ConfigHelper) -> None:
        machine = config.get_server().lookup_component("machine")
        machine.inside_container = False
        machine.system_info["virtualization"] = {
            "virt_type": "none", "virt_identifier": "none"}
        machine.sys_provider = OpenCreatorProvider(
            config.getsection("machine"))
        machine.provider_type = "opencreator"
        machine.system_info["provider"] = "opencreator"
        logging.info("OpenCreator machine provider active")


def load_component(config: ConfigHelper) -> OpenCreatorMachine:
    return OpenCreatorMachine(config)
