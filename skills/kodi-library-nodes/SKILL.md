---
name: kodi-library-nodes
description: >
  Profile library nodes replace Kodi's shipped ones and are never merged. Use
  when the music or video home categories widget is missing Genres, Artists,
  Albums and the other defaults on every skin, when an add-on writes
  library:// nodes, or when library://music/ or library://video/ lists only
  custom folders.
license: CC-BY-SA-4.0
metadata:
  category: kodi-data
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-14"
  verified-method: observed
---

# Profile library nodes hide the shipped ones

If `special://profile/library/music/` exists, that folder **is** `library://music/`.
The shipped tree under `special://xbmc/system/library/music/` is not consulted.
Same rule for `video`. There is no merge and no log line.

Estuary and every Estuary-derived skin feed the music home categories widget from
`library://music/`. So a profile music folder that contains only an add-on
subdirectory presents as a **skin** bug — missing Genres, Artists, Albums, Songs,
Years, and the rest — on every skin at once. Widgets that go to `musicdb://`
directly (recently played, recently added) keep working, because they never
touch the node tree.

The wiki already says to copy the whole shipped tree before adding a custom
node. This skill is the other half: what it looks like when something creates
the profile folder and does not.

## `GetNode` picks one tree

`CLibraryDirectory::GetNode` (`xbmc/filesystem/LibraryDirectory.cpp`, same
shape on 21.3 and current master):

```cpp
std::string libDir = URIUtils::AddFileToFolder(
    m_profileManager->GetLibraryFolder(), url.GetHostName() + "/");
if (!CDirectory::Exists(libDir))
  libDir = URIUtils::AddFileToFolder(
      "special://xbmc/system/library/", url.GetHostName() + "/");
```

`GetLibraryFolder()` is `special://profile/library` when the profile has its
own databases (`CProfileManager::GetLibraryFolder`). `url.GetHostName()` is
`music` or `video`.

Creating `special://profile/library/music/<anything>/` is enough. Kodi does
not require an `index.xml` at the music root. The directory's existence is the
switch.

Music and video are independent. A profile that already holds a full copy of
`system/library/video/` still shows Movies, TV shows, Files, Playlists. The
same profile's `library/music/` can contain a single add-on folder and hide
every shipped music node.

## Diagnose it

```sh
kodi-remote get Files.GetDirectory '{"directory":"library://music/"}'
kodi-remote get Files.GetDirectory '{"directory":"library://video/"}'
```

The listing is the widget. On 21.3 a profile whose music tree held only one
add-on folder returned that one item; the same box's video tree, which still
had the shipped nodes plus the same add-on folder, returned Movies, the add-on
folder, TV shows, Files, Playlists, and Video add-ons.

Then look at the two disks:

```
special://profile/library/music/     what library://music/ actually is
special://xbmc/system/library/music/ what it would be if the profile folder
                                     did not exist
```

If the profile folder exists and is missing `genres.xml`, `artists.xml`,
`albums.xml`, `songs.xml` and the rest, the widget is not broken. Those files
are unused.

A path whose node file is not in the **active** tree fails JSON-RPC
(`Invalid params.`), even when the same filename still exists under
`system/library/`. Observed: `library://music/genres.xml/` after the profile
tree had no `genres.xml`.

## If you write nodes

Seed the shipped tree first, **per media kind**, then write your own folder
inside it. Copy only files that are not already there — the user's node-editor
changes live in the same tree.

```sh
# translate the two special:// paths, then:
cp -an "$SYSTEM/library/music/." "$PROFILE/library/music/"
cp -an "$SYSTEM/library/video/." "$PROFILE/library/video/"
```

Do both. Seeding only video is how you get a Movies row that still has Genres
and a Music row that does not.

Node XML syntax, visibility, and ordering belong on the wiki:
[Video nodes](https://kodi.wiki/view/Video_nodes),
[Music nodes](https://kodi.wiki/view/Music_nodes).

## Repair a profile that already lost the defaults

The same copy. `-n` keeps the custom folder.

`ReloadSkin()` is enough for the home widget to re-read `library://`. No Kodi
restart.

## What fails silently

- Creating `special://profile/library/music/` hides every shipped music node.
  Nothing is logged.
- The same add-on writing `library/video/<id>/` after a video seed, and
  `library/music/<id>/` with no music seed, looks like a music-only skin bug.
- `library://` listings that are missing defaults agree with the widget, so a
  screenshot of "the skin is wrong" is consistent with a node-tree problem.
- A `library://…/genres.xml/` path against a tree that has no `genres.xml`
  returns `Invalid params.`, not the system file.

## Verifying it

```sh
kodi-remote get Files.GetDirectory '{"directory":"library://music/"}'
```

If the result is not the shipped set (Genres, Artists, Albums, Singles, Songs,
Years, Top 100, …) plus any custom folders, list
`special://profile/library/music/` before editing a skin.

## Open questions

- `kodi-addon-driving` records `Files.GetDirectory` returning 0 items for some
  `library://` paths that still rendered in the UI. Root listings of
  `library://music/` and `library://video/`, and a filter node that existed in
  the active video tree (`library://video/movies/genres.xml/`), returned items
  here. The 0-item case has not been re-found.
- Whether a profile with `hasDatabases() == false` still isolates
  `library/music/` under the master profile has not been checked; the
  `GetLibraryFolder` fallback is `GetUserDataFolder()/library`.

## See also

- [`kodi-library-data`](../kodi-library-data/SKILL.md) — the SQLite libraries
  behind `musicdb://` / `videodb://`, which this tree does not touch
- [`kodi-addon-driving`](../kodi-addon-driving/SKILL.md) — firing a node path
  with `GUI.ActivateWindow`
- [`kodi-plugin-handles`](../kodi-plugin-handles/SKILL.md) — a node whose
  `<path>` is a plugin directory must close its handle
- [Kodi wiki: Video nodes](https://kodi.wiki/view/Video_nodes) — authoring,
  including why the whole shipped tree has to be copied
- [Kodi wiki: Music nodes](https://kodi.wiki/view/Music_nodes)
