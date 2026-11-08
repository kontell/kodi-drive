---
name: jellyfin-client
description: >
  Write a Kodi add-on that talks to a Jellyfin or Emby server without losing sync
  state or playing the wrong stream. Use when building or debugging a Jellyfin
  client, when watched state diverges between server and client, when transcoding
  picks the wrong codec, or when a sync misses items. Covers why Etags cannot
  detect userdata changes at all, and the event fan-out that subscribes you to
  another household member's history.
license: CC-BY-SA-4.0
metadata:
  category: adjacent
  verified-kodi: "21.3 Omega, 22.0b1 Piers, 22.0b2 Piers, 22.0-RC1 Piers"
  verified-platform: "Linux x86_64, Android TV, Android phone/tablet"
  verified-date: "2026-11-07"
  verified-method: "observed"
---

# Jellyfin as a Kodi client

Not Kodi knowledge, but three separate Kodi add-ons needed it, and it is the kind
of thing that is otherwise rediscovered from scratch each time.

## Etags cover metadata, not userdata

**This is the one that quietly breaks incremental sync.**

`BaseItem.GetEtag` hashes `DateLastSaved.Ticks`. It accepts a `user` argument that
the base implementation **ignores**.

Proven twice: the same item, for two users with different resume points, returns
an **identical Etag**; and a userdata write does not move it.

So an Etag-gated incremental sync **never re-reads a diverged item's userdata**,
and a wrong value is permanent until a full re-sync. If your sync is Etag-gated,
userdata needs a separate path — do not assume the gate covers it.

## Userdata can change without anything being written

Worse than the above, and harder to defend against.

**Userdata is keyed by provider id**, so a re-added item silently inherits the
previous incarnation's row. No `UserDataSaved`, no websocket message, no change
feed entry — because from the server's perspective nothing was written.

Sampling found **164 of 300 movies** carrying provider-keyed userdata, so the
at-risk population is large even though the trigger is rare.

A userdata-aware checksum does **not** fix this: a silently-inherited item
appears in no response you could compare against.

## `UserDataChanged` reaches sessions containing the user

`SessionInfo.ContainsUser` counts `AdditionalUsers`. So "Add user" on your box
subscribes it to that person's **entire userdata stream, server-wide**.

Present in stock `jellyfin-kodi` since September 2018.

Filter on the message's own `UserId`, with two details that matter:

- **Compare dashless and case-insensitively.** Jellyfin emits GUIDs both ways.
- **Apply when the subject is absent**, rather than dropping. Otherwise you
  silently stop syncing userdata against any server that omits the field.

## Planting another user's userdata, and the echo it sends

From an admin session, `POST /UserItems/{id}/UserData?userId=<user>` with a
partial `UpdateUserItemDataDto` (`{"PlaybackPositionTicks": 3232605000}`)
sets that user's userdata and answers the stored row; `POST` /
`DELETE /UserFavoriteItems/{id}?userId=<user>` flips the favourite. Both fire
`UserDataChanged` to the user's sessions within a second or two. The message
**fires again for an identical body** — re-sending the same ticks produced the
same event and the client wrote the same values — so a client's own
"did anything move" check has to live client-side; the server does not dedupe
(12.0.0).

## A virtual-folder rename is a new library, and the old one lingers

`POST /Library/VirtualFolders/Name?name=A&newName=B` does not rename the view a
client knows: library ids are derived from the path, so `B` arrives as a **new
id** while the old one stays in `/UserViews` — for minutes even with
`refreshLibrary=true`, and a library *deleted* hours earlier was still listed
the same way. `POST /Library/Refresh` and polling `/UserViews` until the stale
entry drops is what settles it (about six seconds on a small instance). A
client that mirrors views by id sees no rename at all, only an addition it did
not ask for and, later, a removal (12.0.0).

Inferred from the same instance, and labelled as such: an empty Collections
library is absent from `/UserViews` and appears there once its first collection
exists (`POST /Collections`), shifting the order of everything after it.

## `PlayCount` is not the watched flag

