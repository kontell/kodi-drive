---
name: kodi-playback-stalls
description: >
  Diagnose playback that pauses for seconds at a time on a network source — a
  4K remux that "glitches" on an Android TV box while the link speed and the
  hardware look more than adequate. Covers the log line that proves it is
  rebuffering and how long each pause will be, measuring what Kodi actually
  receives from the server side, why Kodi's SMB reads cap out far below the
  link's capacity over Wi-Fi, the one setting that fixed it with the before and
  after numbers, the Wi-Fi power-save signature behind the slow round trips,
  what HTTP direct play does instead of SMB, and the refresh-rate whitelist
  miss that adds a twice-a-second judder on sets that only expose 48, 50 and
  60 Hz — with the GUI-mode fallback that puts films on 48 Hz without an
  override.
license: CC-BY-SA-4.0
metadata:
  category: diagnosis
  verified-kodi: "22.0-RC1 Piers (28ea2eac1e)"
  verified-platform: "Android TV (armeabi-v7a build) over 5 GHz Wi-Fi, Linux x86_64 Samba server"
  verified-date: "2026-10-15"
  verified-method: observed
---

# Playback that pauses on a network source

A 99 GB UHD remux (67 Mb/s overall, 96 Mb/s one-second peaks) played from an
SMB share on an Android TV box with an 866 Mb/s Wi-Fi link at -44 dBm,
hardware decoding, a quarter of the CPU busy and 2 GB of memory free. It paused
for about 19 s every one to seven minutes. Nothing about the specification
predicts that, and the decoder log is clean, so the first hour goes to the wrong
suspects. The box was receiving 57 Mb/s, and the reason was not the link.

## It is rebuffering, and one log line proves it

Every pause is `CVideoPlayer::SetCaching - caching state 1`
(`xbmc/cores/VideoPlayer/VideoPlayer.cpp:3634` at `28ea2eac1e`). State 1 is
`CACHESTATE_FULL`, "player is filling up the demux queue"
(`VideoPlayer.h:472-476`); states 2, 3 and 0 follow within milliseconds of each
other when it resumes. `CVideoPlayerAudio::Process - stream stalled`
(`VideoPlayerAudio.cpp:300`) precedes each one by about 200 ms.

List them with their durations and the gaps between them:

```sh
grep -E 'SetCaching - caching state [12]$' kodi.log | awk '{split($2,t,":");
  s=t[1]*3600+t[2]*60+t[3]; if ($NF==1){start=s; if(prev) printf "gap %4.0fs  ", s-prev;
  printf "stall at %s ", $2} else if ($NF==2 && start){printf "lasted %4.1fs\n", s-start;
  prev=s; start=0}}'
```

Observed over 32 minutes, before any change: 12 stalls of 16.7–21.5 s, gaps of
46–402 s, about 12 % of the viewing time paused.

**The pause length is the demux queue size, not the network.** Playback resumes
when `cache.time > m_messageQueueTimeSize` (`VideoPlayer.cpp:2163`), and that
size is `videoplayer.queuetimesize` in tenths of a second
(`VideoPlayer.cpp:790-793`; default 40 = 4 s). This box had it at 160, so every
shortfall became a 16 s refill, which at the rate it was getting took 17–21 s.
A bigger queue makes each stall longer, not rarer, while the source is slower
than the content.

## Measure what Kodi receives — at the server, not the box

Android hides `/sys/class/net/wlan0/statistics` and `ip -s link` from the shell
(`Permission denied`), and the box has no `iperf3`. The server's kernel already
knows everything: sample the SMB socket's `bytes_sent` 30 s apart.

```sh
a=$(ss -tni 'sport = :445' dst <ANDROID_TV_HOST> | grep -oE 'bytes_sent:[0-9]+' | cut -d: -f2)
sleep 30
b=$(ss -tni 'sport = :445' dst <ANDROID_TV_HOST> | grep -oE 'bytes_sent:[0-9]+' | cut -d: -f2)
echo "$(( (b-a)*8/30/1000000 )) Mbps"
```

```
57 Mbps; busy +28812 ms; retrans +123
```

`busy` is the time the socket had unacknowledged data in flight: 96 % of the
window, so the server was not waiting for requests. Compare against the file,
read off the server's own copy; `mediainfo` gives the average and
`ffprobe -read_intervals` a five-minute window of per-second peaks without
reading the whole file:

