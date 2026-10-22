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
  verified-kodi: "21.3 Omega, 22.0b2 Piers, 22.0rc1 Piers"
  verified-platform: "Linux x86_64"
  verified-date: "2026-10-22"
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

The settings dialog gives the same result as the builtin. With focus on the
button, Select closed the dialog, ran the script with `testConnection` in
`sys.argv[1]`, and produced the same success line. So did a full restart of Kodi
with the extension in the manifest.

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
- **`RunScript(<id>,…)` while the add-on is disabled** runs nothing either.
  Kodi logs `error <general>: ExecuteAsync - Not executing non-existing script
  <id>`: the builtin resolves its first argument with `OnlyEnabled::CHOICE_YES`
  on every branch (`xbmc/interfaces/builtins/AddonBuiltins.cpp:243-262` at
  `22.0b2-Piers`), while Configure stays available on a disabled add-on's info
  dialog (`xbmc/addons/gui/GUIDialogAddonInfo.cpp:273-274`). Observed on
  22.0rc1: the client disabled, Configure opened from the add-on browser, a
  script button pressed, that one line and nothing else. `xbmcaddon.Addon('<id>')`
  refuses a disabled add-on the same way (`xbmc/interfaces/legacy/Addon.cpp:69`),
  so the path form of `RunScript` runs the file and then has no way to write
  the setting. Every button built on this round-trip, and the picker above,
  needs the add-on enabled; a native control does not.

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

### The list type is the price of the multi-select control

The obvious fix is to redeclare the setting as `type="string"`, which the switch
has a case for, and keep the `<control type="list" format="string">` with
`<multiselect>true</multiselect>`. Kodi loads that without complaint, draws the
same control, and the `Unknown setting type` line for that setting goes away.
Run on 22.0rc1 against a PVR add-on with one of its three list settings
redeclared this way, the transfer logged two lines instead of three, at load and
again when the settings dialog closed:

```
debug <general>: Calling TransferSettings for: <Add-on name>
error <general>: Unknown setting type of '<second list setting>' for <Add-on name>
error <general>: Unknown setting type of '<third list setting>' for <Add-on name>
```

What it does not do is hold more than one value. Clicking the control opened the
select dialog in multi-selection mode; ticking two entries and pressing OK closed
the select dialog and stored nothing — the control, reopened at once, showed
nothing ticked. Ticking one entry and pressing OK stored that one, and closing
the settings dialog wrote it:

```
<setting id="<setting id>">hevc</setting>
```

Sourced: `CGUIControlListSetting::OnClick` collects the dialog's selected items
and then switches on the setting's type; the `String` case returns `false` when
more than one was selected, before anything is written
(`xbmc/settings/windows/GUIControlSettings.cpp:772-775` at `22.0b2-Piers`). The
`Integer` case does the same (`:766-767`). Only `SettingType::List` takes the
whole selection (`:778-779`).

A comma-joined value cannot come in from the file either. With `h264,hevc`
stored for the string-typed setting, Kodi refused it at load and rewrote the
file with the default at the next save:

```
warning <CSettingsManager>: unable to read value of setting "<setting id>"
warning <CAddonSettings[0@<id>]>: failed to load value "h264,hevc" for setting <setting id>
```

Sourced: `CSettingString::CheckValidity` tests the value against the `<options>`
whenever their labels are string ids, and `allownewoption` relaxes that only for
options with literal labels (`xbmc/settings/lib/Setting.cpp:1498-1516`). The
dialog cannot show such a value either: for a string setting it ticks the one
option equal to the whole value (`GUIControlSettings.cpp:282`), so none is
ticked.

So none of the four types the transfer switch names carries a multi-select, and
the error lines are what a multi-select list costs a binary add-on on 21 and 22.
Read the value in `SetSetting`, which receives `ToString()` of the list;
`GetSettingString` refuses a list with `Setting '<id>' is not a string`
(`xbmc/addons/interfaces/AddonBase.cpp:495`).

### The multi-select that survives the transfer: a string behind a script button

The route that keeps the picker and loses the error line is a `string` setting
with no `<options>`, behind an action button whose script shows the multi-select
and writes the comma-joined result:

