---
name: kodi-library-data
description: >
  Kodi's own SQLite databases — where they live, which are per-profile, how to
  read one safely, and which user-facing operations destroy add-on data. Use
  before reading or writing MyVideos, MyMusic, Addons33 or Textures directly,
  when snapshotting a database for comparison, when a schema version moved under
  you mid-beta, or when library rows have vanished and you need to know whether
  something deleted them.
license: CC-BY-SA-4.0
metadata:
  category: kodi-data
  verified-kodi: "21.3 Omega, 22.0b1 Piers, 22.0b2 Piers"
  verified-platform: "Linux x86_64, armv7l"
  verified-date: "2026-10-09"
  verified-method: "observed"
---

# Kodi's databases

Kodi keeps its state in SQLite files under `userdata/`. Reading them is often the
only way to get ground truth, because JSON-RPC reports intent while the database
holds outcome.

## Where they are, and what is per-profile

```
~/.kodi/userdata/Database/                       master profile
~/.kodi/userdata/profiles/<name>/Database/       each additional profile
```

| File | Holds | Scope |
|---|---|---|
| `Addons33.db` | which add-ons are installed and enabled | per profile |
| `MyVideos*.db` | the video library | per profile |
| `MyMusic*.db` | the music library | per profile |
| `Textures*.db` | the artwork cache | shared |

The trailing number is a schema version and changes between Kodi releases. A path
that works on 21 will silently not exist on 22, and a script that ignores the
error reads nothing while reporting nothing.

**It also changes *within* a release.** Kodi 22 bumped MyVideos twice during
beta, so "the Piers video database" is three different numbers depending on when
the install was built:

| Kodi | MyVideos | MyMusic | Textures |
|---|---|---|---|
| 21 Omega | 131 | 83 | 13 |
| 22 Piers, early beta | 146 | 84 | 14 |
| 22 Piers, from 2026-08 | 147, then 148 | 84 | 14 |

Read the number from the file, never from the Kodi version. An add-on that gates
on a schema version — the right thing to do before writing — will otherwise
refuse to run on a beta that moved under it.

`148` is worth knowing about if you write `streamdetails` yourself: it adds
`iSource` and `iVersion` to that table. `iSource` is a precedence ladder
(`UNDEFINED 0`, `EXTERNAL 10`, `MEDIA 20`, `NFO 30`, `LEGACY 40` in
`xbmc/utils/StreamDetails.h`) and `CStreamDetails::ShouldUpdateWithNewDetails`
lets the player overwrite stored details whose source is lower or equal. Rows
inserted without those columns read back as `UNDEFINED`, so anything the player
observes replaces them on playback stop — which matters when what it observed was
a transcode rather than the source file. Both columns are additive: a writer that
names its columns is unaffected, and the migration is two `ALTER TABLE`s.

**Globbing is not enough either — Kodi leaves the old databases in place.** A
single real install held all of these at once:

```
MyVideos121.db  MyVideos131.db      MyMusic82.db  MyMusic83.db
```

`MyVideos*.db` matches two files, and the lower-numbered one is a stale copy from
before an upgrade. Reading it gives a library that is plausibly populated and
months out of date, which is far harder to spot than an empty result.

**Take the highest-numbered file:**

```sh
db=$(ls -1 ~/.kodi/userdata/Database/MyVideos*.db 2>/dev/null \
     | sed 's/.*MyVideos\([0-9]*\)\.db/\1 &/' | sort -rn | head -1 | cut -d' ' -f2)
```

## Always take the `-wal` and `-shm` with the `.db`

Kodi runs these databases in WAL mode. Recent writes live in `<name>.db-wal` and
have not yet been folded into the `.db` file.

Copy the `.db` alone and you get a **stale snapshot** that looks complete — no
error, no truncation, just an older view. This is a reliable way to spend an hour
concluding that a write never happened when it did.

```sh
cp MyVideos131.db MyVideos131.db-wal MyVideos131.db-shm /tmp/snapshot/
```

Prefer reading while Kodi is stopped where you can.

## Telling a freshly created database from a migrated one

If you are capturing a schema dump as a fixture, the two are not
interchangeable: a fixture is supposed to be what `CreateTables` produces, and a
database that reached its version by migration can carry text no fresh install
has.

You do not need the install's history to tell them apart — the dump says which it
is. SQLite rewrites a table's **stored** `CREATE` statement when you add a
column, splicing in the `ALTER` clause verbatim, so the migration's own
capitalisation and defaults survive:

```console
$ sqlite3 t.db "CREATE TABLE t (a integer, b text);"
$ sqlite3 t.db ".schema t"
CREATE TABLE t (a integer, b text);

$ sqlite3 t.db "ALTER TABLE t ADD iSource INTEGER DEFAULT 40;"
$ sqlite3 t.db ".schema t"
CREATE TABLE t (a integer, b text, iSource INTEGER DEFAULT 40);
```

Kodi's own DDL for that column reads `iSource integer` — lower case, no default —
so a dump showing `iSource INTEGER DEFAULT 40` came through the upgrade path and
one showing `iSource integer` was created at that version. Compare the dump
against the `CreateTables` text in the source rather than trusting the file's
age or the install's apparent history.

The same rewrite is why a dump can differ from an older fixture for reasons that
are not a schema change at all: quoting in `CreateTables` is edited from time to
time — Kodi 22 started backtick-quoting `sets` because it is a reserved word in
MySQL 9.6 — and every database created after that commit carries the new
spelling. SQLite treats the two alike, so it is noise in a diff, not a finding.

## "Clean Library" asks the add-on before deleting a plugin row

Kodi's own **Videos > Files > Clean Library** does not treat a `plugin://` path
as a file it cannot stat. On Omega and Piers, every `files` row whose path is a
plugin URL is put to the add-on: Kodi runs the plugin at that URL with
`kodi_action=check_exists` appended and keeps the row only when the script
answers `xbmcplugin.setResolvedUrl(handle, True, item)`. Any other outcome —
`False`, no answer, a script error — deletes the row. The second pass applies
the same test to each `path` row (sourced: `xbmc/video/VideoDatabase.cpp`
lines 10169–10175 and 10336–10342, `xbmc/filesystem/PluginDirectory.cpp` lines
564–606, at 22.0b2 `e513e0ff`; `21.3-Omega` carries the same branch, `20.5-Nexus`
has none and deletes every plugin row unconditionally).

**Kodi never asks when it cannot ask, and then it deletes.**
`CPluginDirectory::IsMediaLibraryScanningAllowed` refuses before the script
runs when:

- the add-on is **disabled** — the lookup is
  `GetAddon(..., OnlyEnabled::CHOICE_YES)` and the refusal logs
  `error <general>: Unable to find plugin <addon id>`;
- the add-on declares no `<medialibraryscanpath content="movies">` (or
  `tvshows`, `musicvideos`) under its `xbmc.python.pluginsource` extension, or
  the declared path is not a parent of the row's path
  (`xbmc/addons/PluginSource.cpp:28-33` is the parser);
- the path row carries no scraper content, so there is no content type to look
  up.

Observed on 22.0b2 Piers, same library, two runs half a minute apart. With the
add-on enabled, Clean Library invoked `check_exists` once per movie row — one
`CScriptRunner: running add-on script` line each, a millisecond apart — finished
in 3.8 s and deleted nothing. With the add-on disabled it logged
`Unable to find plugin` instead, took 37 s, and emptied the movie table; the
next scan reported the plugin directory `as not in the database`. Kodi's logger
collapses repeats (`Skipped 24 duplicate messages..`), so the number of error
lines is not the number of rows lost.

For an add-on that writes `plugin://` rows into the library:

- **Declare the scan path and answer `check_exists` for every row you own.**
  Answer `True` unless you hold a positive record that the item is gone;
  "unknown" must not read as "deleted", because Kodi acts on it immediately.
- **A disabled add-on cannot defend its rows.** A user who disables it and runs
  Clean Library loses every row, with no prompt specific to add-on content.
  Keep a repair path.
- Clean Library is still user-initiated destruction the add-on cannot see
  coming; the earlier Omega observation stands — movies were deleted and the
  add-on did not rebuild them until a repair pass ran.

## A plugin as a TV source: bind the root *and* every show folder

Binding a plugin directory as `tvshows` content and scanning it is not enough
to import a show. On 22.0b2 Piers the scanner listed every show folder the
plugin returned and imported none, logging only
`VideoInfoScanner: No (new) information was found in dir plugin://…/tvshows/`
(observed; the shows appeared on the next scan once each folder had its own
binding).

