import logging


def material_key(material):
    return " ".join(material.upper().replace("-", " ").replace("_", " ").split())


class OrcaFilamentProfiles:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.client = None
        self.filament_ids = {}
        for line in config.get("filament_ids", "").splitlines():
            if not line.strip():
                continue
            material, separator, filament_id = line.partition(":")
            key = material_key(material)
            filament_id = filament_id.strip()
            if not separator or not key or not filament_id or len(filament_id.split()) != 1:
                raise config.error("Expected a material and filament ID separated by ':' in filament_ids")
            if key in self.filament_ids:
                raise config.error("Duplicate material in filament_ids: " + material.strip())
            self.filament_ids[key] = filament_id
        if self.filament_ids:
            self.printer.register_event_handler("afc:moonraker_connect", self.attach)

    def attach(self, *_args):
        # AFC emits this before PREP publishes the saved lane assignments.
        afc = self.printer.lookup_object("AFC", None)
        client = getattr(afc, "moonraker", None)
        if client is not None and client is self.client:
            return
        publish = getattr(client, "send_lane_data", None)
        if not callable(publish):
            logging.warning("Orca filament profiles: AFC lane publisher unavailable")
            return

        def publish_with_filament_id(payload):
            return publish(self.with_filament_id(payload))

        try:
            client.send_lane_data = publish_with_filament_id
        except (AttributeError, TypeError):
            logging.warning("Orca filament profiles: AFC lane publisher cannot be wrapped")
            return
        self.client = client

    def with_filament_id(self, payload):
        if not isinstance(payload, dict) or payload.get("namespace") != "lane_data":
            return payload
        lane = payload.get("value")
        if not isinstance(lane, dict) or lane.get("filament_id"):
            return payload
        material = lane.get("material")
        if not isinstance(material, str):
            return payload
        filament_id = self.filament_ids.get(material_key(material))
        if filament_id is None:
            return payload
        return dict(payload, value=dict(lane, filament_id=filament_id))


def load_config(config):
    return OrcaFilamentProfiles(config)
