---
name: kodi-playback-resume
description: >
  Hand Kodi an item so the right player opens it, in the right window, at the
  right position. Use when an add-on's playback starts at zero instead of
  resuming, when the wrong info dialog opens, when Now Playing names a different
  song than the one you hear, when the fullscreen window is unexpected, or when
  subtitle tracks are off by a few. Covers the resume property that differs per
  player core, the path-vs-dbid split on a music ListItem, and the flag that
  silently downgrades itself.
license: CC-BY-SA-4.0
metadata:
  category: playback
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-14"
  verified-method: "observed"
---

# Starting playback correctly

## `<provides>` does not pick the player

`<provides>video</provides>` controls only whether your add-on appears under
*Video add-ons* in the browser. **The player core is chosen at playback time from
the ListItem's info tag.**

Getting this backwards has a precise symptom: an audio add-on that declares
`video` makes the **i** (info) button a no-op in the video browser, because Kodi
opens `DialogVideoInfo` for an item carrying only music tags.

So set the info tag for the player you want, and set `<provides>` for the browse
category you want. They are independent decisions.

## The path plays; `setDbId` names the library row

`xbmc.PlayList.add(path, listitem)` opens **the path**.
`listitem.getMusicInfoTag().setDbId(n, "song")` is what `Player.GetItem` reports
as `id`.

They are independent. Observed on Kodi 21.3: a ListItem whose path was song A's
file and whose `setDbId` was song B's id played A's URL. `Player.GetItem`
returned `file` of A and `id` of B. Title and album on that response were the
tags set on the ListItem, so the payload can look internally consistent while
`id` points at a different row.

Anything that keys off the library id — play counts, the info dialog, artwork
loaded from the row, a companion add-on mapping `kodi_id` back to a server item
— follows B. The stream is A. The symptom is "the right queue plays and Now
Playing is a different album".

A library rebuild that deletes and re-inserts songs reuses `idSong` numbers
([`kodi-database-writing`](../kodi-database-writing/SKILL.md)). A stored
`setDbId` then names whoever occupies that number now.

**Resolve the live row before you stamp the id.** Do not persist a Kodi song id
as identity across a wipe. Keep a stable key (the server item id in the URL, or
the file path) and look the current row up at play time.

`AudioLibrary.GetSongs` with
`{"field":"path","operator":"contains","value":"<id-from-the-url>"}` found the
current song. The same filter on `filename` returned **zero rows**: Kodi stores
the directory URL in `path.strPath` and the leaf (`stream.flac?static=true`) in
`song.strFileName`. A unique id that lives in the folder part of the URL is
invisible to `filename`.

## The fullscreen window comes from the content, not the core

**Both player cores route audio-only content to `WINDOW_VISUALISATION`.** Kodi
picks the fullscreen window from `IsPlayingAudio()` / `IsPlayingVideo()`, not
from which core is playing.

What actually differs between the cores is which OSD info-labels populate — for
example **`Player.ChapterCount` is always 0 under PAPlayer** — and which
time-tracking path runs.

## The resume property differs per core

There is no single "start here" property.

| Core | Property | Units | Consumed by |
|---|---|---|---|
| VideoPlayer | `StartOffset` | **milliseconds** | `CFileItem::SetStartOffset`, queues a `SeekTime` after demuxer open |
| PAPlayer | `audiobook_bookmark` | **milliseconds** | read in `QueueNextFileEx()`, converted to a frame offset, applied in `ProcessStream()` **before audio output begins** |

The PAPlayer route is the better one where it applies: because it lands before
output starts, there is **no race with initialisation and no audible blip**.

Note also that `ResumeTime` / `TotalTime` are **seconds**, unlike the two above.
Mixing the units is easy and presents as a resume that is wildly wrong rather
than slightly wrong.

## PAPlayer emits a spurious `SeekTime(0)` at init

Any logic keyed on "a seek happened" must threshold above roughly 100 ms, or
initialisation itself will trip it before the real resume seek arrives.

## `PlayMedia`'s resume flag cannot resume a `plugin://` path

Kodi gates it on `GetItemResumeInformation().isResumable`, which a bare plugin
path never satisfies — it logs `LoadDetails: Unsupported item type` and **the
flag silently downgrades itself to `noresume`**.

Use an explicit start position instead. Similarly, `Player.Open`'s
`options.resume` is **silently ignored for a playlist** — the `playlistid` branch
of `CPlayerOperations::Open` never calls `HandleResumeOption`. Set
`StartOffset` on the ListItem instead; it starts already-seeked with no audible
blip and none of the mute-seek-unmute dance.

## Do not hand Kodi a bare `plugin://` while something is playing

The outgoing player's stop is queued to the application thread, which does not
reach it until **103–105 ms after** `VideoPlayer::OpenFile` — measured, every
time. The new demuxer is aborted mid-open.

The symptom is `OpenDemuxStream - Error creating demuxer`, which looks exactly
like a broken stream and is not.

**Stop, wait for the stop to land, then call `PlayMedia`.** Library playback via
`videodb://` is unaffected, because Kodi sequences the handover itself.

## Sidecar subtitles are ordered before embedded ones

Kodi registers a ListItem's subtitle files during `OpenInputStream`, which runs
**before** `OpenDemuxStream` adds the container's own tracks. So attached
sidecars **lead**, and every embedded track's index shifts by the number of
sidecars.

This fails silently in the worst way: nothing errors, the viewer simply gets a
neighbouring language. Asking for Norwegian and playing Korean is the observed
case.

Verify ordinals against `Player.GetProperties` rather than assuming.

**Kodi also reads a subtitle's language and name out of its filename**, with a
measured grammar:

| Filename | Result |
|---|---|
| `English.eng.srt` | name + language |
| `Commentary.eng.forced.srt` | forced flag consumed |
| `eng.srt` | language, no name |
| `English SDH.eng.sdh.srt` | `sdh` is not a flag and leaks into the name |

A server that serves every track as `Stream.<codec>` — whose stem matches the
video's own — gets that stem stripped as a redundant prefix, leaving Kodi with
nothing to show.

## What fails silently

- `<provides>` mismatching the info tag makes the info button a no-op.
- `PlayMedia`'s resume flag downgrading itself for plugin paths.
- `Player.Open`'s `options.resume` being ignored for playlists.
- A bare `plugin://` during playback aborting the new demuxer, which reads as a
  broken stream.
- Sidecar ordering shifting every embedded subtitle index.
- `setDbId` naming a different library row than the path being played, with no
  error.

## Open questions

- The 103–105 ms handover figure is from one machine. The ordering hazard is
  structural, but the number is not a constant to design against.
- Whether `StartOffset` behaves identically for a `plugin://` path and a library
  item has not been separately confirmed.
- Whether `MusicPlayer.*` infolabels follow the ListItem tags or the library row
  when `setDbId` and the path disagree. `Player.GetItem` title/album followed
  the tags; `id` followed `setDbId`. The skin now-playing banner after a
  *matching* rebind showed the rebound row. The mismatched-id banner was not
  screenshotted.

## See also

- [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) — asserting playback actually
  started, and why `speed: 1` does not mean playing
- [`kodi-inputstream`](../kodi-inputstream/SKILL.md) — what happens to the stream
  after the player opens it
- [`kodi-database-writing`](../kodi-database-writing/SKILL.md) — why a stored
  `songid` can name a different track after a rebuild
