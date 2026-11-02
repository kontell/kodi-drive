---
name: kodi-performance
description: >
  Make a Kodi add-on fast on the hardware people actually run it on. Use when
  something is slow on a TV box or stick but fine on your desktop, when a widget
  or listing lags, or before assuming a desktop measurement generalises. Covers
  the ~170x Python gap between a desktop and an ARM SoC, head-of-line blocking
  between unrelated work, and the import and API calls that cost whole seconds.
license: CC-BY-SA-4.0
metadata:
  category: diagnosis
  verified-kodi: "23.0-ALPHA1, 22.0-RC1 Piers, 22.0b2 Piers, 22.0-BETA1 Piers, 21.3 Omega"
  verified-platform: "Android TV, Linux x86_64, Linux armv7 (LibreELEC)"
  verified-date: "2026-10-29"
  verified-method: "observed"
---

# Performance on real Kodi hardware

Most Kodi runs on an underpowered ARM box plugged into a television. Your desktop
is not a useful proxy for it, and the gap is far larger than intuition suggests.

## Measure the gap before trusting any desktop number

Identical Python work, same code, same database file, desktop versus an Android
TV box:

| Work | Desktop | Android TV box | Ratio |
|---|---|---|---|
| Digest 22,917 rows | 0.090 s | **15.3 s** | ~170x |
| Digest 6,751 rows | 0.039 s | **6.4 s** | ~164x |

That is not I/O and not lock contention — it was confirmed to be real query,
sort and hash work in the Python layer. **A 130 ms desktop operation becomes a
22 second one.**

Any design decision that reasons about "how long this takes" needs the ARM
number, not the desktop number. Several perfectly sound decisions in the case
above were sound *only* at desktop speed.

## The work is rarely where you think

In one investigation, new content took 30.8 seconds to appear in a widget. The
breakdown:

| Stage | Time |
|---|---|
| Deciding whether to refresh | **21.7 s** |
| The refresh itself | **12 ms** |

Nothing was broken, nothing was suppressed, and the data was correct the whole
time. **The cost was asking the question, not doing the work.**

This is why an end-to-end duration is a single reading that fits every theory.
Take intermediate timestamps — see [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md).

## Head-of-line blocking between unrelated work

In the same case, 15.3 s of the 21.7 s was fingerprinting the **music** library,
which had nothing to do with the movie that had just been added. Two ordinary
decisions combined to cause it:

1. The loop iterated `sorted(databases)`, and `"music"` sorts before `"video"`.
2. Nothing was issued until the loop had a verdict for **every** candidate.

So the movie's refresh queued behind a full scan of an unrelated library. Without
music playing it would have completed 16 seconds sooner.

**Emit each result as soon as it is known**, rather than after the whole batch.
And where there is an obvious candidate — the thing that actually changed —
process it first.

## A fast path that declines is still a decision

The same system had a fast path designed to make new content visible
immediately. It early-returned, reasoning that the full refresh was "moments
away, and each refresh costs a scan".

That reasoning is correct at 130 ms. At 22 seconds it is wrong, and the fast
path silently never fires. **Any threshold reasoning of the form "the slow path
is nearly here" has to be evaluated at ARM speed.**

## A Monitor nobody waits on taxes every Python thread in Kodi

Kodi queues one callback for every announcement on **every `xbmc.Monitor`
object alive**, in a single queue for the whole process (`g_callQueue`,
`xbmc/interfaces/legacy/CallbackHandler.cpp` lines 36–43 at `e513e0ff`). A
callback leaves the queue only when the thread that created its Monitor runs
`makePendingCalls`, and the two places that call it are `Monitor.waitForAbort`
and `xbmc.sleep` (`xbmc/interfaces/legacy/Monitor.cpp` lines 39–60,
`ModuleXbmc.cpp` lines 152–166). `abortRequested()` reads an event and takes
nothing off (`Monitor.cpp` lines 62–66). `makePendingCalls` walks the queue
from the front, steps over every entry that belongs to another thread
(`isStateOk`, `xbmc/interfaces/python/CallbackHandler.cpp` lines 33–45) and
goes back to the front after each callback it runs (`CallbackHandler.cpp`
lines 64–122).

