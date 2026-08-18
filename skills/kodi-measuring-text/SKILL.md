---
name: kodi-measuring-text
description: >
  Measure rendered text width from a Python add-on, using hidden auto-width
  labels as rulers. Use when sizing a window, panel or control to its text at
  runtime, when a char-count estimate keeps producing panels that are too wide
  for ordinary lines and too narrow for wide ones, or when a getWidth() read
  stops tracking a control you are resizing. Covers the wrapper cache that
  freezes every geometry read after the first, the pool-of-ids pattern that
  works around it, the cache-defeating trick that looks better and segfaults
  Kodi, and why none of this may run from a window callback.
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
labels, and Python can read the result back. The read has two sharp edges,
and the obvious workaround for the first one crashes Kodi.

## The ruler: auto-width labels bound to a property

Declare probe labels in the window's XML. `<visible>false</visible>` does not
stop them being measured, and the text must arrive via an infolabel binding —
Python `setLabel()` cannot work, for the cache reason below:

```xml
<control type="label" id="3901">
	<width>auto</width>
	<height>44</height>
	<font>font13</font>
	<visible>false</visible>
	<label>$INFO[Window(Home).Property(myaddon.probe.text)]</label>
</control>
<!-- ...more identical labels, 3902, 3903, ... one per measurement -->
```

Then, from the add-on's own thread (never a callback — see below):

```python
home = xbmcgui.Window(10000)
home.setProperty("myaddon.probe.text", text)
xbmc.sleep(400)                       # one settle, then exactly one read
width = self.getControl(3901).getWidth()   # spends id 3901 forever
home.setProperty("myaddon.probe.text", "")
```

The reported width is the true rendered width in skin coordinates, in the
font the active skin resolves — verified within 1% of FreeType advances
computed from the skin's own TTF:

| text | FreeType, NotoSans 30px | Kodi reports |
|---|---|---|
| 37-char mixed-case line | 528 | 534 |
| `MW` × 15 | 827 | 832 |
| `Twelve chars` | 181 | 183 |
| same 37 chars at a 33px font | 581 | 574 |
| `""` | 0 | 1 |

The same lines measured 584 on a different skin's fontset — the point of
measuring rather than estimating.

## The trap: geometry reads are frozen at first fetch

A Python `Control` wrapper copies x, y, width and height out of the live
control **once, at the first `getControl()` ever made for its id**, and every
later read returns that snapshot. `Window.getControl()` also returns the
*same cached wrapper* for a given id, so "fetching again" changes nothing.
Observed: a label re-rendered at 534 → 832 → 183 px reported 534 forever
through the wrapper that fetched it first.

Hence the **pool**: each measurement spends one virgin id. Set the property,
sleep one settle (400 ms was reliable; there is no safe way to poll, because
the first read is the only read), fetch the next unspent id, done. Keep the
property empty between measurements — every unspent label then sits at width
1, so a read of 1 means the renderer had not shown the text yet: that id is
lost, but the caller knows to retry rather than trusting a stale number.

Writes are not cached: `setWidth()`/`setPosition()` reach the live control
every call. The asymmetry is what makes the freeze easy to misdiagnose — the
control visibly moves while its reported geometry never changes.

## The trick that defeats the cache — and segfaults Kodi

A **fresh `xbmcgui.Window(dialog_id)` wrapper** has an empty control cache,
so its first `getControl()` re-reads live geometry. This genuinely works —
four consecutive re-reads through fresh wrappers tracked four text changes
(534 → 832 → 183 → 534) in light, ~400 ms-spaced use.

**Do not build on it.** Two integration runs that constructed fresh wrappers
at a 40 ms polling cadence each **segfaulted Kodi within seconds, at the
same crash site** (`kodi.bin + 0xa24af7` on the Debian 21.3 build,
2:21.3+dfsg-1.2+b2, called directly from a Python vectorcall) — once from a
window's onInit, once from a plain RunScript thread. The per-call failure is
a race with small probability: light probing survives, real use does not.
The pool costs one XML line per measurement and uses only calls that months
of add-on code and these probes exercised crash-free.

## Callbacks are your own thread, re-entered

The first crashed run showed the mechanism in its stack:

```
#8  XBMCAddon_xbmcgui_WindowXMLDialog_Director::onInit()
#9  XBMCAddon::RetardedAsyncCallbackHandler::makePendingCalls()
#10 XBMCAddon::xbmc::sleep(long)
```

`onInit` was delivered **inside the owning thread's `xbmc.sleep`** —
`makePendingCalls` pumps window callbacks whenever that thread sleeps or
waits. Two consequences:

- A callback that itself sleeps re-enters the pump from inside the pump,
  against a window still being activated. Keep onInit and onAction trivial;
  run measurement from the add-on's own loop after the window is up.
- There is no cross-thread race between a service loop and its window's
  callbacks: they are the same thread. State shared between tick() and
  onAction needs no lock.

## What fails silently

- **A warm `getWidth()` returns a plausible, stale number.** Nothing marks it
  as a snapshot; it was correct once, and sizing arithmetic built on it is
  wrong by exactly the amount the text changed.
- **A read taken before the renderer showed the text** measures the previous
  text. Keeping the property empty between measurements turns this into a
  detectable width-1 read; without that, it is silent.
- **Char-count width estimates.** They fail in both directions at once, so
  spot-checking with one typical song hides it: the panel merely looks padded
  until a wide-glyph line hangs past its backing, or past the screen edge.
- **The re-attach trick in light testing.** It passes a hand-rolled probe
  every time and kills Kodi in production cadence — the failure is
  probabilistic per call, so a clean trial run proves nothing.

## Verifying it

With any WindowXMLDialog showing whose XML contains probe labels 3901 and
3902 as above, from the script's own thread:

```python
home = xbmcgui.Window(10000)
for cid, text in ((3901, "short"), (3902, "a much, much longer line")):
    home.setProperty("myaddon.probe.text", text)
    xbmc.sleep(400)
    print(text, self.getControl(cid).getWidth())
    home.setProperty("myaddon.probe.text", "")
```

Two ids reporting two different widths proves the ruler; re-reading 3901
afterwards and getting its first number again proves the cache.

## Open questions

- Verified on Omega only. The wrapper cache is long-standing API behaviour,
  but Piers has not been checked — the verify block above settles it in a
  minute.
- The crash site is unsymbolized (`kodi.bin + 0xa24af7`, no dbgsym): which
  of `getCurrentWindowDialogId()`, the `Window(existingId)` constructor, or
  `getControl()` on such a wrapper actually races is not established, only
  that the combination at polling cadence is fatal and the pool pattern that
  avoids all three is not.
- `<width max="N">auto</width>` measured identically to plain auto below the
  cap; whether the reported width tops out at the cap once text exceeds it
  was not tested.

## See also

- [`kodi-skin-xml`](../kodi-skin-xml/SKILL.md) — the XML side: what a window
  file can declare, and what a reload does and does not re-read
- [`kodi-freeze-diagnosis`](../kodi-freeze-diagnosis/SKILL.md) — reading the
  crashlog that tells you which thread and which call, as done here
- [`kodi-screenshot-review`](../kodi-screenshot-review/SKILL.md) — verifying
  the resulting geometry by looking, which this skill's numbers do not replace
