---
name: kodi-database-writing
description: >
  Write to Kodi's own library databases without corrupting them or wedging Kodi.
  Use when an add-on populates MyVideos or MyMusic directly, when library rows are
  wrong or missing after a sync, when a stored songid points at a different track
  after a rebuild, or when deciding between JSON-RPC and SQLite for library
  writes. Covers the echo loop that JSON-RPC writes cause, the free way to make
  widgets notice a direct write, the reserved artist row, and song-id reuse.
license: CC-BY-SA-4.0
metadata:
  category: kodi-data
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64, Android TV"
  verified-date: "2026-08-14"
  verified-method: "observed"
---

# Writing Kodi's library directly

Some add-ons populate Kodi's own library rather than serving a `plugin://`
listing. It gives native browsing, widgets and artwork — and it means owning a
schema you do not control.

Read [`kodi-library-data`](../kodi-library-data/SKILL.md) first for where the
files are and how to read one safely.

## Never write the library through JSON-RPC

`VideoLibrary.Set*` and its relatives raise Kodi announcements. If your add-on
also *listens* for those announcements to sync back to a server, you have built
an infinite loop:

```
write → VideoLibrary.OnUpdate → push to server → echo back → write → ...
```

Direct SQLite writes raise **no announcement**, which is the only reason such a
sync terminates at all. That is not a happy accident to rely on quietly — it is
the actual load-bearing property, so write it down where the next person will
see it.

## Making a direct write visible, for free

Direct writes leave widgets stale, because nothing announced. The obvious fix —
`UpdateLibrary(video)` — is safe only because plugin paths carry `noUpdate=1`, so
Kodi skips them and the scan is a no-op that still completes the cycle.

**Music has no `noUpdate` column at all.** A bare `UpdateLibrary(music)` therefore
walks the real library — roughly 21,000 remote probes in one measured case — and
overlapping music scans have crashed Kodi outright
(`CMusicLibraryQueue::StopLibraryScanning`, SIGBUS on Android).

The trick that works for both:

```sh
kodi-builtin 'UpdateLibrary(music,/does/not/exist)'
```

Kodi logs *"does not exist - skipping scan"*, finishes in 0 s having probed
nothing, and **still completes the cycle that invalidates cached containers**.

Guard it on `Library.IsScanningMusic` so two never overlap.

## Kodi reserves `idArtist 1`

Row 1 of the artist table is Kodi's `[Missing Tag]` blank artist.

An `add_artist` that computed an id but inserted `None` let SQLite assign rowid
**1** — which happens against an empty table, exactly the state a freshly
repaired music library is in. A real artist then rendered as `[Missing]`, and the
add-on's own mapping pointed at a different row again.

The lesson generalises: **Kodi's schema has reserved and sentinel rows.** Never
let the database assign an id you then need to match.

## `idSong` is reused

`song.idSong` is `INTEGER PRIMARY KEY` with no `AUTOINCREMENT`
(`xbmc/music/MusicDatabase.cpp` `CreateTables`, MyMusic83). There is no
`sqlite_sequence` row for it.

Delete a song and insert another, and SQLite hands the old number out again. An
add-on that persisted `songid` 12 across a library repair then calls
`setDbId(12)` on whoever was inserted first into that hole. The stream URL can
still be the saved file; Now Playing and play counts follow the new row. See
[`kodi-playback-resume`](../kodi-playback-resume/SKILL.md).

A rebuild that deletes a contiguous high block and re-inserts in the same order
can refill that hole with the **same** ids. Observed: a secondary music library
occupying only high ids came back with those ids unchanged after delete+add.
That looks like a clean repair and is a bad reproduction. The failure is a
reshuffle — a newest-first walk of a large library into vacated low numbers.

Do not treat a Kodi song id as identity across a wipe. Keep a stable key (a
server item id in the URL, or the file path) and look the live row up at use
time.

## `song_artist` is how an album's songs are reached

Kodi reaches an album's songs *under an artist* through `song_artist`. A song
written with empty `ArtistItems` gets no row there — so the album appears
**empty under the artist while looking completely correct everywhere else**.

Measured: 166 songs across 15 of 18 albums. Fall back to `AlbumArtists` when the
per-song list is empty, which is what Kodi's own scanner does.

Root cause in that case was damaged ID3: smart quotes in TPE1 truncated to the
low byte of the UTF-16 code unit. Worth knowing that upstream tag damage
presents as a Kodi display bug.

## Ordering, atomicity and partial writes

**Nest two-database writes so Kodi commits before your own mapping database.**
The reverse leaves your mapping claiming rows Kodi never got — invisible to every
later checksum-gated walk, because your side believes the work is done.

**A context manager that commits unconditionally persists half a multi-table
write on the exception path.** Commit on success only.

**A truncated id map is a deletion order, not a smaller answer.** `len(items) <
limit` conflates "no more records" with "fewer than I asked for this time", and a
loaded server is entitled to the latter. Page to the server's declared total, and
**raise rather than return a partial map**.

**A non-atomic state file is silent data loss.** A truncate-then-rewrite let a
concurrent reader parse half a file, default to an empty whitelist, and skip
items with no exception and no report — while the watermark advanced past them.
Write to a temp file, `fsync`, then `os.replace`. And distinguish "missing or
empty" (a fresh install) from "parses but is not an object" (raise loudly).

## Schema versions

Gate on the schema version and **refuse to write an unrecognised one**. Keep
version-keyed constants and `.schema` fixtures dumped from pristine installs, and
use explicit column lists everywhere so additive schema changes are harmless.

Known versions: Omega ships MyVideos131 and MyMusic83; Piers ships MyVideos146
then MyVideos147, and MyMusic84.

**Kodi 22 bumped MyVideos 146→147 mid-beta, and the bump is data-only** — the
migration contains no `CREATE`, `ALTER`, `DROP`, `INSERT` or index statement,
only `UPDATE`s repairing `rar://` escapes and DOS separators. `CreateTables` and
`CreateAnalytics` were byte-identical. So a schema-version gate that refuses 147
outright rejects a database it could have handled.

Piers also renumbered the `VideoAssetType` enum — a value-level change that a
column-level diff will not show you.

## What fails silently

- A JSON-RPC library write starts an echo loop that terminates only by accident.
- `UpdateLibrary(music)` walks the whole library and can crash Kodi.
- A database-assigned id can collide with a reserved sentinel row.
- `idSong` values are reused after delete+insert; a stored songid can name a
  different track after a rebuild, with no error.
- A missing `song_artist` row hides songs under one browse path only.
- A partial page reads as a complete, smaller answer.
- A half-written state file parses as an empty one.

## Open questions

- Whether the `noUpdate` asymmetry between video and music is deliberate has not
  been established from source; only its effect was measured.
- Whether MyVideos147's data-only property holds for the final Kodi 22 release,
  rather than just the beta, is untested.
- Whether `idMovie` / `idEpisode` are also plain `INTEGER PRIMARY KEY` (same
  reuse) was not checked; only `idSong` on MyMusic83 was.

## See also

- [`kodi-library-data`](../kodi-library-data/SKILL.md) — reading, WAL, and which
  operations destroy add-on rows
- [`kodi-announcements`](../kodi-announcements/SKILL.md) — the events a write
  does or does not raise
- [`kodi-performance`](../kodi-performance/SKILL.md) — why a full scan is far
  worse on a TV box
- [`kodi-playback-resume`](../kodi-playback-resume/SKILL.md) — a stale
  `setDbId` names the reused row while the path still plays the saved file
