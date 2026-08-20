---
name: kodi-plugin-listings
description: >
  Predict what Kodi does with the rows a plugin lists — which playlist a click
  lands on, whether the rest of the listing is queued, and which context entries
  a plugin row can never get. Use when a track from your plugin plays alone
  while the same click in another window queues the album, when an album folder
  has no Play, when a context item you declared shows up on rows it makes no
  sense on, or before adding a "play all" of your own. Covers the `<provides>`
  value that decides the playlist type, the window-dependent auto-queue, and the
  gate that keeps Play off every plugin folder.
license: CC-BY-SA-4.0
metadata:
  category: python-addon
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-20"
  verified-method: observed
---

# What Kodi does with a plugin's rows

A plugin builds ListItems; Kodi decides what a click, a queue and a context menu
do with them, and it decides by the window the listing is shown in and by the
add-on's manifest — not by anything on the row. The same album listing plays one
track from the video window and fourteen from the music window, and no window
offers Play on the album itself. Source references are to the Kodi 21.3 Omega
tree; every observation was made against an add-on declaring
`<provides>video audio</provides>`.

## `<provides>` picks the playlist, and video wins

`CGUIViewStateFromItems` sets the listing's playlist from the add-on's
`<provides>`: `TYPE_MUSIC` if it provides audio, then `TYPE_VIDEO` if it provides
video — the second assignment overwrites the first
(`xbmc/view/GUIViewState.cpp:574-586`). An add-on that declares both therefore
queues **everything** onto the video playlist, songs included, in the music
window too.

Observed: a click on a song in the music window queued the listing's 14 audio
rows onto `playlistid` 1 (video); `Player.GetActivePlayers` answered `playerid`
1 with `type` `audio`, and `Player.GetProperties` on `playerid` 0 failed.
Playback itself is unaffected — PAPlayer plays the rows — so the symptom is
anything that assumes audio lives on playlist 0: a remote app asking player 0, a
script reading `xbmc.PlayList(xbmc.PLAYLIST_MUSIC)`, "Now playing" opening the
video playlist window.

If your add-on builds a queue of its own (below), name the playlist explicitly.

## A click queues the rest of the listing only in the music window

`CGUIMediaWindow::OnClick` asks the **current window's** view state whether to
auto-queue, and for an add-on that provides audio it builds a fresh view state
for the window id rather than using the listing's
(`xbmc/windows/GUIMediaWindow.cpp:1157-1182`):

- Music window: `musicplayer.autoplaynextitem && !musicplayer.queuebydefault`
  (`xbmc/music/GUIViewStateMusic.cpp:36-41`) — on by default, so the click calls
  `OnPlayAndQueueMedia` and queues every non-folder row from the clicked one.
- Video window: `AutoPlayNextVideoItem` maps the container's content onto an
  entry of `videoplayer.autoplaynextitem` (`xbmc/view/GUIViewState.cpp:492-498`);
  content `songs` falls under the "Uncategorized" entry, option value 4
  (`system/settings/settings.xml`, the `videoplayer.autoplaynextitem` options),
  which is off by default — so the click plays the one row.

Observed on one 14-track album listing: video window → a 1-item playlist; music
window → 14 items; video window with `videoplayer.autoplaynextitem` set to `[4]`
→ 14 items.

A user reaches your listing through Videos → Add-ons, a video-window favourite,
or a skin shortcut that activates the Videos window; only Music → Add-ons gives
them the music window. The Kodi-side answers are the Uncategorized tick or
opening from the Music section; the add-on-side answer is a Play all of your
own.

## No window offers Play or Queue on a plugin folder

Kodi's Play, Queue item and Play next context entries are gated on
`IsItemPlayable`, and a plugin **folder** satisfies none of its true branches:
the plugin branch wants a playable non-folder item, and the folder branch is
`m_bIsFolder && !IsPlugin()` (`xbmc/video/VideoUtils.cpp:608-628`,
`xbmc/music/MusicUtils.cpp:934-955`). The music window's own `PlayItem`
likewise builds a playlist only for `!IsPlugin()` folders
(`xbmc/music/windows/GUIWindowMusicBase.cpp:617-651`).

Observed: the context menu on an album row from a plugin listing, in both
windows, was Information / Add to favourites plus the add-on's own context
items. Non-folder rows do get Kodi's entries — Play, Play using…, Play next,
Queue item, and in the video window "Play from here"
(`xbmc/video/windows/GUIWindowVideoBase.cpp:820-831`, on every playable row but
the last).

So an album, artist or playlist row from a plugin has no way to play as a whole
unless the add-on offers one.

## Offering Play all yourself

A `RunPlugin` route that expands the container, builds a playlist and starts it
works from the plugin process:

```python
playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)   # explicit: see the first section
playlist.clear()
for track in tracks:
    playlist.add(plugin_url_for(track), build_listitem(track))
stop_whatever_is_playing_and_wait()             # the bare-plugin:// race, kodi-playback-resume
xbmc.Player().play(playlist)
```

Observed: 14 plugin rows queued onto `playlistid` 0 in the order added, and
playback started on the first, which resolved through the add-on's normal play
route. The entry that reaches the route is a `kodi.context.item` in `addon.xml`,
or a `Dialog().contextmenu` of your own behind one.

## `ListItem.DBTYPE` on a plugin row is the info tag's media type

A context item's `<visible>` cannot read add-on settings, and a property stamped
on every row cannot tell a song from a movie. `ListItem.DBTYPE` can: on a plugin
row it is whatever `setMediaType` put on the video or music info tag.

Observed via `XBMC.GetInfoLabels`: rows built with
`InfoTagVideo.setMediaType("movie")` / `("tvshow")` read `movie` / `tvshow`;
rows with `InfoTagMusic.setMediaType("song")` / `("album")` read `song` /
`album`; a row with no info tag reads `''`. So
`String.IsEqual(ListItem.DBTYPE,movie) | String.IsEqual(ListItem.DBTYPE,episode)`
keeps a video-only entry off music rows and folders, where
`!String.IsEmpty(ListItem.Property(myaddon.id))` had put it on every row.
Square brackets group; parentheses fail the whole expression
([`kodi-addon-manifest`](../kodi-addon-manifest/SKILL.md)).

## What fails silently

- Both `<provides>` values: every queue your listings produce lands on the
  video playlist, with no log line.
- A song click playing alone in the video window: no error, one track, and the
  same click queues in the music window.
- A folder row with no Play entry at all — the user reads it as "this add-on
  cannot play albums".
- A context item declared on a row property showing up on rows it makes no
  sense on, because every row carries the property.

## Verifying it

After clicking a song row in each window, three JSON-RPC calls answer the first
two sections:

```
Player.GetActivePlayers
Playlist.GetItems  {"playlistid": 0}    # music
Playlist.GetItems  {"playlistid": 1}    # video
```

The playlist that holds the rows, and whether it holds one or all of them, is
the whole story.

## Open questions

- Piers (22) was not re-run; the source sites above are from the Omega tree and
  were not compared against Piers.
- Whether queuing audio onto the video playlist has consequences beyond the
  player id — party mode, crossfade, "play next song automatically" — was not
  tested.

## See also

- [`kodi-playback-resume`](../kodi-playback-resume/SKILL.md) — the
  stop-before-`PlayMedia` race a self-built queue has to respect, and what Kodi
  remembers about a plugin row's resume point
- [`kodi-plugin-handles`](../kodi-plugin-handles/SKILL.md) — a `RunPlugin`
  route that plays must still close its handle
- [`kodi-addon-manifest`](../kodi-addon-manifest/SKILL.md) — `<provides>` and
  context-item `<visible>` syntax
