# Creator 5 Klippy toolchanger

The host code lives in `kalico/klippy/extras/creator5_toolchanger.py`.
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
Each standalone AFC extruder sets `auto_load_on_tool_: False`, so a
filament-switch transition updates AFC's presence state without automatically
extruding. Tool selection only performs Creator 5 pickup/docking and logical
extruder activation; explicit filament loading and print-purge remain
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

## First-time setup dialog

After installing, Fluidd, Mainsail and the touchscreen show a short setup
dialog. It is a series of `action:prompt` pages from `printer.misc.cfg`, so
any client that shows Klipper prompts can answer it.

| Page | Text | Buttons | Effect |
| --- | --- | --- | --- |
| OpenCreator | Welcome, and that all previous settings were imported (input shaper and PID from FlashForge's calibration, tool offsets, Z offsets and dock positions) | Let's get started! | Next page |
| Pressure Advance Calibration | Run pressure advance calibration (flow calibration) at the start of every print? | No / Yes | Sets the `flow_calibration` switch |
| Purging | Purge each tool into the bucket at the start of every print? | No / Yes | Sets the `purge` switch |
| Clog Detection | Do you want Clog Detection enabled? | No / Yes | Sets the `clog_detection` switch |
| Bed Heat Soak | Do you want bed heat soaking enabled? | No / Yes | Sets the `bed_soak` switch |
| Offsets and docking | Where the offsets come from, and the calibration commands if they're off | Next | Next page |
| Thank you! | Thanks for using the first version of OpenCreator, Public Alpha Version 1, and the Discord link, https://discord.gg/RsdkqDtfww | Finish | Closes the dialog |

**Clog Detection.** With it on, a tool's filament wheel (`fm_exN`) stopping
while that tool is printing and its filament switch still sees filament
pauses the print with `E0163 ... clog detected`. With it off, the wheel is
ignored; running out of filament is still handled by the filament switch and
AFC either way.

**Bed heat soak.** With it on, print start waits at bed temperature for
`bed_soak_minutes` (in `printer.creator5.cfg`) right before a fresh bed mesh,
so the mesh is taken after the plate has finished warping. It only runs when
the print makes a new mesh and the bed is heated.

The answers are the same switches shown under Fans & Outputs and set by
`C5_MISC_BED_SOAK_ON`/`OFF` or `SET_PIN PIN=clog_detection VALUE=1`, so they
can be changed at any time later. Like the other Misc switches, they are saved
in `c5_misc_variables.cfg` and survive restarts.

### When it shows

Klipper cannot tell when a browser opens, so the dialog is driven from
Klipper's side instead:

- `C5_FIRST_SETUP_CHECK` runs 10 seconds after Klipper starts and shows the
  dialog, then shows it again every 60 seconds. A browser opened later sees
  it within a minute.
- It returns on the page last reached, so closing it part way and coming back
  does not start over. A Klipper restart does start over, at the welcome page.
- It is not shown while a print is printing or paused; the 60 second check
  keeps waiting until the printer is idle.
- Reaching the last page saves `c5_first_setup_done: 1` in
  `c5_misc_variables.cfg` and stops the check. From then on it never shows on
  its own, including after updates that keep that file.

### Running it again

- `C5_FIRST_SETUP` opens the dialog at the welcome page. It only shows the
  dialog; answering it changes those switches again.
- To have it show on its own again, as on a fresh install, remove the
  `c5_first_setup_done` line from `c5_misc_variables.cfg` (or run
  `SAVE_VARIABLE VARIABLE=c5_first_setup_done VALUE=0`) and restart Klipper.

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
hand, measures X/Y with `[hd_home X]` and `[hd_home Y]`
(travelling at 200 mm/s to 10 mm short of where the saved holder position puts
each endstop, or `max_mount_correction` + 5 mm if that is wider, and measuring
slowly only from there), rehomes XY to discard the temporary measurement frame, then re-docks at the
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

Run `C5_CALIBRATE_OFFSETS` with no arguments to be walked through it in a
Fluidd/Mainsail prompt: all tools or one tool, then build-plate removal, then
(single tool only) whether to also refresh the levelboard probe reference.
All-tool calibration offers to home first, with the plate still installed,
if the printer is not homed. The final answer runs the command below with
the matching arguments. The prompt is built into the toolchanger module of
Kalico as `C5_OFFSET_WIZARD`; the firmware's own
`C5_TOOL_OFFSET_CALIBRATE` and `C5_CALIBRATE_ALL_OFFSETS` open it too when
run without arguments (the latter starting at the plate step).

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
present in Kalico. This port fixes their incompatible probe call and
the `REMOVE_PEEL` response handler. Keep the stock `[ff_eddy levelboard]`,
`[e_stop X]`, `[e_stop Y]`, and `[e_stop Z]` sections in the printer config.

`[ff_eddy]` only sends `trigger_threshold` to its board when Klippy
connects. Its `GET_BASIC_PARAM_*`, `REMOVE_PEEL_*` and
`SET_TRIGGER_THRESHOLD_*` commands are manual diagnostics; nothing in
OpenCreator or the stock firmwareExe calls them. With Kalico's MCU firmware the
configured values (eboard -20, levelboard 25) are already the firmware
defaults, and the eboard replaces its threshold with one measured from sensor
noise after each calibration. The sections are kept for printers still on
FlashForge's MCU firmware, and because removing the module would stop
existing configs that list them from loading.

## Extruder Rotation Calibration

`C5_EXTRUDER_ROTATION_CALIBRATION` (or `C5_EXTRUDER_ROTATION_CALIBRATE`)
sets a tool's `rotation_distance` from its `fm_exN` filament wheel. It homes
if needed, picks up the tool with AFC, moves to the purge bucket, heats,
applies nozzle Z (`C5_AUTO_NOZZLE_Z`), primes 5 mm, then extrudes a known length. During that extrusion it counts
the wheel's pulses. The measured length is the pulse count times
`wheel_mm_per_pulse`, and the new rotation distance is the current one
scaled by measured ÷ requested. The new value is applied immediately and
staged for `SAVE_CONFIG`. When it finishes or is cancelled, it cools the nozzle at the wiper
(`C5_COOL_FOR_DOCK`), turns the heater off and docks the tool with
`AFC_UNSELECT_TOOL`. If it fails or times out, it only turns the heater off
and leaves the tool mounted. Without `TOOL`, it asks which tool
to calibrate.

| Parameter | Default | |
|---|---|---|
| `TOOL` | prompt | 0–3 |
| `LENGTH` | 100 | mm extruded while counting |
| `SPEED` | 3 | mm/s |
| `TEMP` | 245 | nozzle temperature |
| `MANUAL` | 0 | 1 forces the manual wheel step |
| `MARK` | `LENGTH` + 20 | mark distance for the manual step |

The defaults come from `rotation_calibration_length`,
`rotation_calibration_speed` and `rotation_calibration_temp` in
`[creator5_toolchanger]`. `rotation_calibration_timeout` (30 s) limits the
manual measuring step below.

**Wheel scale (first run).** The wheel's mm per pulse is not known from
stock. While `wheel_mm_per_pulse` is unset, or with `MANUAL=1`, the
calibration stops after priming and asks you to mark the filament `MARK` mm
above where it enters the tool. Press **Extrude**, then measure from the
inlet to the mark and run
`C5_EXTRUDER_ROTATION_CALIBRATE TOOL=n REMAINING=<mm>`. The real length
moved (`MARK` − `REMAINING`) gives `wheel_mm_per_pulse` and a rotation
distance, which is applied to all four tools since they share one motor.
Both are staged for `SAVE_CONFIG`. After that, run the calibration on any
single tool to fine-tune it from its wheel, with no marking. If `REMAINING` is
not sent within 30 seconds of the extrusion finishing, the calibration
errors out and turns that tool's heater off. Later runs on any tool are
automatic. This assumes all four wheels are the same size.

The run stops with an error if the wheel sees fewer than 10 pulses, or if
the measured length is outside 70–130 % of the requested length (slipping,
a wrong mark, or a wrong `wheel_mm_per_pulse`). Each logical extruder keeps
its own `rotation_distance`, so tools can differ.

## Toolchange counter

Every completed pickup adds one to `toolchanges.txt` in the config directory
(next to `printer.cfg`), with a total and a count per head:

```text
Total: 3
T0: 1
T1: 0
T2: 2
T3: 0
```

Selecting a head that is already attached doesn't count. Set
`toolchange_count_path` in `[creator5_toolchanger]` to keep it elsewhere.
Edit or delete the file to reset it; it's re-read when Klipper restarts.

## Printing and AFC

Virtual-SD jobs started through Moonraker/Mainsail or `SDCARD_PRINT_FILE`
now invoke `C5_PRINT_START` automatically before the first file command.
The start hook reads the first 64 KiB for the first nonzero `M104`/`M109`
hotend and `M140`/`M190` bed temperatures and the first T0–T3 selection.
It defaults to T0 and an unheated bed when those are absent, but refuses to
print without a hotend temperature. The updated shared Kalico hook also
passes `MATERIAL0=`–`MATERIAL3=` from Orca's semicolon-separated
`; filament_type = ...` list in the startup prefix or last 64 KiB (trailer
takes precedence), with no Orca edits. Updated config macros apply these
properties to all four hotends without selecting, heating or purging extra
tools. Missing or invalid slots use configured MPC defaults, not settings
from a previous print. This reads metadata, not loaded filament. MPC must
be enabled and calibrated; see [MPC hotend control](CREATOR5_MPC.md).
It also passes `USED_TOOLS=` (slots with filament used in Orca's
`; filament used [mm]`) and `IDLE0=`–`IDLE3=` (nonzero `; idle_temperature`
slots). Before the first tool waits for its print temperature, every other
tool in `TOOLS` or `USED_TOOLS` is set to its `IDLEn`, or 100 °C without one.
A file with `C5_PRINT_START` in its header bypasses generated start and
material commands completely; that explicit command owns `MATERIAL=` /
`MATERIAL0=`–`MATERIAL3=`. It still runs without duplication.
Use plain `.gcode`, not `.gcode.3mf`; direct streamed G-code does not use
virtual SD and is outside this hook.

The slicer can issue AFC's T0–T3 mappings, or call
`C5_PRINT_START TOOL=0 BED=60 HOTEND=220`. `C5_PRINT_START` first checks the
physical sensors through `C5_HOME_FOR_PRINT`. If a head is attached, it first
homes XY and docks that head, then verifies all heads are parked before Z
homing. A recovery failure blocks Z homing. Keep the build plate installed
throughout normal print preparation. After homing, `C5_CHECK_BUILD_PLATE`
confirms the plate is installed using the same stock-pin comparison offset
calibration uses to confirm it is removed: the pin heights at
`plate_check_x`/`plate_check_y` and the factory cylinder must differ by less
than `plate_check_min_delta`. It travels between the probe points at
`plate_check_travel_speed` (default 100 mm/s). A missing plate stops the print before anything
heats. Pass `BUILDPLATE_CHECK=0` to skip it for one job. With all heads parked, it homes normally,
selects only the requested `TOOL` or listed `TOOLS` through `AFC_SELECT_TOOL`,
heats each selected tool,
optionally runs the `C5_FLOW_STROKES` bucket flow check, then runs
`C5_TOOL_PURGE` at the configured bucket at X276.5/Y260 before cooldown at
X266.5/Y13.8. Only prepared tools need filament and fitted nozzles. To
prepare multiple tools at startup, pass an explicit list such as
`C5_PRINT_START TOOL=3 TOOLS=1,3 BED=60 HOTEND=220`; the selected `TOOL`
must be in `TOOLS`. By default each listed tool uses `HOTEND`; pass
`HOTEND0` through `HOTEND3` when their materials need different temperatures.
Automatic virtual-SD startup physically prepares only the initial tool;
its MPC material setup covers all four tools independently. Both
bucket-bound moves approach
through X250/Y250; cooldown leaves through that waypoint. The purge command checks that a
tool is physically attached and its hotend permits extrusion, then activates
that hotend's logical extruder before feeding. There is one shared physical
extrusion motor; the four logical selections provide the hotend contexts.

Failed reference or nozzle calibration restores the previous measurements
and runtime G-code offsets. Partial Z results are not kept if XY probing fails.

Fluidd's Fans & Outputs panel shows the virtual output pins **flow_calibration**,
**purge**, **bed_leveling**, **bed_soak**, **clog_detection**,
**lower_bed_on_end**, **quiet_mode**, **startup_tune**, and
**print_start_tune** controls as on/off switches (plus **chamber_heat_fan_full** on the Pro,
which keeps the chamber heater fan at 90% (`fan_speed`) instead of slowing it near the chamber target). They do not drive physical
MCU pins. Flow and purge start on by default
(`flow_calibration_default` and `purge_default` in `printer.creator5.cfg`)
and control the next print. Turning purge off skips preparation
purges; if flow calibration is also off, the used-tool preparation loop is
skipped entirely. Flow calibration remains independent and still extrudes its
measurement strokes when enabled. Explicit manual `C5_TOOL_PURGE` and
`C5_PURGE_LINE` commands are unaffected. The previous
`C5_MISC_FLOW_ON`/`C5_MISC_FLOW_OFF` commands remain available for scripts,
but no longer clutter the macro buttons. `printer.misc.cfg` still provides
`C5_MISC_BED_LEVEL_ON`/`C5_MISC_BED_LEVEL_OFF`, and `C5_MISC` reports both
states. Fans & Outputs also shows **lower_bed_on_end**, which defaults off. Toggle it
with `SET_PIN PIN=lower_bed_on_end VALUE=1` (or `VALUE=0`).
Its startup default and travel speed are `lower_bed_on_end_default` and
`lower_bed_speed` in `printer.creator5.cfg`. These Misc choices, bed leveling,
and the startup and print-start tune switches are saved across Klippy restarts
in `/usr/data/opencreator/klipper/config/c5_misc_variables.cfg`. Bed leveling defaults on until
changed. The slicer can
override flow calibration, purge, and bed leveling per job using
`C5_PRINT_START ... FLOW_CALIBRATION=1 PURGE=1 BED_LEVELING=1` (or `=0`). Print start
homes XY, docks an attached head, then homes Z. It picks up and primes only
the tool IDs in `TOOLS` (or just `TOOL` when `TOOLS` is omitted), optionally
checking each selected tool's flow over the bucket,
and docks each after cooldown. It then probes a fresh bed mesh if leveling is
enabled (otherwise loads a saved `default` mesh if present), probes the bed
center, picks the head back up, prints a purge line, and enters the file.
Each nozzle is cooled before docking; the requested print nozzle is reheated
before the final purge line.
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

The flow switch runs alternating-speed XY+E strokes over the bucket, centered
on X276.5/Y260 at Z8. The configured 5 mm sweep stays within X274–279,
inside the usable X280 boundary and farther from the chute's inboard wiper.
The touchscreen's full 1.13573/2.27146 mm extrusion pulses are retained;
travel speed and acceleration are scaled to 4.5/22.875 mm/s and 625 mm/s²
so the eboard sees approximately the stock motor-current pulse lengths. The
previous version also scaled extrusion down by eight, making the classifier's
stock waveform threshold unlikely to be met. The host waits 50 ms after
stopping acquisition for the eboard's verdict task. It applies the mean of three
valid eboard-selected pressure-advance candidates. If fewer than three valid
readings arrive, it restores the prior value. This does **not** change the
slicer's filament-flow ratio. Verify the entire X274–279/Y260 path is over the
bucket before enabling this on the physical printer. This timing-equivalent
bucket path still needs a hardware check; it is not the touchscreen's long
straight-line XY path.

The eboard check needs the extruder drivers in StealthChop
(`stealthchop_threshold: 999999` on each `[tmc2209 extruder*]`); in
SpreadCycle `SG_RESULT` stays near zero and no candidate ever passes.

`PAUSE` saves the current print position and raises Z by up to 5 mm without
moving XY toward the docked heads. `RESUME` delegates to Klipper's saved-state
restore with the return move capped at 10 mm/s; AFC's wrapper remains in place
when PREP has installed it. At the
cooldown wiper (X266.5/Y13.8), the nozzle descends to Z2, the eboard
`fanM106` toolhead fan runs during cooldown, and the nozzle rises to Z10
before docking. Verify wiper XY and Z clearances on the physical machine.
Toolchange travel uses the configured 600 mm/s and 30000 mm/s² limits.
Toolchanger UI status polls reuse sensor results for up to one second, but every pickup,
dock, and interlock check still samples the physical sensors directly.
On pickup, the first 20 mm of pullback remains at the configured 80 mm/s latch
clearance speed; the remaining pullback and exit toward X250 use the 600 mm/s
clear-travel speed. The tool is activated only after final sensor verification.
After a successful selection, acceleration is set to 30000 mm/s² for the move
toward the print; a failed pickup restores the prior acceleration.
The `chamber_led` starts at 100% white using `initial_WHITE: 1.0`.

Virtual SD runs `C5_PRINT_STOP` automatically at successful end-of-file when
`auto_creator5_start` is enabled. A file that already calls it is not run
twice. Pauses, cancellations, and command errors do not take the normal EOF
path; a failed stop macro marks the print as errored. Direct streamed G-code
still needs to call the macro itself. `C5_PRINT_STOP` stops heating, turns off the
part fan and chamber fans (`M107`, `M107 P2`, `M107 P3`), and raises Z by up to
10 mm of available travel. When XYZ are homed, it checks the selected physical
extruder's AFC `on_shuttle` status, which samples fresh mount sensors rather
than cached Creator 5 UI status or AFC's loaded filament lane. A matched
attached head uses `AFC_UNSELECT_TOOL` to preserve AFC bookkeeping. Otherwise
it calls the safety coordinator's `C5_TOOL_DOCK` directly: an empty shuttle is
a no-op, while a head mismatched with the selected extruder is docked using
the physical sensors. Invalid mount sensors stop docking at command execution,
after heater and fan shutdown, without allowing subsequent bed lowering or
motor disabling. An empty shuttle never invokes the legacy `UNSELECT_TOOL`
fallback. After successful docking/no-op, the macro optionally lowers the bed
to the physical Z maximum before disabling motors. The optional move only runs
when Z is homed and uses machine coordinates, independent of nozzle Z offsets.
AFC's `custom_tool_swap` and `custom_unselect` entries route
physical changes into the Klippy safety coordinator. AFC's
`enable_standalone_purge` is disabled to avoid a second purge. The stock
filament presence pins belong to AFC; the filament motion encoders remain
in `printer.filament.cfg`.

The Creator 5 AFC profile disables the unused TD-1 reader check,
virtual-lane filament-weight timer, feeder quiet-mode switch, and AFC macro
button injection. T0-T3 mapping, physical filament sensors, runout handling,
and AFC tool selection remain enabled. These opt-outs are confined to the
Creator 5 config; other AFC installations retain their defaults.
The Klipper fork also omits AFC's buffer, button, hub, tip-forming, poop, and
HTLF hardware modules. They are not loaded by this standalone profile. Restore
the modules before configuring feeder hardware that needs them.

## Filament runout and loading

Each AFC toolhead sensor has `enable_tool_runout: True` and
`debounce_delay: 10`. If the active tool loses filament during a print and
the sensor remains clear for ten seconds, AFC pauses the print. The four
filament motion encoders remain diagnostic only; they do not issue a second
pause. AFC's toolhead-sensor runout behavior and debounce setting are
documented in the [AFC hardware config](https://www.afcproject.dev/configuration/AFC_Hardware.cfg.html).

After that pause, `C5_FILAMENT_RUNOUT` (`printer.filament.cfg`) retracts the
remaining filament (`retract_length`, default 100 mm at 10 mm/s) and opens a
Fluidd/Mainsail prompt: "Filament has run out of Tn, would you like to switch
over or start loading new filament".

- **Switch to Tm** appears for every other tool whose sensor detects filament.
  `C5_RUNOUT_SWITCH` heats Tm to Tn's print temperature, swaps heads, maps Tn's
  slicer tool to Tm, returns to the paused position with Tm's offsets, resumes,
  and turns Tn's heater off.
- **Load new filament** reheats Tn and moves it to the purge bucket. Insert
  filament until it stops and press **Load**: Tn purges `load_length` (default
  80 mm), and the print resumes where it paused.
- Closing the prompt leaves the print paused. `RESUME` or `CANCEL_PRINT` work
  as usual.

The lengths are variables on `[gcode_macro C5_FILAMENT_RUNOUT]`.

**Infinite spool:** give a tool a backup in AFC (the lane's runout setting in
Fluidd/Mainsail, or `SET_RUNOUT LANE=extruder RUNOUT=extruder2`). When that tool
runs out, the print pauses and retracts the same way, then switches to the backup
without asking: `C5_FILAMENT_RUNOUT TOOL=n TO=m` runs the same switch as the
prompt's **Switch to Tm**. Later `Tn` commands in the file go to Tm (`SET_MAP`), and
so do `M104`/`M109 Tn`. `C5_PRINT_STOP` resets the mapping. If the backup has no
filament, the prompt appears instead. If the switch fails, the print stays paused
and the prompt comes back.

AFC calls all of this from the filament sensor's background callback. It first
lets the print finish its current line and saves that position. Only then does it
run `PAUSE` and `C5_FILAMENT_RUNOUT` as normal G-code, as Klipper's own runout
handling does, so nothing else runs in the middle of the switch. `PAUSE` lifts the
nozzle 5 mm before the head travels to the dock.

For standalone loading, insert filament manually until AFC reports the
toolhead sensor loaded. `C5_PREPARE_LOAD_T0` through `C5_PREPARE_LOAD_T3`
(optional `TEMP=...`, default 220 C) select and heat the requested tool;
`C5_PREPARE_FILAMENT_LOAD TOOL=0 TEMP=220` is the parameterized equivalent.
Once filament is inserted, `C5_LOAD_FILAMENT LENGTH=20` heats and loads the
physically attached tool, including when invoked from a macro button without
parameters. It requires a valid attached-tool sensor state matching the active
extruder; it never selects a tool implicitly. `TEMP=...` overrides the loading
temperature. Without `TEMP`, it reuses the attached heater's target if it is
within 150–300 C, otherwise it uses 220 C. It sets that target and waits until
the measured temperature reaches at least the target minus 2 C before feeding,
even when cold extrusion is enabled. Measured room temperature is never used
as the loading or cooldown operating temperature.

AFC's "load lane" button sends `CHANGE_TOOL LANE=extruderN`. Outside a print, a
`CHANGE_TOOL` macro (in `printer.afc-standalone.cfg`) runs
`C5_LOAD_FILAMENT TOOL=N` instead, with `NEW_EXTRUDER_TEMP` as `TEMP` and
`PURGE_LENGTH` as `LENGTH` when given. During a print, it's AFC's own tool change
(`_AFC_CHANGE_TOOL`).

Specify a nozzle with `C5_LOAD_FILAMENT TOOL=2 TEMP=255 LENGTH=20`, or several
with `C5_LOAD_FILAMENT TOOLS=0,2 TEMP0=220 TEMP2=255 LENGTH=20`. With explicit
tool selection, `TEMP` sets a common temperature (default 220 C); `TEMP0`
through `TEMP3` override it per nozzle. Explicit loading temperatures must be
finite and within 150–300 C. Each requested tool is selected, heated,
has its calibrated automatic nozzle Z offset applied, purged up to 80 mm
over the rear-right bucket, cooled at the wiper, turned
off, and docked before proceeding to the next. Insert filament into every
requested tool before running the multi-tool command. If a requested tool is
already mounted, it is handled first. A mounted tool not in the requested
list must be safely cooled and docked first; the macro will not switch it
automatically. Use the final purge only after AFC detects filament. During a
paused print, the no-tool-argument form heats and waits, then feeds the attached
tool in place while preserving the paused G-code state. It does not select a
tool, travel to the bucket, cool, or dock across the part. Explicit tool
selection requires an idle print.

The loader passes its chosen loading temperature to `C5_COOL_FOR_DOCK`, not
the measured nozzle temperature. The existing cooldown calculation remains
`max(0, HOTEND - 100)`; no change to the Klippy cooldown command is required.

This implementation has been compiled and statically checked on the host.
Physical sensor polarity, fixture height, four mount coordinates, and
pickup/release timing must be verified on the printer before unattended use.
