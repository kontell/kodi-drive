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
  verified-kodi: "21.3 Omega, 22.0b1 Piers, 22.0rc1 Piers"
  verified-platform: "Linux x86_64, Android"
  verified-date: "2026-10-08"
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
| 22 beta 1, beta 2, RC1 | 9.2.0 | 9.2.0 | **none** |

With `MIN == current`, **the day upstream bumps to 9.3.0/MIN 9.3.0, supporting
Beta 1 and supporting upstream's tip become mutually exclusive.** No single
build can satisfy both, and there is no warning before it happens.

## The window is per interface, and an add-on imports several

Your instance type is not the only interface with a `[MIN, current]` window. A
built `addon.xml` imports one line per interface it compiled against, each with
its own pair:

```xml
<import addon="kodi.binary.global.main" minversion="2.0.3" version="2.0.3"/>
<import addon="kodi.binary.global.general" minversion="1.0.4" version="1.0.5"/>
<import addon="kodi.binary.global.gui" minversion="5.15.0" version="5.15.1"/>
<import addon="kodi.binary.global.filesystem" minversion="1.1.11" version="1.1.11"/>
<import addon="kodi.binary.global.network" minversion="1.0.0" version="1.0.4"/>
<import addon="kodi.binary.global.tools" minversion="1.0.0" version="1.0.4"/>
<import addon="kodi.binary.instance.pvr" minversion="9.2.0" version="9.2.0"/>
```

That is a PVR add-on built against `22.0b1-Piers`: seven interfaces, six of them
`kodi.binary.global.*`. In `versions.h` they are `ADDON_GLOBAL_VERSION_<NAME>`
and `ADDON_GLOBAL_VERSION_<NAME>_MIN`, beside the `ADDON_INSTANCE_VERSION_*`
pair for the instance type.

**They move independently.** Beta 1, beta 2 and RC1 carry identical values for
all seven. After RC1, the head of xbmc's `Piers` branch took `global.main` to
2.0.4 while PVR stayed at 9.2.0. Its minimum stayed at 2.0.3, so a build that
declares 2.0.3 is still inside the window — but a watcher that reads only the
instance type would not have seen it move at all, and would see nothing on the
day one of these minimums rises.

Watch every interface the built `addon.xml` imports. And treat a value the
watcher cannot read as a failure rather than a skipped line: a macro renamed
upstream is drift too.

## After a release branches, master is the next Kodi

"Upstream's tip" stops meaning `master` partway through a release. xbmc cut a
`Piers` branch for Kodi 22; `version.txt` on that branch reads 22.0 RC1, and on
`master` it reads 23.0 ALPHA1. From then on the tip that matters to a Kodi 22
add-on is the head of `Piers`.

A scheduled check still pointed at `master` keeps running and keeps passing or
failing, about the wrong Kodi. Nothing marks the changeover.

The official repository's builder has the same seam, from the other side — see
[`kodi-binary-repo`](../kodi-binary-repo/SKILL.md).

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
- A watcher that reads only your instance type misses the global interfaces,
  which have windows of their own.
- A watcher pointed at `master` goes on answering after the release branches,
  about the next Kodi.
- A tag on the wrong branch produces a plausible release filed in the wrong place.

## Open questions

- The cushion table above is for the PVR instance type on the versions listed.
  Other instance types (inputstream, screensaver, visualisation) have their own
  numbers and have not been tabulated here.
- Whether Kodi 22's final release keeps `MIN == current` for PVR is not settled;
  it was still the state at RC1 and at the head of the `Piers` branch on
  2026-10-08.

## See also

- [`kodi-addon-release`](../kodi-addon-release/SKILL.md) — getting the artifact
  built and published once the version is right
- [`kodi-binary-repo`](../kodi-binary-repo/SKILL.md) — the Kodi branch the
  official builder compiles against
- [Kodi wiki: Add-on rules](https://kodi.wiki/view/Add-on_rules) — the official
  repository's requirements
