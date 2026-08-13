---
name: kodi-keymaps
description: >
  Bind keys and remote buttons in Kodi, and understand why an add-on cannot ship
  a keymap. Use when a skin or script needs a keyboard shortcut, when a keymap
  file is being ignored, or when a window swallows the keys you expected to
  handle. Covers the three directories Kodi actually scans and the reload action
  that saves a restart.
license: CC-BY-SA-4.0
metadata:
  category: skinning
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: sourced
---

# Keymaps

## Kodi scans exactly three directories

`xbmc/input/keymaps/ButtonTranslator.cpp:75-77`:

```cpp
static std::vector<std::string> DIRS_TO_CHECK = {"special://xbmc/system/keymaps/",
                                                 "special://masterprofile/keymaps/",
                                                 "special://profile/keymaps/"};
```

| Path | |
|---|---|
| `special://xbmc/system/keymaps/` | shipped with Kodi |
| `special://masterprofile/keymaps/` | `userdata/keymaps/` |
| `special://profile/keymaps/` | the same in a single-profile setup |

## An add-on cannot ship a keymap

**A `keymaps/` directory inside a skin or a script add-on has no effect.** Kodi
never looks there, and nothing is logged — the file is simply never read, which
looks identical to a keymap that loaded and did not match.

So a skin-specific or companion-script shortcut has to live in
`userdata/keymaps/`, which is **user-local and not shippable with the add-on**.
Plan for that: either instruct the user to install it, or write it from a service
on first run and tell them you did.

Confirm what actually loaded:

```sh
kodi-logtail grep 'Loading .*keymap'
```

## Reload without restarting

```sh
kodi-builtin 'Action(reloadkeymaps)'
```

`reloadkeymaps` maps to `ACTION_RELOAD_KEYMAPS`
(`xbmc/input/actions/ActionTranslator.cpp:130`), so editing a keymap does not
need a Kodi restart — useful, because the alternative is a restart per iteration.

## A window can claim a key before you see it

Kodi's own keymaps bind keys per window, and a window-level binding wins over
whatever a control might have done with the key.

The consequence worth knowing: **a list drawn in a window whose keymap already
binds the arrow keys cannot be scrolled by hand**, however it is focused. In the
visualisation window, for instance, Kodi's keymap binds the arrows to
`StepBack`/`SkipNext`/`StepForward` for the whole window.

Since an add-on cannot ship a keymap to change that, the way out is an **add-on
window**, which gets ordinary navigation.

## What fails silently

- A keymap shipped inside a skin or add-on is never read, and nothing says so.
- A window-level binding swallows a key before any control sees it, which reads
  as a broken control.

## Open questions

- Whether Kodi 22 adds any further directory to `DIRS_TO_CHECK` has not been
  checked; the citation is from 21.3.
- Whether `reloadkeymaps` picks up a **newly created** file, as opposed to an
  edited one, was not tested separately.

## See also

- [`kodi-skin-xml`](../kodi-skin-xml/SKILL.md) — the rest of skin authoring
- [`kodi-builtins` via `kodi-remote`](../kodi-connect/SKILL.md) — running the
  reload action
