---
name: kodi-architecture
description: >
  How Kodi is put together at runtime — the app thread and what must not block it,
  the thread pools, how work crosses threads, and how add-ons attach. Use before
  debugging anything that hangs, freezes, or happens in the wrong order, or when
  you need to reason about which thread your code is on. Explains why so many Kodi
  bugs present as "it stopped, with no error".
license: CC-BY-SA-4.0
metadata:
  category: orientation
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: sourced
---

# How Kodi fits together

Enough of the runtime model to reason about ordering and blocking. For *finding*
code, see [`kodi-source-map`](../kodi-source-map/SKILL.md).

## One app thread, and everything else works around it

`main()` (`xbmc/platform/posix/main.cpp`) calls `XBMC_Run`, which ends in
`CApplication::Run()`. That thread then loops in `CApplication::FrameMove`
(`Application.cpp:1811`) doing input, GUI state and rendering.

**That thread renders. Block it and Kodi freezes.** Not "gets slow" — the UI stops
repainting and stops accepting input, which is what a user reports as "Kodi has
hung".

Almost every architectural feature below exists to keep work off it.

### `CApplication` is a set of components, not one class

Behaviour is split under `xbmc/application/` — `ApplicationPlayer`,
`ApplicationPowerHandling`, `ApplicationVolumeHandling`, `ApplicationSkinHandling`,
`ApplicationSettingsHandling`, `ApplicationPlayerCallback`,
`ApplicationStackHelper`. Look there before concluding something is not
implemented.

## `CServiceBroker` is how everything reaches everything

A static service locator with 47 accessors. There is no dependency injection to
trace: any subsystem can reach any other through it, from any thread.

The upside is navigational — one header lists the whole system. The consequence is
that **you cannot tell from a call site which thread you are on**, so that has to
be reasoned about explicitly rather than read off the code.

## Getting onto the app thread: `CApplicationMessenger`

Work that must happen on the app thread — opening a dialog, starting playback,
changing windows — is posted there:

| Call | Behaviour |
|---|---|
| `PostMsg` | fire and forget |
| `SendMsg` | **blocks the caller until the app thread runs it** |

`SendMsg` from the app thread itself, or while holding a lock the app thread
wants, is a deadlock. `IsProcessThread()` tells you which side you are on.

This is also why ordering surprises happen: a stop posted from one thread does not
take effect until the app thread reaches it, which can be **~100 ms later** — long
enough for a subsequent operation to start first. See
[`kodi-playback-resume`](../kodi-playback-resume/SKILL.md).

## The job system: background work, with a pool

`CJobManager` (`xbmc/utils/JobManager.h` on 21; `xbmc/jobs/` on 22) runs a pool of
`CJobWorker` threads with a per-priority cap. Texture loading, library scanning,
directory fetches and playback callbacks all go through it.

Two properties matter:

- **Workers age out when idle**, and are respawned on demand.
- **A blocked worker is not obviously distinguishable from an idle one**, which is
  the root of the Kodi 22 dispatch stall in
  [`kodi-known-defects`](../kodi-known-defects/SKILL.md) — a callback that blocks
  can take the whole job system down with no log line at all.

**Never block in a job callback.** It is not your thread to hold.

## Announcements: one shared bus

`CAnnouncementManager` (`xbmc/interfaces/AnnouncementManager.cpp`) fans events —
player, library, system, GUI — to every registered `IAnnouncer`, which includes
JSON-RPC clients and every Python add-on.

**Delivery happens after the change is applied, on a thread every add-on shares.**
Both halves have consequences, and they are in
[`kodi-announcements`](../kodi-announcements/SKILL.md).

## Add-ons attach in three different ways

| Kind | Mechanism | Runs |
|---|---|---|
| **Python** | `XBPython` + SWIG bindings in `xbmc/interfaces/legacy/` | its own interpreter thread |
| **Binary** | C ABI via `xbmc/addons/kodi-dev-kit/` | in-process, in Kodi's address space |
| **Skins** | XML parsed by `guilib/` | on the app thread, at render time |

The distinction is not cosmetic:

- A **binary** add-on shares Kodi's process. An escaped exception or a
  `std::terminate` takes Kodi down with it — see
  [`kodi-binary-build`](../kodi-binary-build/SKILL.md).
- A **Python** add-on cannot crash Kodi that way, but it holds the **GIL**, so one
  misbehaving add-on can freeze every other Python add-on while C++ carries on
  normally. That asymmetry is the fastest way to tell the two apart when
  diagnosing — see [`kodi-freeze-diagnosis`](../kodi-freeze-diagnosis/SKILL.md).
- A **skin** error is rendered around: a bad include is dropped and the window
  draws without it.

### Python interpreters are reused, opportunistically

`CScriptInvocationManager` keeps **one** `m_lastInvokerThread`
(`ScriptInvocationManager.cpp:183-189`). If it is reusable for the next script it
is handed over; otherwise it is released and a fresh one is created.

One thread, system-wide, first-come. That is why interpreter reuse is a real
speed-up on a cold click and unreliable as a guarantee, and why a parked
interpreter holds stale modules. See
[`kodi-addon-manifest`](../kodi-addon-manifest/SKILL.md) and
[`kodi-plugin-handles`](../kodi-plugin-handles/SKILL.md).

## Storage

`CDatabase` (`xbmc/dbwrappers/`) backs `CVideoDatabase` and `CMusicDatabase`, over
SQLite or MySQL. Textures are a third database. All are **per-profile** except the
texture cache. See [`kodi-library-data`](../kodi-library-data/SKILL.md).

`filesystem/` implements the VFS: `special://` resolution, network protocols, and
the add-on-provided filesystems. Anything taking a path goes through it, which is
why a slow network share can stall things that look unrelated to networking.

## The shape of a Kodi bug

Most of the hard ones are one of these:

1. **Something blocked a thread it did not own** — the app thread, a job worker,
   the announcement thread.
2. **Something assumed ordering that is not guaranteed**, because the work crossed
   a thread boundary.
3. **Something failed in a layer that recovers by rendering around it**, so there
   is no error to find.

Reach for [`kodi-freeze-diagnosis`](../kodi-freeze-diagnosis/SKILL.md) for the
first, and note that the third is why "there is nothing in the log" is weak
evidence in Kodi specifically.

## Open questions

- The component split under `xbmc/application/` was read on 21.3; Kodi 22 may have
  moved more out of `CApplication`.
- Rendering itself — `windowing/`, `guilib/` render passes, the GL/GLES backends —
  is not covered here. It has not been needed for add-on or skin work so far.

## See also

- [`kodi-source-map`](../kodi-source-map/SKILL.md) — where to look for any of this
- [`kodi-announcements`](../kodi-announcements/SKILL.md) — the event bus in detail
- [`kodi-known-defects`](../kodi-known-defects/SKILL.md) — where these properties
  have already gone wrong upstream
