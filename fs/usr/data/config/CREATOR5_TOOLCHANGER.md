# Creator 5 Klippy toolchanger

The host code lives in `klipper-c5/klippy/extras/creator5_toolchanger.py`.
`printer.base.cfg` includes `printer.creator5.cfg` and
`printer.afc-standalone.cfg`. AFC owns T0 through T3. Install the AFC Klipper
add-on before using this config; stock Klipper does not provide the
`[AFC_Toolchanger]` and `[AFC_extruder]` objects.

Tool presence comes only from the eight physical `extruder_pos1..4` and
`extruder_grab1..4` inputs on the eheaterboard. The Creator 5 toolchanger
checks those pins for motion and status; AFC's `on_shuttle` view follows the
same check through each tool's `creator5_tool_index`. Filament switches and
AFC's saved selection do not determine which head is mounted. Missing or
contradictory mount switches report no tool and block tool motion.
In AFC status, a parked Creator 5 head reports `Parked` even if it has
filament loaded. Only the head confirmed by the dock/grab pins can report
`Idle` or `Printing`. PREP logs filament-switch presence separately from the
physical `mounted`/`parked` state.
Each standalone AFC extruder sets `auto_load_on_tool_start: False`, so a
filament-switch transition updates AFC's presence state without automatically
extruding. Tool selection only performs Creator 5 pickup/docking and logical
extruder activation; explicit filament loading and print-start purge remain
separate commands. Slicer `T0`–`T3` commands take the same swap-only path;
they do not run AFC's standalone lane unload/load routine.

The four dock positions in `printer.creator5.cfg` are the factory defaults
decoded from `Config::initExtruderConfig()` in `firmwareExe.i64`, not
measurements of this printer. They correspond to the firmware's
`x_check_pos/y_check_pos` through `x_check_pos3/y_check_pos3` fields:

| Tool | X | Y |
| --- | ---: | ---: |
| T0 | 298.219 | 56.472 |
| T1 | 298.605 | 107.100 |
| T2 | 298.200 | 156.920 |
| T3 | 298.238 | 207.140 |

At Klippy startup, existing values in
`/usr/data/firmwareRes/config/extruder.json` take precedence over those
fallback defaults for the reference, all four tool measurements, and all
four dock coordinates. The stock `zoffset.json` per-tool adjustments are
loaded separately and added to the measured relative Z offsets.

The same binary uses an X=250 approach, X=280 pre-dock point, a final
approach to each tool's X/Y mount, `MOTOR_GRAB`, a 20 mm X pullback, and
`MOTOR_GRAB2`. The release path uses `MOTOR_RELEASE`. Klippy verifies the
stock dock and grab inputs before and after motion, checks the doors only while
the chamber heater has a nonzero target or output, requires
homed axes, limits automatic coordinate corrections, and disables heaters if
post-motion tool verification fails. The startup scan follows the binary's
four-direction levelboard measurement around the calibration target.

Toolchange speeds are configured in `printer.creator5.cfg` in mm/s:
`clear_travel_speed`, `clearance_z_speed`, `dock_approach_speed`,
`pickup_predock_speed`, `pickup_latch_speed`, `pullback_speed`, and
`departure_speed`. `pickup_accel` is in mm/s². The 600 mm/s clear-travel
setting applies only before entering the dock; close-range and departure
moves retain independent lower limits. `release_latch_wait_ms` controls the
post-`MOTOR_RELEASE` delay. This config sets it, `pickup_latch_wait_ms`, and
`toolchange_sensor_settle_ms` to zero, so there are no fixed pauses during a
normal toolchange. `M400`, synchronous motor commands, and post-move dock/grab
switch verification remain. The slower contact speeds are separately
configurable; zero waits do not make contact at clear-travel speed.

## First use

1. Confirm each `QUERY_BUTTON BUTTON=extruder_pos1` through `pos4` and
   `extruder_grab1` through `grab4` reports the expected state. A parked head
   should have its dock switch pressed and grab switch released. A mounted
   head should show the reverse. Verify `topDoor` and `frontDoor` report
   `PRESSED` while open.
2. Run `C5_TOOL_STATUS` and `C5_MOUNT_COORDS` before any tool motion.
3. Verify the `[e_stop Z]` levelboard trigger path and the fixture clearance
   before running automatic XYZ calibration. The factory sequence probes Z
   first, then scans XY 0.6 mm above that contact height. `scan_height` is
   needed only for the XY-only recovery path or `Z=0` calibration.
