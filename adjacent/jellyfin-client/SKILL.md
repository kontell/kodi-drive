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
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64, Android TV, Android phone/tablet"
  verified-date: "2026-08-27"
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
`PlaybackInfo(AutoOpenLiveStream)` adds a consumer**, and only a correctly-formed
`POST /LiveStreams/Close?liveStreamId=X` decrements one. A client that never closes
leaks them — one observed stream reached 7 consumers and stayed alive 5 hours
after playback stopped.

## The HLS master advertises what the server assumed

For a multi-audio-track live source, Jellyfin stream-copies an un-mapped track —
ffmpeg picks the one with the most channels — while advertising `mp4a.40.2` in
the master playlist.

**Any player that trusts the manifest opens the wrong decoder.** ffmpeg's own
mpegts demuxer is unaffected because it reads the PMT.

## Request shapes that fail opaquely

- **`SortBy` and `SortOrder` must have matching arity.** One field with two orders
  is rejected by 10.11 with an **opaque 400**. Swallowing that turned a rejected
  count-probe into "library synced successfully" with 22,694 items missing.
- **`POST /LiveStreams/Close?liveStreamId=X` — the id must be a query parameter.**
  A JSON or form body returns HTTP 400 and leaks the tuner consumer.
- **Do not send `MediaSourceId` for live TV `PlaybackInfo`** — it returns
  `NoCompatibleStream`.
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
- An opaque 400 from a mismatched sort being read as an empty result.
- Albums sorted by `DateCreated` presenting a rescan as recent additions.
- `Fields=People` on a whole-library query turning a sub-second listing into a
  40-second one, with nothing in the response to say why.

## Open questions

- Whether the provider-id userdata inheritance is intentional Jellyfin behaviour
  or a defect has not been settled upstream.
- The 10.9 user-scoped route migration: 10.11 still serves the old shape while
  having dropped it from the OpenAPI spec, so the spec is not a reliable guide to
  what a given server accepts. When it will actually be removed is unknown.

## See also

- [`kodi-pvr-addon`](../../skills/kodi-pvr-addon/SKILL.md) — the Kodi side of a
  Live TV client
- [`kodi-database-writing`](../../skills/kodi-database-writing/SKILL.md) — writing
  synced content into Kodi's library
- [`kodi-logs`](../../skills/kodi-logs/SKILL.md) — Jellyfin tokens ride on stream
  URLs, which Kodi writes to kodi.log at debug level
