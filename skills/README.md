# Skill catalogue

Every skill is one topic. Load the one you need — you do not need to read this
file first, and neither does an agent: the [Agent Skills
spec](https://agentskills.io/specification) loads every skill's name and
description at startup, so an agent already knows what is here.

This catalogue is for browsing. It is generated from the skills themselves by
`scripts/build-index.py`, grouped by each skill's `metadata.category`.

See [`../README.md`](../README.md) for how to install and use these, and
[`../CONTRIBUTING.md`](../CONTRIBUTING.md) for the bar a new one has to clear.

<!-- BEGIN SKILL INDEX -->

## Start here

*The map, and turning a vague complaint into a diagnosis.*

- [`kodi-architecture`](kodi-architecture/SKILL.md) — How Kodi is put together at runtime — the app thread and what must not block it, the thread pools, how work crosses threads, and how add-ons attach.
- [`kodi-orientation`](kodi-orientation/SKILL.md) — Start here for any Kodi work.
- [`kodi-source-map`](kodi-source-map/SKILL.md) — Find your way around Kodi's C++ source quickly — where each subsystem lives, the naming conventions that make grep work, and the single class that indexes everything.
- [`kodi-triage`](kodi-triage/SKILL.md) — Turn a vague Kodi complaint into a diagnosis.

## Getting hold of a Kodi

*Finding one, driving it, and seeing what it did.*

- [`kodi-adb`](kodi-adb/SKILL.md) — Drive Kodi on Android and Android TV over ADB — screenshots, logs, installing a build, restarting the app, and pulling databases.
- [`kodi-connect`](kodi-connect/SKILL.md) — Find a Kodi on the network and get control of it — JSON-RPC, EventServer, ADB, or SSH — and store its address and credentials safely.
- [`kodi-jsonrpc`](kodi-jsonrpc/SKILL.md) — Use Kodi's JSON-RPC API as ground truth instead of guessing from screenshots.
- [`kodi-screenshot-review`](kodi-screenshot-review/SKILL.md) — Take a Kodi screenshot and actually read it, rather than filing it next to a claim of success.
- [`kodi-test-rig`](kodi-test-rig/SKILL.md) — Stand up a throwaway Kodi an agent can restart, misconfigure, and break.
- [`kodi-ui-navigation`](kodi-ui-navigation/SKILL.md) — Navigate Kodi's UI blind without firing actions at the wrong control.

## Working out what happened

*Logs, freezes, defects, and isolating a bad add-on.*

- [`kodi-clean-profile`](kodi-clean-profile/SKILL.md) — Isolate a Kodi problem by reproducing it in a clean profile with no add-ons, then bisect to find the culprit.
- [`kodi-freeze-diagnosis`](kodi-freeze-diagnosis/SKILL.md) — Work out why Kodi froze, hung, or stopped responding — including getting native backtraces off an unrooted Android TV box.
- [`kodi-known-defects`](kodi-known-defects/SKILL.md) — Kodi and inputstream.adaptive defects confirmed by investigation, with their symptoms, upstream status, and how to recognise each from a log.
- [`kodi-logs`](kodi-logs/SKILL.md) — Read kodi.log usefully — turn on debug logging without the on-screen overlay, find the log on any platform, grep for the right severity, and read a crashlog.
- [`kodi-performance`](kodi-performance/SKILL.md) — Make a Kodi add-on fast on the hardware people actually run it on.
- [`kodi-process-control`](kodi-process-control/SKILL.md) — Stop, restart, and measure a Kodi process without killing your own shell or measuring the wrong one.
- [`kodi-profiles`](kodi-profiles/SKILL.md) — Switch Kodi profiles from a script, and enable add-ons in the profile you actually meant.

## Playback and streams

*Getting Kodi to play the right thing, in the right place, at the right rate.*

- [`kodi-inputstream`](kodi-inputstream/SKILL.md) — Choose between inputstream.adaptive and inputstream.ffmpegdirect, and get seeking and timing right.
- [`kodi-paplayer`](kodi-paplayer/SKILL.md) — Control Kodi's audio player (PAPlayer) safely, especially while it is paused.
- [`kodi-playback-resume`](kodi-playback-resume/SKILL.md) — Hand Kodi an item so the right player opens it, in the right window, at the right position.
- [`kodi-playback-tempo`](kodi-playback-tempo/SKILL.md) — Change playback rate with pitch correction, and find out why it silently does nothing.
- [`kodi-pvr-addon`](kodi-pvr-addon/SKILL.md) — Write a Kodi PVR client that plays, records and reports correctly.
- [`kodi-pvr-menu-hooks`](kodi-pvr-menu-hooks/SKILL.md) — Add context-menu entries to a binary PVR add-on, and know what they can and cannot do.

## Writing a Python add-on

*The manifest, the lifecycle, and the ways an add-on hangs Kodi.*

- [`kodi-addon-driving`](kodi-addon-driving/SKILL.md) — Install, enable, and exercise a Kodi add-on without navigating menus — fire plugin routes directly, send it service commands, change its settings, and simulate an offline server.
- [`kodi-addon-lifecycle`](kodi-addon-lifecycle/SKILL.md) — Survive being started, stopped, updated and superseded.
- [`kodi-addon-manifest`](kodi-addon-manifest/SKILL.md) — Get addon.xml right, including the parts Kodi ignores without telling you.
- [`kodi-announcements`](kodi-announcements/SKILL.md) — React correctly to Kodi's notifications — Player.OnStop, Playlist.OnClear, OnAdd and friends — over JSON-RPC or in an add-on's onNotification.
- [`kodi-idle-screensaver`](kodi-idle-screensaver/SKILL.md) — Detect idleness and control the screen from a Kodi add-on — dim it, blank it, or turn the display off — without stranding the user's settings.
- [`kodi-plugin-handles`](kodi-plugin-handles/SKILL.md) — Close your plugin handle, or hang the caller forever.

## Writing a binary add-on

*Building it so it loads on someone else's machine.*

- [`kodi-android-ndk`](kodi-android-ndk/SKILL.md) — Cross-compile a Kodi binary add-on and its dependencies for Android.
- [`kodi-binary-build`](kodi-binary-build/SKILL.md) — Build a Kodi binary add-on that installs on the Kodi versions you meant, on the systems your users have.
- [`kodi-binary-settings`](kodi-binary-settings/SKILL.md) — Build a settings UI for a binary Kodi add-on, including action buttons the API does not support.

## Skinning

*Skin XML and the coordinate spaces behind it.*

- [`kodi-keymaps`](kodi-keymaps/SKILL.md) — Bind keys and remote buttons in Kodi, and understand why an add-on cannot ship a keymap.
- [`kodi-skin-res-scaling`](kodi-skin-res-scaling/SKILL.md) — Understand Kodi's skin coordinate spaces and which XML file wins when two share a name.
- [`kodi-skin-xml`](kodi-skin-xml/SKILL.md) — Edit Kodi skin XML without silent failures.

## Kodi's own data

*The databases and the artwork cache.*

- [`kodi-database-writing`](kodi-database-writing/SKILL.md) — Write to Kodi's own library databases without corrupting them or wedging Kodi.
- [`kodi-library-data`](kodi-library-data/SKILL.md) — Kodi's own SQLite databases — where they live, which are per-profile, how to read one safely, and which user-facing operations destroy add-on data.
- [`kodi-texture-cache`](kodi-texture-cache/SKILL.md) — Serve artwork Kodi caches efficiently, and understand when caching saves nothing at all.

## Shipping it

*Versions, releases, and getting a change accepted upstream.*

- [`kodi-addon-release`](kodi-addon-release/SKILL.md) — Package and release a Kodi add-on without shipping a broken or incomplete zip.
- [`kodi-contributing`](kodi-contributing/SKILL.md) — Get a change accepted into Kodi itself, or an add-on into the official repository.
- [`kodi-versions-abi`](kodi-versions-abi/SKILL.md) — Pick a version number and an API level that the Kodi versions you care about will actually accept.

## Adjacent systems

*Not Kodi, but things Kodi add-ons routinely talk to.*

- [`jellyfin-client`](../adjacent/jellyfin-client/SKILL.md) — Write a Kodi add-on that talks to a Jellyfin or Emby server without losing sync state or playing the wrong stream.

## Working with this repo

*Contributing what a session learned, and keeping the repo from silting up.*

- [`audit`](audit/SKILL.md) — Sweep kodi-drive for the decay that per-PR checks cannot catch — duplicate coverage, claims verified against a Kodi nobody runs any more, skills nothing links to, and defects recorded but never filed upstream.
- [`contribute`](contribute/SKILL.md) — Turn what this session learned into a kodi-drive pull request, or into an issue when the evidence does not reach the bar.

<!-- END SKILL INDEX -->

Add-on-specific knowledge lives in [`../addons/`](../addons/); knowledge about
non-Kodi systems lives in [`../adjacent/`](../adjacent/).
