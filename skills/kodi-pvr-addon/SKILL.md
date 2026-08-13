---
name: kodi-pvr-addon
description: >
  Write a Kodi PVR client that plays, records and reports correctly. Use when
  building or debugging a PVR add-on, when playback works from one part of the UI
  and not another, when a stream session is never closed, or when choosing between
  the stream-properties and demuxer approaches. Covers which UI path calls which
  entry point, and the stop callback that does not fire.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega"]
    platform: ["Linux x86_64", "Android TV"]
    date: "2026-08-13"
    method: observed
---

# PVR client add-ons

## Stream properties, or a demuxer

Two approaches. **Stream properties** — return a URL plus inputstream
configuration from `GetChannelStreamProperties()` and let Kodi's own pipeline do
the work — is far less code and gets you inputstream.adaptive and
inputstream.ffmpegdirect for free.

Its cost is the entire section below: you give up the lifecycle callbacks.

## Which UI path calls which entry point

This is the trap that produces "it plays from the home screen but not from the
Recordings section". Recordings have **two completely different code paths** in
Kodi v21:

| Entry point | Calls | Notes |
|---|---|---|
| Home-screen widgets, EPG actions | `GetRecordingStreamProperties()` | `OpenRecordedStream()` is **never** called |
| PVR Recordings window (10701) | `OpenRecordedStream()` | `GetRecordingStreamProperties()` is **not** called |

The second opens `pvr://recordings/...` directly through
`CInputStreamPVRRecording`. So an add-on that implements only stream properties
works from a widget and fails from the Recordings list, and vice versa.

**Implement both**, and test both. Reaching one from the other is not possible
from your side.

## `CloseLiveStream()` does not fire on a normal stop

Under the stream-properties path, **Kodi v21 does not call `CloseLiveStream()`
when playback stops normally.** It fires only from the destructor, or when
switching channels via `GetItemStreamUrl()`.

If your backend needs an explicit close — releasing a tuner, ending a server
session — that close will simply never be sent, and the symptom is a leaked
consumer on the server rather than anything visible in Kodi.

**The workaround is a companion Python service**, which does get
`xbmc.Player` callbacks. Make that service the *single* close authority, so a
shared session id can never be double-closed, and have it also handle the case
where new playback replaces current playback with no stop event at all — a
channel zap — by finalising the outgoing session from `onAVStarted`.

This is the same binary-API gap described in
[`kodi-binary-settings`](../kodi-binary-settings/SKILL.md).

## Play-from-EPG changes which entry point runs

`PVR_STREAM_PROPERTY_EPGPLAYBACKASLIVE=true` makes Kodi open the **channel**, so
playback runs through `GetChannelStreamProperties()` rather than the EPG-tag
path.

If your EPG path applies special handling — a catchup pipeline, direct-play
overrides — that handling is bypassed unless `GetChannelStreamProperties()` also
detects the pending timeshifted state and applies the same overrides. Otherwise
the global settings resolve a live-only URL that cannot seek back to the chosen
programme.

## Timer types: the first one listed is the default

Declare your timer types in the order you want them offered. There is no
"default" flag — position is the mechanism.

A useful set is one-shot manual, one-shot from EPG, a read-only child type
created by a series rule, and the series rule itself.

## Cross-referencing recordings to EPG

Use `SetEPGEventId()` and `SetChannelUid()` to link a recording to its programme.

When building the cross-reference from timers, **build it only from in-progress
timers**. Two back-to-back programmes can share an identical truncated title, so
a later same-named future timer will otherwise hijack the in-progress
recording's EPG link.

## HTTP through Kodi's VFS

Use `kodi::vfs::CFile` for HTTP, and note that **POST data must be Base64-encoded
via the `postdata` protocol option**.

The important limitation: **an unreachable server and an expired token are
indistinguishable.** `CURLOpen` fails for both and exposes no status code.

So **never auto-clear stored credentials on a validation failure** — a transient
network blip would log the user out. Only an explicit logout should clear them.
Retry briefly on startup instead, since a just-reconnected server may not serve
the authenticated API immediately.

## Polling

A `Process()` loop polling timers and recordings, then triggering Kodi UI
updates, is the normal shape. Make the interval a setting, clamp it (15–3600 s is
reasonable), and **re-read it every pass** so a change takes effect without a
restart.

Skip the poll entirely while logged out, or you generate traffic and log noise
for nothing.

## What fails silently

- An add-on implementing only one recording path works from one UI location and
  not another, with no error.
- `CloseLiveStream()` never firing leaks server-side sessions invisibly.
- `EPGPLAYBACKASLIVE` silently rerouting playback past your EPG-path handling.
- A future timer with the same truncated title hijacking an EPG cross-reference.
- Credentials cleared on a transient network failure, presenting as "it logged
  me out again".

## Open questions

- Whether Kodi 22 changed the `CloseLiveStream()` behaviour under the
  stream-properties path has not been retested.
- The two-recording-paths split was established on v21; whether 22 unified them
  is unknown.

## See also

- [`kodi-binary-settings`](../kodi-binary-settings/SKILL.md) — the settings ABI
  gap, and the companion-service pattern
- [`kodi-inputstream`](../kodi-inputstream/SKILL.md) — choosing what to hand the
  stream to
- [`kodi-versions-abi`](../kodi-versions-abi/SKILL.md) — PVR API levels
