# Clock

The Creator 5 has no hardware clock (no `/dev/rtc`), so every boot starts at
1 January 1970 until something sets the time. Logs, print history and file
dates from before that read 1970.

LoopScript's `02-fixtime.sh` handles it in three steps:

1. **At boot** the clock is put back to the last saved time
   (`/usr/data/opencreator/.clock`, seconds since 1970), so even with no
   network it is only behind by how long the printer was switched off. It is
   only ever moved forward.
2. **In the background** it is set from the network as soon as that answers:
   `rdate` from `time.nist.gov` (Time protocol, TCP 37), or, on networks that
   block that, the `Date` header of a plain HTTP request to
   `connectivitycheck.gstatic.com` or `www.google.com`. It retries every 10 s
   until one works, then resyncs hourly. (`captive.apple.com` is not used: its
   cached replies can be days old.)
3. **Every 5 minutes**, and after each sync, the time is saved again.

The old script pinged `time.nist.gov` first and gave up after a minute. Many
networks drop ping (and NIST's servers often don't answer it), so it usually
never got as far as `rdate` and the clock stayed at 1970 until the next boot.

Klipper and Moonraker time their work with the monotonic clock, so the jump
from 1970 (or from the saved time) to the real time doesn't affect a print.