4. After a dry pickup and park, use `C5_MOUNT_CORRECT T=0 X=... Y=... SAVE=1`
   for each measured mount center. `SAVE=1` writes the selected holder's
   coordinates to `extruder.json` with a backup, so startup reloads them.
   It does not require `SAVE_CONFIG`.

## Extruder Position Calibrate

The stock **Extruder Position Calibrate** workflow measures holder coordinates.
It is separate from **Extruder Offset Calibration**, which aligns the nozzles
for printing. The operator selects T0–T3 and manually moves the master
carriage to the selected holder after the motors are released. The stock code
waits for its grab/holder sensor state, then uses `HDHOME` against the X and Y
endstops to measure the holder position. It releases and re-docks the head,
then writes the measured `x_check_pos*` and `y_check_pos*` fields to
`extruder.json`. Those coordinates are subsequently used for tool pickup and
docking.

`EXTRUDER_POSITION_CALIBRATE` without `T` asks for a T0–T3 selection.
After homing XYZ, parking every head, cooling the toolheads, and raising Z
above `safe_z`, run `EXTRUDER_POSITION_CALIBRATE T=0` (or T1–T3). The port
releases the X/Y motors for manual alignment, waits up to 30 seconds for the
selected holder and grab sensors, pauses five seconds for you to release your
hand, measures X/Y with `[hd_home X]` and `[hd_home Y]`,
rehomes XY to discard the temporary measurement frame, then re-docks at the
measured coordinates and verifies
the head, then updates **only** that tool's `x_check_pos*` and `y_check_pos*`
fields in `extruder.json`. It creates a timestamped backup first. A timeout,
sensor mismatch, endstop error, or correction beyond `max_mount_correction`
stops without saving; rehome XY before other motion. This guided motion
workflow is implemented but **not yet validated on hardware**.

`C5_MOUNT_CORRECT` remains a manual-coordinate command.
`C5_MOUNT_PROBE T=... CENTER_X=... CENTER_Y=... SCAN_Z=...` is a separate,
experimental levelboard-fiducial probe; it does not reproduce the stock
holder calibration and should not be used as its substitute. Do not infer a
safe probing height from the factory mount coordinates.

`C5_TOOL_OFFSET_CALIBRATE T=0 Z=1 SAVE=1 BUILDPLATE_REMOVED=1` probes Z using `[e_stop Z]`, then
measures XY using `[e_stop X]` and `[e_stop Y]` on `levelboard:PD0`. It
stores raw T0 to T3 measurements; G-code offsets are relative to T0, with
the separate `zoffset.json` per-tool adjustment added to Z. Run
`SAVE_CONFIG` after reviewing staged values.

For `TOOL=ALL`, the stock touchscreen's ordinary calibration pin is also
used before any tool is picked up. The bare carriage's `[probe]` on
`eboard:PG0` measures X43/Y226 and the cylinder location from `test.json`
three times each. A spread of 0.1 mm or more, or a difference between the
locations below 0.8 mm, aborts calibration as an untrustworthy reading or
possible installed build plate. Its first Z reading limits the levelboard
Z approach (never past `z_probe_target`). The levelboard still measures the
actual fixture and each nozzle; the ordinary pin alone is not used as a
tool offset. A single-tool run with a head already mounted cannot repeat
the bare-carriage pin check, so use `TOOL=ALL` for the complete stock-like
sequence.

Normal attached-head recovery uses `C5_PREPARE_MACHINE` with the build plate
installed. It homes X/Y and docks the detected head, without measuring nozzle
offsets or probing Z. The configured `safe_z_home` clearance hop is still used
before XY travel, including when Z is unreferenced. This is distinct from
explicit extruder offset calibration, which requires plate removal.
An all-axis `G28` (including the touchscreen Home All action) uses this same
physical-pin check. With a head mounted it homes XY, verifies and docks that
head, then homes only Z; it does not home XY a second time. With all heads
parked it uses Klipper's normal all-axis homing. A partial `G28 Z` is rejected
while a head is mounted.

The config-level wrapper first prompts for build-plate removal and stops
without moving. Once the plate is removed, rerun it as
`C5_CALIBRATE_OFFSETS TOOL=0 BUILDPLATE_REMOVED=1`. The specified tool
must already be physically mounted; home XYZ first. Doors may remain open if
the chamber heater is off. It
automatically probes Z, then scans XY at the measured Z +0.6 mm. `SAVE=1`
stages the values in Klipper and writes `/usr/data/firmwareRes/config/extruder.json`
after making a timestamped backup. Run `SAVE_CONFIG` to persist the Klipper
config too. `Z=0 SCAN_Z=<measured height>` is an opt-in XY-only mode. The
single-tool wrapper does not pick up or dock heads automatically.

