# OrcaSlicer filament sync

The Creator 5 standalone toolchanger has four physical tools but no AFC feeder
lanes. `creator5_filament_sync` publishes T0 through T3 to Moonraker's
`lane_data` database, which OrcaSlicer's Moonraker connection reads for its
filament sync control. This changes only the filament inventory shown in Orca.
It does not select a tool, load filament, or change heater targets.

After installing the updated `klipper-c5` and `printer.creator5.cfg`, use AFC's
filament commands from the Mainsail console. The standalone tool names for
these commands are `T0` through `T3`:

```gcode
SET_MATERIAL LANE=T0 MATERIAL=PLA
SET_COLOR LANE=T0 COLOR=FF5533
AFC_SET_SPOOL_TEMP LANE=T0 EXTRUDER_TEMP=220 BED_TEMP=60
SET_MATERIAL LANE=T2 MATERIAL=PCTG
SET_COLOR LANE=T2 COLOR=3366CC
AFC_CLEAR_FILAMENT LANE=T1
C5_FILAMENT_STATUS
```

If Spoolman is configured, `SET_SPOOL_ID LANE=T2 SPOOL_ID=42` uses AFC's
Spoolman lookup to set that tool's material, color, and temperature hints.
Changing material or color manually clears the saved spool ID. AFC's Spoolman
lookup is synchronous, so assign spool IDs while the printer is idle.

`MATERIAL` should be a material family Orca recognizes, such as PLA, PETG,
PCTG, ABS, ASA, or TPU. `COLOR` is six hexadecimal digits without a `#`;
AFC adds it for Orca. `EXTRUDER_TEMP` and `BED_TEMP` are optional informational
values; they do not heat anything. An
unset or cleared tool appears as an empty slot. The assignments survive
Klipper restarts in `/usr/data/config/c5_filaments.json`.

Connect OrcaSlicer to the printer using its Moonraker host, then use Orca's
filament sync control. If the list has not refreshed, run `C5_SYNC_FILAMENTS`
and reconnect or refresh in Orca. You can verify Moonraker's published data at
`http://<printer-ip>:7125/server/database/item?namespace=lane_data`.

The AFC tool status also exposes these assignments. The integration sends
database updates in a background worker so Moonraker
HTTP requests do not interrupt MCU timing. It republishes at Klipper startup
and after AFC reconnects to Moonraker. Orca matches material families, but
may choose a generic preset rather than a custom brand-specific profile.
