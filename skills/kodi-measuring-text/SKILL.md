---
name: kodi-measuring-text
description: >
  Measure rendered text width from a Python add-on, using a hidden auto-width
  label as the ruler. Use when sizing a window, panel or control to its text at
  runtime, when a char-count estimate keeps producing panels that are too wide
  for ordinary lines and too narrow for wide ones, or when a getWidth() read
  stops tracking a control you are resizing. Covers the wrapper cache that
  freezes every geometry read after the first, and the fresh-wrapper trick that
  defeats it.
license: CC-BY-SA-4.0
metadata:
  category: python-addon
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-18"
  verified-method: observed
---

# Measuring rendered text from Python

Sizing a control to its text at runtime looks impossible: `xbmcgui` has no
measure call, so add-ons fall back to `len(text) * K` — and with a
proportional font no constant works. Measured against the skin's own TTF at a
30px font, ordinary mixed-case text averages **14.4 px/char** while upper-case
runs **16.9** and `M`/`W` glyphs reach **28**; a flat 20 px/char both
over-sizes normal lines by ~40% and lets wide-glyph lines overflow the panel.
But Kodi *can* measure text — the renderer already does it for auto-width
labels, and Python can read the result back.

## The ruler: an auto-width label bound to a property

Declare a probe label in the window's XML. `<visible>false</visible>` does not
stop it being measured, and the label must take its text from an infolabel —
Python `setLabel()` cannot be used, for the cache reason below:

```xml
<control type="label" id="915">
	<width>auto</width>
	<height>44</height>
	<font>font13</font>
	<visible>false</visible>
	<label>$INFO[Window(Home).Property(myaddon.probe.text)]</label>
</control>
```

Then, from Python:

```python
xbmcgui.Window(10000).setProperty("myaddon.probe.text", text)
xbmc.sleep(400)  # the width updates when the render loop next processes
width = xbmcgui.Window(dialog_id).getControl(915).getWidth()
```

`dialog_id` is `xbmcgui.getCurrentWindowDialogId()` taken while your dialog is
up (13000 for the first addon dialog). The reported width is the true rendered
width in skin coordinates, in the font the active skin resolves — verified
within 1% of FreeType advances computed from the skin's own TTF:

| text | FreeType, NotoSans 30px | Kodi reports |
|---|---|---|
| 37-char mixed-case line | 528 | 534 |
| `MW` × 15 | 827 | 832 |
| `Twelve chars` | 181 | 183 |
| same 37 chars at a 33px font | 581 | 574 |
| `""` | 0 | 1 |

## The trap: geometry reads are frozen at first fetch

A Python `Control` wrapper copies x, y, width and height out of the live
control **once, at its first `getControl()`**, and every later read returns
that snapshot. `Window.getControl()` also returns the *same cached wrapper*
for a given id, so "fetching again" through the same window object changes
nothing. Observed: a label re-rendered at 534 → 832 → 183 px reported 534
forever through the wrapper that fetched it first.

Two consequences:

- **`setLabel()` then `getWidth()` on one control object can never work** —
  by the time you hold the control object, its width is already frozen. Hence
  the property binding above: the text changes without touching the wrapper.
- **Repeat measurements need a fresh window wrapper per read.** Construct a
  new `xbmcgui.Window(dialog_id)` each time; its control cache starts empty,
  so the first `getControl()` through it re-reads live geometry. Verified
  534 → 832 → 183 → 534 tracking four text changes through one label id.

Writes are not cached: `setWidth()`/`setPosition()` reach the live control
every call. The asymmetry is what makes the freeze easy to misdiagnose — the
control visibly moves while its reported geometry never changes.

## What fails silently

- **A warm `getWidth()` returns a plausible, stale number.** Nothing marks it
  as a snapshot; it was correct once, and sizing arithmetic built on it is
  wrong by exactly the amount the text changed.
- **Char-count width estimates.** They fail in both directions at once, so
  spot-checking with one typical song hides it: the panel merely looks padded
  until a wide-glyph line hangs past its backing, or past the screen edge.
- **The probe label measuring the *previous* text.** The width updates on the
  render loop, not on `setProperty`. Read it too early and you get the old
  measurement with nothing to say so — sleep at least one frame, or poll until
  the value moves.

## Verifying it

With any WindowXMLDialog showing whose XML contains the probe label above:

```python
home, probe = xbmcgui.Window(10000), 915
for text in ("short", "a much, much longer line of text"):
    home.setProperty("myaddon.probe.text", text)
    xbmc.sleep(400)
    print(text, xbmcgui.Window(xbmcgui.getCurrentWindowDialogId())
          .getControl(probe).getWidth())
```

Two different widths proves the ruler; re-reading through a held wrapper and
getting the first number twice proves the cache.

## Open questions

- Verified on Omega only. The wrapper cache is long-standing API behaviour,
  but Piers has not been checked — the verify block above settles it in a
  minute.
- `getCurrentWindowDialogId()` was read with a single addon dialog up. With
  stacked dialogs it presumably names the topmost, which may not be yours.
- `<width max="N">auto</width>` measured identically to plain auto below the
  cap in these probes; whether the reported width tops out at the cap once
  text exceeds it was not tested.

## See also

- [`kodi-skin-xml`](../kodi-skin-xml/SKILL.md) — the XML side: what a window
  file can declare, and what a reload does and does not re-read
- [`kodi-screenshot-review`](../kodi-screenshot-review/SKILL.md) — verifying
  the resulting geometry by looking, which this skill's numbers do not replace
