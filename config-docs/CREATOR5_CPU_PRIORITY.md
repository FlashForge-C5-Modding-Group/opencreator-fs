# Motion start after idle and CPU priority

## Why

`MCU 'mcu' shutdown: Stepper too far in past` right after a toolchange (step 6
run 1, run 3 at 92%) came from steps arriving late, not from stepping too
fast. In run 3 the first X/Y steps after the change to T1 were due at MCU time
47585.193 and left the host at 47585.211; the mainboard shut down 18 ms past
the due time.

When motion starts from idle, Kalico sets the start time to now + 0.25 s
(`BUFFER_TIME_START`) and then queues every move of the flush before any steps
are generated. After a toolchange the flush is 7-8 s of short moves, and on
the Creator 5's MIPS SoC queuing them takes nearly the whole 0.25 s, so a few
milliseconds of competing load (camera streaming, screen capture) was enough.

## What changed

- **Kalico `toolhead.py` / `motion_queuing.py`**: when starting from idle, once
  0.5 s of moves (`PRIME_STEP_GEN_TIME`) is queued, steps for that part are
  generated and sent right away (`prime_step_generation`), then the rest of the
  burst is queued. The start time no longer has to cover the whole burst. The
  first steps go out no later than 0.7 s ahead, the same window the background
  flush uses; the remaining moves follow through the normal flush.
- **`10-klipper.sh`**: Klippy runs at `nice -20`, the highest normal priority. A real-time class (`chrt`) is not used: Klippy can take a full core during bursts and would starve SSH, Moonraker and the screen.
- **`30-camera.sh`**: mjpg_streamer runs at `nice 10`.

- **Cameras (`20-msmr.sh`)**: nginx no longer relays webcam frames. Relaying
  a 720p/30 fps MJPEG stream cost nginx about 20% of the CPU, plus the
  kernel's copies in and out. At boot, each `/webcamN/` location's
  `proxy_pass` becomes a redirect to mjpg-streamer's own port
  (`/webcam/?action=stream` → `http://<host>:8080/?action=stream`,
  `/webcam2/` → 8081, up to 8083), so the browser streams straight from
  mjpg-streamer. The stock nginx 1.5.0 has no rewrite module: the redirect is
  `error_page 403 404 =302 …` on a root that doesn't exist. mjpg-streamer sends
  `Access-Control-Allow-Origin: *`, so Fluidd's adaptive mode (which fetches
  snapshots) works across the port. Existing camera URLs (`/webcam/...`) need
  no change. Tunnel installs are not affected.

`nice` doesn't reach kernel network work (the camera's streaming traffic), so
the Kalico change is the actual fix; the priorities only take userspace load
off Klippy. Anything else started by hand during a print, such as a screen
mirror, should also run under `nice -n 10`.