```sh
mediainfo --Inform="General;%OverallBitRate/String%\n" "$F"        # 67.2 Mb/s
ffprobe -v error -read_intervals 1200%+300 -select_streams v:0 \
  -show_entries packet=pts_time,size -of csv=p=0 "$F" \
  | awk -F, '{b[int($1)]+=$2} END{for(s in b) print b[s]*8/1e6}' | sort -n | tail -3
```

```
video-only Mbps: mean=59.3 p50=58.3 p90=76.6 p99=93.7 max=96.3; 10s-avg max=90.3
```

57 Mb/s delivered against 67 Mb/s needed is the whole story; the rest is
finding out why 57.

## The link is not the limit: a bulk test with what Android ships

The box has no `wget` or `curl`, but Android 14's toybox has `nc` and
`timeout`. A dozen lines of Python on the server send a blob of random bytes
to whoever connects and print the rate each second:

```python
import socket, time
data = open("blob.bin", "rb").read()           # head -c 256M /dev/urandom > blob.bin
srv = socket.socket(); srv.bind(("<DEVBOX_HOST>", 9000)); srv.listen(1)
c, _ = srv.accept(); sent = 0; off = 0; t0 = last = time.time()
try:
    while True:
        n = c.send(data[off:off + 1048576]); sent += n; off = (off + n) % (len(data) - 1048576)
        if time.time() - last >= 1: print(f"{sent*8/(time.time()-t0)/1e6:.0f} Mbps"); last = time.time()
except OSError: pass
```

```sh
adb -s <ADB_SERIAL> shell "timeout 10 nc <DEVBOX_HOST> 9000 < /dev/null > /dev/null"
```

```
TOTAL 347728512 bytes in 10.0s = 278.6 Mbps      (263–290 Mbps every second)
```

That ran while the film was still streaming. The same Wi-Fi link carries five
times what Kodi's SMB read gets from it. It also steals the stream's airtime
for ten seconds, so expect one stall from the test itself.

## Why SMB caps out: one chunk per round trip

`CSMBFile::GetChunkSize` returns `smb.chunksize` kilobytes when
`smb.minprotocol` is above 2, else 64 KB
(`xbmc/platform/posix/filesystem/SMBFile.cpp:1593-1605`), and
`CFile::DetermineChunkSize` makes the cache chunk follow the source chunk
whenever the source names one (`xbmc/filesystem/File.cpp:435-440`), so
`filecache.chunksize` is not the knob for SMB. The default is 128 KB
(`system/settings/settings.xml:2660-2663`), and the cache logs what it ended up
with at every open:

```
CFileCache::Open - <...> source chunk size is 131072, setting cache chunk size to 131072
```

`CFileCache::Process` issues one `smbc_read` of that size at a time from one
thread, and nothing else reads ahead. Throughput is therefore one chunk per
round trip: 128 KB every 18 ms is 57 Mb/s, which is what the server measured.
On a wired LAN the round trip is a fraction of a millisecond and the same loop
never shows; over Wi-Fi it is the bottleneck.

The adaptive read factor (`FileCache.cpp:366-371`, 4.0× the bitrate with an
empty cache down to 1.5× full) sits above this and never engaged: the cache
could not reach the rate it was allowed.

## The fix, and what it looked like after

`smb.chunksize` goes to 1 MB (Settings › Services › SMB client; the option
list is 16 KB to 1 MB, `xbmc/settings/ServicesSettings.cpp:26-32`). It is read
at `CFileCache::Open`, so the file playing now keeps 128 KB until it is stopped
and started again. The open line confirms the change landed:

```
CFileCache::Open - <...> source chunk size is 1048576, setting cache chunk size to 1048576
```

Before and after, same file, same server, same Wi-Fi:

| | 128 KB chunk | 1 MB chunk |
|---|---|---|
| `Player.CacheLevel` (forward cache fill) | 0 % throughout | 2–98 %, cycling |
| demux lead (`cachepercentage` − `percentage` × file size) | ~80 MB, shrinking | 107–159 MB, steady |
| server-side SMB rate | 57 Mb/s, socket busy 96 % | 54–80 Mb/s, paced by playback |
| `SetCaching - caching state 1` | 12 in 32 min | 0 in the next 10 min |

`Player.CacheLevel` is `cached / maxforward` from `GetCachingTimes`
(`VideoPlayer.cpp:2101`). It reads 0 while the demuxer drains the forward cache
as fast as the network fills it, which is the source-bound signature; once the
source outruns playback the forward cache fills and the number comes alive.

## Wi-Fi power-save is what makes each round trip slow

Pinging the box at 10 Hz from the server:

