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
  verified-date: "2026-10-08"
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

- A `.db` copied without its `-wal` reads as a complete but older database.
- A hardcoded schema-numbered filename simply does not exist on another Kodi
  version; a script that does not check reports an empty library.
- Clean Library removes rows with no warning specific to add-on content, and the
  loss is only visible later, as absence. With the add-on disabled the only
  trace is `Unable to find plugin` at error level, repeat-collapsed.

## Open questions

- Whether Clean Library's behaviour differs for music added from a `plugin://`
  source has not been tested — only video was observed. The Omega run removed
  movies and kept episodes; the files loop treats every media type alike and
  keys the `<medialibraryscanpath>` lookup on the row's scraper content
  (sourced, above), so the asymmetry has to come from what that add-on declared
  or answered per content type (inferred). Its declarations at the time were not
  recorded.
- Whether Kodi holds any add-on enablement state in memory for non-active
  profiles, which would delay or defeat a direct `Addons33.db` edit, is untested.

## See also

- [`kodi-profiles`](../kodi-profiles/SKILL.md) — per-profile scope and its traps
- [`kodi-process-control`](../kodi-process-control/SKILL.md) — stopping Kodi
  cleanly before reading its databases
- [`kodi-library-nodes`](../kodi-library-nodes/SKILL.md) — the `library://`
  XML trees, which are not these databases
