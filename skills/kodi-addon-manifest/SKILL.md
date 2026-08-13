---
name: kodi-addon-manifest
description: >
  Get addon.xml right, including the parts Kodi ignores without telling you. Use
  when writing or debugging an addon.xml, when a setting or flag appears to have
  no effect, when a context item never shows up, or when a dependency is not
  installed. Covers the element that only works in one extension point, why
  extension order is load-bearing, and the visibility syntax that fails the whole
  expression.
license: CC-BY-SA-4.0
metadata:
  category: python-addon
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
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

## The first `<extension>` decides your LibPath

An add-on's `LibPath` comes from its **first** `<extension>` element, and that is
what `RunScript` resolves. So extension order is load-bearing, not cosmetic.

An add-on that is both a script and a service must declare the script extension
first, or `RunScript` resolves to the wrong entry point.

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
- Extension order changing what `RunScript` resolves.
- An optional dependency simply not being there.
- A parenthesised `<visible>` failing the whole expression, so the item vanishes.
- `<dependencies>` on a `list[string]` setting unregistering the referenced setting.
- `start="login"` never firing on a single-profile install.

## Open questions

- Whether the `<dependencies>` on `list[string]` behaviour is fixed in Kodi 22
  has not been retested — it was bisected on 21.3 only.
- Whether `LibPath` still derives from the first extension in Kodi 22 has not
  been re-verified against 22 source.

## See also

- [`kodi-plugin-handles`](../kodi-plugin-handles/SKILL.md) — the other half of
  the invoker-reuse story, and how it can hang a caller forever
- [`kodi-addon-driving`](../kodi-addon-driving/SKILL.md) — bouncing an add-on to
  pick up changes
- [Kodi wiki: addon.xml](https://kodi.wiki/view/Addon.xml) — the reference this
  deliberately does not duplicate
