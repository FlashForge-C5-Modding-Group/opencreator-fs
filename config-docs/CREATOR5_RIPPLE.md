# Motor ripple correction

The X and Y motors don't turn perfectly evenly: detent torque and current shape give a small wobble at fixed
multiples of the motor's electrical angle (4 full steps per electrical cycle). On the Creator 5 the strong ones
are harmonics 2, 4 (once per full step), 6 and 8. That wobble shakes the toolhead at those frequencies, which
is most of the hum and buzz at printing speeds.

Ripple correction feeds a small opposing current to each motor at those harmonics. The right current changes
with speed, so each harmonic has a table of corrections at several speeds, and the mainboard interpolates
between them from the step rate.

## Calibrating

```
RIPPLE_CALIBRATE
```

Homes, picks up the first tool, parks at the bed centre, then for each motor (`AXIS=X` or `AXIS=Y` for one)
moves along the diagonal that turns only that motor and measures the vibration at each harmonic with the
toolhead accelerometer. About 10 minutes per motor; `SAVE_CONFIG` at the end keeps it (`SAVE=0` to skip).
All toolheads must be docked first.

Each point prints the vibration at that harmonic before and after, e.g.

```
stepper_y harmonic 4 at 297 Hz (60 mm/s motor): forward 351 -> 11, reverse 332 -> 26 mm/s^2
```

The result is saved as `ripple_<harmonic>` in `[mclib stepper_x]` / `[mclib stepper_y]`: groups of electrical
frequency (Hz), forward amplitude (A) and phase (rad), reverse amplitude and phase.

## Lower level

- `MCLIB_RIPPLE_CALIBRATE STEPPER=stepper_x HARMONICS=2,4,6,8 SPEEDS=8,15,30,60,120 ROUNDS=2 SAVE=1`: one
  motor. Speeds are mm/s of motor travel (the toolhead moves at 0.71 of that on the diagonal). A point whose
  harmonic would be under 20 Hz or over 700 Hz (what the accelerometer can see) is skipped.
- `MCLIB_RIPPLE_MEASURE STEPPER=stepper_x SPEED=30`: the vibration at harmonics 1 to 8 at one speed, forward
  and reverse, with the current correction.
- `MCLIB_SET_RIPPLE STEPPER=stepper_x`: show the tables. `HARMONIC=4 DIR=1 AMP=0.005 PHASE=1.2` sets one
  correction for every speed (`DIR=1` is the motor's forward), `AMP=0` in both directions clears it.

`[mclib_ripple]` options: `accel_chip` (lis2dw), `center` (130, 130), `accel` (5000) for the test moves,
`speeds` (8, 15, 30, 60, 120), `probe` (0.015 A, the test current), `cruise_time` (0.5 s measured per move),
`fan_hold` (0.5) and `fan_settle` (3 s).

## How it calibrates

The vibration power at a harmonic is a quadratic in the correction c (a complex number: amplitude and phase):
P(c) = P0 + 2·Re(w·c) + g·|c|². Measuring at c, c+δ, c−δ and c+iδ gives g and w, and the minimum is at
c − conj(w)/g. That is checked with one more move and kept only if the vibration went down, then repeated with
half the step. Forward and reverse are measured on the same out-and-back move. Above the fastest calibrated
speed the correction fades out by 1.1 times that frequency, and below the slowest to nothing at half its
frequency, as nothing was measured there.

## Stock VFA damping

VFA (`VFA_COMPENSATION`) corrects harmonics 1, 2 and 4, tuned near the frame's resonance, so mostly at higher
speeds. The mainboard hands over by speed: where a ripple table covers the motor's current speed it replaces
the VFA value for that harmonic, outside the table VFA applies, and in between (the fade zones) the two are
blended. So both can stay calibrated, and VFA keeps working above the fastest ripple point.

## Board fans

Both calibration and `MCLIB_RIPPLE_MEASURE` hold the mainboard and power supply fans at `fan_hold` (50%), and
wait `fan_settle` (3 s) for them to get there, so their vibration stays the same through the measurement.
Otherwise the fans speed up as the mainboard warms during the test, which shows up in the measurement and
throws the calibration off. A hold from `_FANS_HOLD` (as `RIPPLE_CALIBRATE` sets) is kept afterwards.

## Needs

Mainboard firmware with `mclib_set_ripple` (Kalico `phase-stepping` branch); older firmware ignores the
`ripple_*` settings with a warning in the log.

## Measured

Creator 5 Pro, toolhead accelerometer, board fans held at 50%, RMS vibration in 10–100 / 100–300 / 300–800 Hz:
step interpolation plus ripple correction (average of three sessions) against the firmware before both.

| Move | Change |
|---|---|
| Y 5 mm/s | −24% / −39% / −58% |
| Y 10 mm/s | −37% / −38% / −52% |
| Y 20 mm/s | −42% / −54% / −45% |
| Y 80 mm/s | −4% / −30% / +1% |
| X 5 mm/s | −40% / −15% / −17% |
| X 10 mm/s | −34% / +18% / −4% |
| X 20 mm/s | −23% / −42% / −36% |
| X 40 mm/s | +2% / −27% / −4% |
| X 80 mm/s | −12% / −22% / −9% |
| X 150 mm/s | −11% / −6% / −4% |
| Diagonal 5 mm/s | −34% / −29% / −16% |
| Diagonal 20 mm/s | −32% / −62% / −14% |
| Diagonal 80 mm/s | +2% / −14% / −13% |
| Slow speed changes | −2 to −17% / −6 to −10% / −5 to −14% |

The same test 15 minutes apart moves single numbers by up to about ±30%.

## Safety limits

Calibration caps a correction at 0.06 A (good ones stay under 0.05 A) and `ripple_*` values over 0.1 A are a
config error, as too much current at a high harmonic grinds the motor. A point is only kept if it takes at least
20% off the vibration, a fit is only used if the test corrections clearly moved it, and if nothing improved the
previous tables are put back and nothing is saved.