`PlayCount` **survives being marked unwatched**. `Played` is the state; `PlayCount`
only sizes it.

Reading `PlayCount` first re-watched 103 of 1771 movies in dynamic listings.

## A play is counted when it starts, and a short item is played at any stop

`OnPlaybackStart` increments `PlayCount` and stamps `LastPlayedDate`, and it
marks the item `Played` there and then when the item supports the played flag
but not a resume position, which is a song
(`Emby.Server.Implementations/Session/SessionManager.cs` lines 841–853 at
v12.0-rc6; `Audio.SupportsPlayedStatus` is true and
`BaseItem.SupportsPositionTicksResume` defaults to false). Observed on
12.2.0: an unplayed song stopped three seconds in read back `Played: true`,
`PlayCount: 1`. A client that counts a play only at the end of a track
disagrees with the server by design; send the server `Played`, never a count
of your own.

At a stop, `UpdatePlayState` decides from the position reported
(`Emby.Server.Implementations/Library/UserDataManager.cs` lines 439–512): under
`MinResumePct` (5) the position is dropped; over `MaxResumePct` (90), or within
a second of the end, the item is played; and **in between, an item shorter
than `MinResumeDurationSeconds` (300) is marked played too**, with no resume
point (defaults in `MediaBrowser.Model/Configuration/ServerConfiguration.cs`
lines 133–145). Test media meant to hold a resume point therefore has to run
five minutes or more. A stop reported with no position at all increments
`PlayCount` a second time (`OnPlaybackStopped`, `SessionManager.cs` lines
1162–1184).

Nothing in a playback report clears `Played` on a video; `UpdatePlayState`
sets it false only for an item without the played flag (line 502). So **a
watched video that is played again and stopped partway stays `Played: true`
and gains a resume position.** Only an explicit write clears the flag:
`DELETE /UserPlayedItems/{itemId}`, which also zeroes `PlayCount` and the
position (`ResetPlayedState`, `MediaBrowser.Controller/Entities/BaseItem.cs`
lines 2233–2241), or `POST /UserItems/{itemId}/UserData` carrying
`Played: false`. This is new in 12.0: on 10.11, `OnPlaybackStart` set
`Played = false` on every item that holds a resume position
(`SessionManager.cs` lines 821–828 at v10.11.11), so the same re-watch read
back unplayed. jellyfin/jellyfin#15762 removed that branch, first shipping in
v12.0-rc1. Kodi shows the difference in the context menu, which offers
**Mark as watched** only at a play count of 0 (`CVideoMarkWatched::IsVisible`,
`xbmc/video/ContextMenus.cpp` line 123 at 21.3-Omega, line 125 at
22.0b1-Piers). A client that maps `Played` to the play count therefore offers
**Mark as unwatched** and **Reset resume position** for that item on 12.0,
where 10.11 offered **Mark as watched**.

## DirectPlayProfile and TranscodingProfile answer different questions

A `DirectPlayProfile`'s codec list says what you can play as-is. A
`TranscodingProfile`'s says what you can *receive*.

Jellyfin reads a source codec appearing in the **transcoding** list as a
passthrough candidate and then discards the alternatives — `audioCodecs` becomes
`[audioStream.Codec]`. So listing E-AC3 there pins output to eac3 with no
fallback, and once a bitrate cap makes that copy non-viable, **Jellyfin 10.11
answers HTTP 400 with an ArgumentNullException and never starts ffmpeg**.

**Name the encode target, not the decode list.**

A related consequence worth knowing: emitting two transcoding profiles (say fMP4
for AV1, TS for everything else) means the server selects by codec-copy
compatibility — so "preferred codec = AV1" only yields AV1 when the *source* is
already AV1. That is Jellyfin's design, not a bug.

## `GetAudioEncoder` null-derefs when the server elects to stream-copy audio

**A server-side crash you trigger by asking for the codec you already have.**

`EncodingHelper.GetAudioEncoder` (`EncodingHelper.cs:746-753` in 10.11.10) matches a
regex against `state.OutputAudioCodec` **with no null guard** — unlike
`GetVideoEncoder` at line 468, which does guard. When the server decides to
**stream-copy** the audio, `OutputAudioCodec` is null, `IsMatch(null)` throws
`ArgumentNullException`, and the request returns **HTTP 400 "Error processing
request."**

