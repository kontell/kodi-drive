---
name: kodi-binary-settings
description: >
  Build a settings UI for a binary Kodi add-on, including action buttons the API
  does not support. Use when a C++ add-on needs a Login, Test Connection or Reset
  button, when a settings action must open a dialog, or when deciding between
  global and per-instance settings. Explains the missing callback in the binary
  settings ABI and the script round-trip that works around it.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega"]
    platform: ["Linux x86_64"]
    date: "2026-08-13"
    method: observed
---

# Settings in a binary add-on

## The gap

The binary settings ABI delivers **only value-change callbacks** — `SetSetting`,
`SetInstanceSetting*`. There is:

- **no action-button-press callback**
- **no builtin to write an add-on setting**
- **no way for the add-on to close its own settings dialog**, or to learn that it
  closed

So anything shaped like "the user pressed a button and something should happen"
has no native route. A Python add-on has one; a binary add-on does not.

## Why a self-resetting toggle does not work

The obvious workaround is a boolean the add-on resets after reading it. It
compiles, and it breaks at runtime for a specific reason.

**The callback fires while the settings dialog is still open**, and the settings
dialog is modal. Any modal your action opens — a `Select`, a `Keyboard`, a
progress dialog — then fights the still-open settings dialog.

If your action needs no dialog at all, the toggle is fine. If it needs input, it
is not.

### The problem is the open settings dialog, not modals in general

Worth stating plainly, because the section above invites the wrong conclusion:
**modal `Select` and `YesNo` dialogs work fine from a PVR menu hook.** No
round-trip is needed there — nothing modal is already on screen.

The workaround below exists *only* for settings action-buttons, which fire while
the settings dialog is up. Do not carry it into menu-hook code.

Menu hooks have their own limits, which are different ones — see
[`kodi-pvr-addon`](../kodi-pvr-addon/SKILL.md).

## The round-trip that does work

Use an action control that closes settings first, then re-enters through the
value-change callback:

```xml
<setting id="login" type="action">
  <control type="button" format="action">
    <label>30xxx</label>
    <close>true</close>
  </control>
  <data>RunScript(special://home/addons/&lt;id&gt;/resources/scripts/trigger.py,login)</data>
</setting>
```

`trigger.py` then does one thing:

```python
xbmcaddon.Addon().setSetting(sys.argv[1], 'trigger')
```

`<close>true</close>` closes the dialog **before** the script runs, so by the time
your C++ `SetSetting()` callback fires, the modal is gone and your own dialogs are
free to open.

**Use a sentinel value, not a boolean.** Firing only when the value is
`"trigger"` distinguishes a real button press from ordinary settings-save noise,
which otherwise re-runs your action every time the user touches anything. Clear
it immediately after handling.

This is a deliberate workaround for a real API gap, not a hack to be modernised
away. It is worth a comment in the code saying so, because it looks removable.

## The same gap bites playback reporting

Under the stream-properties path, a binary add-on gets **no reliable player-event
callbacks** — so anything that must happen on stop (closing a server-side
session, reporting progress) cannot live in C++ either.

The same answer applies: a companion Python service, which does have
`xbmc.Player` callbacks. That also makes the service the *single* authority for
those calls, which matters when a shared session id must not be closed twice.

## Categorized settings format

Use `settings.xml` with `version="1"` and `<section>` / `<category>` / `<group>`,
with `type="string" | "boolean" | "integer" | "list[string]"`. Read and write
from C++ with:

```cpp
kodi::addon::GetSettingString("id");
kodi::addon::GetSettingInt("id");
kodi::addon::GetSettingBoolean("id");
kodi::addon::SetSettingString("id", value);
```

`instance-settings.xml` and multi-instance support are a separate mechanism. If
your add-on is genuinely single-instance, global settings are simpler and the two
should not be mixed.

Labels are string ids from `resources/language/resource.language.en_gb/strings.po`.

## What fails silently

- A settings action that opens a modal compiles and then does nothing visible,
  because it is fighting the open settings dialog.
- A boolean trigger without a sentinel re-fires on every settings save.
- A C++ stop-handler under the stream-properties path is never called, so
  server-side sessions leak.

## Open questions

- Quick-Connect-style flows that need no modal input *could* run natively via a
  non-modal notification plus background polling. That path was identified but
  not built, so it is untested.
- Whether Kodi 22 added an action callback to the binary settings ABI has not
  been checked.

## See also

- [`kodi-pvr-addon`](../kodi-pvr-addon/SKILL.md) — where the missing player
  callbacks bite hardest
- [`kodi-binary-build`](../kodi-binary-build/SKILL.md) — building the thing
- [`kodi-addon-driving`](../kodi-addon-driving/SKILL.md) — testing a settings
  action without clicking it
