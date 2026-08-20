---
name: kodi-runtime-geometry
description: >
  Move, resize and animate Kodi controls at runtime from Python — including
  controls a skin owns. Use when a panel must fit content per item, when a
  python-triggered fade or VisibleChange animation silently does nothing, when
  a skin needs a size a user typed, or before writing to controls of a window
  that has been open a while. Covers the stepped-write glide that is the only
  smooth resize there is, the $INFO geometry that renders zero-wide, and the
  use-after-free that segfaults Kodi when the window was closed out from
  under the add-on.
license: CC-BY-SA-4.0
metadata:
  category: python-addon
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-19"
  verified-method: observed
---

# Runtime geometry from Python

Kodi looks like it should let a skin or an add-on size a panel to its
content: labels have auto width, animations exist, properties reach
everywhere. In practice the paths that look easiest fail silently, the one
that works is undocumented, and the failure mode of writing at the wrong
moment is a segfault, not an exception. Everything below was verified live
on 21.3.

## What works: direct writes, and stepped writes for motion

`setWidth`, `setHeight` and `setPosition` reach the live control on every
call (writes are not cached — reads are, see
[`kodi-measuring-text`](../kodi-measuring-text/SKILL.md)). A list given a new
height relayouts to the rows that fit, cleanly.

For *smooth* motion, step the writes from your own thread:

```python
for step in range(1, steps + 1):
    eased = (1 - math.cos(math.pi * step / steps)) / 2
    apply_geometry(round(start + (target - start) * eased))
    xbmc.sleep(25)
```

12 × 25ms steps rendered as a real glide at the full frame rate (43fps
during the test), three cycles of 120 writes, no crash. This is not a
workaround but the only mechanism: the animation system is out of reach
(next section).

**Controls a skin owns can be driven the same way.** A service attached to
the skin's window moved and resized the skin's own list live:

```python
w = xbmcgui.Window(12006)           # the window the skin control lives in
c = w.getControl(9500)              # the skin's list
c.setWidth(400); c.setPosition(150, 10)
```

That is how an add-on gives a skin a size the user typed, since the skin
cannot read one (below). Two caveats: item layouts never re-lay (text stops
centring — shift the whole list instead of narrowing it), and the skin's
window rebuilds its controls from XML every time it loads, so anything
written is silently gone after a reload — re-apply when the window comes
back, detectable by its container becoming addressable again. Construct the
`Window` wrapper once per application, not per poll: wrapper churn at
polling rate is a crasher (see `kodi-measuring-text`).

## What fails silently

- **Python cannot trigger skin animations.** `setVisible(False)` hides a
  control *instantly* even when it carries a `VisibleChange` fade, and
  animations installed with `setAnimations([('visible', ...), ('hidden',
  ...)])` are ignored by `setVisible` just the same — verified in both
  directions with 500ms fades and mid-fade screenshots showing fully
  hidden/shown. Condition-driven visibility animates; python-driven does
  not. The only animations a python window reliably gets are `WindowOpen`
  and `WindowClose`.
- **Skin geometry cannot bind a property.** `<width>$INFO[Window(Home)
  .Property(x)]</width>` parses without complaint and renders the control
  zero-wide (`getWidth()` returns 0, an image draws as a sliver). A skin
  that must react to per-item sizes gets a coarse *class* published in a
  property and switches authored variants on it with `String.IsEqual`
  visibility — those crossfade and conditional-slide normally.
- **Anything you wrote to a skin's controls evaporates on window reload**,
  with nothing to say so; the controls are rebuilt from XML at authored
  geometry.

## What crashes: writing to a window Kodi closed

Kodi can close a python dialog with the add-on's `close()` never running —
`Dialog.Close(all,true)` does it on demand, and something in a live setup
did it unprompted. A closed WindowXML frees its control tree (it is rebuilt
from XML on every open — that is the "Loading skin file" log line each
time), while the add-on's cached Control wrappers keep their pointers. The
next write through one is a use-after-free:

```
#0  XBMCAddon::xbmcgui::Control::setWidth(long)   <- SIGSEGV
#1  (python binding glue) ... CPythonInvoker::execute
```

No `except` catches it; Kodi dies. The add-on's own `closed` flag cannot
know. The defense that held up under `Dialog.Close(all)` plus the
previously-crashing track change:

1. Learn the dialog's id once, from the add-on's own thread, and validate
   it: fetch a sentinel control id only your XML declares through
   `xbmcgui.Window(dialog_id)` — a foreign dialog raises, so a wrong
   topmost guess cannot be adopted.
2. Before every control write, ask Kodi rather than any wrapper:
   `xbmc.getCondVisibility("Window.IsVisible(%d)" % dialog_id)` — cheap and
   repeatable. False means the window is gone: mark it closed and reopen,
   never write.

## Verifying it

With any shown WindowXMLDialog: `Dialog.Close(all,true)` from another
channel, then `Window.IsVisible(<id>)` — false, while the python object's
own state still says open. For the animation trap: give a control a 500ms
`VisibleChange` fade, `setVisible(False)`, screenshot at 250ms — it is
already fully gone.

## Open questions

- What closes a dialog unprompted in a live setup was not identified — the
  observed close did not recur in a 200s soak. `Dialog.Close(all)` from any
  add-on or a remote-control app are candidates.
- Verified on Omega only.
- Whether animation *attributes* (`end=`, `time=`) accept `$INFO` was not
  tested — only geometry tags were.

## See also

- [`kodi-measuring-text`](../kodi-measuring-text/SKILL.md) — the read side:
  measuring rendered text, and the wrapper cache these writes are exempt from
- [`kodi-skin-xml`](../kodi-skin-xml/SKILL.md) — what skin XML can declare,
  and what a reload does and does not re-read
- [`kodi-freeze-diagnosis`](../kodi-freeze-diagnosis/SKILL.md) — getting the
  crashlog stack that names the write, as done here
