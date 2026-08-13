---
name: kodi-skin-xml
description: >
  Edit Kodi skin XML without silent failures. Use when working on a skin or a
  script add-on's window XML, when an include or control does not appear, when
  navigation between controls stops working, or when a change has no visible
  effect. Covers what a reload does and does not re-read, the parse failure that
  is logged and then ignored, and the layout rules that break when you wrap
  something in a group.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega"]
    platform: ["Linux x86_64"]
    date: "2026-08-13"
    method: observed
---

# Skin XML

Skin XML is the least forgiving surface in Kodi to work on blind, because almost
nothing raises. A broken file renders as a slightly wrong screen.

## `ReloadSkin()` does not re-read `addon.xml`

```sh
kodi-remote reload      # ReloadSkin() — re-reads xml/, nothing else
```

It re-reads the skin's `xml/` directory. It does **not** re-read `addon.xml`, so
a `<res>` change, a version bump, or a new dependency needs a **full Kodi
restart**. See [`kodi-process-control`](../kodi-process-control/SKILL.md).

And note which tree it reads: the **installed** skin, not your working copy. An
edit to a development checkout is invisible until it is copied across. The two
drift, so diff before concluding a change had no effect.

## A malformed include fails silently

Kodi logs a parse error, **drops the include**, renders the window without it,
and carries on. There is no dialog, no missing-file error, and the screen looks
plausible — just missing something.

**A missing element is a parse failure until proven otherwise.** Check the log
first, before re-reading your XML:

```sh
kodi-logtail mark && kodi-remote reload && sleep 4 && kodi-logtail errors
```

`Window Init (<full path>)` lines are the other half of this: they print the
**full path of the XML that actually loaded**, which is how you tell a skin
override from an add-on's own window file.

## A spec-strict validator will reject files Kodi loads fine

Kodi parses window XML with TinyXML — `CXBMCTinyXML` in
`xbmc/guilib/GUIWindow.cpp:130`, and `CXBMCTinyXML2` wrapping `tinyxml2` for
newer paths. It is more permissive than the XML specification.

Observed consequence: a validator built on a strict parser rejected skin files
that Kodi loaded and rendered without complaint. If you build an XML lint into
your skin's CI, expect to have to relax it — or strip comments before parsing —
or it will fail on working files and train everyone to ignore it.

## Grouplist auto-wiring stops at a group

A `grouplist` automatically wires `up`/`down`/`left`/`right` between its **direct
focusable children**. That is what makes a flat control safe to drop into one.

**Wrapping a control in a `<control type="group">` breaks it.** The group is the
direct child, and the auto-wiring does not reach through it — so every caller
must now pass explicit `onup`/`ondown`/`onleft`/`onright`.

The rule that follows: **convert at the call site, never promote a shared include
to the group form.** Promoting it silently breaks navigation everywhere else it
is used.

## Skin variables are first-match-wins

`<variable>` conditions evaluate in order and the **first** match wins. A new
condition added below an existing broader one never fires.

Observed: a badge variable added after `ListItem.IsResumable` and the playcount
conditions never evaluated, because those matched first. The fix is placement,
not logic — which is invisible in a diff that looks correct.

## Coordinates inherit through nested groups

A control inside `<control type="group">` with `<left>70</left>` is positioned
relative to that group. A nominal `x=0` inside it renders at skin x=70.

When a position looks wrong by a constant, walk up the group chain before
adjusting the value — the offset is usually a parent you forgot about.

## Parameterise shared includes rather than forking them

```xml
<include name="Thing">
  <param name="label_width">300</param>
  ...<width>$PARAM[label_width]</width>...
</include>

<include content="Thing">
  <param name="label_width" value="420"/>
</include>
```

Only the call site that needs a change passes one. Forking the include instead
means every future fix has to be applied twice, and the second copy is the one
people forget.

## Two smaller traps

**`Defaults.xml` supplies implicit values.** A `<label>` with no `<font>` gets the
default font from there, not from nothing — so a font change can have effects in
places you did not edit.

**Fontsets must be kept in step.** A skin usually ships more than one fontset. A
change touching a font must be mirrored in all of them, or the skin renders
correctly only for users on the default.

## What fails silently

- A parse error drops an include and renders the window anyway.
- `ReloadSkin()` reads the installed tree, so a dev-tree edit changes nothing.
- A `<res>` change is ignored until a full restart.
- Wrapping a control in a group silently removes grouplist navigation.
- A skin variable placed below a broader match never fires.

## Open questions

- The exact permissiveness difference between TinyXML and a spec-strict parser
  was not pinned down — the observed fact is that a strict validator rejected
  files Kodi rendered, but which construct triggered it (comments containing
  `--` was the hypothesis) was not confirmed against TinyXML's source.
- Whether Kodi 22 has moved window loading fully to `tinyxml2`, and whether that
  changes the tolerance, has not been checked.

## See also

- [`kodi-skin-res-scaling`](../kodi-skin-res-scaling/SKILL.md) — coordinate
  spaces, and which XML file wins when two have the same name
- [`kodi-screenshot-review`](../kodi-screenshot-review/SKILL.md) — confirming a
  skin change actually rendered
- [`kodi-logs`](../kodi-logs/SKILL.md) — finding the parse error
