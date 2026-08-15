---
name: kodi-source-map
description: >
  Find your way around Kodi's C++ source quickly — where each subsystem lives,
  the naming conventions that make grep work, and the single class that indexes
  everything. Use whenever you need to check what Kodi actually does rather than
  what the docs say: tracing a behaviour, confirming a claim, or answering "where
  is this implemented".
license: CC-BY-SA-4.0
metadata:
  category: orientation
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: sourced
---

# Finding things in Kodi's source

**3,870 C++ files, 42 MB.** Grepping it blind is slow and the results are noisy.
Three things make it navigable.

## Find the tree first; do not invent a search

Work from a clone of the version you are debugging, not from memory. It is often
already on the machine under a name like `ref/kodi-piers-full` or
`ref/kodi-omega-full`.

1. `ls` those conventional sibling paths. Stop there.
2. If they are absent, ask where the tree is.
3. If there is no tree, ask before cloning. Then:

```sh
git clone --depth 1 --branch 21.3-Omega https://github.com/xbmc/xbmc kodi-omega
```

Once you have the tree, grep *inside it*. `find xbmc -name 'JobManager.*'` is
how you locate a file that moved between majors. `find $HOME -name Player.cpp`
is not.

Everything below is Kodi 21.3, verified against that tree.

## `CServiceBroker` is the index

`xbmc/ServiceBroker.h` is a static service locator with **47 accessors**, and
almost every subsystem is reachable through exactly one of them. Reading that one
header tells you what Kodi is made of:

```
GetActiveAE            GetAddonMgr             GetAnnouncementManager
GetAppComponents       GetAppMessenger         GetBinaryAddonManager
GetContextMenuManager  GetDatabaseManager      GetDataCacheCore
GetFavouritesService   GetGUI                  GetInputManager
GetJobManager          GetMediaManager         GetNetwork
GetPeripherals         GetPlayerCoreFactory    GetPlaylistPlayer
GetPVRManager          GetRenderSystem         GetRepositoryUpdater
GetServiceAddons       GetSettingsComponent    GetTextureCache
GetWeatherManager      GetWinSystem            GetXBPython
```

**Two practical uses.** To find a subsystem, find its accessor. And to find every
*caller* of a subsystem, grep for the accessor rather than the class — callers go
through the broker, so `GetPVRManager()` finds them and `CPVRManager` mostly finds
the implementation.

`GetGUI()` is a second tier: `GetWindowManager`, `GetInfoManager`,
`GetTextureManager`, `GetLargeTextureManager`, `GetColorManager`,
`GetAudioManager`, `GetStereoscopicsManager`.

## Naming conventions that make grep precise

| Prefix | Means | Count |
|---|---|---|
| `C` | concrete class | 3,329 |
| `I` | interface / pure virtual | 399 |
| `m_` | member variable | 15,879 |

So `class CPVRManager` finds a definition, `IAnnouncer` finds an interface you can
implement, and `m_processing` finds state rather than API.

Two greps worth knowing:

```sh
grep -rn "^class C<Thing>"  xbmc --include=*.h   # the definition
grep -rn "::<Method>("      xbmc --include=*.cpp # the implementation
```

The `::` form matters — `Foo(` matches every call site, `::Foo(` matches the
definition and little else.

## Where things live

| Directory | `.cpp` | What |
|---|---|---|
| `cores/` | 280 | players, decoders, audio engine — `VideoPlayer/`, `paplayer/`, `AudioEngine/`, `playercorefactory/` |
| `platform/` | 177 | per-OS code; `platform/posix/main.cpp` holds `int main()` |
| `utils/` | 145 | helpers — check here before writing one |
| `filesystem/` | 119 | VFS, `special://` resolution, network protocols |
| `guilib/` | 106 | controls, windows, skin XML parsing |
| `pvr/` | 94 | live TV, EPG, timers, recordings |
| `interfaces/` | 90 | JSON-RPC, Python, builtins, announcements |
| `addons/` | 86 | add-on manager, binary ABI, `kodi-dev-kit` |
| `windowing/` | 82 | display, resolution, per-backend windowing |
| `video/`, `music/` | 96 | libraries, databases, info scanners |
| `settings/` | 42 | the settings system |
| `dialogs/` | 31 | the shared dialogs |

## Specific starting points

| Question | Start at |
|---|---|
| What runs at startup? | `xbmc/platform/posix/main.cpp` → `XBMC_Run` |
| The frame loop | `CApplication::FrameMove`, `Application.cpp:1811` |
| Which player opens a file | `xbmc/cores/playercorefactory/PlayerCoreFactory.h` — `GetDefaultPlayer(const CFileItem&)` |
| What a window id means | `xbmc/guilib/WindowIDs.h` — 152 defines, `WINDOW_HOME` is 10000 |
| How a skin control is built | `xbmc/guilib/GUIControlFactory.cpp` |
| A JSON-RPC method's real behaviour | `xbmc/interfaces/json-rpc/*Operations.cpp` |
| A Python API's real behaviour | `xbmc/interfaces/legacy/` (SWIG-bound) |
| An add-on manifest field | `xbmc/addons/addoninfo/AddonInfoBuilder.cpp` |
| The library schema | `xbmc/video/VideoDatabase.h`, `xbmc/music/MusicDatabase.h`, both on `CDatabase` |
| Who is told about an event | `xbmc/interfaces/AnnouncementManager.cpp`, `IAnnouncer.h` |

## `Application.cpp` is decomposed, so search the siblings

`CApplication` was split into components under `xbmc/application/`:
`ApplicationPlayer`, `ApplicationPowerHandling`, `ApplicationVolumeHandling`,
`ApplicationSkinHandling`, `ApplicationSettingsHandling`,
`ApplicationPlayerCallback`, `ApplicationStackHelper`.

If a behaviour looks like it should be in `Application.cpp` and is not, it is
almost certainly in one of those.

## Paths move between majors — cite symbols

Directories get reorganised, so a path that is right for one Kodi is wrong for
the next. A live example:

| | Kodi 21 | Kodi 22 |
|---|---|---|
| `JobManager` | `xbmc/utils/JobManager.cpp` | `xbmc/jobs/JobManager.cpp` |

Anyone following a Kodi-22 bug report into a Kodi-21 tree looks in a directory
that does not exist, and `find` is the fix:

```sh
find xbmc -name 'JobManager.*'
```

**Prefer citing a class and method over a path.** `CJobManager::OnJobComplete`
survives a reorganisation; `xbmc/jobs/JobManager.cpp:412` does not survive even a
patch release.

## The JSON-RPC and Python surfaces are separate code

`interfaces/json-rpc/` and `interfaces/legacy/` are **different implementations**,
which is why the two APIs overlap without matching. If you are checking whether an
add-on can do something, check `interfaces/legacy/`; JSON-RPC's answer does not
transfer. See [`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md).

## What fails silently

- Grepping `Foo(` instead of `::Foo(` buries the definition in call sites.
- Searching `Application.cpp` for something that moved to a component file.
- Reading `interfaces/json-rpc/` to answer a question about the Python API.
- Checking a tree whose version is not the one you are debugging.

## Open questions

- The counts and paths are Kodi 21.3. Kodi 22 keeps the same shape as far as was
  checked, but line numbers and the `application/` split will differ — cite a
  symbol rather than a line where you can.

## See also

- [`kodi-architecture`](../kodi-architecture/SKILL.md) — how these pieces fit
  together at runtime
- [`kodi-contributing`](../kodi-contributing/SKILL.md) — what the project expects
  of a change once you have found the place to make it
