---
name: kodi-pvr-addon
description: >
  Write a Kodi PVR client that plays, records and reports correctly. Use when
  building or debugging a PVR add-on, when playback works from one part of the UI
  and not another, when a stream session is never closed, or when choosing between
  the stream-properties and demuxer approaches. Covers the user setting that
  decides which entry point Kodi calls, and the stop callback that does not fire.
license: CC-BY-SA-4.0
metadata:
  category: playback
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64, Android TV"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# PVR client add-ons

## Stream properties, or a demuxer

Two approaches. **Stream properties** — return a URL plus inputstream
configuration from `GetChannelStreamProperties()` and let Kodi's own pipeline do
the work — is far less code and gets you inputstream.adaptive and
inputstream.ffmpegdirect for free.

Its cost is the entire section below: you give up the lifecycle callbacks.

## A user setting decides which recording entry point Kodi uses

This is the trap that produces "it plays from one place and not another". Two
different add-on entry points can be reached **from the same window, by the same
button** — and what selects between them is a setting, not the UI location.

`CPVRGUIActionsPlayback::PlayRecording` branches at
`xbmc/pvr/guilib/PVRGUIActionsPlayback.cpp:127`:

```cpp
if (!item.m_bIsFolder && VIDEO_UTILS::IsAutoPlayNextItem(item))
```

| Autoplay-next-item | Route | Your entry point |
|---|---|---|
| **off** | → `CPVRPlaybackState::StartPlayback` | **`GetRecordingStreamProperties()`** |
| **on** | builds a playlist, posts `TMSG_MEDIA_PLAY` | `pvr://recordings/…` via the ordinary file pipeline → **`OpenRecordedStream()`** |

`PlayRecordingFolder()` takes the playlist route too.

`StartPlayback` branches on item type and calls `GetRecordingStreamProperties()`
for any `IsPVRRecording()` item (`xbmc/pvr/PVRPlaybackState.cpp:363-365`), then
applies the returned URL with `SetDynPath` **only `if (props.size())`**. So the
`CInputStreamPVRRecording` byte-stream route is also the **fallback when your
add-on returns no properties** — not a separate window-driven path.

**Implement both, and test both — with the setting flipped each way.** Testing
only one value of a setting you did not know was involved is how this stays
hidden.

> **Correction, 2026-08-13.** This skill previously said the Recordings window
> (10701) calls `OpenRecordedStream()` and never calls
> `GetRecordingStreamProperties()`. That is wrong. It was inherited from a
> project note that was also wrong, and the source above disproves both. The
> practical advice — implement both — was right for the wrong reason.

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

## Timer types: list first the one that works without an EPG tag

Kodi pre-selects your **first registered type**, and it does so without checking
whether that type can actually be used in the current context.
`CPVRTimerType::GetFirstAvailableType` is, in full
(`xbmc/pvr/timers/PVRTimerType.cpp:106-118`):

```cpp
const std::vector<std::shared_ptr<CPVRTimerType>>& types = client->GetTimerTypes();
if (!types.empty())
  return *(types.begin());
```

No regard for `REQUIRES_EPG_TAG_ON_CREATE`, `IS_READONLY`, or
`FORBIDS_NEW_INSTANCES`. So if your first type requires an EPG tag, adding a
timer with no EPG context offers a type that cannot work, already selected.

