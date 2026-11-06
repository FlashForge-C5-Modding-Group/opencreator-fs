# Clock

The Creator 5 has no hardware clock (no `/dev/rtc`), so every boot starts at
1 January 1970 until something sets the time. Logs, print history and file
dates from before that read 1970.

LoopScript's `02-fixtime.sh` handles it in three steps:

1. **At boot** the clock is put back to the last saved time
   (`/usr/data/opencreator/.clock`, seconds since 1970), so even with no
   network it is only behind by how long the printer was switched off. It is
   only ever moved forward.
2. **In the background** it is set from the network as soon as that answers.
   All the time servers are asked at once, and the first answer sets the
   clock. If none answers within 8 s, all the web servers are asked at once:
   - **NTP (UDP 123):** `pool.ntp.org`, `time.google.com`, `time.cloudflare.com`,
     `time.apple.com`, `time.windows.com`, `0.pool.ntp.org`, `1.pool.ntp.org`,
     `ntp.aliyun.com`, `ntp.tencent.com`, `time.nist.gov`.
   - **Time protocol (TCP 37), with `rdate`:** `time.nist.gov`,
     `time-a-g.nist.gov`, `time-b-g.nist.gov`, `time-a-wwv.nist.gov`.
   - **The `Date` header of a plain HTTP request**, for networks that block both:
     `connectivitycheck.gstatic.com`, `www.google.com`, `bin.entware.net`,
     `github.com`, `www.cloudflare.com`, `www.baidu.com`, `www.microsoft.com`.

   Unanswered attempts are stopped after 8 s, because busybox `ntpd -q`
   otherwise retries forever when port 123 is silently dropped. A blocked
   network costs about 8 s, not one timeout per server. It retries every 10 s
   until one source works, then resyncs hourly. (`captive.apple.com` is not
   used: its cached replies can be days old.)
3. **Every 5 minutes**, and after each sync, the time is saved again.

The old script pinged `time.nist.gov` first and gave up after a minute. Many
networks drop ping (and NIST's servers often don't answer it), so it usually
never got as far as `rdate` and the clock stayed at 1970 until the next boot.

Klipper and Moonraker time their work with the monotonic clock, so the jump
from 1970 (or from the saved time) to the real time doesn't affect a print.
