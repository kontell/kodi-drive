---
name: kodi-announcements
description: >
  React correctly to Kodi's notifications — Player.OnStop, Playlist.OnClear,
  OnAdd and friends — over JSON-RPC or in an add-on's onNotification. Use when
  writing a service that watches playback or the playlist, or when a handler fires
  but sees the wrong data. Covers why querying inside a handler returns state that
  has already changed, which events fire in which order, and the shared thread
  that makes slow handlers everyone else's problem.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega"]
    platform: ["Linux x86_64"]
    date: "2026-08-13"
    method: observed
---

# Reacting to Kodi's announcements

Kodi's notifications tell you **when** something happened. They are unreliable
about **what** — and the natural way to find out makes it worse.

## Announcements arrive after the change is applied

This is the rule everything else follows from. A handler runs on a worker thread,
**after** Kodi has already made the change.

So querying inside a handler returns the *new* state, not the state that just
disappeared. Measured: `Playlist.GetItems` called from a `Playlist.OnClear`
handler returned the **incoming** queue and `position: 0`. The outgoing queue's
ten tracks and its position were already gone.

**If you need what was lost, you must have been keeping a shadow copy.** There is
no way to ask for it after the fact. Maintain the copy continuously, update it on
`OnAdd`, and read *your* copy in the handler.

## Event ordering, and which event actually means what

`Playlist.OnClear` fires **before** `Player.OnStop`. It also fires **only when
the list was non-empty** — `CPlayList::Clear()` announces conditionally — so the
first album of a session produces no `OnClear` at all.

**Starting a video does not clear the music queue.** This surprises people.
`VideoGUIUtils` clears only `TYPE_VIDEO`; the music playlist survives, and
`Playlist.GetItems(playlistid=0)` still returns every track during and after the
video.

What is actually lost is the *position*: `CPlayListPlayer::OnMessage` on
`GUI_MSG_PLAYBACK_STOPPED` calls `Reset()`. The tracks survive; where you were
does not. A different signal, needing different handling.

| What happened | The signal | Queue at that moment |
|---|---|---|
| New playlist replaces the current one | `Playlist.OnClear{playlistid:0}` | **already gone** |
| A video interrupts music | `Player.OnStop{item.type:"song", end:false}` | intact, position lost |
| User stops playback | `Player.OnStop{item.type:"song", end:false}` | intact, position lost |
| Queue reaches the end | `Player.OnStop{end:true}` on the last track | intact, position lost |
| Kodi quits | `System.OnQuit` | discarded on exit |

Three of those share one signal, so handling that one covers all three.

## `Player.OnStop` carries no `playerid`

The payload is `{"end": bool, "item": {...}}` and nothing more. **Distinguish
audio from video by `item.type`**, not by player id.

It also fires on **every track change**, not only on a real stop. A genuine stop
therefore needs a grace period before you act on it, or every track boundary
looks like the user leaving.

## Notification payloads cannot rebuild a queue

`CopyMusicTagInfoToObject` emits **no file path** when the database id is 0 — so a
`Playlist.OnAdd` payload for a non-library item is not enough to reconstruct
anything.

Treat the split as: **`OnAdd` tells you *when* to re-read; `Playlist.GetItems`
tells you *what*.**

And re-read once, not per event: a ten-track album fires **ten separate `OnAdd`
notifications within about 10 ms**. Debounce around 250 ms or you will do the
same work ten times.

## Handlers run on a thread every add-on shares

Kodi delivers player and monitor callbacks on **the announcement thread that
every add-on shares**. Doing HTTP, or anything slow, inside a handler stalls
every other add-on on the box.

```python
def onNotification(self, sender, method, data):
    # capture and enqueue; do not work here
    self._queue.put((method, data))
```

Capture the payload at event time, enqueue it, and let a single FIFO worker do
the work. The payload matters because by the time your worker runs, the state has
moved on again.

## Sender matching is exact and silent

When sending your own messages with `JSONRPC.NotifyAll`, the sender string must
match the receiver's constant exactly. A near miss produces no log line, no
error, and a cheerful `"result":"OK"`. See
[`kodi-addon-driving`](../kodi-addon-driving/SKILL.md).

## What fails silently

- Querying inside a handler returns post-change state that looks plausible.
- The first playlist of a session produces no `OnClear`.
- A video interrupting music produces no `OnClear` for the music playlist.
- `OnStop` on every track change looks like a stop.
- An `OnAdd` payload for a non-library item has no path, and no error says so.
- A slow handler degrades every other add-on, with nothing pointing at you.

## Open questions

- Whether `Playlist.OnClear`'s non-empty-only behaviour is identical for video
  playlists has not been checked — only the music path was traced.
- The 250 ms debounce is a working figure from a ten-track album on one machine,
  not a measured threshold. A slower device may need more.

## See also

- [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) — querying state, and the readings
  that agree with whatever you hoped
- [`kodi-addon-driving`](../kodi-addon-driving/SKILL.md) — sending notifications
  rather than receiving them
- [`kodi-freeze-diagnosis`](../kodi-freeze-diagnosis/SKILL.md) — when a shared
  thread stops moving