You reach it by sending `AudioCodec=<the source codec>`: source equals target, so
the server picks a copy, and the copy path is the one that crashes.

It is easy to hit on live TV because **channel metadata is declared, not probed**
(`Live tv media info probe took 0.0001s`). A channel declaring E-AC3 5.1 while
actually carrying stereo AAC will still make the client ask for `eac3`.

Three fixes, each independently verified to turn 400 into 200:

| | |
|---|---|
| `AudioCodec=copy` | explicit copy |
| `AudioCodec=aac` | force a re-encode |
| `TranscodingMaxAudioChannels=2` | channel count over the limit forces a re-encode |

The durable shape: keep `eac3`/`ac3` in your **DirectPlayProfiles** so passthrough
still works, and leave them out of the **TranscodingProfile** audio list so the
transcode target is never the source codec.

## `ReadAtNativeFramerate` is snapshotted at stream open

`MediaSourceInfo.ReadAtNativeFramerate` puts `-re` on the remux ffmpeg, which
paces output to realtime — so the first HLS segment takes a full segment-duration
to appear. Measured: `live.m3u8` blocking **4.83 s** per channel change, dropping
to **1.53 s** with it off.

**The trap is the caching, not the setting.** The value is snapshotted when the
shared stream opens and persists until the consumer count reaches zero, so
**changing the tuner setting does not affect an already-open stream**. Two A/B runs
falsely showed no difference before that was understood.

Related, and worth checking if you see this: **every
`PlaybackInfo(AutoOpenLiveStream)` adds a consumer**, and three things take one
back: a correctly-formed `POST /LiveStreams/Close?liveStreamId=X`, a Stopped report
that names the `LiveStreamId`, and the idle kill of a transcode (next section). A
client that never closes leaks them — one observed stream reached 7 consumers and
stayed alive 5 hours after playback stopped.

## A transcode's idle kill closes its live stream

