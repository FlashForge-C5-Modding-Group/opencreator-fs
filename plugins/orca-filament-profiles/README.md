# Orca Filament Profiles

OrcaSlicer 2.5 can use the `filament_id` in a Moonraker lane record to select a
compatible filament preset. This optional OpenCreator plugin adds an ID based
on the material AFC reports. It preserves IDs AFC already supplies and lets
Orca use its usual matching for materials outside your mapping.

## Install

On an OpenCreator SoC install, run this from SSH when your installed
`opencreator-fs` checkout contains the plugin:

```sh
oc-plugin install --no-restart /usr/data/opencreator/opencreator-fs/plugins/orca-filament-profiles
```

For another layout, pass the path to this directory in your checkout.
`oc-plugin` copies the files into its plugins directory. On the SoC, edit
`/usr/data/opencreator/plugins/orca-filament-profiles/orca-filament-profiles.cfg`
to add your own mappings. The following example uses stock OrcaSlicer 2.5
presets for the Flashforge Creator 5 Pro:

```ini
[oc_orca_filament_profiles]
filament_ids:
    PLA: OFJ3F2jm
    PETG: OFXiArjA
    TPU-90A: OFwlZ7gH
```

Use material labels that AFC publishes, and the `filament_id` from a compatible
preset in your OrcaSlicer version. Each mapping applies to every lane carrying
that material label. Case, spaces, hyphens, and underscores are normalized, so
`TPU-90A` and `tpu_90a` match the same entry. An empty mapping leaves Orca's
normal selection in place.

Restart Klipper while the printer is idle. In OrcaSlicer, run **Synchronize
filament list from AMS** with **Filament & Color** selected. To inspect the
published IDs, open
`http://<printer-ip>:7125/server/database/item?namespace=lane_data`.

The installed copy and its configuration sit outside the Kalico checkout.
OpenCreator restores the links at Klipper startup. Manage the plugin with
`oc-plugin disable orca-filament-profiles` or
`oc-plugin enable orca-filament-profiles`.