So a thread that constructs a Monitor and then blocks somewhere else — a
websocket's `run_forever`, a long HTTP read, a `queue.get()` — leaves its
callbacks queued for as long as it blocks, and every other Python thread in
Kodi, in every add-on, walks past all of them on each 100 ms slice of its own
wait. During a library import that is one callback per row written.

Observed on 22.0b2 on a Raspberry Pi 3, importing 22,381 songs from a plugin
while a websocket thread of the same add-on held such a Monitor: the scan
fell from 72 songs a second to 13 in seven minutes and was still falling when
it was stopped, one plugin listing took 139 ms in the first minute and 800 ms
in the eighth, and six `LanguageInvoker` threads used 9–23 % of a core each
throughout. With the Monitor made only for that thread's own waits, the same
library scanned in 323 s and never slower than 60 songs a second, a listing
took 32–40 ms from the first minute to the last, and one `LanguageInvoker`
thread was busy: the plugin's own.

**A library removal is the worst burst.** Kodi announces `VideoLibrary.OnRemove`
for every row it deletes, also when one call removes a whole source
(`VideoLibrary.SetSourceContent`, `clearmode: "remove"`). The queue is a
`std::vector`, each callback taken off is an `erase`, and the thread delivering
announcements needs the same lock to add one (`CallbackHandler.cpp` lines 32,
38–43, 78), so a drain costs the square of what is queued.

Observed on 22.0b2 on a 32-bit Android TV, several add-ons' services running,
when one cleared a source of 4,751 rows with that call. Ten seconds in, every
Python thread in Kodi stopped, in every add-on; the main thread, a binary PVR
add-on and key handling carried on. A `waitForAbort(3)` on the clearing thread
returned after 47 s. A plugin invocation created to resolve the next music
track reached its add-on's code 2 min 45 s later, behind a busy dialog, and
the track failed to open. A service working through 5,632 requests without waiting on its
Monitor fell from 55 a second to about one, and was still there three minutes
after the clear ended. At quit, four add-ons' services outlasted Kodi's five
seconds and were killed. A clear that size on an x86_64 desktop took 11 s.

- Make a Monitor on the thread that will wait on it, for the wait:
  `xbmc.Monitor().waitForAbort(n)` is a complete reconnect delay.
- A thread that keeps one while it works has to take its callbacks off:
  `monitor.waitForAbort(0.001)` between batches. **`waitForAbort(0)` waits for
  ever** — a timeout of zero or less is infinite (`Monitor.cpp` lines 44–45).
- A thread that only polls `abortRequested()` needs no Monitor of its own.
- Your own writes do it to you: a burst of JSON-RPC setters from a thread
  that does not wait in between queues a callback per setter on that
  thread's Monitor.
- A service's long loop waits on its Monitor too, whatever the loop is doing.
  It is the add-on that is not waiting whose callbacks every other add-on
  walks past, and under the starvation that follows its loop only gets longer.

## A large file write stalls all of Kodi through its log

Kodi writes its log synchronously, on whichever thread logs. Every logger feeds
one `dist_sink_mt`, which takes a mutex, and `flush_on(spdlog::level::debug)`
flushes each record at debug level or above as it is written
(`xbmc/utils/log.cpp` lines 89 and 102, the same on master `7b12e7be16` and Piers
`d4c425ce7b`). So when a `write()` to `kodi.log` blocks on storage, every thread
that logs waits on that mutex. With debug logging on, that is effectively the
whole process, the app thread included.

