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
  verified-kodi: "21.3 Omega, 22.0b1 Piers, 23.0-ALPHA1 (master c7c26084f8)"
  verified-platform: "Linux x86_64"
  verified-date: "2026-10-18"
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
tempo, whatever the setting says. What counts as realtime is the input stream's
own answer, and an inputstream add-on's defaults to yes — see
[`kodi-inputstream`](../kodi-inputstream/SKILL.md).

A stream with no time range is refused as well: `UpdatePlayState()` clears
`cantempo` whenever `timeMin` equals `timeMax` (`VideoPlayer.cpp:5939-5942` at
master `c7c26084f8`).

## Above 2 %, the display clock re-makes the atempo filter at every correction

With the display clock the audio is resampled to the clock
(`VideoPlayerAudio.cpp:139-140` at master `c7c26084f8`), and the engine's sync
servo sets the ratio again after every sync error it takes
(`SetRR(stream->CalcResampleRatio(error), ...)`, `ActiveAE.cpp:2754`). That
ratio is `1 / clockspeed` plus a proportional and an integral term
(`ActiveAEStream.cpp:204`), so it moves a little every time.

Within `audiooutput.atempothreshold` (default 2 %, `system/settings/settings.xml:3425`)
the ratio goes to the resampler. Beyond it, it goes to the `atempo` filter as
`1 / ratio` (`CActiveAEStreamBuffers::SetRR`, `ActiveAEStream.cpp:733-743`),
and any new tempo value sets `m_changeFilter`
(`CActiveAEBufferPoolAtempo::SetTempo`, `ActiveAEBuffer.cpp:692-700`). The pool
then stops taking input (`:539`), drains the filter, pads the last packet with
zeros (`:592-596`) and re-makes it (`:619-621`). A tempo beyond 2 % in this
mode is re-made at nearly every correction. The same function clamps the
filter's tempo to 0.5–2.0 (`:694-697`).

Measured on a build of master `c7c26084f8` with unmerged tempo patches that put a
realtime stream through this same resample path at 1.5 (Linux x86_64, headless,
ALSA null sink): ActiveAE logged 1350 `large audio sync error` warnings over a
few minutes of playback, swinging between −1.4 s and +2.2 s. With the audio
made the clock for the tempo instead, so that the stream is asked for 1/1.5
once, the same sequence re-run logged none.

## A stall at a tempo is not rebuffered

VideoPlayer's stall handling runs only at normal speed:
`if (m_playSpeed == DVD_PLAYSPEED_NORMAL && !tolerateStall)`
(`VideoPlayer.cpp:2235` at master `c7c26084f8`). That block holds both the
realtime and the non-realtime stall branches and the live-stream clock
adjustment (`:2281`). At a tempo none of it runs, so a stream whose queues run
dry is not put back into buffering the way it is at 1.0.

## The debug overlay's a/v is not a sync reading at a tempo

`Player: a/v` in the player debug overlay is the audio player's playing pts
minus the video's (`CVideoPlayer::GetGeneralInfo`, `VideoPlayer.cpp:3976-3993`).
The audio side is the last frame's end minus the engine's delay
(`m_playingPts = audioframe.pts + audioframe.duration - GetDelay()`,
`AudioSinkAE.cpp:163`), and that delay is in output seconds
(`AudioSinkAE.cpp:207-216`). At a tempo an output second holds tempo times as
much of the stream, so the reading runs high.

On the patched build above, with the audio as the clock at 1.5, the overlay read
`a/v` 0.40 on a live channel and 0.43 on a recording, against −0.13 at 1.0 on the
same recording.

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
- Realtime streams refuse tempo even with the setting on, and an inputstream
  add-on's streams are realtime unless it says otherwise.
- Beyond the 2 % atempo threshold, a resampled tempo re-makes its filter at
  nearly every servo correction.
- A stall at a tempo is not rebuffered.
- The overlay's `a/v` reads high at any tempo.

## Open questions

- The keyframe re-seek on returning to 1.0, and its fix in Kodi 22, are reported
  rather than verified here — neither was reproduced against a live player.
- Whether PAPlayer has any tempo path at all was not investigated; everything
  above is VideoPlayer.
- `CVideoPlayerWebOS` overrides `CanTempo()` to also allow it when the WebOS media
  pipeline is active (`VideoPlayerWebOS.cpp:98`), so webOS behaviour differs and
  has not been characterised.
- The atempo re-making was measured only with a realtime stream on a patched
  build. On stock Kodi the display clock is the one path to that code, and how it
  sounds and what sync error it produces there was not measured.
- The overlay's `a/v` at a tempo was read only on the patched build, with the
  audio as the clock. Stock Kodi's display-clock tempo goes through the same
  `GetDelay()` and was not read.

## See also

- [`kodi-inputstream`](../kodi-inputstream/SKILL.md) — rate-shifting in the demux
  path, and the output-vs-content clock problem it creates
- [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) — why Introspect will not save you
  from a property that does not exist, and what `time` means on a live channel
- [`kodi-playback-stalls`](../kodi-playback-stalls/SKILL.md) — what a rebuffer
  looks like in the log
