---
name: iptv-catchup-download
description: >
  Download a past programme from an IPTV provider's catchup archive to a local
  .ts file, starting from the M3U entry pvr.iptvsimple plays it from. Use when
  you need a real broadcast as a test fixture for a PVR client, an inputstream
  or a commercial detector, or when iptvsimple catchup plays the wrong span.
  Covers which catchup URL forms stop where you asked, the archive starting up
  to one segment late, and the failures that come back as HTTP 200 with a
  stand-in video.
license: CC-BY-SA-4.0
metadata:
  category: adjacent
  verified-kodi: "22.0-RC1 Piers"
  verified-platform: "Linux x86_64"
  verified-date: "2026-11-16"
  verified-method: sourced
---

# Downloading a catchup programme from an IPTV source

pvr.iptvsimple turns a channel's live URL into a catchup template and fills it
from the EPG. The template it plays from is the wrong one to download with: on a
Flussonic-style archive, two of the forms it generates do not stop where the
programme stops, one of them never stops, and every failure seen here came back
as an HTTP 200 playlist that ffmpeg reads without an error. Build a bounded URL,
check the playlist, then copy it.

Tested with pvr.iptvsimple 22.6.4 and inputstream.ffmpegdirect 22.2.7 on Kodi
22.0-RC1 (Linux x86_64), ffmpeg 7.1.5, against one provider whose archive
answers Flussonic's URL forms (behind nginx, 7-day archive, 8 s target
duration). Source references are to pvr.iptvsimple 22.6.4 (`Piers` branch).
Claims about Xtream Codes are sourced from iptvsimple only.

## 1. The template iptvsimple uses

The M3U entry decides the mode, and the mode decides the template
(`src/iptvsimple/PlaylistLoader.cpp:415-471`, `src/iptvsimple/data/Channel.cpp:376-575`).
The Shift, Flussonic and Default rows were also observed in Kodi's debug log
(`ConfigureCatchupMode`).

| M3U entry | Mode | Template |
|---|---|---|
| `catchup="default" catchup-source="URL"` | Default | `catchup-source` as given |
| `catchup="append" catchup-source="QUERY"` | Append | live URL + `catchup-source` |
| `catchup="shift"`, or only `timeshift="N"` | Shift (SIPTV) | live URL + `?utc={utc}&lutc={lutc}` (`&` when the URL already has a query) |
| `catchup="flussonic"`, `"flussonic-hls"`, `"fs"`, `"flussonic-ts"` | Flussonic | `<host>/<id>/timeshift_rel-{offset:1}.m3u8<query>` for a `…/index.m3u8` live URL (`<name>-timeshift_rel-…` for another name); `timeshift_abs-${start}.ts` for `…/mpegts` |
| `catchup="xc"` | Xtream Codes | `<host>/timeshift/<user>/<pass>/{duration:60}/{Y}-{m}-{d}:{H}-{M}/<id>.ts` |
| `catchup="vod"` | VOD | `{catchup-id}`, from the XMLTV programme |

A bare `timeshift="7"` is the old SIPTV tag: it gives Shift mode, not Flussonic,
even when the server is Flussonic-style.