An add-on writing a large file can make storage block it. The kernel lets a
writer fill the page cache at network speed up to its dirty limit, then holds
every writer to the storage's speed while it drains. Observed on an Android TV
(Kodi 23.0-ALPHA1, ARM 32-bit, debug logging on): an add-on downloading 379 MB
at about 40 MB/s over Wi-Fi, to flash that sustains 8–11 MB/s, held about
120 MB dirty (`Dirty` in `/proc/meminfo`). The app thread's round trip (see
[How to measure it properly](#how-to-measure-it-properly)) reached 1.9–8.8 s
across four runs, against 35 ms idle, and during the 8.8 s stall no thread
logged a line for 10 s.

**Write the file through yourself, a window at a time.** Call
`os.fdatasync(fd)` every few MiB, then
`os.posix_fadvise(fd, offset, length, os.POSIX_FADV_DONTNEED)` for that window,
so the dirty pages never exceed one window. With 8 MiB windows the worst stall
fell to 0.3–2.7 s over four runs. It does not fall further, because the flash
takes about 2 s over roughly one sync in four, and every Kodi write queues
behind that sync.

**Then rest after a slow sync.** When a sync took longer than its window took
to arrive, storage is the slower side, so sleep as long as the sync took. That
brought the worst stall to 0.6–1.0 s over two runs, at about 15 % off the
download's speed. The rule costs fast storage nothing:

| Device | Sync vs window | Rested | 1.2 GB download |
|---|---|---|---|
| Linux x86_64, NVMe (22.0-RC1 Flatpak), 50 MB/s | 0.07 s vs 0.13 s | never | 21–28 s, against 24.5 s unsynced |
| Raspberry Pi 3 (LibreELEC, 22.0b2), 2 MB/s | network is slower | never | no change |

Resting as long as every sync took, slow or not, did better on the TV, but it
cost the NVMe desktop up to 40 %: 70 ms on each of 144 windows.

`sync_file_range()` does not replace `fdatasync` on Android. Called through
`ctypes` it returned 0 and dirty pages still climbed to 110 MB. The files were
under `Android/data`, which Android 14 serves through FUSE passthrough, so the
cause is inferred: the range call reaches the FUSE file and not the backing
file. `fdatasync` does reach it.

Run-to-run variance is large. The unsynced download's worst stall ranged from
0.2 s to 8.8 s on the same file, so alternate the variants and compare several
runs of each.

## Specific costs worth knowing

**`import requests` costs 1.11 s on Kodi 21 and 0.93 s on Kodi 22** inside Kodi's
embedded Python. Bytecode caching does not help — the cost is executing the
package's module bodies, and `.pyc` files were present on both. By comparison
`http.client`, `ssl`, `json` and `urllib` cost 0.000 s.

Keep `requests` in long-lived processes — a service, a sync stack — where the
import is paid once. **In the short-lived plugin process, use the stdlib.**

**`xbmcaddon.Addon()` costs ~2.9 ms.** Constructing one per list item accounted
for ~5 s of a 15 s listing. Build one and pass it, or read what you need once.

**On armv7 the same `xbmcaddon.Addon()` is about 20 ms.** Two settings reads
per item, each constructing one, turned a 14 s plugin listing of 1,788 movies
into 80 s on a 1 GB LibreELEC box (22.0b2); the figure is inferred from that
difference, not timed in isolation. Memoise a setting for the length of a
listing.

**A plugin's Python heap is Kodi's heap, and the kernel pays for it.** Every
interpreter an add-on runs lives inside `kodi.bin`: with its music scan
stopped and the add-on disabled, a 1 GB box's Kodi fell from 595 MB to
235 MB resident. Anything over 512 bytes CPython allocates is malloc'd and
glibc keeps the block after it is freed, so a heap that grew for an
enumeration stays grown; `ctypes.CDLL("libc.so.6").malloc_trim(0)` after
the big phase hands it back on glibc builds (applied, not isolated). Measured
on x86_64: 6,616 Jellyfin item payloads are 58 MB of JSON and 200 MB of
Python objects; a listing that loaded 1,788 of them grew Kodi by 100 MB in a
minute. Once the page cache is squeezed, every cold interpreter and every
fresh SQLite connection reads evicted pages off the card: on that box a
fresh connection's first statement took 13–24 s (5.6 s even with
`immutable=1`), the device read 15 MB/s continuously, one album listing of
a dozen songs took 45–67 s with the CPU idle, and ssh accepted the TCP
connection but never reached the banner until the box was power-cycled.
Stream payloads, keep one connection per interpreter, and watch
`MemAvailable` — it counts the cache being thrashed.

