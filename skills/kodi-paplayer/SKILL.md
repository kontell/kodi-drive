---
name: kodi-paplayer
description: >
  Control Kodi's audio player (PAPlayer) safely, especially while it is paused.
  Use when an add-on pauses, seeks or resumes music, when a paused track resumes
  itself, when playback jams and ignores commands, or when tempo has no effect on
  audio. Covers the seek that silently restarts playback and the state reads that
  are unreliable at a track boundary.
license: CC-BY-SA-4.0
metadata:
  category: playback
  verified-kodi: "21.3 Omega, 22.0b2 Piers"
  verified-platform: "Linux x86_64, Android TV, Android"
  verified-date: "2026-10-12"
  verified-method: "sourced"
---

# Driving PAPlayer

PAPlayer is Kodi's audio player core, and it does not behave like VideoPlayer.
Code written against VideoPlayer's semantics fails here in ways that look like
your own bugs.

## Seeking a paused PAPlayer resumes it

`xbmc/cores/paplayer/PAPlayer.cpp:1097-1098`, inside `SeekTime`:

```cpp
if (m_playbackSpeed != 1)
  SetSpeed(1);
```

A paused player is speed 0, so **any seek while paused sets it playing.**
`CVideoPlayer::SeekTime` does nothing comparable.

Observed consequence: pause → seek to align → the player resumes on its own →
runs ahead → gets corrected with a visible double rewind. It reads as a race in
your own code.

**The invariant that avoids it: never seek a paused audio player.** Do audio
alignment while running, at resume time — toggle play first, then seek if you are
still far enough out to care.

## State reads near a paused boundary are unreliable

On at least one Android device, `isPlaying()`, `getTime()` and `Player.Paused`
returned **nondeterministically wrong** values on a PAPlayer paused at a track
boundary. Two distinct failure modes were seen in the field:

- **Self-resume** — the seek-resumes behaviour above.
- **Full jam** — seeks never execute and a subsequent pause-toggle is swallowed.
  In one capture there was **not one player event for 31 seconds**, until user
  input flushed the queued seek.

So a one-shot, read-gated decision is not safe here. The working pattern:

1. **Decide from your own state**, not from the player's.
2. **Verify by observed clock movement** — accept success only when `getTime()`
   demonstrably advances between samples, not because a read said "playing".
3. **Nudge and retry** rather than commanding once. A pause-toggle is safe even
   when nothing is loaded; Kodi ignores it.

## Tempo does not work on audio at all

`Player.SetTempo` is a no-op under PAPlayer — it neither applies nor errors. A
backstop that watches for a rejected `SetTempo` therefore never fires, so any
rate-based correction must require an active **video** player before engaging.

See [`kodi-playback-tempo`](../kodi-playback-tempo/SKILL.md) for the separate
reason tempo is off on most installs even for video.

## Other PAPlayer differences worth knowing

- **`Player.ChapterCount` is always 0** under PAPlayer.
- **PAPlayer emits a spurious `SeekTime(0)` at init**, so any "a seek happened"
  logic must threshold above ~100 ms.
- **Resume uses `audiobook_bookmark`** (milliseconds), applied before audio output
  begins — see [`kodi-playback-resume`](../kodi-playback-resume/SKILL.md).

## There is no pre-boundary hook

`onPlayBackEnded` does **not** fire on a gapless playlist advance, so there is no
point at which an add-on can act just before a track ends. Anything that needs to
happen at a boundary has to be reactive, and will be at least a callback delivery
late.

Pre-pausing at the track tail, and muting the tail to mask the gap, were both
tried and rejected as unworkable.

## A track queued ahead plays under its plugin URL, not what it resolved to

PAPlayer asks for the next track five seconds before the current one ends
(`TIME_TO_CACHE_NEXT_FILE`, `xbmc/cores/paplayer/PAPlayer.cpp` line 39 at
`e513e0ff`), so a `plugin://` track is resolved while its predecessor is still
playing. On 22.0b2 `OnQueueNextItem` was logged 19.5 s into a 25 s song and the
plugin's play route ran 0.1 s later (observed).

When that track starts, `xbmc.Player().getPlayingFile()` returns the plugin URL
it was queued under. A track opened directly returns the stream the plugin
resolved it to. Observed on 22.0b2, polled once a second across the first
change of an album opened by `albumid`:

```
One Track 1 | http://<SERVER_URL>/Audio/<id>/stream.flac?static=true&mediaSourceId=<id>
One Track 2 | plugin://plugin.video.example/<path>/<id>.flac
```

An add-on that recognises its own playback by the path it resolved recognises
the first track of an album and none after it. Match a queued track by its
plugin URL, or by an id carried in it, and expect the resolve seconds before
the start, not at it.

## What fails silently

- A seek while paused resumes playback, with no error.
- Player state reads at a boundary return plausible wrong values.
- `SetTempo` on audio does nothing and reports nothing.
- A gapless advance produces no `onPlayBackEnded`.
- A queued `plugin://` track reports its plugin URL as the playing file, so a
  match on the resolved stream misses every track after the first.

## Open questions

- The nondeterministic state reads were characterised on one Android device
  family. Whether desktop PAPlayer is reliable at a paused boundary was not
  established — the safe pattern above costs little, so it is worth using
  regardless.
- Whether Kodi 22 changed any of this has not been checked; the source citation
  above is from 21.3.

## See also

- [`kodi-playback-resume`](../kodi-playback-resume/SKILL.md) — starting playback
  in the right place, per player core
- [`kodi-playback-tempo`](../kodi-playback-tempo/SKILL.md) — why tempo is usually
  unavailable
- [`kodi-announcements`](../kodi-announcements/SKILL.md) — the callback thread
  these commands arrive on
