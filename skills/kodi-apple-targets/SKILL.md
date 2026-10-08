---
name: kodi-apple-targets
description: >
  Build a Kodi binary add-on for macOS, iOS and tvOS from one Mac, without
  bootstrapping Kodi's depends tree. Use when CI has to cover the Apple platforms
  the official repository builds, when a macOS add-on loads on Apple Silicon and
  not on Intel or the reverse, or when you need the SDK and minimum OS version
  Kodi itself targets. Covers the toolchain file, the values Kodi's builder
  uses, and proving what a build produced.
license: CC-BY-SA-4.0
metadata:
  category: binary-addon
  verified-kodi: "22.0b1 Piers, 22.0rc1 Piers"
  verified-platform: "macOS arm64"
  verified-date: "2026-10-08"
  verified-method: "sourced"
---

# Building for macOS, iOS and tvOS

Kodi's official builder compiles every binary add-on for four Apple targets, and
gets there by bootstrapping its whole depends tree first. An add-on whose own
dependencies are plain CMake projects needs none of that — only the same
answers Kodi arrives at, written into a toolchain file.

## The four targets, and what Kodi builds them with

Sourced from `tools/depends/configure.ac:499-515` and `:544-574`, and
`tools/depends/target/Toolchain_binaddons.cmake.in:23-47`, at `22.0rc1-Piers`:

| Tag | SDK | `-arch` | Minimum | `CORE_SYSTEM_NAME` | `CORE_PLATFORM_NAME` |
|---|---|---|---|---|---|
| `osx-x86_64` | `macosx` | `x86_64` | 10.15 | `osx` | — |
| `osx-arm64` | `macosx` | `arm64` | 11.0 | `osx` | — |
| `ios-aarch64` | `iphoneos` | `arm64` | 12.0 | `darwin_embedded` | `ios` |
| `tvos-aarch64` | `appletvos` | `arm64` | 12.0 | `darwin_embedded` | `tvos` |

**The minimums move within a release.** macOS x86_64 was 10.14 at
`22.0b1-Piers` and has been 10.15 since `22.0b2-Piers`; the other three are the
same at beta 1, beta 2, RC1 and on `master`. Copy them from the tag you are
targeting, not from a tree you happen to have.

It matters in the direction you would not guess. A *lower* minimum than Kodi's
is the stricter build, and rejects code Kodi's own builder accepts. libc++ marks
`<filesystem>` as introduced in macOS 10.15
(`libcxx/include/__configuration/availability.h:253` and `:304-306` at
`llvmorg-19.1.0`), so it does not compile for 10.14.

**The tag is derived, not chosen.** `cmake/scripts/common/PrepareEnv.cmake:57-65`
builds it from those variables — `CORE_PLATFORM_NAME` plus `-aarch64` when `CPU`
matches `arm64`, or `osx-` plus `CPU`. Kodi matches it at install time against
the list in `xbmc/addons/addoninfo/AddonInfoBuilder.cpp:865-895`.

## The toolchain file

The `cmake/addons` superbuild — still Kodi's, and the one a Linux build already
uses — reaches all four given a toolchain file and nothing else. This is the iOS
one; the others differ only in the values from the table:

```cmake
set(CMAKE_SYSTEM_NAME Darwin)
set(CMAKE_SYSTEM_PROCESSOR arm64)
set(CPU arm64)
set(CORE_SYSTEM_NAME darwin_embedded)      # osx for macOS
set(CORE_PLATFORM_NAME ios)                # tvos; leave out for macOS
set(CMAKE_OSX_SYSROOT <sdk>)               # xcrun --sdk iphoneos --show-sdk-path
set(CMAKE_C_FLAGS   "-arch arm64 -miphoneos-version-min=12.0 -isysroot <sdk>")
set(CMAKE_CXX_FLAGS "-arch arm64 -miphoneos-version-min=12.0 -isysroot <sdk>")
set(CMAKE_FIND_ROOT_PATH <sdk> <sdk>/usr)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_FRAMEWORK LAST)
```

```sh
cmake -B build \
  -DADDONS_TO_BUILD=<id> -DADDON_SRC_PREFIX=<parent of the add-on> \
  -DADDONS_DEFINITION_DIR=<kodi-src>/cmake/addons/addons \
  -DCMAKE_TOOLCHAIN_FILE=<that file> -DPACKAGE_ZIP=1 \
  <kodi-src>/cmake/addons
make -C build
```

Observed on a GitHub `macos-15` runner — arm64, Xcode 16.4 — with an add-on
whose one dependency is jsoncpp, against `22.0b1-Piers` headers. **All four came
from that one runner, the x86_64 build included**, and the libraries reported:

| Target | `lipo -archs` | `vtool` platform | `minos` |
|---|---|---|---|
| `osx-x86_64` | `x86_64` | `MACOS` | 10.15 |
| `osx-arm64` | `arm64` | `MACOS` | 11.0 |
| `ios-aarch64` | `arm64` | `IOS` | 12.0 |
| `tvos-aarch64` | `arm64` | `TVOS` | 12.0 |

Each zip's `addon.xml` carried the matching `<platform>` tag, with the library
named in `library_osx` for the first two and `library_darwin_embedded` for the
others.

## Prove what it produced

Each of these is a cross-build of some kind, and one that fell back to the
host's architecture or platform would still configure, compile, package and
upload:

```sh
lipo -archs <lib>.dylib               # x86_64 | arm64
xcrun vtool -show-build <lib>.dylib   # "platform MACOS|IOS|TVOS" and "minos"
```

## What fails silently

- A minimum OS version copied from one Kodi tag is stale two tags later, and
  nothing complains: the build is merely stricter or looser than Kodi's.
- A library built for the runner instead of the target passes every step.

## Open questions

- None of the four was loaded by a Kodi on its platform. They were compiled,
  packaged and inspected.
- The route was tried with one dependency, jsoncpp, which is a plain CMake
  project. An add-on with autotools dependencies, or ones that need Kodi's
  patched libraries, was not tried this way.
- Whether a stock iOS or tvOS install can load an add-on library that arrives
  after the app was signed was not tested. Kodi's builder archives those two
  zips and deploys neither.

## See also

- [`kodi-binary-repo`](../kodi-binary-repo/SKILL.md) — the full list of
  platforms the official repository builds and deploys
- [`kodi-binary-build`](../kodi-binary-build/SKILL.md) — the superbuild itself,
  and the other Windows architectures
- [`kodi-android-ndk`](../kodi-android-ndk/SKILL.md) — the Android equivalent