**Kodi's library databases are rollback journals, and every write waits on
the card for it.** On a connection Kodi sets a cache size,
`synchronous='NORMAL'` and nothing about the journal
(`xbmc/dbwrappers/sqlitedataset.cpp` line 421 at `e513e0ff`), so a database
Kodi created stays in SQLite's default `delete` mode and one a tool switched
to WAL stays WAL — the mode is stored in the file. In `delete` mode every
autocommit statement of a JSON-RPC setter, and every item a scanner commits,
is a journal file written, synced and removed. Observed on a Raspberry Pi 3
with its databases on an SD card (22.0b2, a library of 1,353 songs; 82, 21
and 6 calls):

| Call | `delete` | WAL |
|---|---|---|
| `AudioLibrary.SetAlbumDetails` | 57 ms | 16 ms |
| `AudioLibrary.SetArtistDetails` | 148 ms | 14 ms |
| `AudioLibrary.SetSongDetails` | 133 ms | 17 ms |

With 22,381 songs in the library the same three calls cost 93, 163 and
288 ms in `delete` mode against 54, 28 and 47 ms in WAL.

An add-on that may not open Kodi's databases cannot change the mode; one
that may, changes it once with Kodi's library idle. A writer that finds the
database locked sleeps 100 ms before it asks again (`busy_callback`,
`sqlitedataset.cpp` lines 205–209), so two writers on one database queue in
tenths of a second.

**Kodi's video scanner looks every name up with a table scan.** `AddActor`
runs `select actor_id from actor where name like '<name>'` for each cast
member, director and writer (`xbmc/video/VideoDatabase.cpp` line 1595), and
`AddToTable` the same statement for each tag, studio, genre and country
(line 1352). Each of those tables has a unique index on `name`
(`xbmc/video/VideoDatabaseDDL.cpp` lines 199–202, 286 and 635–639), but it
is a BINARY one and LIKE ignores case, so SQLite cannot use it for the
lookup: `EXPLAIN QUERY PLAN` reports `SCAN` for all of them and each lookup
costs as much as the table has rows. Observed on
the Pi 3, Kodi's statements against a library of 1,788 movies and 4,300
episodes: 28.2 ms a lookup on `actor` (38,284 rows), 6.1 ms on `tag` (8,140),
2.3 ms on `studio` (2,443). With an index on `name COLLATE NOCASE` beside
Kodi's own the same statements took 0.15–0.21 ms and returned the same rows.
What a plugin lists decides how many lookups an item makes: one per cast
member and one per tag.

The same rows, not the same order. Kodi takes the first row of that lookup
with no `ORDER BY`, and where two rows differ by case alone the index
changes which one that is: scanning its BINARY index Kodi meets the spelling
that sorts first (capitals before lower case), searching a NOCASE one it
meets the row with the lowest id. Kodi's own lookup never creates such a
pair, since it finds the existing spelling; another writer can. Observed
with `jean reno`, `Jean Reno` and `JEAN RENO` inserted in that order on a
MyVideos149 schema: the first `actor_id` returned went from the capitals'
row to the lower-case one.

**A season read is a listing of the show's seasons.**
`VideoLibrary.GetSeasonDetails` calls `GetSeasonInfo`, which runs
`GetSeasonsNav` for the whole show and picks one row out of it
(`xbmc/video/VideoDatabase.cpp` lines 2090–2126 at `e513e0ff`), and
`SetSeasonDetails` reads the season the same way before it writes
(`xbmc/interfaces/json-rpc/VideoLibrary.cpp` line 733). Observed on a
Raspberry Pi 3 with 4,300 episodes in the library: 79 ms a
`GetSeasonDetails`, 79 ms for one `GetSeasons` of the same show with the same
properties, and 120 ms a `SetSeasonDetails` whether the database was in
`delete` or WAL mode. Episodes are cheaper but the shape is the same:
50 ms a `GetEpisodeDetails`, 64 ms for six episodes of one show in one
`GetEpisodes`. Read a show's rows with the listing, and do not send a
season a setter for what the scanner can file with the show (season names
through `addSeason`, season art through `addAvailableArtwork` with
`season=`).