```xml
<setting id="<setting id>" type="string" label="30xxx" help="30xxx">
  <level>0</level>
  <default>a,b,c</default>
  <constraints>
    <allowempty>true</allowempty>
  </constraints>
  <control type="button" format="action">
    <data>RunScript(<id>,pick-<setting id>)</data>
  </control>
</setting>
```

```python
addon = xbmcaddon.Addon('<id>')
current = addon.getSetting('<setting id>').split(',')
preselect = [i for i, v in enumerate(values) if v in current]
picked = xbmcgui.Dialog().multiselect(heading, labels, preselect=preselect)
if picked is not None:
    addon.setSetting('<setting id>', ','.join(values[i] for i in picked))
```

No `<close>true</close>` and no reopening of settings afterwards: Kodi handles a
script writing a setting while that add-on's settings dialog is open.
`xbmcaddon.Addon.setSetting` first looks for an active add-on settings dialog
for the same add-on and, finding one, posts `GUI_MSG_SETTING_UPDATED` to it
instead of writing the file (`xbmc/interfaces/legacy/Addon.cpp:34-53` at
`22.0b2-Piers`); the dialog calls `FromString` on its own setting
(`xbmc/addons/gui/GUIDialogAddonSettings.cpp:71-92`). The dialog, the script's
`Addon` object and the PVR manager all hold the one running instance, because
`CAddonMgr::GetAddon` swaps the object it builds for the running one
(`xbmc/addons/AddonManager.cpp:627-649`, the swap at `:644`), so there is one
copy of the value. The button itself runs the builtin through the app
messenger with the dialog left open (`xbmc/addons/settings/AddonSettings.cpp:179-220`).

Observed on 22.0rc1, on the PVR add-on above with one list setting redeclared
this way and the C++ untouched:

- Pressing the button ran the script with the settings dialog still open
  (`Window.IsActive(addonsettings)` read `True` inside it), and the multi-select
  opened on top, pre-ticked from the current value.
- Unticking two entries and pressing OK put the new value on the button's
  value label at once; the file was untouched. Pressing the button again
  pre-ticked the unsaved value, so `getSetting` reads the dialog's copy.
- OK on the settings dialog wrote the file and ran the transfer with no line
  for that setting:

```
<setting id="<setting id>">h264_10bit,hevc_rext,av1,mpeg2video,vp9,vc1</setting>
debug <general>: Calling TransferSettings for: <Add-on name>
error <general>: Unknown setting type of '<second list setting>' for <Add-on name>
error <general>: Unknown setting type of '<third list setting>' for <Add-on name>
```

- Cancel on the settings dialog after a pick left the file as it was, and the
  next press of the button pre-ticked the saved value, not the cancelled one:
  the dialog's cancel path reloads the add-on's settings from the file
  (`GUIDialogAddonSettings.cpp:205-209`).

Two things to decide. The button shows the raw value as its second label — the
comma-joined ids, scrolling — unless the control carries
`<hidevalue>true</hidevalue>`. And `getSetting` straight after `setSetting`
still returns the old value, because the dialog applies the message on the GUI
thread; read it back on the next run of the script, not in the same one.

The stored values stay as they were: a `string` with no `<options>` accepts the
comma-joined value a `list[string]` wrote, so a setting moved this way needs no
migration.

`21.3-Omega` carries the same `UpdateSettingInActiveDialog`
(`xbmc/interfaces/legacy/Addon.cpp:33`), the same `GUI_MSG_SETTING_UPDATED`
handler (`xbmc/addons/gui/GUIDialogAddonSettings.cpp:60`) and the same
running-instance swap (`xbmc/addons/AddonManager.cpp:647`); the script route
was not run on it.

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
- A `string` setting behind a multi-select list control: the dialog lets the
  user tick several, OK stores none of them, and a comma-joined value in the
  settings file is replaced by the default.
- A script button, or the picker, pressed in the settings of a disabled add-on:
  one `ExecuteAsync` error line in the log and nothing on screen.
- `getSetting` in the same script run that just called `setSetting` with the
  settings dialog open: the old value, because the update is a queued GUI
  message.

## Open questions

- Quick-Connect-style flows that need no modal input *could* run natively via a
  non-modal notification plus background polling. That path was identified but
  not built, so it is untested.
- Whether Kodi 22 added an action callback to the binary settings ABI has not
  been checked.
- The id form was run on 22.0b2 on Linux only. Omega carries the same resolution
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