| traffic on the link | p50 | p90 | p99 | max | share over 50 ms |
|---|---|---|---|---|---|
| Kodi's SMB reads, 128 KB | 3.6 ms | 321 ms | 1177 ms | 1280 ms | 35 % |
| the continuous `nc` stream above | 24.4 ms | 26.9 ms | 28.6 ms | 28.6 ms | 0 % |
| Kodi's SMB reads, 1 MB | 44.5 ms | 415 ms | 1217 ms | 1217 ms | 47 % |

A continuous flow has a flat 25 ms of queueing and no outliers; Kodi's
request-and-wait pattern, at either chunk size, has second-long holes. Kodi
takes no Android Wi-Fi lock: `git grep -i wifilock 28ea2eac1e --
xbmc/platform/android tools/android` matches nothing, and on the box
`dumpsys wifi` reports `Locks acquired: 0 full high perf, 0 full low latency`
during playback. Labelled `inferred`, from those two observations: the station
dozes in the gap between one read's data and the next request, and the access
point holds the next response until it wakes. The 1 MB chunk does not remove
the holes; it makes each one cost a megabyte of progress instead of 128 KB,
which is enough.

## HTTP instead of SMB: one stream, no round trips

The same file played again through its media server's direct-play URL
(`/Videos/<id>/stream.mkv?static=true`, served by the same machine from the
same disk, no transcode) goes through `CCurlFile`, which reports no chunk size
of its own (`source chunk size is 0, setting cache chunk size to 131072`) and
keeps one TCP stream open that the server fills as fast as the cache drains.
Same box, same Wi-Fi, 19 minutes:

| | SMB, 128 KB | SMB, 1 MB | HTTP direct play |
|---|---|---|---|
| `SetCaching - caching state 1` | 12 in 32 min | 0 in 10 min | 0 in 19 min |
| demux lead | ~80 MB, shrinking | 107–159 MB | 156–159 MB, flat |
| `Player.CacheLevel` | 0 % | 2–98 % | 84–99 % |
| ping to the box, p50 / p99 | 3.6 ms / 1177 ms | 44 ms / 1217 ms | 9.5 ms / 127 ms |

On the server the stream socket showed `rwnd_limited` 87 % of its busy time
with `delivery_rate` 161 Mb/s: the TV's receive window, not the link, was
pacing it, which is what a full cache looks like from the other end. Where a
server can serve the file over HTTP, that is the transport to pick on Wi-Fi.

## The other stutter: a refresh rate the whitelist never matches

The same box logs its panel modes at every display change:

```
CAndroidUtils: available mode: 1: 3840x2160@60.000000
CAndroidUtils: available mode: 2: 3840x2160@50.000000
CAndroidUtils: available mode: 3: 3840x2160@48.000004
```

No 24 or 23.976 Hz mode exists, and the whitelist matcher compares to
0.01 Hz (`xbmc/windowing/Resolution.cpp:125` for the exact rate, `:160` for
double). 23.976 × 2 = 47.952, which is 0.048 away from 48.000004, so a
whitelist of 48 and 50 Hz produces, for every film:

```
[WHITELIST] Searching the whitelist for: width: 3840, height: 2160, fps: 23.976, 3D: false
[WHITELIST] No match for an exact resolution with double the refresh rate
[WHITELIST] No resolution matched
Display resolution ADJUST : 3840x2160 @ 50.000000 - Full Screen (18) (weight: 0.000)
```

`No resolution matched` (`Resolution.cpp:305`) is debug level and the fallback
is the GUI mode, so a 50 Hz panel plays 24p content in a 2:2:2:2:3 cadence.
With `avtiming` logging on, `CRenderManager::PrepareNextRender` shows its
`diff` walking from -1.9 ms to -21.9 ms over about 12 frames and then one
frame held for a third vsync: 218 of 2,528 frames in a five-minute window,
twice a second. Only 24.000 fps content would ever reach 48 Hz by matching.

**What matches nothing inherits the GUI mode.** `ChooseBestResolution` starts
from the current video resolution (`Resolution.cpp:59`) and a whitelist miss
leaves it untouched, so setting Kodi's own display mode (Settings › System ›
Display) to 48 Hz puts every 23.976 film on 48 Hz with no override at all.
Observed after exactly that change:

```
[WHITELIST] Searching the whitelist for: width: 3840, height: 2160, fps: 23.976, 3D: false
[WHITELIST] No resolution matched
Display resolution ADJUST : 3840x2160 @ 48.000004 - Full Screen (19) (weight: 0.000)
```

