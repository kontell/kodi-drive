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
  verified:
    kodi: ["21.3 Omega"]
    platform: ["Linux x86_64", "Android TV", "Android"]
    date: "2026-08-13"
    method: sourced
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

## What fails silently

- A seek while paused resumes playback, with no error.
- Player state reads at a boundary return plausible wrong values.
- `SetTempo` on audio does nothing and reports nothing.
- A gapless advance produces no `onPlayBackEnded`.

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
