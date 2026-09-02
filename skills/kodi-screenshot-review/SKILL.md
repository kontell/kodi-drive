---
name: kodi-screenshot-review
description: >
  Take a Kodi screenshot and actually read it, rather than filing it next to a
  claim of success. Use whenever you are verifying a visual change, comparing
  before and after, or about to say a skin edit worked. Covers when to shoot so
  you do not catch an animation, what to look for in the image, what an
  "identical" diff is really telling you, and what to do when Kodi's own
  screenshot action produces no file and no log line (Kodi 22).
license: CC-BY-SA-4.0
metadata:
  category: access
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64"
  verified-date: "2026-09-02"
  verified-method: "observed"
---

# Screenshot review

A screenshot is not a receipt. Taking one proves Kodi was alive; it proves
nothing about the change until it has been **read**. Treat review as its own step
with its own output.

## Take

```sh
kodi-shot                 # downscaled to 1280 wide, path printed
kodi-shot --raw           # original resolution
kodi-shot --width 1920    # custom width
```

Then **read the file back**. An unread screenshot is worth nothing — do not take
one and move on.

### When no file appears (Kodi 22)

On Kodi 22 the screenshot action is asynchronous: `TakeScreenshot()` submits a
capture to the render capture service and does the folder lookup, naming and
write in a callback — and that callback **returns silently when the capture
delivered no pixels** (`xbmc/utils/Screenshot.cpp:148-176` at
`22.0b1-Piers-911-g8a80976219`: `if (!result.pixels) return;` runs before the
"Saving screenshot" log line). So `Input.ExecuteAction {"action":"screenshot"}`
answers `OK`, `debug.screenshotpath` is set and writable, and nothing appears —
no file, no warning, no error. `kodi-shot` reports it as "no new screenshot
appeared". A capture that produced pixels always logs
`Saving screenshot <path>` at debug level, so **the absence of that line is the
diagnosis**: the render system captured nothing. Observed on a Piers flatpak
using the X11 windowing system and running as a window on a desktop rather than
fullscreen; whether a fullscreen X11 Kodi 22 captures is not settled (see
Open questions).

The way round it is to grab the window from the X server instead, on the Kodi
host, by window id:

```sh
export DISPLAY=:0
xwininfo -root -tree | grep -E '^\s+0x[0-9a-f]+ "Kodi"'
#   0x6a00002 "Kodi": ("Kodi" "Kodi")  1142x642+0+0  +38+1340
import -window 0x6a00002 shot.png          # ImageMagick; -resize 1280x to downscale
```

`import -window <id>` captures exactly that window. **Never grab the root
window** on a shared display: that is the whole desktop, terminals and browsers
included, and it goes straight into a transcript.

Kodi's X11 window carries **no `_NET_WM_PID`** (`xprop -id <id> _NET_WM_PID` →
"not found"), same `WM_CLASS` and title on every instance, so two Kodis on one
display cannot be told apart from X properties alone. Grab each `"Kodi"` window
and identify them by content, or run one at a time.

Let the UI settle first, or you will misread a frame mid-animation:

| After | Wait |
|---|---|
| navigation | a few hundred ms |
| opening a dialog or context menu | ~1200 ms |
| a skin reload | ~4 s |

## Read

Work through the image deliberately, in this order:

1. **Where is focus?** Find the highlighted control. If it is not the one you
   intended to act on, everything you were about to conclude is void — navigate
   again and re-shoot.
2. **Is the thing you changed actually on screen?** The right widget row, the
   right section — not a similar-looking neighbour one row up.
3. **What is around it?** Layout regressions show up as clipped labels,
   overlapping cards, a widget pushed off-screen — usually in the elements you
   were *not* editing.
4. **Does it contradict what you expected?** Say so out loud. A screenshot that
   disagrees with your prediction is the most valuable output of the loop, and
   the easiest to explain away.

When comparing menus, dialogs, or lists, **enumerate the entries** in your
response rather than summarising as "looks right". Differences hide in the
entries a list is *missing*, and those are invisible unless written down.

## Compare

```sh
before=$(kodi-shot)
# make the change, reload, navigate back to the same view
after=$(kodi-shot)
kodi-diff "$before" "$after"
```

`kodi-diff` masks the clock and applies a threshold, so **"identical" means the
UI genuinely did not move.** That is a signal, not a null result — it usually
means a reload silently failed, an edit went to the wrong tree, or a `<visible>`
condition never evaluated true.

When it reports `changed`, read the diff image too. It localises *what* moved,
which is often not what you expected to move.

The comparison is only meaningful if both shots are of the same view: same
window, same section, same widget row, same focused item. Navigate back
deliberately — do not assume a reload left you where you were.

## Report

Show the user what you saw, in words, alongside the image.

> "Filtering works, one card, resume bar intact"

is a finding. "See screenshot" is not — the user did not watch the loop run and
cannot reconstruct it from a file path.

## What fails silently

- An unread screenshot proves nothing but looks like evidence in a transcript.
- A shot taken mid-animation shows a state that never really existed.
- Two shots of *different* views compare cleanly and mean nothing.
- Focus on the wrong control invalidates every conclusion downstream, and the
  image looks perfectly normal.

## Open questions

- The settle times above are rules of thumb from one skin on one machine. A
  slower device — a TV box, a Pi — will need longer, and the failure mode is a
  misread rather than an error, so err high there.
- The silent no-pixels capture was seen on one Kodi 22 build (a Piers flatpak,
  X11 windowing, windowed on a desktop). Whether the same Kodi captures when
  fullscreen, on Wayland, or on GBM has not been checked; the log line is the
  test either way.
- The X-Resource extension maps X clients to process ids and would tell two
  Kodi windows apart; the box this was seen on had no `xrestop`, `wmctrl`,
  `xdotool` or python3-xlib to query it with, so that route is untested.

## See also

- [`kodi-ui-navigation`](../kodi-ui-navigation/SKILL.md) — getting focus where
  you meant before you shoot
- [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) — for anything with state behind it,
  which a picture cannot show
