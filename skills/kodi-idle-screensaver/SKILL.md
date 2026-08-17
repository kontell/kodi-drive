---
name: kodi-idle-screensaver
description: >
  Detect idleness and control the screen from a Kodi add-on — dim it, blank it,
  or turn the display off — without stranding the user's settings. Use when
  building a sleep timer, a screen-off feature, a wake-time hook, or anything
  that suppresses the screensaver, and when a feature must survive Kodi being
  killed mid-operation. Covers the screensaver that will not fire during video,
  the wake event that never fires when the screensaver is set to None, and the
  crash breadcrumb that prevents leaving settings changed.
license: CC-BY-SA-4.0
metadata:
  category: python-addon
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64, Android TV"
  verified-date: "2026-08-17"
  verified-method: "observed"
---

# Idle detection and screen control

## Detecting idleness

`xbmc.getGlobalIdleTime()` returns seconds since the last user input. Poll it
against your threshold rather than trying to hook input events.

**Fire once per idle period and re-arm when the user interacts**, or your action
repeats every poll for as long as they stay away.

## Four ways to darken a screen, with different reach

| Mechanism | Reaches | Notes |
|---|---|---|
| Kodi's screensaver | Kodi's own window | **inhibited during VideoPlayer playback** |
| A `WindowDialog` overlay | Kodi's own window | works during playback, which the screensaver does not |
| `CECStandby` builtin | the TV, over HDMI-CEC | actually powers the display off |
| DPMS toggle | the display, on Android | |

**`ActivateScreenSaver` does nothing while VideoPlayer is playing.** Kodi inhibits
it deliberately. If your feature must dim or black the screen during playback —
which is the whole point of a sleep timer — a full-screen `WindowDialog` drawing
a black image is the route that works.

## Restore what you changed, and expect not to be asked

Anything that overrides the user's screensaver mode or volume must put it back.
The hard part is that your add-on may not get a chance to.

**Save the original values to disk before changing anything**, and treat that
file as a crash-recovery breadcrumb:

```
on activate:   read current screensaver mode + volume -> state.json, then override
on expiry:     restore, delete state.json
on service start: if state.json exists but the feature is not active,
                  restore from it and delete it
```

Without that last line, a Kodi killed mid-operation leaves the user's screensaver
disabled and their volume at zero, permanently, with nothing to explain it. The
observed failure was exactly this: screensaver-inhibit logic losing the user's
setting on a mid-operation quit.

## Ramping volume

If you fade volume before stopping, **back off when the user adjusts it
themselves** mid-ramp. Otherwise you are fighting them, and the fight is
invisible — they turn it up, it goes down again, and nothing indicates why.

## Waking again

Distinguish the two endings:

- **Expiry** — stop playback, restore volume and the screensaver setting, but
  leave the screen dark. The user's next interaction wakes it, which is what they
  asked for.
- **Cancellation, or playback stopping** — restore everything *including* waking
  the screen, because the user is present.

## Wake-time resync

`GUI.OnScreensaverDeactivated` is a useful hook for "the user just came back":
resync state that may have gone stale while idle, rather than polling for changes
nobody was watching.

**But the wake event never fires when the screensaver is set to None.** With
`screensaver.mode` empty — the user picked "None", which real installs do —
activation still *happens*: `ActivateScreenSaver` flips
`System.ScreenSaverActive` to true and `GUI.OnScreensaverActivated` is
announced. The wake is what goes missing: input ends the screensaver state
(the boolean drops back to false) and **no `GUI.OnScreensaverDeactivated` is
ever announced**. Observed on 21.3 by capturing the JSON-RPC TCP announcement
stream through a full activate → wake cycle in both configurations: with a
saver configured the pair arrives, with mode empty only `OnScreensaverActivated`
does — and a service add-on subscribed via `onNotification` saw the same
absence over a longer horizon.

So a wake hook on `OnScreensaverDeactivated` is dead code on a
screensaver-None box, in production and not just in tests. If the resync
matters, give it a second trigger — `System.OnWake`, or a poll — rather than
trusting the pair to be symmetric.

## Driving the screensaver in a test

The whole cycle can be driven headlessly, with two traps:

```sh
# a saver must be configured, or the wake event above never comes
kodi-remote get Settings.SetSettingValue \
  '{"setting":"screensaver.mode","value":"screensaver.xbmc.builtin.dim"}'
kodi-builtin 'ActivateScreenSaver'
kodi-remote get XBMC.GetInfoBooleans \
  '{"booleans":["System.ScreenSaverActive"]}'          # readback: true
kodi-remote get Input.ExecuteAction '{"action":"noop"}' # wake without pressing
kodi-remote get Settings.SetSettingValue \
  '{"setting":"screensaver.mode","value":""}'           # restore
```

- **Wake with the `noop` action**, which deactivates the screensaver and does
  nothing else. Any real input wakes it too, but `Select` lands on whatever has
  focus and can answer a dialog you did not know was open.
- **kodi.log is not a witness here.** On 21.3 neither activation nor
  deactivation writes a log line at any level, debug included. Read
  `System.ScreenSaverActive`, or watch the announcements.

## What fails silently

- `ActivateScreenSaver` during playback does nothing, with no error.
- Screensaver "None" activates and goes `System.ScreenSaverActive`-true like
  any other, but its wake announces no `GUI.OnScreensaverDeactivated` — a
  wake hook simply never runs there.
- Neither screensaver transition writes a kodi.log line, even at debug.
- A mid-operation quit leaves the screensaver disabled and volume at zero
  permanently.
- An action that does not re-arm fires on every poll while the user is away.
- Fighting a user's volume adjustment during a ramp.

## Open questions

- What a screensaver-None activation *draws*, if anything, was not checked —
  the observation covers state and announcements, not pixels. Whether the
  missing wake announcement reproduces on Piers is also untested.
- DPMS toggling was used on Android; whether the same call is appropriate on a
  Linux desktop session, where a compositor may own DPMS, has not been tested.
- Whether `CECStandby` reliably returns the display afterwards depends on the TV
  and was not characterised across devices.

## See also

- [`kodi-addon-lifecycle`](../kodi-addon-lifecycle/SKILL.md) — surviving the
  shutdown that strands your state
- [`kodi-test-rig`](../kodi-test-rig/SKILL.md) — the device-level screen settings
  that otherwise end every long test early