**Full-scan-and-hash in Python does not scale.** Where a gate needs a fingerprint
of a library, compute it in SQL as an aggregate, or maintain a checksum on write.
Materialising rows into Python tuples, sorting, `repr`-ing and hashing them is
O(library) per decision, and on ARM that is seconds every time.

## How to measure it properly

Take the measurement on the slow device, not on your desktop, and take
intermediates:

```sh
kodi-logtail mark
# trigger the operation
kodi-logtail since | grep -E 'your-addon-prefix'
```

Add a log line at each stage boundary in the code you are timing. Three
timestamps beat two, because two only tell you that time passed.

For time inside Kodi's own database code, switch the `database` log
component on for a minute. `Settings.SetSettingValue` with
`debug.setextraloglevel` = `[131072]` and `debug.extralogging` = `true` takes
effect at once over JSON-RPC (`xbmc/utils/log.cpp` lines 116–128 at
`e513e0ff`), so a running scan can be sampled and the component switched off
again. Two things about what it prints decide how to read it
(`xbmc/dbwrappers/sqlitedataset.cpp`): `N ms for query: …` is logged for
statements run through `exec` — the writes — and not for `query` (lines
843–898 against 936), so a SELECT's cost is the gap before the next line of
that thread; and `Sqlite commit transaction` is logged after the commit
returns (lines 610–616), so a commit's cost is the gap *before* that line.
Group the lines by thread id first: the texture cache's worker logs into the
same stream.

To measure how long the UI thread takes to answer, time `XBMC.GetInfoLabels`
over JSON-RPC. It is sent to the app thread with
`SendMsg(TMSG_GUI_INFOLABEL, …)` and waits for the answer
(`xbmc/interfaces/json-rpc/XBMCOperations.cpp` line 33). `JSONRPC.Ping` stays
on the webserver thread, so the difference between the two is the app thread's
share; [`kodi-profiles`](../kodi-profiles/SKILL.md) uses the same pair as a
liveness check. `Input.ExecuteAction` measures nothing: it posts the action and returns
at once (`InputOperations.cpp` lines 39 and 54, `waitResult` defaults to
`false`).

```sh
curl -s -o /dev/null -w '%{time_total}\n' -u "$KODI_USER:$KODI_PASS" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"XBMC.GetInfoLabels","params":{"labels":["System.FPS"]}}' \
  http://localhost:<KODI_PORT>/jsonrpc
```

Run it on the device, against `localhost`. From another machine the round trip
also carries the network queue, and a download fills exactly that queue. An
Android TV shell has no `curl`, but it has `nc` and `$EPOCHREALTIME`, which is
enough to send the request and time it.

For process-level cost, see
[`kodi-process-control`](../kodi-process-control/SKILL.md) — and note that
sampling the wrong process reports a plausible ~1 MB, and Kodi's own footprint
dominates any absolute figure, so measure add-on cost as a delta.

## What fails silently

- A desktop benchmark passes and the feature is unusable on the target hardware.
- A fast path early-returns on reasoning that was true in development.
- Work queues behind unrelated work because of an incidental sort order.
- Nothing errors, nothing is logged, and the feature merely feels slow.
- A Monitor held by a blocked thread slows every add-on's threads, and nothing
  names the add-on that holds it.
- A large file write stalls every thread that logs, and nothing names the
  add-on that is writing.

## Open questions

- The ~170x figure comes from one ARM SoC in a TV. Other Android TV hardware,
  and a Raspberry Pi, have not been measured — the order of magnitude is the
  useful part, not the exact number.
- Whether the Python gap is dominated by CPU, memory bandwidth, or Kodi's
  embedded interpreter build has not been isolated.

## See also

- [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) — timing stages instead of theorising
- [`kodi-process-control`](../kodi-process-control/SKILL.md) — measuring memory
  and CPU without measuring the wrapper
- [`kodi-test-rig`](../kodi-test-rig/SKILL.md) — getting the slow device to test on