The cause is how Kodi walks up a plugin path. `URIUtils::GetParentPath`
treats the parent of **any** `plugin://` path that still has a file name as the
plugin root `plugin://<addon id>/`, not the directory above it
(`xbmc/utils/URIUtils.cpp` lines 532–549 at `e513e0ff`: the options are
stripped first, then the whole file name). `CVideoDatabase::GetScraperForPath`
looks the folder's own `path` row up and, finding no content on it, "drills up
until a scraper is configured" through exactly that function
(`xbmc/video/VideoDatabase.cpp` lines 8678 and 8784–8790), so from
`plugin://<id>/tvshows/<show>/` it reaches the plugin root, which has no
binding, and the folder is skipped without a line of its own
(`RetrieveVideoInfo` drops an item whose scraper lookup fails,
`xbmc/video/VideoInfoScanner.cpp` line 924 onward).

What works, as the phase-0 probe found and the import confirmed:

- Bind the root with `VideoLibrary.SetSourceContent` (`content: "tvshows"`,
  `scraperid: "metadata.local"`), **and** bind each show folder the same way
  with `containssingleitem: true`. The folder then owns a `path` row with
  content, and the scan of the root imports the show and its episodes
  (observed: the same root scan that had imported nothing added every show
  and episode once the folders were bound).
- The add-on's manifest must declare a `<medialibraryscanpath>` **for each
  content type** it scans. `CPluginDirectory::IsMediaLibraryScanningAllowed`
  keys the lookup on the scraper's content (`xbmc/filesystem/PluginDirectory.cpp`
  lines 564–590; the parser is `xbmc/addons/PluginSource.cpp` lines 26–38). With
  only `content="movies"` declared the scan ends at once with
  `VideoInfoScanner: Plugin '…' does not support media library scanning for
  'TV shows' content` (observed).
- Episodes are matched to their show by directory: the scanner lists the show
  folder recursively and files each item whose tag carries season and episode
  numbers (`ProcessItemByVideoInfoTag`, `VideoInfoScanner.cpp` lines 1998–2014).
  A tag is accepted when `season >= 0 and episode > 0`, or — for a plugin
  item only — `season > 0 and episode >= 0`. **Season 0 with no episode number
  never imports** (observed: every unnumbered special stayed out of the
  library while its numbered neighbours came in). Nothing logs the refusal
  beyond `Could not enumerate file`.
- A show folder may carry a `hash` property. `EnumerateSeriesFolder` compares it
  with the hash stored for the folder and skips the listing when they match
  (`VideoInfoScanner.cpp` lines 1836–1846; the stored hash is written after the
  episodes were added). The root listing's own hash is built from each folder's
  path, size and **date at day precision** (`GetPathHash`, lines 2945–2965), so
  a show whose contents changed has to present a different `setDateTime` day or
  a scan of the root skips every folder at once (`Skipping dir … due to no
  change`, observed for each unchanged show).
- `SetSourceContent` with `content: "none"` deletes the rows under the path
  only with `clearmode: "remove"`; that branch alone calls
  `RemoveContentForPath` (`xbmc/interfaces/json-rpc/VideoLibrary.cpp` lines
  1044–1046), and `GetSubPaths` makes it cover every `path` row with the given
  prefix (`VideoDatabase.cpp` line 6036 onward), shows included. `"clear"`
  unbinds the scraper and leaves the rows (observed on 22.0b2: a `"clear"` left
  every movie in place; a `"remove"` on a library root took its movies and its
  shows in one call).

## A plugin as a music source: one directory at a time

