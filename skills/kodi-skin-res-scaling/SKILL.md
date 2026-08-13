---
name: kodi-skin-res-scaling
description: >
  Understand Kodi's skin coordinate spaces and which XML file wins when two share
  a name. Use when a script add-on's dialog renders at the wrong size inside a
  skin, when a skin declares a non-1080p resolution, or when a window looks
  correct in one skin and broken in another. Explains why a skin must not fork a
  script add-on's window XML, and what a resolution change requires.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega"]
    platform: ["Linux x86_64"]
    date: "2026-08-13"
    method: observed
---

# Coordinate spaces and file precedence

Two rules explain most "it renders at the wrong size" problems, and they interact
in a way that is easy to get backwards.

## A skin declares its own coordinate space

`addon.xml` can declare a logical coordinate space that is not 1080p:

```xml
<res width="2256" height="1269" aspect="16:9" default="true" folder="xml"/>
```

Skin XML is then authored in **those units**, and Kodi maps them to the physical
display. A skin at 2256 wide is not "a 2256-pixel skin" — it is a skin whose
coordinate system is 2256 units wide, whatever the panel is.

## Which files get scaled, and which do not

This is the part that catches people:

| File | Kodi treats its coordinates as |
|---|---|
| An **add-on's** `resources/skins/default/1080i/foo.xml` | a declared 1920×1080 space, **scaled** into the skin's space |
| The **skin's own** `xml/foo.xml` | already in the skin's space, **not scaled** |

So a literal `<width>1920</width>` behaves completely differently depending on
which of the two files it sits in. In a skin declaring 2256 units, that width
renders as about 85% of the screen rather than full width.

An add-on's own window XML therefore works correctly at any skin resolution
without the add-on knowing anything about the skin. That is the design, and it
works — until the next rule intervenes.

## A skin's file wins over the add-on's, by filename

**If a skin ships a file with the same basename as a script add-on's window XML,
Kodi prefers the skin's copy.**

The consequence is severe and non-obvious: fork a script add-on's window XML into
your skin, and you have silently opted that dialog out of the auto-scaling above
— because it is now the skin's file, in the skin's coordinate space, with the
add-on's 1080-based numbers in it.

**Do not fork script-addon WindowXMLs into a skin.** If a dialog needs restyling,
work with the add-on, or accept the default. This is the single rule most worth
taking away from this skill.

Diagnosing it is easy once you know: `Window Init (<full path>)` in the log
prints the file that actually loaded, so it says outright whether the skin's copy
or the add-on's original won.

```sh
kodi-logtail mark
# open the dialog
kodi-logtail grep 'Window Init'
```

## Changing `<res>` needs a full restart

Kodi parses `addon.xml` only when the skin loads. `ReloadSkin()` re-reads `xml/`
and nothing else, so a `<res>` change has no effect at all until Kodi is
restarted — the old resolution stays in force. See [`kodi-skin-xml`](../kodi-skin-xml/SKILL.md).

## A skin cannot edit its own `addon.xml`

Nothing in the skinning engine can rewrite the skin's own manifest, so a skin
cannot offer a resolution switcher by itself.

The working pattern is a **companion script add-on**: the skin exposes a setting,
the script rewrites `addon.xml` and prompts for the required restart. Keep the
displayed value in step with the file using an `<onload>` hook gated on
`System.HasAddon(...)`, or a hand-edited `addon.xml` leaves the UI showing the
wrong resolution.

## What fails silently

- The same literal width renders at two different sizes depending on which file
  it is in.
- A forked WindowXML silently loses auto-scaling and looks broken only at some
  resolutions.
- A `<res>` change has no effect after a reload, with nothing logged.
- A hand-edited `addon.xml` desyncs the skin setting that reports it.

## Open questions

- Whether the skin-wins-by-basename precedence applies to every window type, or
  only to dialogs loaded through the add-on window path, has not been tested
  exhaustively — it was observed for a script add-on's dialog.
- Whether Kodi 22 changed the `1080i` folder convention has not been checked.

## See also

- [`kodi-skin-xml`](../kodi-skin-xml/SKILL.md) — everything else about editing
  skin XML
- [`kodi-process-control`](../kodi-process-control/SKILL.md) — restarting, since
  a reload is not enough here
- [Kodi wiki: Skinning](https://kodi.wiki/view/Skinning) — the reference this
  does not duplicate