To measure all four in one run, first call `C5_CALIBRATE_OFFSETS TOOL=ALL` to
see the removal prompt, remove the build plate, then call
`C5_CALIBRATE_OFFSETS TOOL=ALL BUILDPLATE_REMOVED=1`. It requires
XYZ already homed and all heads parked. It first checks the ordinary probe
pin, then probes Z and scans XY for the bare levelboard reference; AFC then
selects, probes Z, scans XY, and docks
T0 through T3 in order. Each XY scan uses its own measured Z +0.6 mm. After
all four succeed, it writes `extruder.json` atomically with a timestamped
backup and stages the Klipper config. The stock `zoffset.json` is read as a
separate per-tool fine adjustment and is not overwritten. Run `SAVE_CONFIG`
after reviewing results. If any step fails, the sequence stops without
writing `extruder.json`, possibly with a head still attached. Inspect the
tool and sensor state before resuming.

The factory `ff_eddy.py`, `e_stop.py`, and `hd_home.py` Klippy modules are
present in `klipper-c5`. This port fixes their incompatible probe call and
the `REMOVE_PEEL` response handler. Keep the stock `[ff_eddy levelboard]`,
`[e_stop X]`, `[e_stop Y]`, and `[e_stop Z]` sections in the printer config.

## Printing and AFC

Virtual-SD jobs started through Moonraker/Mainsail or `SDCARD_PRINT_FILE`
now invoke `C5_PRINT_START` automatically before the first file command.
The start hook reads the first 64 KiB for the first nonzero `M104`/`M109`
hotend and `M140`/`M190` bed temperatures and the first T0–T3 selection.
It defaults to T0 and an unheated bed when those are absent, but refuses to
print without a hotend temperature. A file that already contains
`C5_PRINT_START` in its header runs that command instead, without duplication.
Use plain `.gcode`, not `.gcode.3mf`; direct streamed G-code does not use
virtual SD and is outside this hook.

The slicer can issue AFC's T0–T3 mappings, or call
`C5_PRINT_START TOOL=0 BED=60 HOTEND=220`. `C5_PRINT_START` first checks the
physical sensors through `C5_HOME_FOR_PRINT`. If a head is attached, it first
homes XY and docks that head, then verifies all heads are parked before Z
homing. A recovery failure blocks Z homing. Keep the build plate installed
throughout normal print preparation. With all heads parked, it homes normally,
selects the tool through `AFC_SELECT_TOOL`, heats it, optionally runs the
`C5_FLOW_STROKES` measurement, then runs `C5_TOOL_PURGE` in the factory
preparation area at X266.5/Y13.8 before cooldown. The purge command checks that a
tool is physically attached and its hotend permits extrusion, then activates
that hotend's logical extruder before feeding. There is one shared physical
extrusion motor; the four logical selections provide the hotend contexts.

Failed reference or nozzle calibration restores the previous measurements
and runtime G-code offsets. Partial Z results are not kept if XY probing fails.

