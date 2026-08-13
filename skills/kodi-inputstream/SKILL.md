---
name: kodi-inputstream
description: >
  Choose between inputstream.adaptive and inputstream.ffmpegdirect, and get
  seeking and timing right. Use when a stream will not seek, reports the wrong
  duration, plays at 0:00 forever, or when writing an inputstream add-on. Covers
  why an HLS playlist type decides which add-on can handle it, and the two clocks
  a tempo-shifting inputstream has to satisfy at once.
license: CC-BY-SA-4.0
metadata:
  category: playback
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64, Android TV"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Choosing and writing an inputstream

## adaptive or ffmpegdirect

The deciding factor for HLS is usually the playlist type, not the codec.

**`#EXT-X-PLAYLIST-TYPE:EVENT` without `#EXT-X-ENDLIST` reads as live and
growing.** `inputstream.ffmpegdirect` treats it that way and cannot seek in it —
`stream_mode=catchup` reported `LengthStream: -1`, and `stream_mode=default` still
would not seek. `inputstream.adaptive` handles HLS segment-based seeking
correctly.

Worth knowing *why*, because it is not a heuristic. ISA's playlist parser
(`src/parser/HLSTree.cpp:592`, checked at 21.5.19-Omega) handles the tag like
this:

```cpp
else if (tagName == "#EXT-X-PLAYLIST-TYPE")
{
  if (STRING::CompareNoCase(tagValue, "VOD"))
  {
    m_isLive = false;
    m_updateInterval = NO_VALUE;
  }
}
```

**`EVENT` is not handled at all.** Only `VOD` — or an `EXT-X-ENDLIST` — flips a
stream out of live. So an EVENT playlist is live by omission, and there is no
property that overrides it.

### Live streams start behind the playlist head

For a live stream, ISA starts `liveDelay` behind the **head of the playlist**, not
at the beginning of the content. On a stream whose transcode has only just started
publishing, the head is short, so playback lands tens of seconds in — and that has
nothing to do with the content's real length.

```
inputstream.adaptive.play_timeshift_buffer=true
```

starts from segment 0 instead. That property is the fix for "it starts 30 seconds
in", and it is easy to mistake for a seek problem.

### `manifest_type` is deprecated

`inputstream.adaptive.manifest_type` is redundant once the MIME type selects the
format, and ISA logs a deprecation warning for it
(`src/CompKodiProps.cpp:42`, marked *"to be removed on next Kodi release"*). Drop
it from any property set you are copying from an older example.

Jellyfin's remuxed HLS is exactly that shape, so recordings played through it
need adaptive. Bump `MinSegments` to 3.

**ffmpegdirect is the one that can shift a catchup template into the past.** If
you need catchup or timeshift against a template URL, adaptive will not do it —
that is ffmpegdirect's catchup mode, and it is the only pipeline for it.

A related trap worth knowing: a **raw static file** (`?static=true` and similar)
is not seekable through ffmpegdirect, Kodi's default inputstream, or VLC. A
remuxed HLS stream with real segment indices is. If seeking matters, remux.

## Two clocks: output rate and content rate

Only relevant if your inputstream changes playback rate, but it explains an
entire class of "the OSD time is wrong" bugs.

**ActiveAE schedules audio against packet `pts`/`dts`**, so those must advance at
the **output** rate — the rate the sink consumes samples. The OSD, meanwhile,
wants the **content** rate: the real position in the source. At any speed other
than 1×, the two diverge.

Emit both. Packet `pts`/`dts` carry output time; a separate display field carries
content time.

For VideoPlayer, `state.time = m_clock.GetClock() − ptsStart`, and `m_clock` is
locked to packet pts. So a *dynamic* `ptsStart` — `packet.pts − displayTime` —
makes `state.time` track content time.

**Compute it at packet pop, not at emit.** Reading at pop bounds the value by
Kodi's actual consumption rate; the emit-time version drifts ahead whenever demux
runs ahead of playback, and the reported time explodes. Invalidate the cached
value on seek and flush, or the old delta survives a position change.