The placeholders (`src/iptvsimple/CatchupController.cpp:363-406`, and the add-on
README's "Catchup format specifiers"): `{utc}` and `${start}` are the start in
Unix seconds, `{utcend}` and `${end}` the start plus `{duration}`, `{lutc}` and
`${now}` the current time, `{offset:1}` now minus start, `{duration:60}` the
duration in minutes. `{Y}` `{m}` `{d}` `{H}` `{M}` `{S}` are the start in **the
local time zone of the machine running Kodi** (`localtime_r`,
`src/iptvsimple/utilities/TimeUtils.h:13-21`), so an Xtream Codes URL built on a
Kodi in another zone than the server asks for the wrong hour. The start written
into the URL is the XMLTV start minus `catchup-correction` (hours): the
`tvg-shift` added to the guide Kodi shows (`src/iptvsimple/Epg.cpp:621`, `:634`)
is taken off again (`CatchupController.cpp:538`, `:495`).

**What it fills in from the guide.** Played from the EPG with default settings
("Play from EPG in Live TV mode" off), a 30-minute programme starting 09:00:00
UTC produced `archive-1794819600-3000.m3u8`: `{utc}` is the programme start and
`{duration}` is the programme plus the begin and end buffers
(`catchupWatchEpgBeginBufferMins` 5, `catchupWatchEpgEndBufferMins` 15). Kodi
showed a 50:00 total, and 12 s after opening the position was 5:10.

## 2. Download a bounded form

Each form, asked for 120 s starting six hours earlier (the `-now` row from ten
minutes earlier):

| URL (last path element) | What came back |
|---|---|
| `archive-{utc}-{duration}.m3u8` | EVENT playlist with `#EXT-X-ENDLIST`, 17 segments, 122.4 s |
| `<name>-{utc}-{duration}.m3u8` (`index-…`, `mono-…`) | identical to `archive-` |
| `timeshift_abs-{utc}.m3u8` | EVENT with ENDLIST, 10,796.6 s: three hours, whatever you wanted |
| live URL `+ &utc={utc}&lutc={lutc}` (Shift) | the same three hours as `timeshift_abs` |
| `timeshift_rel-{offset}.m3u8` (Flussonic mode) | no ENDLIST, 14,677.9 s so far: it runs on to live |
| `index-{utc}-now.m3u8` | no ENDLIST, 594.0 s: from the start up to now |
| `timeshift_abs-{utc}.ts` | `302` redirect |

Download `archive-{utc}-{duration}.m3u8` or `<name>-{utc}-{duration}.m3u8`; the
`index-FROM-DURATION.m3u8` form is
[Flussonic's documented one](https://flussonic.com/doc/dvr/playback/). If all you
have is a Shift or `timeshift_abs` URL, bound the copy with ffmpeg's `-t`. A
playlist without ENDLIST is one ffmpeg keeps re-reading, so a `timeshift_rel`
or `-now` copy without `-t` runs until it is killed (*inferred* from HLS
semantics; not run to the end here).

## 3. Ask for one segment early

In four requests the archive playlist held exactly the segments that **start**
inside `[{utc}, {utc} + {duration})`. The segment that contains `{utc}` is left
out, so the copy begins up to one target duration late. Asking for 09:23:00, :30 and :37
gave first segments at 09:23:05.165, :33.465 and :41.145. Subtract
`#EXT-X-TARGETDURATION` (8 s here) from the start and add it to the duration.
The end is covered: the last segment is the one that starts before the end.

## 4. Check the playlist first: failures are HTTP 200

Observed on the tested provider:

| Request | Reply |
|---|---|
| another channel's token, or none | 200 after a redirect off the channel's path to a stub playlist: a 101 s stand-in video |
| start older than the archive (7 days plus 1 hour) | 200 after a redirect to another stub: a 100 s VOD playlist |
| start in the future | the live playlist, no ENDLIST |
| window ending after now | EVENT with ENDLIST, cut at now (96.4 s of 120) |

**Every channel's URL carries its own token.** Take the URL from the line after
that channel's `#EXTINF`; a URL rebuilt with another channel's token fetches the
stub. The stubs belong to this provider; four checks catch all four replies
without depending on them: the reply was not redirected off the channel's
path, it has `#EXT-X-ENDLIST`, its first `#EXT-X-PROGRAM-DATE-TIME` is within a
segment of the start, and its `#EXTINF` durations add up to what you asked for.

## 5. Copy it

This script does sections 2 to 4 and the copy. It reads the playlist, never
prints the URL, and exits non-zero with the reason when a check fails.

```python
#!/usr/bin/env python3
"""catchup-fetch.py PLAYLIST.m3u "CHANNEL NAME" 2026-11-15T20:00:00 SECONDS OUT.ts
START is UTC. Never prints the URL: it carries the channel's token."""
import re, subprocess, sys, urllib.request
from datetime import datetime, timezone

PAD = 8  # one #EXT-X-TARGETDURATION: the archive starts at the first segment after {utc}

m3u, channel, start, secs, out = sys.argv[1:6]
lines = open(m3u, encoding='utf-8').read().splitlines()
i = next(i for i, l in enumerate(lines)
         if l.startswith('#EXTINF') and l.rsplit(',', 1)[-1].strip() == channel)
live = next(l.strip() for l in lines[i + 1:] if l.strip() and not l.startswith('#'))
m = re.match(r'^(https?://[^/]+/.+/)[^/?]+\.m3u8(\?.*)?$', live)
if not m:
    sys.exit('the live URL is not .../NAME.m3u8, so not a Flussonic-style channel')
t0 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()) - PAD
url = '%sarchive-%d-%d.m3u8%s' % (m.group(1), t0, int(secs) + PAD, m.group(2) or '')

with urllib.request.urlopen(url, timeout=20) as r:
    final, text = r.geturl(), r.read().decode('utf-8', 'replace')
total = sum(float(l[8:].split(',')[0]) for l in text.splitlines() if l.startswith('#EXTINF:'))
pdt = re.search(r'^#EXT-X-PROGRAM-DATE-TIME:(\S+)', text, re.M)
first = datetime.fromisoformat(pdt.group(1).replace('Z', '+00:00')).timestamp() if pdt else None
problems = []
if final.split('?')[0].rsplit('/', 1)[0] != url.split('?')[0].rsplit('/', 1)[0]:
    problems.append('redirected away from the channel: wrong token, or outside the archive')
if '#EXT-X-ENDLIST' not in text:
    problems.append('no #EXT-X-ENDLIST: the start is in the future')
if first is None or not t0 <= first <= t0 + 2 * PAD:
    problems.append('the first segment is not at the requested start')
if total < int(secs):
    problems.append('only %.0f s of %s s: the window ends after now' % (total, secs))
if problems:
    sys.exit('; '.join(problems))
sys.exit(subprocess.run(['ffmpeg', '-nostdin', '-v', 'warning', '-i', url,
                         '-map', '0', '-c', 'copy', '-f', 'mpegts', out]).returncode)
```

A 608 s window of 1080p HEVC with E-AC-3 (393 MB) copied in 19.9 s, about 30×
real time on one connection, and `ffprobe` reported 606.7 s. Each failure in
section 4 stopped the script before ffmpeg ran. `-map 0` keeps every stream;
without it ffmpeg picks one stream per type
([stream selection](https://ffmpeg.org/ffmpeg.html#Stream-selection)).

**Programme times** come from the XMLTV guide's `start="20261115135000 +0000"`
attributes. Parse the offset rather than assuming UTC; this prints the START
the script takes:

```python
from datetime import datetime, timezone
start = datetime.strptime(p.get('start'), '%Y%m%d%H%M%S %z')  # p: a <programme> element
print(start.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'))
```

## Keep the token out of logs

- **ffmpeg prints it at its default log level.** Its HLS demuxer logs the
  playlist URL and `Opening '…ts?token=…' for reading` for every segment: 4 of 44
  stderr lines for a 20 s copy. At `-v warning` the 608 s copy wrote one line,
  with no URL.
- **iptvsimple writes it to `kodi.log` at debug level.** Its `RedactUrl` masks
  only `user:password@` (`src/iptvsimple/utilities/WebUtils.cpp:129-142`), and
  ffmpegdirect logs `catchup_url_format_string` in full. Three catchup plays left
  70 lines carrying `token=`. See
  [Privacy and security](../../CONTRIBUTING.md#privacy-and-security) before
  pasting any of it.

## What fails silently

- A Shift or `timeshift_abs` URL copies three hours whatever the programme's
  length.
- A `timeshift_rel` or `-now` URL has no end.
- The copy starts up to one segment after the requested start.
- A wrong token, a start outside the archive, and a start in the future all
  return HTTP 200 with a playable playlist: a stand-in video, or the live
  channel. A frame grab from the stand-in exited 0.
- A programme still on air comes back cut at now, with ENDLIST, so it looks
  complete.
- An Xtream Codes URL's date and time are Kodi's local time, not UTC.

## Open questions

- Xtream Codes was not tested against a server: whether `/timeshift/…` stops at
  `{duration:60}` minutes, and which zone the server reads the date in.
- Whether a download counts against the account's concurrent-connection limit,
  and so cuts off someone watching on the same account. The tests ran one
  connection at a time on an idle account.
- Whether other Flussonic-style providers answer failures with a redirect to a
  stub, or with an HTTP error.

## See also

- [`kodi-inputstream`](../../skills/kodi-inputstream/SKILL.md) — ffmpegdirect's
  catchup mode, which plays these templates inside Kodi
- [`kodi-pvr-addon`](../../skills/kodi-pvr-addon/SKILL.md) — writing the PVR
  client that a downloaded fixture tests
