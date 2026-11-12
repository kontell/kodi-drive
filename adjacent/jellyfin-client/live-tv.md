# Jellyfin live TV from a Kodi client

How a Jellyfin server opens, shares and closes a live TV stream, and what it
tells a client about one. Companion to [SKILL.md](SKILL.md); these sections
live here because the skill outgrew its length limit.

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