Importing songs from a `plugin://` listing works through `AudioLibrary.Scan`
with a `directory`, without registering a music source (observed on 22.0b2:
a five-figure song library imported from one scan of the plugin's music root).
What the music scanner does differently from the video one decides the layout.

- **A scan replaces exactly one directory.** `RetrieveMusicInfo` calls
  `RemoveSongsFromPath(strDirectory, songsMap)` and the declaration defaults
  `exact` to `true` (`xbmc/music/MusicDatabase.h`, the `RemoveSongsFromPath`
  declaration; `xbmc/music/infoscanner/MusicInfoScanner.cpp`, in
  `RetrieveMusicInfo`), so the songs on that path are deleted and re-added from
  the listing, and a folder the root listing no longer names keeps its songs.
  Ids, play counts and last-played survive by **file name** (`FileItemsToAlbums`
  looks each item's path up in the map and copies `idSong`, `iTimesPlayed`,
  `lastPlayed`). To remove a song, list its directory without it; to remove an
  album, list its directory empty; a root walk removes nothing on its own
  (observed: a root scan with every album folder absent from the root listing
  left every song; the same scan with the folders still listed and each listing
  empty removed them all and the orphan albums and artists with them).
- **A song's URL must be a file, not a query.** The music database stores a
  song as a path row plus a file name through `URIUtils::Split`
  (`CMusicDatabase::SplitPath`), and `Split` drops the options from the file
  name (`xbmc/utils/URIUtils.cpp`, the "if actual uri, ignore options" branch),
  where `CVideoDatabase::SplitPath` keeps a plugin URL whole. Observed on
  22.0b2: songs listed as `plugin://…/<album>/?mode=play&id=<id>` came back
  from `AudioLibrary.GetSongs` with `file` equal to the bare directory, every
  song of an album alike — unplayable and unmatched on a rescan. Listed as
  `plugin://…/<album>/<id>.<ext>` they came back intact.
- **A new song's play count is zero whatever the tag says.** `CSong::CSong(CFileItem&)`
  sets `iTimesPlayed = 0` (`xbmc/music/Song.cpp`); only a rescan of an existing
  row keeps the database's value. Play counts go in afterwards with
  `AudioLibrary.SetSongDetails`.
- **Kodi takes no art from a plugin listing.** `CFileItem::GetUserMusicThumb`
  returns an empty string for `IsPlugin()` paths (`xbmc/FileItem.cpp`), so
  `FindArtForAlbums` finds nothing and `RetrieveLocalArt` lists every added
  album directory a second time after the walk, looking for folder art it
  cannot see (observed: one extra listing per new album, each on a fresh
  interpreter). Album and artist art go in with `SetAlbumDetails` and
  `SetArtistDetails`.
- **Every setter is a burst of autocommit statements.** With the `database`
  log component on (`debug.setextraloglevel` = `[131072]`), one
  `AudioLibrary.SetSongDetails` carrying only `playcount` and `lastplayed`
  ran nine statements — `UPDATE song …`, `DELETE FROM song_genre …`, one
  `INSERT INTO song_genre …` per genre, `UPDATE song SET strGenres …` — at
  3–5 ms each on an NVMe disk with the database in WAL mode (observed on
  22.0b2). An isolated call answers in under a millisecond; twenty-five in a
  row cost 36–47 ms each, and eight parallel HTTP clients made each call
  slower, not the burst faster.
- **Announcements made while the music scanner is busy are a transaction.**
  `AnnounceUpdate` in `xbmc/music/MusicDatabase.cpp` (the unnamed-namespace
  helper) sets `data["transaction"] = true` when
  `CMusicLibraryQueue::IsScanningLibrary()`, and the home-screen widget
  provider returns before refreshing on such an announcement
  (`xbmc/guilib/listproviders/DirectoryProvider.cpp`, the subscriber's
  `Announce`). Outside a scan, every `SetSongDetails` made Estuary's music
  widgets re-query the library (observed: `CDirectoryProvider[…random_albums.xsp]:
  refreshing...` and its three siblings after each burst); inside one, none did.
  `CVideoDatabase::AnnounceUpdate` carries no such flag.
- **Clean Library never asks about a music row and never deletes one.**
  `CleanupSongsByIds` tests each song with `CFile::Exists`, and
  `CPluginFile::Exists` returns `true` unconditionally
  (`xbmc/filesystem/PluginFile.cpp`); the video cleaner's `check_exists` route
  (above) has no music counterpart. Observed on 22.0b2: `AudioLibrary.Clean`
  with the add-on enabled finished in under a second and kept every song.
- **`Player.Open` by `songid` cannot play a plugin song.** JSON-RPC opens
  `musicdb://songs/<id>.<ext>`, and `CMusicDatabaseFile::TranslateUrl`
  (`xbmc/filesystem/MusicDatabaseFile.cpp`) resolves that to the stored path
  and opens it as a file, which a `plugin://` URL cannot be (observed: `Init:
  Error opening file musicdb://songs/<id>.mp3`, `PAPlayer::QueueNextFileEx -
  Failed to create the decoder`). Opened by its `file` — what the music windows
  do — the same song resolved through the plugin and played.

## What the public API cannot set or list

Three fields read back as if the setter had failed. None of them is a bug in
the caller.

**A show's `dateadded` is derived.** The `tvshowcounts` view defines it as
`MAX(files.dateAdded)` over the show's episodes, and `tvshow_view` reads it from
there (`xbmc/video/VideoDatabaseDDL.cpp` lines 430–446 and 469).
`VideoLibrary.SetTVShowDetails` accepts `dateadded`
(`xbmc/interfaces/json-rpc/VideoLibrary.cpp` lines 1484–1487) and
`UpdateDetailsForTvShow` writes the `tvshow` table, which has no such column
(`VideoDatabase.cpp` line 2714 onward). Observed on 22.0b2: `SetTVShowDetails`
with `dateadded: "2001-01-01 00:00:00"` answered `OK`; `GetTVShowDetails`
still returned the newest episode's `dateadded`, to the second.

**A season with no episode row is invisible.** `season_view` joins `episode`
and `files` without `LEFT` (`VideoDatabaseDDL.cpp` lines 493–520), so
`VideoLibrary.GetSeasons` never returns a season that `addSeason` created
but no imported episode belongs to. Observed: the seasons a plugin had named
through `InfoTagVideo.addSeason` for which no episode imported were absent
from `GetSeasons`, while their siblings with episodes were listed with the
names given.

**`lastplayed` and `dateadded` are local time, and the API stores what it is
given.** `CVideoDatabase::SetPlayCount` fills a missing date with
`CDateTime::GetCurrentDateTime()` and writes `GetAsDBDateTime()`, local wall
clock (`VideoDatabase.cpp`, the `SetPlayCount(const CFileItem&, int, const
CDateTime&)` overload); `GetDateAdded` falls back to the file's modification
time or the current local time. A `Set*Details` call stores the text it is
sent verbatim. Observed on 22.0b2, on a machine one hour ahead of UTC: a
playback stopped at 18:34:03 UTC left `lastplayed: "2026-10-08 19:34:03"`;
a `SetEpisodeDetails` sent `"2026-10-08 18:36:22"` (the server's UTC) read back
unchanged and showed an hour early. Convert server timestamps to local time
before writing them; leave calendar dates (`premiered`, `firstaired`) alone,
since shifting a date by the zone moves it a day.

## Changing add-on enablement without loading the profile

A profile Kodi does not currently have open can be edited directly:

```sh
sqlite3 "$HOME/.kodi/userdata/profiles/<name>/Database/Addons33.db" \
  "UPDATE installed SET enabled=1 WHERE addonID='plugin.video.example';"
```

This is the escape hatch when profile switching is itself the broken thing — see
[`kodi-profiles`](../kodi-profiles/SKILL.md), where `Addons.SetAddonEnabled`
silently applies to whichever profile happens to be loaded.

Only touch a profile that is not currently open.

## What fails silently

- A show folder under a bound `tvshows/` plugin root that has no binding of its
  own is skipped with nothing but `No (new) information was found` for the
  root.
- A manifest missing a `<medialibraryscanpath>` for the content being scanned
  ends the scan in under 100 ms with one info line.
- A `Set*Details` call that answers `OK` for a derived field changed nothing;
  only a readback shows it.
- A `.db` copied without its `-wal` reads as a complete but older database.
- A hardcoded schema-numbered filename simply does not exist on another Kodi
  version; a script that does not check reports an empty library.
- Clean Library removes rows with no warning specific to add-on content, and the
  loss is only visible later, as absence. With the add-on disabled the only
  trace is `Unable to find plugin` at error level, repeat-collapsed.

## Open questions

- The Omega Clean Library run removed movies and kept episodes; the files loop
  treats every video type alike and keys the `<medialibraryscanpath>` lookup on
  the row's scraper content (sourced, above), so the asymmetry has to come from
  what that add-on declared or answered per content type (inferred). Its
  declarations at the time were not recorded. Music is settled above: the music
  cleaner never asks.
- Why a burst of music setters costs 3–5 ms a statement on an NVMe disk in WAL
  mode while an isolated call answers in under a millisecond was not found; the
  statements themselves are the measured cost, and neither the widget refreshes
  (silenced under a scan) nor parallel clients changed it.
- Whether Kodi holds any add-on enablement state in memory for non-active
  profiles, which would delay or defeat a direct `Addons33.db` edit, is untested.
- Whether a show folder's own binding is needed on Omega as well was not
  tested; `GetParentPath`'s plugin branch is the same there (sourced), the
  import was observed on Piers only.
- `GetSeasons` was only checked through JSON-RPC; whether the GUI's season
  listing uses the same join and hides the same rows was not looked at.

## See also

- [`kodi-profiles`](../kodi-profiles/SKILL.md) — per-profile scope and its traps
- [`kodi-process-control`](../kodi-process-control/SKILL.md) — stopping Kodi
  cleanly before reading its databases
- [`kodi-library-nodes`](../kodi-library-nodes/SKILL.md) — the `library://`
  XML trees, which are not these databases
