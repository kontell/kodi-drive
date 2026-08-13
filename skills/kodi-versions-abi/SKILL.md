---
name: kodi-versions-abi
description: >
  Pick a version number and an API level that the Kodi versions you care about
  will actually accept. Use when releasing a binary add-on, deciding which Kodi
  branches to support, or working out why a zip installs on one Kodi and not
  another. Covers the acceptance window, the pinned-headers trap that changes your
  declared version with no commit of your own, and when supporting two Kodi
  versions becomes impossible.
license: CC-BY-SA-4.0
metadata:
  category: shipping
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64, Android"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Kodi versions and the ABI window

## The acceptance rule

**Kodi accepts a binary add-on only if its declared API version falls within
`[MIN, current]`** for that instance type, where both numbers come from the Kodi
build doing the installing.

That single rule explains most "why will this not install" questions.

## Kodi releases

| Major | Codename | Notes |
|---|---|---|
| 17 | Krypton | |
| 18 | Leia | |
| 19 | Matrix | Python 3 only from here |
| 20 | Nexus | |
| 21 | Omega | |
| 22 | Piers | |

## Your declared version comes from the headers you built against

`@ADDON_DEPENDS@` is filled from the **checked-out Kodi source's** headers. So an
unpinned `xbmc/xbmc` reference moves your declared
`kodi.binary.instance.<type>` version **with no commit of your own** — and the
resulting zip then stops installing on a Kodi the user already has.

**Pin the Kodi ref per release channel**, e.g. `21.3-Omega` and `22.0b1-Piers`,
and treat changing that pin as a deliberate, reviewed act.

## Cushion, and when it runs out

Observed for the PVR instance type:

| Kodi | Declares | MIN | Cushion |
|---|---|---|---|
| 21 Omega | 8.3.0 | 8.2.0 | yes |
| 22 (beta) | 9.2.0 | 9.2.0 | **none** |

With `MIN == current`, **the day master bumps to 9.3.0/MIN 9.3.0, supporting Beta
1 and supporting master tip become mutually exclusive.** No single build can
satisfy both, and there is no warning before it happens.

Watch upstream's declared floor on a schedule — a weekly job that reads the
current header values and fails when they move is enough. That converts a silent
break into a notification.

## Let the major carry the Kodi version

The upstream binary-add-on convention is that the add-on's **major version is the
Kodi major it targets**: `21.y.z` for Omega, `22.y.z` for Piers.

This is not cosmetic. Before adopting it, two different binaries for two
different Kodi versions carried **identical version strings**, so a repository
had no way to file them apart and users could receive the wrong one.

It also means the upgrade path across channels works by ordinary version
ordering: `0.13.0` → `22.13.0` is an upgrade, so it is offered normally. There is
deliberately no downgrade path.

## Channel branches with no common ancestor

Where the two channels are separate vendor drops rather than a fork, `git log
omega..piers` will never tell you what is missing, and every change crosses by
hand.

That is survivable but invisible until it bites, so record it where someone will
read it, and note on each ported commit which runtime it was actually verified
against. "Verified on Omega; unverified on Piers" is honest and useful; silence
implies both.

## Tag on the wrong branch produces a plausible wrong release

A tag pushed on the wrong channel branch otherwise yields a complete, entirely
believable release that a repository files into the wrong directory.

**Guard on the tag's major matching the branch's channel** in CI.

## Python add-ons

Simpler: `<import addon="xbmc.python" version="3.0.0"/>` declares the API level.
Kodi 19+ is Python 3 only, and contributions requiring Python 2 are no longer
accepted anywhere.

## What fails silently

- An unpinned Kodi ref changes your declared ABI version between builds.
- A zip built against newer headers installs on your dev box and not on users'.
- `MIN == current` upstream removes the possibility of supporting two versions,
  with no notice.
- A tag on the wrong branch produces a plausible release filed in the wrong place.

## Open questions

- The cushion table above is for the PVR instance type on the versions listed.
  Other instance types (inputstream, screensaver, visualisation) have their own
  numbers and have not been tabulated here.
- Whether Kodi 22's final release keeps `MIN == current` for PVR is not settled;
  that was the beta's state.

## See also

- [`kodi-addon-release`](../kodi-addon-release/SKILL.md) — getting the artifact
  built and published once the version is right
- [Kodi wiki: Add-on rules](https://kodi.wiki/view/Add-on_rules) — the official
  repository's requirements
