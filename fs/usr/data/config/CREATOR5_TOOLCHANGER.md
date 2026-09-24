# Creator 5 Klippy toolchanger

The host code lives in `klipper-c5/klippy/extras/creator5_toolchanger.py`.
`printer.base.cfg` includes `printer.creator5.cfg` and
`printer.afc-standalone.cfg`. AFC owns T0 through T3. Install the AFC Klipper
add-on before using this config; stock Klipper does not provide the
`[AFC_Toolchanger]` and `[AFC_extruder]` objects.

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
stock dock and grab inputs before and after motion, checks the doors, requires
homed axes, limits automatic coordinate corrections, and disables heaters if
post-motion tool verification fails. The startup scan follows the binary's
four-direction levelboard measurement around the calibration target.

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
hand **and close the doors**, measures X/Y with `[hd_home X]` and `[hd_home Y]`,
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

Normal attached-head recovery uses `C5_PREPARE_MACHINE` with the build plate
installed. It homes X/Y and docks the detected head, without measuring nozzle
offsets or probing Z. The configured `safe_z_home` clearance hop is still used
before XY travel, including when Z is unreferenced. This is distinct from
explicit extruder offset calibration, which requires plate removal.

The config-level wrapper first prompts for build-plate removal and stops
without moving. Once the plate is removed, rerun it as
`C5_CALIBRATE_OFFSETS TOOL=0 BUILDPLATE_REMOVED=1`. The specified tool
must already be physically mounted; home XYZ first, with doors closed. It
automatically probes Z, then scans XY at the measured Z +0.6 mm. `SAVE=1`
stages the values in Klipper and writes `/usr/data/firmwareRes/config/extruder.json`
after making a timestamped backup. Run `SAVE_CONFIG` to persist the Klipper
config too. `Z=0 SCAN_Z=<measured height>` is an opt-in XY-only mode. The
single-tool wrapper does not pick up or dock heads automatically.

To measure all four in one run, first call `C5_CALIBRATE_OFFSETS TOOL=ALL` to
see the removal prompt, remove the build plate, then call
`C5_CALIBRATE_OFFSETS TOOL=ALL BUILDPLATE_REMOVED=1`. It requires
XYZ already homed and all heads parked. It first probes Z and scans XY for
the bare levelboard reference; then AFC selects, probes Z, scans XY, and docks
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

The slicer can issue AFC's T0–T3 mappings, or call
`C5_PRINT_START TOOL=0 BED=60 HOTEND=220`. `C5_PRINT_START` first checks the
physical sensors through `C5_HOME_FOR_PRINT`. If a head is attached, it first
homes XY and docks that head, then verifies all heads are parked before full
homing. A recovery failure blocks Z homing. Keep the build plate installed
throughout normal print preparation. With all heads parked, it homes, selects
the tool through `AFC_SELECT_TOOL`, heats it, and runs `C5_TOOL_PURGE` in the
factory preparation area at X266.5/Y13.8. The purge command checks that a
tool is physically attached and its hotend permits extrusion, then activates
that hotend's logical extruder before feeding. There is one shared physical
extrusion motor; the four logical selections provide the hotend contexts.

Failed reference or nozzle calibration restores the previous measurements
and runtime G-code offsets. Partial Z results are not kept if XY probing fails.

`printer.misc.cfg` provides touchscreen/web UI macros
`C5_MISC_FLOW_ON`/`C5_MISC_FLOW_OFF` and
`C5_MISC_BED_LEVEL_ON`/`C5_MISC_BED_LEVEL_OFF`. `C5_MISC` reports their
current state. Defaults are off at each Klippy restart. The slicer can
override either switch per job using
`C5_PRINT_START ... FLOW_CALIBRATION=1 BED_LEVELING=1` (or `=0`). When bed
leveling is on, the bed reaches its requested temperature, the machine homes,
then a fresh `BED_MESH_CALIBRATE` runs. When off, a saved `default` mesh is
loaded if available; otherwise no mesh is applied.

The flow switch prints an 80 mm, known-volume test line at X100–180/Y20,
Z0.3 after the selected tool is hot. Inspect or measure that line to tune
the slicer's flow ratio. It **does not automatically measure or correct**
filament flow: no verified sensor/algorithm for that is present in this port.
Run it only after verifying the bed surface, Z offset, and these XY positions.
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