**This is an upstream defect, not a design you should lean on** — see
[`kodi-known-defects`](../kodi-known-defects/SKILL.md). Order your types so the
first is the one usable in every context (a one-shot manual timer), and treat
that as a workaround rather than the intended mechanism.

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
the authenticated API immediately. A brief retry inside one connect is not
enough on its own; see
[Re-announcing CONNECTED does nothing](#re-announcing-connected-does-nothing).

## Polling

A `Process()` loop polling timers and recordings, then triggering Kodi UI
updates, is the normal shape. Make the interval a setting, clamp it (15–3600 s is
reasonable), and **re-read it every pass** so a change takes effect without a
restart.

Skip the poll entirely while logged out, or you generate traffic and log noise
for nothing.

## Kodi reads your channels once: trigger after every reload

Kodi loads a client's channels and groups when the client first connects, and
after that only on wake or when the add-on calls `TriggerChannelUpdate()` or
`TriggerChannelGroupsUpdate()`. A reconnect does not count.
`CPVRManager::UpdateComponents` loads only the clients it has not loaded before
(`xbmc/pvr/PVRManager.cpp:715-745` at `22.0b2-Piers`), and the only other
refresh is `OnWake` (`:667-669`).

So a reload the add-on does on its own (a refresh timer, a settings change, the
reload on reconnect) changes its model and nothing on screen, until Kodi is
restarted or woken. Observed on a Kodi 22.0 beta 2 build: after a reconnect, and
again after a settings change, the add-on loaded one channel fewer and
`PVR.GetChannels` went on reporting the old count.

**Trigger after every load that succeeds, including the one on connect.** That
is safe on the first connect too. Each per-client trigger job returns early for
a client Kodi has not loaded yet (`if (!IsKnownClient(clientId)) return;`, at
`PVRManager.cpp:965` for channels and `:985` for groups, with the same guard for
recordings, timers and providers at `:906`, `:926` and `:945`), and Kodi loads
the client itself once told it is connected. After a failed load there is
nothing new to show, so skip the trigger.

## Re-announcing CONNECTED does nothing

Kodi drops a connection-state callback that repeats the current state
(`xbmc/pvr/addons/PVRClient.cpp:2527` at `22.0b2-Piers`):

```cpp
if (prevState == newState)
  return;
```

So a client already reported CONNECTED cannot make Kodi do anything by reporting
it again. Bouncing through another state does not force a refresh either. The
client is already known, so Kodi reloads nothing; observed through
`SERVER_UNREACHABLE` on the same beta. A bounce through `SERVER_UNREACHABLE` or
`DISCONNECTED` also notifies the user twice, once for that state and once for
the `CONNECTED` after it. Kodi silences `SERVER_UNREACHABLE` and `CONNECTED`
only when they follow `UNKNOWN` or `CONNECTING`, and never silences
`DISCONNECTED` (`xbmc/pvr/addons/PVRClients.cpp:876-904`). Refresh through the
triggers above.

The same rule catches a connection manager that reports CONNECTED from a health
check and only then authenticates or loads. The one in `pvr.iptvsimple`, which
PVR clients commonly copy, calls `ConnectionEstablished()` only on a state change
(`src/iptvsimple/ConnectionManager.cpp:92-102` on its `Piers` branch at
`739177c`) and sets CONNECTED after every successful check (`:172`). If the work
in `ConnectionEstablished()` fails after the check passed (a token check while
the backend is still starting, say, or a playlist download that times out),
nothing calls it again while the checks keep passing. Observed on a Kodi 22.0
beta 2 build with a fork of that manager: the one connect attempt failed, none
followed, and the client still had no channels 30 s after the backend
recovered. Record the failure and call `ConnectionEstablished()` again at the
next successful check.

## What fails silently

- An add-on implementing only one recording path works with a user setting one
  way and not the other, from the same button, with no error.
- `CloseLiveStream()` never firing leaks server-side sessions invisibly.
- `EPGPLAYBACKASLIVE` silently rerouting playback past your EPG-path handling.
- A future timer with the same truncated title hijacking an EPG cross-reference.
- Credentials cleared on a transient network failure, presenting as "it logged
  me out again".
- A reload with no trigger after it: the add-on's model changes and Kodi shows
  the old one until it restarts or wakes.
- A connect that fails after the health check passed, which nothing retries
  while the check keeps passing.

## Open questions

- Whether Kodi 22 changed the `CloseLiveStream()` behaviour under the
  stream-properties path has not been retested.
- On Kodi 22, `GetRecordingStreamProperties` is called from
  `PVRPlaybackState.cpp:204`, so the overall shape holds — but the
  `IsAutoPlayNextItem` branch has not been re-verified there.

## See also

- [`kodi-binary-settings`](../kodi-binary-settings/SKILL.md) — the settings ABI
  gap, and the companion-service pattern
- [`kodi-inputstream`](../kodi-inputstream/SKILL.md) — choosing what to hand the
  stream to
- [`kodi-versions-abi`](../kodi-versions-abi/SKILL.md) — PVR API levels
- [`kodi-android-standby`](../kodi-android-standby/SKILL.md) — `OnSystemSleep`
  never arriving on an Android TV, and `OnSystemWake` arriving without it