An HLS transcoding job that no request has pinged for 60 s is killed by its timer,
and that kill closes the job's live stream: `OnTranscodeKillTimerStopped` calls
`KillTranscodingJob(job, true, …)`, whose `closeLiveStream` branch calls
`CloseLiveStreamIfNeededAsync(job.LiveStreamId, job.PlaySessionId)`
(`MediaBrowser.MediaEncoding/Transcoding/TranscodeManager.cs`, `PingTimer` for the
60 s; a progressive job's is 10 s). A stream id no playback report named is closed
unconditionally (`SessionManager.CloseLiveStreamIfNeededAsync`, its `else` branch).

Observed on 12.4.0, with a client whose stop report and close were both refused:
about 56 s after each stop the server logged `Transcoding kill timer stopped for
JobId … Killing transcoding`, then, once ffmpeg had exited, `Live stream "<id>"
consumer count is now 0` and `Closing live stream`.

- **A transcoded play whose close never arrives holds its stream for about a
  minute, not for good.** The timer belongs to the `TranscodingJob`, so an open
  with no job behind it, such as a `PlaybackInfo` whose play never started, has
  none (inferred from the source above).
- **The late close takes back whatever the stream holds by then.** Every open of a
  channel shares one `LiveStreamId`, so a re-tune of the same channel inside that
  minute is the open it consumes. Observed: a first play's kill took the count
  from 1 to 0 and closed the stream that a second play of the channel had opened
  since.
- **A Stopped report kills the job without closing the stream.**
  `PlaystateController` stops through `KillTranscodingJobs`, which passes
  `closeLiveStream: false`, and `OnPlaybackStopped` closes only a `LiveStreamId`
  the report names. A client that leaves it out of the report must send the
  close itself. Observed: after such a report the job stopped at once, and the
  stream closed only on the client's `POST /LiveStreams/Close`, 48 ms after the
  server logged the stop.

## A late close can shut the stream someone is watching

A close names a `LiveStreamId` and nothing else, and the id does not tell one open
from another:

- **A channel's `LiveStreamId` is the same on every open.** Observed on `v12.0-rc5`
  with an M3U tuner: every open of one channel over a session, across server
  restarts, returned `<tuner>_<channel>_<source>`, the same each time.
- **An open of a stream the server still holds is counted on that stream**
  (`src/Jellyfin.LiveTv/DefaultLiveTvService.cs:470`), and a close takes one
  consumer away, shutting the stream at zero
  (`Emby.Server.Implementations/Library/MediaSourceManager.cs:1004`).
- **A close of an id the server does not hold does nothing and still answers
  204** (`MediaSourceManager.cs:1002`, `Jellyfin.Api/Controllers/MediaInfoController.cs:317`).

So a client that keeps a close to retry later, because the server refused it or
could not be reached, can take back the wrong open. If the server dropped the
old stream in the meantime (a restart drops them all) and the same channel has
been opened again since, the retried close takes the new open's only consumer.
The server then closes the stream under the player. Observed on Kodi 23.0-ALPHA1
against the server above, with the held-over close sent when the replay of the
channel started:

```
12:19:10 Live stream "<source>" consumer count is now 0
12:19:10 Live stream "<tuner>_<channel>_<source>" closed successfully
```

The player's clock stopped at 00:02.

**Send a held-over close only after the playback using that id has sent its
own.** In that order the count comes out right either way:
- **The server still held the older open:** it goes 2 → 1 → 0.
- **It had dropped it:** the playback's own close reaches 0, and the held-over
  close gets 204 and changes nothing.

Closing it any earlier is right in the first case and shuts the stream in the
second, and the client cannot tell which case it is in.

## The HLS master advertises what the server assumed

For a multi-audio-track live source, Jellyfin stream-copies an un-mapped track —
ffmpeg picks the one with the most channels — while advertising `mp4a.40.2` in
the master playlist.

**Any player that trusts the manifest opens the wrong decoder.** ffmpeg's own
mpegts demuxer is unaffected because it reads the PMT.

## A live stream's `Path` can name the server's own loopback

An opened M3U or HDHomeRun stream that the server shares comes back from
`PlaybackInfo` with `MediaSources[0].Path` set to
`<api url>/LiveTv/LiveStreamFiles/<id>/stream.ts`. A client that direct-plays
hands that URL to Kodi as it stands, and its host is not always one Kodi can
reach.

- The server builds it from `GetApiUrlForLocalAccess()`
  (`src/Jellyfin.LiveTv/TunerHosts/SharedHttpStream.cs:66`,
  `HdHomerun/HdHomerunUdpStream.cs:150`), and v12 re-bases it on the requesting
  client's smart API URL (`Jellyfin.Api/Helpers/MediaInfoHelper.cs:550`).
- When no non-loopback interface survives the server's interface filtering,
  the bind address falls back to `127.0.0.1`, or to `::1` for an IPv6 source
  with IPv6 enabled or with IPv4 disabled
  (`src/Jellyfin.Networking/Manager/NetworkManager.cs:922`).
  A published-server override can name any host at all.
- `::1` arrives bracketed, as `http://[::1]:8096/...`. **A host parser that
  stops at the first colon reads that host as `[`**, so an exact-match rewrite
  of `127.0.0.1` and `localhost` silently passes it through. End an IPv6
  literal's host at `]`.

Observed against a v12 server answering `http://[::1]:<port>` (recipe in
[`jellyfin-test-server`](../jellyfin-test-server/SKILL.md#a-live-tv-source-that-direct-plays)):
Kodi 22.0-RC1 logs `CCurlFile::Open - <http://[::1]:<port>/LiveTv/LiveStreamFiles/<id>/stream.ts> Failed with code 0`
and the channel does not play. Rewriting the bracketed host to the address the
add-on reached the server on plays it.

## A Python add-on's requests carry `Python-urllib`

A binary add-on's `kodi::vfs::CFile` requests go out through Kodi's curl with
Kodi's User-Agent (`xbmc/filesystem/CurlFile.cpp:679`). A Python add-on's
`urllib.request` sends Python's default. Observed from one add-on on Kodi
22.0-RC1, through a logging proxy:

```
POST /Items/<id>/PlaybackInfo   ua='Kodi/22.0-RC1 (X11; Linux x86_64) ...'   # C++ half
POST /Sessions/Playing          ua='Python-urllib/3.13'                      # service script
```

A proxy that screens user agents can therefore pass one half of an add-on and
refuse the other. Live TV plays while the server never hears the playback
reports, and a refused `/LiveStreams/Close` leaves the tuner stream open on
the server. **Set `User-Agent` explicitly.** `xbmc.getUserAgent()` returns
`CSysInfo::GetUserAgent()` (`xbmc/interfaces/legacy/ModuleXbmc.cpp:555`), the
same function Kodi's curl default comes from
(`xbmc/settings/AdvancedSettings.cpp:559`), so it makes both halves look alike.

## Request shapes that fail opaquely

- **`SortBy` and `SortOrder` must have matching arity.** One field with two orders
  is rejected by 10.11 with an **opaque 400**. Swallowing that turned a rejected
  count-probe into "library synced successfully" with 22,694 items missing.
- **`POST /LiveStreams/Close?liveStreamId=X` — the id must be a query parameter.**
  A JSON or form body returns HTTP 400 and leaks the tuner consumer.
- **Do not send `MediaSourceId` for live TV `PlaybackInfo`** — it returns
  `NoCompatibleStream`.
- **An `Authorization` header value must be ASCII or UTF-8; percent-encode the
  device name.** A byte that is not valid UTF-8 gets a 400. Observed on 12.4.0,
  unauthenticated `GET /System/Info/Public`: `Device="K\xfcche"` 400; the same
  name in UTF-8, a Cyrillic one in UTF-8, or `K%C3%BCche`, 200. A signed-in POST
  with the Latin-1 name got the same 400 on 12.0.0. Python's `http.client`
  encodes header values as Latin-1 (`HTTPConnection.putheader`), so a device name
  such as "Küche" gets that 400, and one Latin-1 cannot carry (Cyrillic, CJK, a
  typographic apostrophe) raises `UnicodeEncodeError` before anything is sent.
  The server URL-decodes every value of the header
  (`Jellyfin.Server.Implementations/Security/AuthorizationContext.cs`,
  `WebUtility.UrlDecode`), so a name percent-encoded as `encodeURIComponent`
  encodes it is recorded as typed. Observed on 12.0.0: `/Sessions` read
  `DeviceName` back as `Küche`, `Гостиная` and `A "quoted", name+plus`;
  unencoded, the last was recorded as `A quoted, name plus`.
- **EPG filtering uses `MaxStartDate`, not `MaxEndDate`.**
- Use the `Authorization` header and the `ApiKey` query parameter. The deprecated
  `X-Emby-Authorization` and `api_key` forms are being removed — and **from v12
  they are off by default**, see below.

## v12 rejects the legacy auth forms by default

`ServerConfiguration.EnableLegacyAuthorization` lost its `= true` initializer, so
a fresh v12 server writes `false`. The code that consults it did not change, only
the default, so nothing in a diff points at it. Measured on a fresh v12.0-rc5
instance with a valid token:

| form | v12 default |
|---|---|
| `Authorization: MediaBrowser ..., Token="..."` | 200 |
| `?ApiKey=<token>` | 200 |
| `?api_key=<token>` | **401** |
| `X-Emby-Authorization:` / `X-Emby-Token:` header | **401** |
| `Authorization: Emby ...` scheme name | **401** |

**On `/socket` the rejection is a 403 on the handshake, not a 401** — so a client
still building its socket URL with `api_key=` fails in a way that looks like a
routing or upgrade problem rather than an auth one.

A client that already uses the `Authorization` header and `ApiKey` needs no
change. Anything else stops working the day a user upgrades.

## Keep-alive: what the numbers actually are

The server advertises and enforces a WebSocket keep-alive contract. Measured by
connecting and then staying deliberately silent (identical constants in 10.11.11
and v12.0-rc5, so this is both):

```
t+ 0.1s  ForceKeepAlive  data=60   <- advertisement, sent unconditionally on connect
t+48.1s  ForceKeepAlive  data=60   <- inactivity warning
t+60.1s  ForceKeepAlive  data=60   <- inactivity warning
t+80.2s  socket closed
```

Three things worth knowing:

- **The first `ForceKeepAlive` is not a warning.** It arrives immediately on
  connect and its `Data` is the timeout in seconds. Treating it as "the server
  thinks I am idle" misreads a normal connection.
- **Warnings start at ~48 s**, the first watcher tick past the 45 s threshold
  (`WebSocketLostTimeout` 60 × `ForceKeepAliveFactor` 0.75).
- **The drop is later than the 60 s timeout suggests** — observed at 80 s.
  `LastKeepAliveDate` is refreshed *only* by the client's own `KeepAlive`;
  sending a `ForceKeepAlive` does not reset it, so the socket is classed lost on
  a tick past 60 s and the close frame follows.

A client sending `KeepAlive` every 30 s sits inside the warning threshold and
should never see an inactivity `ForceKeepAlive` at all.

## Downloading and seeking

- **`/Videos/{id}/stream.mkv` progressive transcode has no duration header and no
  cues**, because ffmpeg cannot seek back on a socket. Kodi reports 0:00, refuses
  to seek, and mis-marks watched.
- **`stream.ts` works** but costs about +5% and has no AV1 mapping.
- **Progressive mp4 is emitted as fragmented MP4** (`frag_keyframe+empty_moov+delay_moov`)
  and ffprobes at full duration even when cut off mid-stream — roughly 0%
  overhead. This is the one to use.
- **Transcoding throttling is force-disabled in 10.11** (migration
  `DisableTranscodingThrottling`), so a progressive transcode ran at **~28x
  realtime**. Cap concurrent transcode downloads at 1, or you saturate someone's
  encoder unbidden.

## A change feed scoped by media type cannot separate two libraries

A client whitelisting one library and able to see another received **all 12,404
items from both**, with nothing in the record to distinguish them — one
`/Items/{id}/Ancestors` round trip and one error per irrelevant item, ~17 minutes
at ~12 items/s, and **81% of all log errors**.

Resolving library ids needs `ILibraryManager.GetCollectionFolders`, **not
`GetTopParent()`** — which answers with a physical folder id no client can match.
It must be a *list*, because an item under two libraries belongs to both and
`/Items/{id}/Ancestors` reports only the first. And removals must resolve from
the **event's Parent**, because `DeleteItem` clears the item's own parent before
firing `ItemRemoved`.

## An album's `DateCreated` is when the scanner created its row

Sorting albums by `DateCreated` lists a scan, not arrivals. The field is set when
the scanner creates the album entity, and a rescan that re-creates album rows
stamps them in folder order. Observed on 10.11.11: a library of 1,538 albums
shared 768 distinct `DateCreated` seconds, in blocks of 47–65 albums per second,
and the 25 "newest" by that field were the first artists of the alphabet, all
within one second of each other, while the albums added that week were nowhere
near the top. `SortBy=DateLastContentAdded` is no alternative: albums answered
`DateLastMediaAdded` as `0001-01-01`.

Ask `/Items/Latest` instead — `userId`, `ParentId`, `IncludeItemTypes=Audio`,
`GroupItems=true`, `Limit` — which sorts the **songs** by `DateCreated` and
returns each one's album. That is the web client's Recently added query, and it
returned the week's additions first. Three shape differences from `/Items`: the
answer is a bare list, not an `Items` envelope; `Fields` is honoured and
`UserData`/`ImageTags` are present; and with `isPlayed` omitted it applies the
account's `HidePlayedInLatest` preference
(`Jellyfin.Api/Controllers/UserLibraryController.cs`, `GetLatestMedia`), with
`IsPlayed=true`/`false` each selecting one side and no value for both. Observed
on an account with the preference on: 0 played albums among the first 200;
`IsPlayed=true` → played only.

## `People` costs the server per row

`Fields=People` is linear in rows, server-side, on 10.11.11: about 7–25 ms and
~7 KB per item. Measured on one server, the same query with and without the
field:

| Listing | Rows | Without | With |
|---|---|---|---|
| movies by `DateCreated`, `Limit=25` | 25 | 116 ms / 310 KB | 709 ms / 485 KB |
| whole movie library | 1,775 | 0.65 s / 3.6 MB | 42.7 s / 14.7 MB |
| `/Shows/NextUp` | 12 | 352 ms | 431 ms |
| `/UserItems/Resume` | 8 | 116 ms | 268 ms |

A People-only follow-up (`/Items?Ids=…&Fields=People`) is no cheaper — 663 ms
for the same 25 — so the cost cannot be moved off the critical path, only kept
off unbounded listings. The single-item `/Items/{id}` answer carries `People`
without being asked (55 ms, ~22 KB) and is the place to get cast for one item.

## Driving another client's session from outside

A session is identified by the `Client` name and `DeviceId` in the
`Authorization` header, with the token. Any HTTP call carrying a client's exact
`MediaBrowser Client="…", DeviceId="…", Version="…", Token="…"` acts **as that
session**: a `POST /SyncPlay/New`, `/Join`, `/SetNewQueue`, `/Pause` or
`/Unpause` made from a test host with a Kodi client's own fields creates or
steers a group for that Kodi, and the resulting `SyncPlayGroupJoined` /
`SyncPlayCommand` messages arrive at the real client over its own websocket —
its log shows `--->[ syncplay group/<id> ] protocol v2` and the scheduled
commands exactly as if the user had used the menu (Jellyfin 10.11.11, four Kodi
clients driven this way for two days).

That is the way to test a client's SyncPlay behaviour without driving its UI:
read `deviceId` and the token off the client's own settings file, mirror the
`Client` name, and script the server. Mismatch the `Client` name and the call
makes a *new* session that the client never hears about.

## Reproducing a transcode bug

**Use a fresh `PlaySessionId` for every attempt.** The server reuses a running job
for the same session, so replaying a failing URL after a successful one returns
200, and a bug that is still there reads as fixed.

## What fails silently

- An Etag-gated sync never noticing diverged userdata.
- A re-added item inheriting stale userdata with no event of any kind.
- `UserDataChanged` delivering another user's entire history.
- `PlayCount` re-marking items watched after they were cleared.
- A skipped song counted as a play, and a short clip marked played at a stop
  in its middle, with nothing in the stop report's answer to say so.
- An opaque 400 from a mismatched sort being read as an empty result.
- Albums sorted by `DateCreated` presenting a rescan as recent additions.
- `Fields=People` on a whole-library query turning a sub-second listing into a
  40-second one, with nothing in the response to say why.
- Playback reports a User-Agent-screening proxy refused: the stream plays, the
  dashboard stays empty, and the stream the client stopped stays open on the
  server.

## Open questions

- Whether the provider-id userdata inheritance is intentional Jellyfin behaviour
  or a defect has not been settled upstream.
- The 10.9 user-scoped route migration: 10.11 still serves the old shape while
  having dropped it from the OpenAPI spec, so the spec is not a reliable guide to
  what a given server accepts. When it will actually be removed is unknown.
- Which proxies refuse `Python-urllib`. A user reported Cloudflare's Browser
  Integrity Check (on by default) doing so, with the 403s in Cloudflare's
  security events (kontell/pvr.kofin#105). That has not been reproduced against
  Cloudflare here; the observation above used a stand-in proxy.

## See also

- [`kodi-pvr-addon`](../../skills/kodi-pvr-addon/SKILL.md) — the Kodi side of a
  Live TV client
- [`kodi-database-writing`](../../skills/kodi-database-writing/SKILL.md) — writing
  synced content into Kodi's library
- [`kodi-logs`](../../skills/kodi-logs/SKILL.md) — Jellyfin tokens ride on stream
  URLs, which Kodi writes to kodi.log at debug level