It is a fallback, not a match, so it carries 29.97 and 59.94 fps material to
48 Hz as well, while 25/50 fps still switches to 50 Hz and 30/60 fps to 60 Hz
through the whitelist. 48.000004 Hz against 23.976 fps leaves a 0.1 %
difference, which with audio as the clock is one frame repeated every ~42 s.

`advancedsettings.xml` overrides are consulted before the whitelist
(`Resolution.cpp:62`) and match a refresh range against an fps range
(`xbmc/settings/AdvancedSettings.cpp:733-779`):

```xml
<advancedsettings>
  <video>
    <adjustrefreshrate>
      <override>
        <fpsmin>23.9</fpsmin><fpsmax>24.1</fpsmax>
        <refreshmin>47.9</refreshmin><refreshmax>48.1</refreshmax>
      </override>
    </adjustrefreshrate>
  </video>
</advancedsettings>
```

That is `sourced`; whether an override behaves any differently from the GUI
fallback above is under Open questions.

## What fails silently

- `Player.CacheLevel` reads 0 for the whole film when the source is the
  bottleneck, which looks like "no cache" rather than "cache drained faster
  than filled".
- A large `videoplayer.queuetimesize` lengthens every stall to its own size
  and changes nothing about their cause.
- `filecache.chunksize` has no effect on SMB; the source's chunk wins.
- `smb.chunksize` changes nothing for the file already playing.
- The whitelist's fallback to the GUI refresh rate is logged at debug level
  only, with no notification — and it applies to every unmatched rate, so a
  GUI parked on 48 Hz for films also receives 29.97 and 59.94 fps content.
- A network outage is not a pause: `CCurlFile` returns a short read,
  FFmpeg logs `[matroska,webm] File ended prematurely`, and `CVideoPlayer`
  exits as if the file had ended, saving a resume point ~20 s after the
  last byte arrived.
- A debug log with `avtiming` on writes 50 lines a second; grep it on the
  workstation from an `adb exec-out "tail -c 40000000 …"` slice. An on-device
  `grep` of the full file ran for minutes on one core of the box.

## Verifying it

Three samples of the cache level during playback separate the two regimes in
under a minute: pinned at 0 is source-bound, moving is not.

```sh
for i in 1 2 3; do kodi-remote get XBMC.GetInfoLabels '{"labels":["Player.CacheLevel"]}'; sleep 10; done
```

Then the stall listing above against the log of the same session.

## Open questions

- The GUI-at-48 Hz fallback was watched for two minutes only. Whether the
  one-frame-per-42 s repeat is visible, and whether
  `videoplayer.usedisplayasclock` (which makes the display the clock and
  resamples audio by the 0.1 %) removes it, has not been checked; nor has the
  `advancedsettings.xml` override been run at all.
- During HTTP direct play the box's Wi-Fi data path froze while still
  associated: bytes stopped at 13:09:38 after 5.5 minutes of continuous
  ~78 Mb/s receive, Android logged `CMD_IP_REACHABILITY_FAILURE` 45 s later
  and then `NETWORK_SELECTION_DISABLED_NO_INTERNET_TEMPORARY`, and nothing
  recovered it until Wi-Fi was toggled off and on 19 minutes later (which also
  rotates the wireless-debugging port). No deauth, beacon loss or supplicant
  event was logged; every thermal zone read 42 °C; the access point kept
  serving another client. One occurrence in an hour of SMB and 19 minutes of
  HTTP, so whether sustained continuous receive provokes it is unknown — the
  driver log would say and needs root.
- Whether a `WifiManager.WifiLock` of `WIFI_MODE_FULL_HIGH_PERF` held by Kodi
  during network playback removes the second-long ping holes is untested; it
  is the natural Kodi-side experiment, and a cable on the box's unused
  Ethernet port the natural user-side one.
- The server ran Samba with defaults and the box's bundled client is Samba
  4.24.4. Whether a 1 MB `smbc_read` is issued as one SMB2 READ or pipelined
  was not captured; the throughput result stands either way.

## See also

- [`kodi-logs`](../kodi-logs/SKILL.md) — mark-and-read instead of grepping a
  170 MB log
- [`kodi-adb`](../kodi-adb/SKILL.md) — the channel into the box, and why
  `adb push` must be checksummed
- [`kodi-performance`](../kodi-performance/SKILL.md) — the other way an
  Android TV box is slower than its specification
- [`kodi-triage`](../kodi-triage/SKILL.md) — the ladder this sits at the end of
