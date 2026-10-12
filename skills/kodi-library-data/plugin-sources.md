# A plugin as a scanner source

What Kodi's video and music scanners do with a `plugin://` source, each fact
sourced to the Kodi file and function or observed with the command and its
output. Companion to [SKILL.md](SKILL.md), which holds the database facts;
this file holds the scanner ones because the skill outgrew its length limit.

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

## An episode's `tvshow.*` and `season.*` art is the show's and the season's

`VideoLibrary.GetEpisodeDetails` and the episode listings return art the
thumb loader filled in: `CVideoThumbLoader::FillLibraryArt` appends the
show's art under the `tvshow.` prefix and the season's under `season.` when
the episode lacks them, with `fanart` falling back to `tvshow.fanart`
(`xbmc/video/VideoThumbLoader.cpp`; JSON-RPC calls it from
`xbmc/interfaces/json-rpc/FileItemHandler.cpp`). Those keys are read off
the show and season rows, so `SetEpisodeDetails` can neither make one true
nor clear it; setting one pins a copy on the episode that goes stale when
the show's art moves. Observed on 22.0b2: two episodes whose desired art
carried `tvshow.poster` failed their readback every 35 s after the show's
URL changed. Keep an episode's art to the keys the episode row owns.

## A path row per item costs the scanner, once

Filing each movie under a directory of its own (`…/movies/<id>/?…`, one
path row per item) costs the video scanner about 40 ms a movie on x86_64
and 130 ms on armv7 at import: 1,788 movies took 100–132 s under one
directory and 202–209 s under one each on a 22.0b2 Flatpak, 1,630 s against
1,869 s on a 1 GB LibreELEC box. The price is paid once; a later change to
one movie then costs a 0.5 s scan of its folder (bound first, as a show
folder is) instead of a re-walk of the whole directory.

## What the video scanner spends on each item, and which part a plugin sets

A trace of the scanner thread with the `database` log component on
([`kodi-performance`](../kodi-performance/SKILL.md) says how to read one),
half way through a first import of 1,788 movies from a plugin on a Raspberry
Pi 3 (22.0b2, databases on an SD card, about 11,000 actors and 4,000 tags
filed so far), put one movie at 600 ms:

| Where | Per movie | Why |
|---|---|---|
| The gap before `Sqlite commit transaction` | 160–190 ms | One transaction per item (`SetDetailsForMovie`), committed to a rollback journal |
| `insert into path …` | 20–50 ms | The item's own path row, autocommitted outside that transaction |
| The gap after each `insert into actor_link` | 8 ms × 19 | `AddActor`'s `select actor_id from actor where name like '…'`, a table scan |
| The gap after each `insert into tag_link` | 4 ms × 14 | `AddToTable`'s twin on `tag`, a table scan |
| Between the play-count update and the next item | 90–110 ms | No statement of the scanner's is logged here; inferred to be `FetchActorThumbs`, since switching it off (below) took 105 ms off a movie |

A plugin sets two of these. **Every cast member and every tag it lists is a
table scan that grows with the library** (the figures are in
`kodi-performance`), so a field added to every item is quadratic over an
import. And **the last row is the "Download actor thumbnails" setting**
(`videolibrary.actorthumbs`): with it on, `FetchActorThumbs` calls
`CacheArtwork` for every cast member
(`xbmc/video/VideoInfoScanner.cpp` lines 2604–2616 and 3157–3215 at
`e513e0ff`), and each call is `CTextureCache::BackgroundCacheImage`
(`xbmc/TextureCache.cpp` line 118) — a lookup in the texture database under
`m_databaseSection` (line 270), the lock the cache's worker holds while it
writes a cached image, then `CJobQueue::AddJob`, which searches the whole
queue for an equal job before adding one (`xbmc/jobs/JobQueue.cpp` lines
71–78). The texture cache is a queue with one worker
(`CJobQueue(false, 1, CJob::PRIORITY_LOW_PAUSABLE)`, `TextureCache.cpp`
lines 39–40), and a first import fills it faster than the worker empties
it: during the 1,300 s scan the worker cached 2,968 actor pictures of the
17,735 the listing named.

Turning the setting off over JSON-RPC for the length of the scan
(`Settings.SetSettingValue`) and back on afterwards, observed on the same
import:

| | Setting on | Off for the scan |
|---|---|---|
| Stock databases | 1,265 s | 1,078 s |
| WAL, and `NOCASE` indexes on `actor`, `tag` and `studio` names | 446 s | 259 s |

