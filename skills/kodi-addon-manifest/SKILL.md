---
name: kodi-addon-manifest
description: >
  Get addon.xml right, including the parts Kodi ignores without telling you. Use
  when writing or debugging an addon.xml, when a setting or flag appears to have
  no effect, when a context item never shows up, or when a dependency is not
  installed. Covers the element that only works in one extension point, which
  extension RunScript runs, and the visibility syntax that fails the whole
  expression.
license: CC-BY-SA-4.0
metadata:
  category: python-addon
  verified-kodi: "21.3 Omega, 22.0b2 Piers"
  verified-platform: "Linux x86_64"
  verified-date: "2026-10-08"
  verified-method: "sourced"
---

# addon.xml, and what Kodi silently ignores

`addon.xml` fails quietly. A misplaced element is not an error — it simply never
takes effect, and nothing is logged either way.

## `<reuselanguageinvoker>` works in exactly one place

It must be inside `<extension point="xbmc.addon.metadata">`. Put it under
`xbmc.python.pluginsource` — where it reads as though it belongs — and it is
**never parsed at all**.

Confirmed in `xbmc/addons/addoninfo/AddonInfoBuilder.cpp`. The parse at line 531
sits inside a block gated at line 389:

```cpp
if (point == "kodi.addon.metadata" || point == "xbmc.addon.metadata")
```

so `AddExtraInfo("reuselanguageinvoker", ...)` never runs for any other extension
point, and `ExtraInfo()` never contains the key.

```xml
<extension point="xbmc.addon.metadata">
  <reuselanguageinvoker>true</reuselanguageinvoker>
</extension>
```

Getting it right is worth real time: a root listing went from **0.62–0.91 s to
0.17–0.25 s** on Kodi 21.

Two things to know once it works:

- **Reuse is opportunistic, not guaranteed.** Kodi keeps one reusable invoker
  thread system-wide and releases it as soon as any other script runs. Lazy
  imports still earn their keep on a cold click.
- **A code change does not take effect on the next click.** The parked
  interpreter holds the old modules in `sys.modules`, so copying new files in
  changes nothing until that thread is discarded. An add-on disable/enable bounce
  does it.

## `RunScript(<id>)` runs the script extension, wherever it sits

`RunScript(<addon id>,…)` does not run the add-on's first extension. It asks for
the add-on as a script, trying four extension points in this order and running
the `library=` of the first one the add-on declares:

`xbmc.python.script` → `xbmc.python.weather` → `xbmc.python.lyrics` →
`xbmc.python.library`

That is `xbmc/interfaces/builtins/AddonBuiltins.cpp:245-255` at `22.0b2-Piers`,
which hands the matched type to `CAddon::LibPath()`
(`xbmc/addons/Addon.cpp:637-648`) to pick that extension's library. `21.3-Omega`
has the same code at `AddonBuiltins.cpp:244-254` and `Addon.cpp:640-651`.
Position in the file plays no part.

So an add-on whose first extension is something else entirely can still be run
by id. Observed on 22.0b2, on a binary PVR add-on declaring `kodi.pvrclient`,
then `xbmc.service`, then:

```xml
<extension point="xbmc.python.library" library="resources/scripts/probe.py"/>
```

```sh
kodi-builtin 'RunScript(<id>,step2,afterRescan)'
```

```
debug <general>: CPythonInvoker(30, <ADDONS>/<id>/resources/scripts/probe.py): start processing
 info <general>: KOFIN-RUNSCRIPT-PROBE argv=['probe.py', 'step2', 'afterRescan']
```

The arguments arrive from `sys.argv[1]` on. The add-on's type did not change:
`Addons.GetAddonDetails` still answered `kodi.pvrclient`, and `Addons.GetAddons`
listed it under `xbmc.python.library` in addition, under neither
`xbmc.python.script` nor `xbmc.addon.executable`.

**What the first extension does decide** is the add-on's main type and its
*master* library (`xbmc/addons/addoninfo/AddonInfoBuilder.cpp:611` at
`22.0b2-Piers`, `:588` at `21.3-Omega`). `RunScript(<id>)` falls back to the
master library only when the add-on declares none of the four points, and says
so:

```
warning <general>: RunScript called for a non-script addon '<id>'. This behaviour is deprecated.
```

On a binary add-on the master library is the shared object, so the fallback runs
nothing. That line was the whole result of `RunScript(<id>,…)` on the PVR add-on
above before it had the library extension.

**An `addon.xml` edited in place is not read until a rescan.** With the new
extension already on disk, the same call still took the fallback and logged the
warning. After `UpdateLocalAddons()` it ran the script.

