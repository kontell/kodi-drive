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
  verified-date: "2026-08-20"
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

What `<provides>` *does* decide is which playlist a listing of yours queues onto
— and with both values declared, video wins even for songs. See
[`kodi-plugin-listings`](../kodi-plugin-listings/SKILL.md).

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

## Kodi keeps its own resume bookmark for a plugin row

When a `plugin://` item stops, Kodi writes a MyVideos bookmark for it keyed on
the row's path: `CPluginDirectory` stamps `original_listitem_url` on the
resolved item (`xbmc/filesystem/PluginDirectory.cpp:146-147`) and the save job
keys the bookmark on that property for plugin sources
(`xbmc/utils/SaveFileStateJob.cpp:42-61`). The `files` row holds the whole URL in
`strFilename`, with `strPath` the URL up to its options.

When the row is listed again, `GetNonFolderItemResumeInformation` reads the
ListItem's own resume point first and **falls back to that bookmark only when no
point is set** (`xbmc/video/VideoUtils.cpp:708-794`). For an add-on whose
resume points come from a server:

- Stamp `setResumePoint(position, total)` on every listing row that has a
  total, **position 0 included**. A zero point with a total reads as "set,
  nothing to resume" — `IsResumable` false — and skips the fallback. Observed
  on 21.3: a row whose server position was 0, with a 600 s bookmark planted on
  its plugin path, read `ListItem.IsResumable` false once the listing stamped
  `(0, total)`. Without the stamp the fallback is the stale local time.
- That rule is for listing rows. Whether a zero point on the **resolved** item
  (`setResolvedUrl`) is read as a resume is in Open questions; leave it
  unstamped when playback is to start at 0.

## Kodi's "Reset resume position" never reaches an add-on

The entry is visible on any row whose `GetItemResumeInformation` is resumable
(`xbmc/video/ContextMenus.cpp:76-84`), so a plugin row that stamps a server
position shows it. Executing it queues `CVideoLibraryResetResumePointJob`
(`ContextMenus.cpp:86-90`), whose whole effect is
`CVideoDatabase::DeleteResumeBookMark` — the MyVideos bookmark for the item's
file id, or for its path when the tag carries none
(`xbmc/video/jobs/VideoLibraryResetResumePointJob.cpp:45-85`,
`xbmc/video/VideoDatabase.cpp:3396-3436`). The `VideoLibrary.OnUpdate`
announcement fires only for library content types, and the job's completion
refreshes the container (`xbmc/video/VideoLibraryQueue.cpp:238-244`), which
re-reads the listing.

So for a plugin row nothing tells the add-on, and the refresh stamps the
server's position straight back. Offer a reset of your own — and clear Kodi's
half too, or the fallback above resurrects the position you just removed:

```
Files.SetFileDetails  {"file": "<the row's plugin:// path>", "media": "video", "resume": {"position": 0}}
```

It is the one JSON-RPC write that reaches a plugin path: it requires the file to
exist, and `CPluginFile::Exists` answers true for any `plugin://`
(`xbmc/filesystem/PluginFile.cpp:26-29`); a zero position makes
`UpdateResumePoint` clear the bookmark rather than write one
(`xbmc/interfaces/json-rpc/VideoLibrary.cpp:1176-1196`). Observed on 21.3:
`"resume": {"position": 100, "total": 1000}` on a plugin path produced a
`bookmark` row (100.0 / 1000.0) joined to a new `files` row; `"position": 0`
removed the bookmark and left the `files` row, which is what Kodi leaves after
any plugin play.

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
- A plugin row with no stamped resume point advertising a stale bookmark Kodi
  saved for it, however the server now stands.
- Kodi's "Reset resume position" on a plugin row deleting a local bookmark and
  nothing else, then refreshing the listing that restores the position.

## Open questions

- The 103–105 ms handover figure is from one machine. The ordering hazard is
  structural, but the number is not a constant to design against.
- Whether `StartOffset` behaves identically for a `plugin://` path and a library
  item has not been separately confirmed.
- Whether a zero resume point stamped on the *resolved* item makes Kodi treat
  the play as a resume and seek to the MyVideos bookmark for the path. One
  add-on records that it does and builds its resolved item without a point for
  a start at 0; it was not re-verified here.
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
