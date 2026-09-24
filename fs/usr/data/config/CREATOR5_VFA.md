# Creator 5 VFA compensation

`VFA_COMPENSATION` is the MCLib calibration button for the custom Klipper
configuration. It mirrors the stock `firmwareExe.i64` VFA path: home, move to
Z100 and X130/Y130, then run `STEPPER_RESONANCE_FACTORY_CALIBRATE`.

Run it only with a clear build area and all toolheads docked. The macro rejects
an active or paused print and an attached toolhead. Calibration measures X and
Y with the configured LIS2DW accelerometer, stages the resulting `td1`, `td2`,
and `td4` amplitude/phase values in the `[mclib stepper_x]` and
`[mclib stepper_y]` sections, then runs `SAVE_CONFIG`. That command writes the
values and restarts Klipper.

`C5_PRINT_START` calls `STEPPER_RESONANCE_DAMP_ENABLE` before print motion.
That macro now invokes `MCLIB_APPLY_CALIBRATION` for X and Y, restoring the
saved MCLib values instead of fixed factory numbers. The Klipper host must be
updated along with these config files because the restore command is new.

This workflow is implemented but still needs on-printer validation. Confirm
homing, test travel, accelerometer readings, saved values, and subsequent print
motion before using it unattended.