Mainsail's Misc controls now show **flow_calibration** as an on/off switch,
like AFC's quiet mode. It starts on by default (`flow_calibration_default`
in `printer.creator5.cfg`) and controls the next print; the previous
`C5_MISC_FLOW_ON`/`C5_MISC_FLOW_OFF` commands remain available for scripts,
but no longer clutter the macro buttons. `printer.misc.cfg` still provides
`C5_MISC_BED_LEVEL_ON`/`C5_MISC_BED_LEVEL_OFF`, and `C5_MISC` reports both
states. Bed leveling defaults on at each Klippy restart. The slicer can
override either setting per job using
`C5_PRINT_START ... FLOW_CALIBRATION=1 BED_LEVELING=1` (or `=0`). Print start
homes XY, docks an attached head, then homes Z. It heats and picks up the
requested head, purges at the preparation area, and optionally prints the
flow-test line. It then docks the head, probes a fresh bed mesh if leveling is
enabled (otherwise loads a saved `default` mesh if present), probes the bed
center, picks the head back up, prints a purge line, and enters the file.
The selected nozzle is turned off after the preparation purge and optional
flow test, so it cools while parked; it is reheated before the final purge
line.
Before either low-Z purge, `C5_AUTO_NOZZLE_Z` applies the measured
tool-to-station nozzle clearance and `C5_VERIFY_NOZZLE_Z` rejects a missing
or reset offset. The stock firmware uses `SET_GCODE_OFFSET ... MOVE=1`; the
Creator 5 port now does the same. The stock example `extruder.json` yields
about 2.86 mm for T0 before print compensation, but actual printer calibration
values are authoritative. As in factory `BuildPage::startPrint`, the offset
also includes `(hotend - 120) * tempOffset` from `test.json`, -0.08 mm for a
bed target of at least 100 C, -0.06 mm for a first layer below 0.11 mm, and
the selected tool's saved touchscreen adjustment. Orca's
`; first_layer_height = ...` header is passed through automatically when
present; otherwise the print macro uses 0.2 mm. This is a saved-calibration
calculation, not a fresh nozzle-to-bed contact probe.
The center `PROBE` reading establishes/checks the bed reference. On the final
pickup, `C5_AUTO_NOZZLE_Z` applies the factory print-start relationship:
selected tool `tN_offset_z` minus `z_station_pos` from the measured
`extruder.json`, plus the touchscreen-saved `z_offset_t1`–`z_offset_t4` from
`zoffset.json`. It refuses missing calibration files, the wrong attached tool,
or a result outside 0.5–5 mm. This is the automatic nozzle Z correction;
the probe reading alone is not treated as nozzle contact.
A live touchscreen `SET_GCODE_OFFSET` adjustment that is not saved to that JSON
is not persistent across docking or restarting. After the touchscreen applies
its live `SET_GCODE_OFFSET Z=...` value, it should send
`C5_SAVE_TOUCHSCREEN_Z_OFFSET` while that tool is still physically attached.
This command subtracts the currently applied automatic nozzle Z baseline
(or the tool's levelboard-relative Z before automatic correction), writes its
`z_offset_t1`–`z_offset_t4` adjustment to the stock JSON, and keeps a dated
backup. It does not move the nozzle. The probe-to-nozzle reference
must still be validated on hardware before relying on an unattended first layer.

The flow switch prints an 80 mm, known-volume test line at X100–180/Y20,
Z0.3 after the selected tool is hot. Inspect or measure that line to tune
the slicer's flow ratio. It **does not automatically measure or correct**
filament flow: no verified sensor/algorithm for that is present in this port.
Run it only after verifying the bed surface, Z offset, and these XY positions.
Because this test line runs before meshing, verify it does not overlap any
mesh probe point; disable the flow switch if it does.
The `chamber_led` starts at 100% white using `initial_WHITE: 1.0`.

Use `C5_PRINT_STOP` at the end of a print. It stops heating, turns off the
part fan, calls `AFC_UNSELECT_TOOL` to park the current head when homed, and
disables motors. AFC's `custom_tool_swap` and `custom_unselect` entries route
physical changes into the Klippy safety coordinator. AFC's
`enable_standalone_purge` is disabled to avoid a second purge. The stock
filament presence pins belong to AFC; the filament motion encoders remain
in `printer.filament.cfg`.

## Filament runout and loading

Each AFC toolhead sensor has `enable_tool_runout: True` and
`debounce_delay: 10`. If the active tool loses filament during a print and
the sensor remains clear for ten seconds, AFC pauses the print. The four
filament motion encoders remain diagnostic only; they do not issue a second
pause. AFC's toolhead-sensor runout behavior and debounce setting are
documented in the [AFC hardware config](https://www.afcproject.dev/configuration/AFC_Hardware.cfg.html).

For standalone loading, insert filament manually until AFC reports the
toolhead sensor loaded. `C5_PREPARE_LOAD_T0` through `C5_PREPARE_LOAD_T3`
(optional `TEMP=...`, default 220 C) select and heat the requested tool;
`C5_PREPARE_FILAMENT_LOAD TOOL=0 TEMP=220` is the parameterized equivalent.
Once hot, `C5_LOAD_FILAMENT LENGTH=20` feeds and purges up to 80 mm in the
factory preparation area. Use that final feed only if AFC has not already
completed the load; AFC standalone behavior may vary by add-on version.
Loading is blocked while a print is running, including while it is paused, because tool selection and purging move the toolhead. Finish or cancel the print before loading filament.

This implementation has been compiled and statically checked on the host.
Physical sensor polarity, fixture height, four mount coordinates, and
pickup/release timing must be verified on the printer before unattended use.
