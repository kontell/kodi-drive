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
  category: binary-addon
  verified-kodi: "21.3 Omega, 22.0b2 Piers"
  verified-platform: "Linux x86_64"
  verified-date: "2026-10-08"
  verified-method: "sourced"
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

Declare a script in `addon.xml`, after the binary extension, so that Kodi can run
it by add-on id:

```xml
<extension point="xbmc.python.library" library="resources/scripts/trigger.py"/>
```

Then use an action control that closes settings first, and re-enters through the
value-change callback:

```xml
<setting id="login" type="action">
  <control type="button" format="action">
    <label>30xxx</label>
    <close>true</close>
  </control>
  <data>RunScript(&lt;id&gt;,login)</data>
</setting>
```

`trigger.py` then does one thing:

```python
xbmcaddon.Addon().setSetting(sys.argv[1], 'trigger')
```

`<close>true</close>` closes the dialog **before** the script runs, so by the time
your C++ `SetSetting()` callback fires, the modal is gone and your own dialogs are
free to open.

**Use a sentinel value, not a boolean.** The reason is specific and worth knowing:
**Kodi calls `SetSetting` for _every_ setting when the dialog closes, not only the
ones that changed.** So without a value check, *every* action button fires at
once, every time the user closes settings — including the ones they did not touch.

Firing only on `"trigger"`, and clearing it immediately after handling, is what
makes the button a button. Clearing also prevents a re-fire the next time settings
opens.

**Do not override both `SetSetting` and `SetInstanceSetting*`.** The add-on-level
`SetSetting` already forwards to instances, so implementing both doubles every
callback — and a doubled action button runs your action twice.

This is a deliberate workaround for a real API gap, not a hack to be modernised
away. It is worth a comment in the code saying so, because it looks removable.

### Address the script by add-on id, not by path

`RunScript(special://home/addons/<id>/resources/scripts/trigger.py,login)` runs
the same script, and names a place the add-on is not always in.
`special://home/addons` is one of the roots Kodi loads add-ons from, and
`special://xbmc/addons` is another. From a probe script on a 22.0b2 Flatpak,
asking about the skin that ships with Kodi and about a PVR add-on the user
installed:

```
special://home/addons/skin.estuary/addon.xml exists=False
special://xbmc/addons/skin.estuary/addon.xml exists=True
special://home/addons/<id>/addon.xml exists=True
special://xbmc/addons/<id>/addon.xml exists=False
```

Each was in one root and missing from the other, so a path written against
`special://home/addons` reaches only an add-on that landed there.

`RunScript(<id>,login)` names no directory. Observed on 22.0b2, on a PVR add-on
with a companion service, fired as `RunScript(<id>,testConnection)`:

```
debug <general>: CPythonInvoker(31, <ADDONS>/<id>/resources/scripts/trigger.py): start processing
debug <general>: CPythonInvoker(31):  trigger.py
debug <general>: CPythonInvoker(31):  testConnection
 info <<id>>: <id> - TestConnectionInternal - Test connection successful
```

The last line is the C++ `SetSetting` callback acting on the sentinel. Two things
held alongside it. The add-on stayed a `kodi.pvrclient` — the extra extension
lists it under `xbmc.python.library` as well, and under neither
`xbmc.python.script` nor `xbmc.addon.executable`. And a disable/enable with the
extension in place brought the PVR client and the service back as before, with
the id form still working.

How `RunScript` picks the library, and why its position in `addon.xml` does not
matter, is in [`kodi-addon-manifest`](../kodi-addon-manifest/SKILL.md).

**One add-on, one entry script.** `RunScript(<id>,…)` takes no file name, so every
button arrives at the same `library=` with its action in `sys.argv[1]`. Check
that argument against the list of settings the script exists to poke: `RunScript`
is callable by any add-on or skin, and an unchecked
`setSetting(sys.argv[1], 'trigger')` writes whichever setting the caller names.

### What does not work, so you can stop trying

- **`RunPlugin` and `RunAddon` do nothing** — a PVR add-on is not a plugin.
- **`action=""`** does nothing.
- **`action="SetSetting(...)"`** is not a valid Kodi builtin.
- **`RunScript(<id>,…)` without the `xbmc.python.library` extension** runs
  nothing. Kodi logs `RunScript called for a non-script addon '<id>'. This
  behaviour is deprecated.` and stops there.

`RunScript` is the one that works, because a script *is* something Kodi can run.

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

### A `list[string]` setting logs an error every time settings are handed over

Observed on 22.0b2, on a PVR add-on with three `list[string]` settings: one line
per list setting, at `error` level, when the add-on loads and again whenever a
setting is written —

```
error <general>: Unknown setting type of '<setting id>' for <Add-on name>
```

Sourced: `CAddonDll::TransferSettings` switches on the setting's type with cases
for boolean, integer, number and string, and no case for a list
(`xbmc/addons/binary-addons/AddonDll.cpp:395-469` at `22.0b2-Piers`). A list
lands in `default:` (`:471-488`), which logs that line and then passes
`setting->ToString()` to the add-on's string callback anyway. `21.3-Omega` has
the same switch at `:398` and the same `default:` at `:473`.

So the setting keeps working and the log gains an error that reads like a fault
in the add-on. The lines come from Kodi's side of the transfer, before the
add-on's callback runs.

Labels are string ids from `resources/language/resource.language.en_gb/strings.po`.

## What fails silently

- A settings action that opens a modal compiles and then does nothing visible,
  because it is fighting the open settings dialog.
- A boolean trigger without a sentinel re-fires on every settings save.
- A C++ stop-handler under the stream-properties path is never called, so
  server-side sessions leak.
- `RunScript(<id>,…)` on a binary add-on that declares no script extension: one
  warning in the log, no script run, and a button that does nothing.
- A `list[string]` setting works, and puts an `error` line in the log on every
  settings transfer.

## Open questions

- Quick-Connect-style flows that need no modal input *could* run natively via a
  non-modal notification plus background polling. That path was identified but
  not built, so it is untested.
- Whether Kodi 22 added an action callback to the binary settings ABI has not
  been checked.
- The id form was fired through the EventServer rather than by pressing the
  settings button, on 22.0b2 on Linux only. Omega carries the same resolution
  code — see `kodi-addon-manifest` — and was not run.
- A path-form button on a binary add-on installed under `special://xbmc/addons`
  was not tried. The root listing above says the path finds nothing there; no
  binary add-on was available in that location to press the button on.
- Whether `xbmc.python.script` in place of `xbmc.python.library` would also put a
  binary add-on in the Program add-ons list was not tried.
- The transfer switch has no case for an action setting either. Whether a
  `type="action"` setting therefore logs the same `Unknown setting type` line was
  not run: the add-on the list lines were seen on declares its buttons as
  `type="string"` with a button control.

## See also

- [`kodi-pvr-addon`](../kodi-pvr-addon/SKILL.md) — where the missing player
  callbacks bite hardest
- [`kodi-binary-build`](../kodi-binary-build/SKILL.md) — building the thing
- [`kodi-addon-driving`](../kodi-addon-driving/SKILL.md) — testing a settings
  action without clicking it
