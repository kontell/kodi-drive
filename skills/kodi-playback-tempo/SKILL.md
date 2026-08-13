---
name: kodi-playback-tempo
description: >
  Change playback rate with pitch correction, and find out why it silently does
  nothing. Use when Player.SetTempo has no effect, when probing whether tempo is
  available, or when building speed control into an add-on. Covers the display
  setting that gates it and is off by default, and the JSON-RPC property people
  reach for that does not exist.
license: CC-BY-SA-4.0
metadata:
  category: playback
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: "sourced"
---

# Tempo (pitch-corrected speed)

`Player.SetTempo` does nothing on most installs, reports no error, and there is no
JSON-RPC property that tells you why.

## Tempo is gated on a display setting that defaults to off

VideoPlayer allows tempo only when **"Sync playback to display"**
(`videoplayer.usedisplayasclock`) is on **and** the stream is not realtime.

Kodi 21 does it inline (`xbmc/cores/VideoPlayer/VideoPlayer.cpp:4917-4924`):

```cpp
if (CServiceBroker::GetSettingsComponent()->GetSettings()->GetBool(
        CSettings::SETTING_VIDEOPLAYER_USEDISPLAYASCLOCK) && !realtime)
  state.cantempo = true;
else
  state.cantempo = false;
```

Kodi 22 extracts the same logic (`VideoPlayer.cpp:5604`), with the realtime check
moved to the call site at `:5513`:

```cpp
bool CVideoPlayer::CanTempo()
{
  return CServiceBroker::GetSettingsComponent()->GetSettings()->GetBool(
      CSettings::SETTING_VIDEOPLAYER_USEDISPLAYASCLOCK);
}
...
state.cantempo = CanTempo() && !realtime;
```

**`videoplayer.usedisplayasclock` defaults to `false`** on both versions
(`system/settings/settings.xml`). So on a default install, tempo is unavailable
and `SetTempo` is a no-op.

The `!realtime` half matters too: live TV and other realtime inputs can never
tempo, whatever the setting says.

## There is no `canchangetempo` property

This is the trap that costs the most time. Reaching for the obvious name gets you
`False` forever, because the property does not exist — an absent JSON-RPC property
does not error, it simply is not there.

Searched across the whole tree: **`cantempo` is never exposed through JSON-RPC.**
The only related property is `canchangespeed`, and it means something else
entirely (`xbmc/interfaces/json-rpc/PlayerOperations.cpp:1833`):

```cpp
else if (property == "canchangespeed")
{
  case Video:
  case Audio:
    result = !IsPVRChannel();
```

That is "is this not a live channel", not "can this do tempo".

**Read the setting instead**, and treat a rejected live `SetTempo` as the
backstop:

```sh
kodi-remote get Settings.GetSettingValue '{"setting":"videoplayer.usedisplayasclock"}'
```

## Two more behaviours worth knowing

- **Returning tempo to 1.0 triggers a keyframe re-seek** on some builds, which is
  audible and visible. *Reported as fixed in Kodi 22; not re-verified here.*
- **The tempo OSD is skin-driven** from `Player.IsTempo` and `Player.PlaySpeed`,
  and **there is no add-on API to suppress it**. If you need it off screen, the
  only lever is holding tempo at exactly 1.0.

## Doing it in the stream instead

If you need rate control that does not depend on a user setting, do it in an
inputstream add-on rather than through the player — an FFmpeg `atempo` filter in
the demux path. That brings its own problems (two clocks to satisfy at once), all
of which are in [`kodi-inputstream`](../kodi-inputstream/SKILL.md).

## What fails silently

- `SetTempo` is a no-op on a default install, with no error.
- Probing `canchangetempo` returns nothing and reads as "not supported".
- `canchangespeed` looks like the right property and answers a different question.
- Realtime streams refuse tempo even with the setting on.

## Open questions

- The keyframe re-seek on returning to 1.0, and its fix in Kodi 22, are reported
  rather than verified here — neither was reproduced against a live player.
- Whether PAPlayer has any tempo path at all was not investigated; everything
  above is VideoPlayer.
- `CVideoPlayerWebOS` overrides `CanTempo()` to also allow it when the WebOS media
  pipeline is active (`VideoPlayerWebOS.cpp:98`), so webOS behaviour differs and
  has not been characterised.

## See also

- [`kodi-inputstream`](../kodi-inputstream/SKILL.md) — rate-shifting in the demux
  path, and the output-vs-content clock problem it creates
- [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) — why Introspect will not save you
  from a property that does not exist