## Kodi does not install optional dependencies

If your add-on genuinely needs a companion, it must be a hard `<import>`. There
is no soft-dependency mechanism that results in the dependency being present.

## `<visible>` conditions

**Group with square brackets, not parentheses.** Parentheses are infolabel
argument syntax. Using them fails the *entire* expression to parse — logged as
"Error parsing boolean expression" — and the symptom is simply that your context
item never appears.

```xml
<visible>[String.IsEqual(Window(Home).Property(x),true) + !Player.HasVideo]</visible>
```

**A `<visible>` condition cannot read an add-on setting.** Mirror the setting into
a window property from your service, and gate on the property.

**Test the condition without opening a single menu.** `XBMC.GetInfoBooleans`
evaluates any condition string against the focused list item, so you can point a
media window at a listing, focus a row, and ask whether your context item would
appear — for every row kind in a loop, and for two versions of the expression
side by side. It is the difference between checking one menu you happened to
think of and checking all of them.

```sh
kodi-builtin 'ActivateWindow(Videos,videodb://movies/titles/,return)'
kodi-remote post Input.Down
kodi-remote post XBMC.GetInfoBooleans '{"booleans": [
  "String.IsEqual(ListItem.DBTYPE,movie)",
  "[String.IsEqual(ListItem.DBTYPE,movie) + !String.IsEmpty(ListItem.DBID)]",
  "[String.IsEqual(ListItem.DBTYPE,movie) + String.IsEmpty(ListItem.DBID)]",
  "(String.IsEqual(ListItem.DBTYPE,movie))"]}'
```

On a focused library movie (`DBTYPE=movie`, `DBID=3`) that answers `True`,
`True`, `False`, `False`. The last one is the parenthesis trap above, caught in
one call rather than as an item that mysteriously never appears. Note what that
means: **an unparseable condition answers `False` here, indistinguishable from one
that parsed and evaluated false.** The log line "Error parsing boolean expression"
is what separates the two.

Two things this does not do. It evaluates in the *current window* context rather
than the context menu's, which is what makes it usable at all, but means a
condition reading `Container.FolderPath` answers for the window you are looking
at. And it tells you the condition's value, not that Kodi will draw the item —
`CContextMenuManager` also drops a duplicate item, so confirm the real menu once
with a screenshot after the sweep says yes.

## Settings schema

In settings format `version="1"`, `visible="false"` must be a **child element**,
not an attribute. The attribute form is invalid and renders a stray `1` in the
settings UI rather than hiding anything.

**Never attach `<dependencies>` to a `list[string]` setting.** On Kodi 21 this
silently unregisters the setting the condition references — bisected live on 21.3.

## `start="login"` is not startup

`<extension point="xbmc.service" start="login">` fires on **profile switch**, not
on normal Kodi startup. A service that must run from boot needs
`start="startup"`.

## `<provides>` does not choose the player

`<provides>video</provides>` controls only whether the add-on appears under *Video
add-ons* in the browser. The player core is selected at playback time from the
ListItem's info tag.

Getting this backwards has a specific symptom: an audio add-on that declares
`video` makes the **i** (info) button a no-op in the video browser, because Kodi
opens `DialogVideoInfo` for items carrying only music tags.

## What fails silently

- `<reuselanguageinvoker>` in the wrong extension point: no log line either way.
- `RunScript(<id>)` on an add-on with no script-type extension: one deprecation
  warning, and nothing runs.
- An extension added to an installed `addon.xml`: the old manifest keeps
  answering until `UpdateLocalAddons()`.
- An optional dependency simply not being there.
- A parenthesised `<visible>` failing the whole expression, so the item vanishes.
- `<dependencies>` on a `list[string]` setting unregistering the referenced setting.
- `start="login"` never firing on a single-profile install.

## Open questions

- Whether the `<dependencies>` on `list[string]` behaviour is fixed in Kodi 22
  has not been retested — it was bisected on 21.3 only.
- The script-plus-service case — `xbmc.service` first, `xbmc.python.script`
  second — was read from source and not run. What was run is
  `xbmc.python.library` in third place on a binary add-on, on 22.0b2 only.

## See also

- [`kodi-plugin-handles`](../kodi-plugin-handles/SKILL.md) — the other half of
  the invoker-reuse story, and how it can hang a caller forever
- [`kodi-addon-driving`](../kodi-addon-driving/SKILL.md) — bouncing an add-on to
  pick up changes
- [Kodi wiki: addon.xml](https://kodi.wiki/view/Addon.xml) — the reference this
  deliberately does not duplicate