The pictures survive it. `xbmc.Actor`'s thumbnail fills both `thumbUrl` and
`thumb` (`xbmc/interfaces/legacy/InfoTagVideo.cpp` lines 42–44), `AddActor`
stores `art_urls` and the `art` row whenever they are set
(`xbmc/video/VideoDatabase.cpp`, `AddActor`), and the info dialog shows
`thumb` when it has one whatever the setting says
(`xbmc/video/dialogs/GUIDialogVideoInfo.cpp` lines 383–386); the image is
fetched when it is first shown. The scanner reads the setting for each item
(`VideoInfoScanner.cpp` line 2606), not once a scan. Without the setting the
WAL run held between 6.6 and 8.9 movies a second for the whole import; with
it the same run fell from 6.6 a second to 3.4 as the queue grew. An
add-on that flips a user's setting owes it back after a crash: record the
old value before the write.

## `UpdateLibrary(video)` with no path lists every bound plugin folder

The builtin with no directory scans every path row with content, and for a
plugin source that means listing each bound show folder to compare its hash:
83 show folders, 44 s, on the LibreELEC box (22.0b2), with every one
"Skipping dir … due to no change". It is the cheapest way to fire the
library-updated event the home widgets listen for only when few paths are
bound.

When the event is all that is wanted, scan a directory that does not exist.
`VideoLibrary.Scan` with `"directory": "special://temp/no-such-directory/"`
announced `VideoLibrary.OnScanStarted` and `VideoLibrary.OnScanFinished` 0.1 s
apart and listed nothing (observed on 22.0b2).

A clean asked for while any scan runs is refused, and the caller is not told:
`VideoLibrary.Clean` answered `OK` and Kodi logged `CleanLibrary is not
possible while scanning or cleaning`
(`xbmc/interfaces/builtins/LibraryBuiltins.cpp` line 95 at `e513e0ff`; observed
on 22.0b2 with a clean sent right after a scan with no path). Wait for
`OnScanFinished` before cleaning, and do not start a walk of every path just
before a clean that matters.

## An InfoTag is a pointer into its ListItem

