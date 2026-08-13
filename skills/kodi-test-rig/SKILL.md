---
name: kodi-test-rig
description: >
  Stand up a throwaway Kodi an agent can restart, misconfigure, and break. Use
  before letting an agent loose on a Kodi anyone actually watches things on, when
  you need to test Android-specific behaviour, or when you want a reproducible
  baseline. Covers using an old Android phone as a test box, the screen and
  screensaver settings that otherwise interrupt every long run, and keeping the
  rig disposable.
license: CC-BY-SA-4.0
metadata:
  category: access
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64, Android TV"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# A Kodi you can afford to break

**Do not test on the Kodi you watch things on.** An agent working properly will
restart it, wipe profiles, install broken builds, change settings, and leave
experiments behind. That is what it is *supposed* to do, and it is miserable if
the box also has to be usable that evening.

A throwaway rig also makes results trustworthy. On a real install you can never
be sure whether the thing you just observed was your change or one of forty
accumulated add-ons.

## Options, cheapest first

**An old Android phone.** The best value here by a distance. Kodi runs from the
Play Store or a sideloaded APK, ADB gives you logs, screenshots, installs, and
restarts, and it is the only way to test Android-specific behaviour — which
genuinely differs, particularly around the filesystem and process lifecycle. It
costs nothing if you already have a drawer phone.

**A second Kodi on your desktop, in portable mode.** Keeps its data beside the
binary rather than in `~/.kodi`, so it cannot disturb your real install:

```sh
kodi --portable
```

**A spare Android TV box or stick.** Closest to what most users actually run,
which makes it the best rig for reproducing a user's report.

**A VM or container.** Reproducible and snapshottable, but Kodi wants a GPU and a
display, so this is more setup than it looks.

## Settings to change immediately on a phone

A phone will otherwise sleep partway through every long run, and an agent waiting
on a bounded poll will read the resulting silence as a failure.

- **Kodi's own screensaver: set it to `None`.** Settings > Interface >
  Screensaver > Screensaver mode. Kodi will otherwise dim or blank the screen
  mid-test and your screenshots capture the screensaver.
- **Android display timeout: as long as it goes**, or Developer Options > "Stay
  awake" while charging. This matters more than the Kodi setting, because the
  device turning its screen off stops rendering entirely.
- **Disable the lock screen** for the duration, or every wake needs a human.

Worth doing on a TV box too. It is critical on a phone, where the defaults are
aggressive.

## Turn on what an agent needs

Do this once, on the rig, and never think about it again:

| Setting | Path |
|---|---|
| Allow remote control via HTTP | Settings > Services > Control |
| Allow programs on other systems to control Kodi | Settings > Services > Control |
| Announce services to other systems | Settings > Services > General |
| Debug logging without the overlay | `advancedsettings.xml`, see [`kodi-logs`](../kodi-logs/SKILL.md) |

Settings level must be **Standard** or higher or the Services section is hidden.

Then confirm from the machine the agent runs on:

```sh
kodi-discover
```

## Keep it disposable

The value of the rig is that you can throw it away. Preserve that:

- Take a copy of `userdata/` once it is set up the way you like. Restoring it is
  faster than reconfiguring, and it gives every run the same baseline.
- Prefer a **profile** for each experiment over reconfiguring the main one — see
  [`kodi-clean-profile`](../kodi-clean-profile/SKILL.md).
- Do not connect it to a media library you care about. A library scan against a
  real NAS is slow, and Clean Library on a plugin-populated library deletes rows.

## Reproducing a user's problem

Match what actually matters, in this order: **Kodi version**, then **platform**,
then skin, then add-on set. Behaviour genuinely diverges across all four, and
version and platform account for most of it — a bug that reproduces on Linux 21
and not Android 22 has told you something useful.

## What fails silently

- A phone sleeping mid-run looks like a hung Kodi to any polling loop.
- Kodi's screensaver appears in screenshots and reads as a rendering bug.
- A rig configured from a copy of a real install carries the problem across.

## Open questions

- Whether Kodi's `--portable` flag behaves identically across Linux, Windows, and
  macOS has not been checked here; only Linux was used.
- Kodi on a phone and Kodi on an Android TV box differ in input handling and
  window management. How far a phone result generalises to a TV box has not been
  characterised.

## See also

- [`kodi-connect`](../kodi-connect/SKILL.md) — getting the agent talking to it
- [`kodi-adb`](../kodi-adb/SKILL.md) — driving the Android rig
- [`kodi-triage`](../kodi-triage/SKILL.md) — what the rig is for