## Capability flags change how Kodi treats your seeks

- **Without `INPUTSTREAM_SUPPORTS_IDISPLAYTIME`**, `PAPlayer`'s seek path clamps
  every seek to 0.
- **Without `INPUTSTREAM_SUPPORTS_IPOSTIME`**, VideoPlayer subtracts
  `time_offset` from seek targets — converting content time to output time, so at
  any non-1× rate every OSD seek lands somewhere wrong.

Both present as "seeking is broken" rather than as a missing capability.

## Filters carry state across a flush

`atempo` keeps internal sample history across `avcodec_flush_buffers`, so
post-seek frames blend residual pre-seek samples — an audible click.

Rebuilding the filter graph fixes that, but rebuilding on **every** seek
regresses mid-stream skips: it discards in-flight PCM with nothing to fill the
sink, producing a pause at each skip. Gate the rebuild on being inside the
startup window (a small emitted-packet count) and keep the warm filter for
mid-stream seeks.

Related: **do not return zero-size packets to hold playback.** That starves
PAPlayer's format detection and it reports `Failed to create the decoder`.
Zero-**fill** the PCM instead, so format metadata and timestamps keep flowing
while the audio is silent.

## FFmpeg version differences inside Kodi

Kodi builds bundle different FFmpeg majors, and the demuxers differ.

**FFmpeg 6's matroska/webm demuxer leaves the codec context's `sample_rate`,
`ch_layout` and `sample_fmt` unpopulated for Opus until the first packet
decodes** — the values are in `codecpar` but not in the context. Build a filter
graph from the context and you get `time_base=1/0` and a failure. FFmpeg 7
populates them up front.

Backfill from `codecpar` after `avcodec_open2`, and **if graph construction still
fails, disable your processing path rather than continuing** — the observed
crash was dereferencing a freed decoder context after a failed init.

Two more decoder-level traps:

- **Always use the canonical drain-then-retry send/receive loop.** A single
  `avcodec_send_packet` that loses its packet on `EAGAIN` produced *no* output at
  all for small-frame codecs like 20 ms Opus, while AAC worked because its frames
  are larger. It looks codec-specific and is not.
- **`AV_DISPOSITION_ATTACHED_PIC` cover art surfaces as a video stream.** In m4b
  and mp3 that becomes "Unsupported stream" → stream disabled → but the video
  pipeline is already initialised → `MSGQ_NOT_INITIALIZED`, with the audio thread
  paused waiting on a video sync that never arrives. Discard attached_pic in
  `AddStream`.

## Startup analysis is often the bottleneck

FFmpeg's defaults analyse 5 s / 5 MB before reporting streams. For containers
that carry codec parameters in their headers — audiobooks, podcasts — that is
pure latency:

```
analyzeduration = 500000    # 0.5 s
probesize       = 131072    # 128 KB
```

Set before `avformat_find_stream_info()`.

## What fails silently

- An EVENT playlist plays but will not seek, with no error.
- A missing capability flag turns every seek into a clamp to zero.
- Emit-time `ptsStart` drifts and the OSD time explodes without erroring.
- A lost `EAGAIN` packet produces silence only for small-frame codecs.
- Cover art initialises the video pipeline and then wedges the audio thread.

## Open questions

- Which Kodi builds ship FFmpeg 6 versus 7 varies by distribution and by
  `ENABLE_INTERNAL_FFMPEG`; there is no single answer, so probe rather than assume.
- The startup-window threshold for filter rebuilds was tuned empirically on one
  add-on and is not a Kodi-defined boundary.

## See also

- [`kodi-pvr-addon`](../kodi-pvr-addon/SKILL.md) — handing streams to these from
  a PVR client
- [`kodi-known-defects`](../kodi-known-defects/SKILL.md) — inputstream.adaptive's
  missing MP3/MP2 codec identity, and its live-seek clamp
- [`kodi-playback-resume`](../kodi-playback-resume/SKILL.md) — getting playback
  to start in the right place