`ListItem.getVideoInfoTag()` and `getMusicInfoTag()` return a wrapper around
the item's own tag, not a copy: `new InfoTagVideo(GetVideoInfoTag(),
m_offscreen)` uses the constructor that sets `owned(false)`
(`xbmc/interfaces/legacy/ListItem.cpp`, `InfoTagVideo.cpp`,
`InfoTagMusic.cpp` at e513e0ff), and `CFileItem::~CFileItem` deletes the tag.
A tag taken from a temporary — `xbmcgui.ListItem().getVideoInfoTag()` — dangles
as soon as the expression ends, and every setter on it writes freed memory.
Observed: a 32-bit ARM Kodi 22.0b2 (LibreELEC nightly, Python 3.14)
segfaulted twice in `InfoTagVideo::setGenres` on exactly that line, at the
start of a plugin listing during a video scan (`kodi_crashlog`, frame 0
`setGenres`, scanner thread in `CScriptRunner::WaitOnScriptResult` under
`EnumerateSeriesFolder`); the same code had listed the same library on an
x86_64 22.0b2 Flatpak for weeks without a symptom. Keep the ListItem in a
name that outlives every use of its tag.

## A music scan with a dialog lists every directory twice

`AudioLibrary.Scan` with `showdialogs: true` (the `UpdateLibrary` builtin's
`userInitiated`) gives the music scanner a progress handle, and with a
handle `CMusicInfoScanner::Process` starts its `MusicFileCounter` thread
(`xbmc/music/infoscanner/MusicInfoScanner.cpp`, `m_fileCountReader`), which
walks the whole tree through `CountFilesRecursively` to size the bar while
the scan itself walks it again. For a plugin source that is two listings
of every directory, concurrently: observed on 22.0b2, two `CScriptRunner`
threads listing the same music root at the same moment, each taking 62 s on
a 32-bit ARM box where the same listing took 20 s alone, and album
directories listed twice over for the rest of the scan (one album listing
45–67 s doubled, 0.25 s alone with the interpreter reused). Pass `showdialogs: false` to a music
scan of a plugin source and draw any progress yourself. The video scanner
has no counting thread; its dialog costs no extra listing.

## A plugin folder listed in a movies directory becomes a phantom disc

Before the video scanner looks at a movies listing it calls
`CFileItemList::Stack()`, whose `ConvertDiscFoldersToFiles` asks
`VIDEO::UTILS::GetOpticalMediaPath` of every folder item, and that checks
`CFileUtils::Exists(<folder>/VIDEO_TS.IFO)` (`xbmc/FileItemList.cpp`,
`xbmc/video/VideoUtils.cpp`). `CPluginFile::Exists` returns true for any
URL (`xbmc/filesystem/PluginFile.cpp`), so every plugin folder in a movies
listing is rewritten into `<folder>/VIDEO_TS.IFO`, scraped as a disc
("No NFO file found. Using title search for '…/VIDEO_TS.IFO'"), imported by
no local scraper, and never recursed into; the bound sub-paths are then
dropped as "Skipped N missing sub directories". Observed on 22.0b2 with
1,788 folders in 1.4 s. A plugin cannot give a movies root sub-folders.
It can still file each movie under a URL of its own
(`…/movies/<id>/?mode=play&id=<id>`): Kodi creates the path row from the
file's directory, and a later `VideoLibrary.Scan(directory=<that folder>)`
lists and imports that one movie, provided the folder carries its own
content binding (`GetScraperForPath` takes a plugin path's parent to be the
plugin root). Bind such a folder without `containssingleitem`, which would
make the folder the movie. The tvshows path is different: a show folder is
listed as a folder on purpose and skipped through its `hash` property.

## A scan requested while one is running stops it

`VideoLibrary.Scan` and `AudioLibrary.Scan` both execute the `UpdateLibrary`
builtin, and that builtin toggles: when the library queue reports a scan in
progress it calls `StopLibraryScanning()` and does **not** queue the new
request (`xbmc/interfaces/builtins/LibraryBuiltins.cpp`, `UpdateLibrary`,
both the `music` and the `video` branch). Observed on 22.0b2: two
`VideoLibrary.Scan` calls for two different directories issued within a
second logged one `VideoInfoScanner: Starting scan` and one `Finished scan`,
the second directory was never listed; a `VideoLibrary.Scan` sent while a
movies import was running ended that import with `No (new) information was
found` after a part of the directory, and the rest stayed out. Issue one
scan, wait for `OnScanFinished` (or for `Library.IsScanningVideo` /
`Library.IsScanningMusic` to drop), then issue the next. A user's own
"Update library" during an add-on's scan does the same to it.

## Refreshing a show keeps its rows only without `refreshepisodes`

A refresh removes "any existing data for the item" and scans it again: a movie
through `DeleteMovie`, an episode through `DeleteEpisode`, a season through
`DeleteSeason`, and a show through `DeleteTvShow` **only when the job was asked
to refresh everything** (`xbmc/video/jobs/VideoLibraryRefreshingJob.cpp` lines
455–473 at `e513e0ff`; `VideoLibrary.RefreshTVShow` passes its
`refreshepisodes` as that flag, `xbmc/interfaces/json-rpc/VideoLibrary.cpp`
lines 902–904). So `refreshepisodes: true` deletes the show with its seasons
and episodes and imports them again under new ids, and anything keyed on the
old ids is orphaned. With `refreshepisodes: false` the scanner takes its
`refreshShowInfoOnly` branch and rewrites the show's row where it is
(`xbmc/video/VideoInfoScanner.cpp` lines 1060–1100): on 22.0b2 a show
refreshed that way kept its `tvshowid`, and its five episodes kept their ids
and their play counts (observed, on a plugin source bound to
`metadata.local`).

Use the show-only form when what changed is the show's own data, such as its
cast, which no setter takes.

## A played song with no date is "played now"; an album is "added" when last scanned

`CMusicDatabase::UpdateSong` (xbmc/music/MusicDatabase.cpp) writes
`lastplayed = GetCurrentDateTime()` when the play count is above zero and
the date passed is invalid, and `AudioLibrary.SetSongDetails` passes the
song's existing date when the call carries none. A client that sets
`playcount` for an item its server marks played without a date therefore
stamps the moment of the call: sixteen such songs topped a tablet's
recently played albums on the day of its import (22.0b2). Send a date.

The same lines mean a song's `lastplayed` cannot be cleared through the API.
An empty string fails `CDateTime::SetFromDBDateTime`, which wants nineteen
characters, so the song keeps the date `SetSongDetails` loaded it with
(`xbmc/interfaces/json-rpc/AudioLibrary.cpp` lines 985–986 at `e513e0ff`), and
`UpdateSong` writes a valid date back whatever the play count
(`xbmc/music/MusicDatabase.cpp` lines 1401–1408); only a song that never had
a date reaches the branch that writes `NULL`. Observed on 22.0b2: a song with
play count 10, sent `{"playcount": 0, "lastplayed": ""}`, read back play count
0 with its date unchanged. A client that compares what it wants with a
readback must hold no opinion on the date of an unplayed song, or it sends
the same call on every pass.

`GetRecentlyAddedAlbums` orders by `album.dateAdded`, which the scanner sets
to the newest `song.dateAdded` of the album (`UPDATE album SET dateAdded`
after the songs), and `song.dateAdded` is the media file's timestamp
(`GetMediaDateFromFile`), which a plugin path cannot give, so it is the
scan time. Neither `SetSongDetails` nor `SetAlbumDetails` takes a date
added, and the music `ListItem.setInfo` has no `dateadded` key (the video
one does). A plugin source therefore controls the order only through the
order its directories are scanned in (label order, `DoScan` sorts by
label), and every re-listing of a directory moves its album to the top of
recently added; a user-accepted "rescan tags from files" re-stamps the
whole library.

## A stopped music scan leaves a directory hash without its songs

`CMusicInfoScanner::DoScan` stores a directory's hash
(`m_musicDatabase.SetPathHash(strDirectory, hash)`) after
`RetrieveMusicInfo` returns, whatever it returned
(`xbmc/music/infoscanner/MusicInfoScanner.cpp`, `DoScan`), and the
add loop inside `RetrieveMusicInfo` returns early on `m_bStop`. A scan
stopped while a directory is being written — a second `AudioLibrary.Scan`
request stops the running one — can therefore leave the directory's hash
stored with none or some of its songs, and every later scan of it logs
`Skipping dir '…' due to no change` and imports nothing. Observed on
22.0b2: two plugin album directories, 23 songs, skipped on every scan after
a scan was stopped by hand. Nothing Kodi offers rescans such a directory
short of changing what it lists (a date on each item moves the hash) or a
scan with `SCAN_RESCAN`, which a plugin cannot request through JSON-RPC.

## A music scan re-lists every album it added, out of a cache of fifty

After the walk, `RetrieveLocalArt` asks for each added album's directory
again, looking for cover files (`AddLocalArtwork`,
`xbmc/music/infoscanner/MusicInfoScanner.cpp` line 2246 at `e513e0ff`,
called from lines 2125 and 2159). The request carries `DIR_FLAG_READ_CACHE`,
and the directory cache holds fifty listings, dropping the least recently
used (`MAX_CACHED_DIRS`, `xbmc/filesystem/DirectoryCache.cpp` lines 24 and
212–233). So the second request is free while one scan covered a few dozen
directories, and a second full plugin listing of every album once it covered
more. The second request is made whenever the music artwork level takes
any extra art type (`AddLocalArtwork` returns early otherwise, lines
2224–2236).

Observed on 22.0b2 on a Raspberry Pi 3, the same plugin library scanned as
one root and as directories that each list thirty-two album folders:

| Library | One root | Thirty-two album folders to a scan |
|---|---|---|
| 87 album folders, rollback journal | 27.2 s | 20.6 s |
| 87 album folders, WAL | 21.5 s | 12.0 s |
| 1,557 album folders, WAL | 323 s | 293 s |

**The grouping directory needs a parent that lists it.** The scanner decides
whether a directory it was asked to scan exists from the cached listing of
its parent: `CDirectory::Exists` returns what `FileExists` finds there
whenever the parent is in the cache (`xbmc/filesystem/Directory.cpp` lines
383–389), and a directory the cached parent does not name is skipped with
`directory '…' does not exist - skipping scan` (`MusicInfoScanner.cpp` line
145). Kodi caches a parent on its own account — the art pass lists the
common path of an album whose songs span two directories (`AddAlbumArtwork`,
lines 2069–2081). Observed: of three grouping directories placed under the
plugin's music root the first two were scanned and the third was skipped
with that warning; under a parent of their own whose listing names every one
of them, all were scanned. A new album folder scanned by its own name, whose
parent was cached before the album existed, fails the same check (inferred;
not observed).

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
  `AudioLibrary.SetSongDetails` — for the played songs only: `UpdateSong`
  writes `dateAdded` on every call, from `GetMediaDateFromFile`
  (`xbmc/music/MusicDatabase.cpp` lines 1371–1386 at `e513e0ff`), which is
  the current time for a path with no valid modification date (lines
  13859–13881). A setter sent to a song that needed nothing re-stamps it as
  added now.
- **Kodi takes no art from a plugin listing.** `CFileItem::GetUserMusicThumb`
  returns an empty string for `IsPlugin()` paths (`xbmc/FileItem.cpp`), so
  `FindArtForAlbums` finds nothing and `RetrieveLocalArt` lists every added
  album directory a second time after the walk, looking for folder art it
  cannot see (observed: one extra listing per new album, each on a fresh
  interpreter; the section above says when that listing is free). Album and
  artist art go in with `SetAlbumDetails` and `SetArtistDetails`.
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

