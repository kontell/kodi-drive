---
name: kodi-idle-screensaver
description: >
  Detect idleness and control the screen from a Kodi add-on — dim it, blank it,
  or turn the display off — without stranding the user's settings. Use when
  building a sleep timer, a screen-off feature, or anything that suppresses the
  screensaver, and when a feature must survive Kodi being killed mid-operation.
  Covers the screensaver that will not fire during video, and the crash breadcrumb
  that prevents leaving settings changed.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega"]
    platform: ["Linux x86_64", "Android TV"]
    date: "2026-08-13"
    method: observed
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

## What fails silently

- `ActivateScreenSaver` during playback does nothing, with no error.
- A mid-operation quit leaves the screensaver disabled and volume at zero
  permanently.
- An action that does not re-arm fires on every poll while the user is away.
- Fighting a user's volume adjustment during a ramp.

## Open questions

- DPMS toggling was used on Android; whether the same call is appropriate on a
  Linux desktop session, where a compositor may own DPMS, has not been tested.
- Whether `CECStandby` reliably returns the display afterwards depends on the TV
  and was not characterised across devices.

## See also

- [`kodi-addon-lifecycle`](../kodi-addon-lifecycle/SKILL.md) — surviving the
  shutdown that strands your state
- [`kodi-test-rig`](../kodi-test-rig/SKILL.md) — the device-level screen settings
  that otherwise end every long test early
