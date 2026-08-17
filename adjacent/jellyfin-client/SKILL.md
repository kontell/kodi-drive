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
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64, Android TV"
  verified-date: "2026-08-17"
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
