---
name: kodi-ui-navigation
description: >
  Navigate Kodi's UI blind without firing actions at the wrong control. Use
  whenever you are sending key presses to a Kodi you cannot watch — driving a
  skin, answering a dialog, reaching a setting, or stepping a list. Covers lists
  that wrap instead of clamping, the dialogs whose focus defaults you can exploit,
  where pagedown silently stops working, and why addon settings.xml lies about
  what you just changed.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega"]
    platform: ["Linux x86_64"]
    date: "2026-08-13"
    method: observed
---

# Navigating blind

Key presses go into a UI you cannot see. The most expensive mistake available is
assuming focus landed where you intended, then firing `ok` at the wrong control
and drawing a conclusion from the result.

**After any burst of navigation, screenshot and confirm the focused item before
the action that matters.** Focus highlight is visible in the shot. See
[`kodi-screenshot-review`](../kodi-screenshot-review/SKILL.md).

When lost, `kodi-remote debug` toggles an overlay showing the active window id
and focused control id — which tells you exactly which XML file and control you
are actually in.

## Lists wrap; they do not clamp

Over-counting does not stop at the last row. It comes back round to the top. So
`down` × 14 on a ten-item context menu leaves focus on **item 4**, not item 10,
and the `ok` after it fires something you never saw.

This is the worst failure mode here because it *acts* rather than failing, and
the action it picks is arbitrary. In one session this silently added two
favourites and toggled a setting, all discovered only afterwards.

**Count rows off a screenshot, never off a guess, and re-shoot before the `ok`
that matters.**

## `pageup`/`pagedown` clamp in a select dialog

In a `Dialog.select`, page keys do **not** wrap — they clamp. That makes them the
safe way to cross a long list: ten `pageup`s on a 22-page list from page 9 land
on row 0, not somewhere near the bottom.

A long `Dialog.select` also tells you where you are. The footer reads
`193 items - 9/22`, so page size is `ceil(total/pages)` and any row index becomes
a deterministic number of page keys plus a couple of `down`s. Read the footer,
compute, then screenshot to confirm the last step — rather than stepping 82 times
and hoping.

## A settings list is a different control, and `pagedown` gives up partway

On a 21-row settings category, two `pagedown`s moved focus from row 1 to row 11
and **the third moved nothing** — two identical screenshots, which reads like a
dropped keypress rather than the control declining to move.

Use the wrap instead. A settings list *does* wrap on `up`/`down`, so `up` from
the first row lands on the last — the cheapest way to reach a setting appended to
the end of a category.

The wrap doubles as a row count: 12 `down`s from row 11 landing on row 2 says
there are 21 rows, without scrolling through them.

## Dialog focus defaults worth exploiting

| Dialog | Default focus | To reach the other thing |
|---|---|---|
| Yes/No | **No** | `left` then `ok` |
| Multiselect | the rows | `up` reaches OK; `right` reaches Cancel |
| Settings list | a row | `right` **twice** to reach OK/Cancel |

The settings list needs two `right`s because the scrollbar is a focusable control
in between. The first `right` leaves no row highlighted and no button highlighted
either, which reads exactly like nothing happened.

Also in a settings list, `left` does not step a spinner's value — it leaves the
list entirely for the category column.

Screenshot between dialogs regardless: a skin can reorder buttons, and one
EventServer key can answer a whole dialog cascade with defaults.

## A settings dialog is free to experiment in

Nothing is written until OK. Toggle whatever you need to observe — dependent
visibility, spinner ranges, help text — then **Cancel to discard the lot**.

## Do not confirm a settings change by reading `settings.xml`

Kodi holds add-on settings in memory and persists the file lazily. Pressing OK
does not necessarily rewrite it.

Measured: a toggle was flipped and committed with OK while the file's mtime
stayed **two days old** and its value stayed the pre-change one, indefinitely.

The in-memory value is the real one, and it is what every add-on process reads —
`xbmcaddon.Addon().getSetting*` queries the core, so a separate plugin invocation
sees the new value while the file still shows the old one.

Read it back through add-on code instead: fire a route that renders the setting,
or reopen the settings dialog and look at the control. The file is only
trustworthy in the disable → edit → enable cycle, where the add-on is down and
Kodi has no in-memory copy to win with. See
[`kodi-addon-driving`](../kodi-addon-driving/SKILL.md).

## What fails silently

- A wrapped list acts on an arbitrary control instead of erroring.
- The third `pagedown` in a settings list does nothing, indistinguishable from a
  dropped keypress.
- The first `right` in a settings list highlights nothing at all.
- `settings.xml` reports a stale value indefinitely, with a stale mtime to match.

## Open questions

- Whether the `pagedown` stall in settings lists is row-count dependent, or
  happens at a fixed offset, has not been isolated — only the 21-row case was
  measured.
- Skins may reorder dialog buttons. The defaults above were observed on an
  Estuary-derived skin and have not been checked against others.

## See also

- [`kodi-screenshot-review`](../kodi-screenshot-review/SKILL.md) — reading the
  shot you just took
- [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) — confirming state rather than pixels
