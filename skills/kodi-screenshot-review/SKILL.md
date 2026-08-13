---
name: kodi-screenshot-review
description: >
  Take a Kodi screenshot and actually read it, rather than filing it next to a
  claim of success. Use whenever you are verifying a visual change, comparing
  before and after, or about to say a skin edit worked. Covers when to shoot so
  you do not catch an animation, what to look for in the image, and what an
  "identical" diff is really telling you.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega"]
    platform: ["Linux x86_64"]
    date: "2026-08-13"
    method: observed
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

## See also

- [`kodi-ui-navigation`](../kodi-ui-navigation/SKILL.md) — getting focus where
  you meant before you shoot
- [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) — for anything with state behind it,
  which a picture cannot show
