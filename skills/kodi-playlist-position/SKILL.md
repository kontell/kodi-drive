---
name: kodi-playlist-position
description: >
  Find out which item of a playlist is actually playing, when Kodi's own answer
  belongs to a different playlist. Use when an add-on that watches or records the
  queue reports track 1 for a listen that was several tracks in, when a video
  interrupting music loses the position, or before polling
  `PlayList.getposition()` on a timer. Covers the read that answers for the
  player rather than the list it was called on, and the four-second window where
  every other player read still agrees with the wrong one.
license: CC-BY-SA-4.0
metadata:
  category: playback
  verified-kodi: "22.0-BETA1 Piers"
  verified-platform: "Android TV ARM 32-bit"
  verified-date: "2026-08-18"
  verified-method: observed
---

# Which track is playing

An add-on that samples the music queue on a timer records the right track for a
whole listen, and then records track 1 the moment a video interrupts it. The
saved elapsed time is right — two minutes and eleven seconds — and it is
attributed to a track that stopped playing twenty minutes earlier. Nothing is
logged, nothing raises, and the sample loop that produced it looks correct.

## `getposition()` answers for the player, not for the playlist

`xbmc.PlayList(id)` looks like a handle on one of Kodi's playlists, and for
`add()`, `clear()` and `size()` it behaves like one. `getposition()` does not: it
reports the **playlist player's** current index, which belongs to whichever
playlist the player is on — not to the object you called it on.

Observed with 16 songs queued, track 4 playing, and the video playlist empty:

```
pl0.pos=3  pl0.size=16   pl1.pos=3  pl1.size=0
```

`PlayList(1)` held nothing at all and still reported index 3. The two objects
never disagree, whatever is in them.

## A video takes the index over seconds before the music stops

Opening a video switches the playlist player to the video playlist and its index
to 0. The audio player is still running when that happens. Sampling once a
second across the transition:

```
16:32:09.975  pl0.pos=3  pl1.size=0  t=128.0  file=<track 4>
16:32:10.984  pl0.pos=0  pl1.size=1  t=128.9  file=<track 4>   <- still audible
16:32:11.987  pl0.pos=0  pl1.size=1  t=129.9  file=<track 4>
16:32:12.988  pl0.pos=0  pl1.size=1  t=130.9  file=<track 4>
16:32:14.996  Player.OnStop for the song
```

Four seconds, and **every other read stays correct**: `isPlayingAudio()` is still
true, `getPlayingFile()` is still track 4, `getTime()` is still climbing. A
sampler that sanity-checks the position against "is audio playing?" gets a
confident yes.

So anything keeping a shadow copy of the queue — a recorder, a scrobbler, a
resume feature — attributes the last few samples of a listen to the wrong track,
and the snapshot it writes when the music finally stops carries the wrong track
with the right elapsed time.

## Only playback that goes through the playlist player flips it

This matters mostly for reproducing it:

| Route | Flips the index |
|---|---|
| Playing an item from a media window | yes |
| JSON-RPC `Player.Open {"item": {"playlistid": 1, "position": 0}}` | yes |
| `PlayMedia(<path>)` builtin | **no** |

`PlayMedia` hands the file straight to the player rather than going through the
playlist player. Observed: the same video, started that way over the same music,
left `pl0.pos` at 3 for the whole interruption and the resulting snapshot was
correct. **A reproduction built on `PlayMedia` therefore passes while the bug is
still there.**

## Reconcile against the file

`getPlayingFile()` has no such ambiguity — it is the file the player is on. Take
the reported position while it is unchanged (the common case, and free), and let
the file decide whenever it moves:

```python
if position != last_position:
    matches = [i for i, item in enumerate(queue) if item.file == playing]
    if matches:
        # A queue can hold the same file twice; prefer the copy nearest to
        # where playback already was.
        position = min(matches, key=lambda i: abs(i - last_position))
```

When the file is not in your copy of the queue at all — a plugin that resolved to
some other URL — the remaining signature is a position that jumped **backwards
while the elapsed time kept climbing**. One track cannot move, so that is another
playlist taking the player over, and the sample should be dropped rather than
believed.

## What fails silently

- `getposition()` on an **empty** playlist returns another playlist's index
  rather than -1, 0 or an error.
- Nothing is logged when the playlist player switches, at any log level.
- Every other player read agrees with the wrong position for the whole window, so
  the obvious guard does not catch it.
- A reproduction driven by `PlayMedia` passes.

## Verifying it

Start music, get several tracks in, and run this while it plays:

```python
import xbmc
xbmc.log("%s/%s  %s/%s" % (xbmc.PlayList(0).getposition(), xbmc.PlayList(0).size(),
                           xbmc.PlayList(1).getposition(), xbmc.PlayList(1).size()),
         xbmc.LOGINFO)
```

Two positions that agree while the two sizes do not is the whole finding. Then
open a video and watch the position go to 0 while `xbmc.Player().getTime()` keeps
advancing on the same track.

## Open questions

- Confirmed on Kodi 22.0-BETA1 on Android TV. Not re-checked on 21.3 Omega or on
  desktop, and not read against `xbmc/interfaces/legacy/PlayList.cpp` — that the
  value is the playlist player's current index is the reading the measurements
  fit, not one taken from the source.
- Whether JSON-RPC `Player.GetProperties`, which takes an explicit player id,
  reports the position correctly during the same window was not tested.
  `Playlist.GetItems` takes an explicit `playlistid` and is a separate question
  again; neither was sampled across the transition.

## See also

- [`kodi-paplayer`](../kodi-paplayer/SKILL.md) — the audio player's own reads, and
  the ones that are unreliable at a track boundary
- [`kodi-announcements`](../kodi-announcements/SKILL.md) — why the notification
  that tells you the queue changed arrives after it already has
- [`kodi-playback-resume`](../kodi-playback-resume/SKILL.md) — putting a queue
  back at a position, once you have recorded the right one
