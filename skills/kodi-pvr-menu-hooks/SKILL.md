---
name: kodi-pvr-menu-hooks
description: >
  Add context-menu entries to a binary PVR add-on, and know what they can and
  cannot do. Use when designing a per-channel or per-recording action, when a hook
  needs to ask the user something, or when deciding whether an add-on can switch
  channels itself. Covers the callbacks the dev kit does not expose, and why a
  hook cannot be added or removed at runtime.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega", "22.0b1 Piers"]
    platform: ["Linux x86_64"]
    date: "2026-08-13"
    method: sourced
---

# PVR menu hooks

A menu hook puts an entry in the context menu for a channel, a recording, a timer
or the add-on's settings. It is the only way a binary PVR add-on offers an action
that is not a setting.

```cpp
AddMenuHook(kodi::addon::PVRMenuhook(1, 30000, PVR_MENUHOOK_CHANNEL));
```

## Hooks are registered at construction, and cannot be removed

The dev kit documents that hook instances "have to be added in `constructor()`",
and — verified against `kodi/addon-instance/PVR.h` on both Omega and Piers —
**there is no `RemoveMenuHook`**. Zero occurrences.

So a setting that enables or disables a feature **cannot** add or remove its hook
in response. The hook is either always present or never present for that run of
Kodi.

Two consequences:

- If a hook only makes sense sometimes, register it always and have the handler
  explain why it is unavailable, rather than trying to hide it.
- A settings change that should change the menu needs an **add-on restart** to
  take effect. Say so in the setting's help text; the user will otherwise assume
  it did nothing.

## Your add-on cannot initiate playback

This is the hard limit, and it rules out the most commonly wanted hook.

**The kodi-dev-kit exposes no `ExecuteBuiltin`, no `PlayMedia`, and no
`Player().play`** — searched across the whole include tree, no hits. The complete
set of add-on-to-Kodi callbacks is the trigger family:

```
TriggerChannelUpdate    TriggerChannelGroupsUpdate    TriggerEpgUpdate
TriggerRecordingUpdate  TriggerTimerUpdate            TriggerProvidersUpdate
```

Those tell Kodi *to re-read data from you*. None of them makes Kodi do anything
else.

So a hook cannot "switch to this channel", "play this recording now", or open a
window. If you need that, the action has to reach Kodi from something that has
those APIs — a companion Python service, which is the same answer as for the
missing playback callbacks in
[`kodi-pvr-addon`](../kodi-pvr-addon/SKILL.md).

## Modal dialogs *do* work from a hook

Worth stating explicitly, because the settings-button workaround in
[`kodi-binary-settings`](../kodi-binary-settings/SKILL.md) invites the opposite
conclusion.

A `Select` or `YesNo` dialog opened directly from a menu hook is fine. **The
problem there was never modals — it was the modal settings dialog already being
on screen.** A menu hook fires with nothing modal open, so it can ask the user
whatever it needs.

Do not carry the `trigger.py` round-trip into hook code. It buys nothing there
and adds a moving part.

## Categories, and what they scope to

`PVR_MENUHOOK_CHANNEL` and `PVR_MENUHOOK_SETTING` are both present on Omega and
Piers. Channel and EPG hooks are **auto-scoped to your own add-on's channels** —
you do not receive, and cannot receive, a hook invocation for another PVR client's
content.

## What fails silently

- A settings change that should show or hide a hook does nothing until restart,
  and nothing says so.
- A hook designed to start playback has no API to do it — discovered at
  implementation time rather than at design time.
- Copying the settings-button round-trip into a hook adds indirection for a
  problem that is not present.

## Open questions

- Whether `PVR_MENUHOOK_RECORDING`, `_TIMER` and `_EPG` categories exist under
  different names was not enumerated exhaustively — only `_CHANNEL` and
  `_SETTING` were confirmed present in both trees. Check the header for the full
  enum before relying on a category not listed here.
- Whether a companion Python service can be invoked *from* a hook cleanly, rather
  than polling for a flag the hook sets, has not been tested.

## See also

- [`kodi-pvr-addon`](../kodi-pvr-addon/SKILL.md) — the rest of the PVR surface,
  and the companion-service pattern
- [`kodi-binary-settings`](../kodi-binary-settings/SKILL.md) — the settings
  action-button workaround, and why it does not apply here
