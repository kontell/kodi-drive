---
name: kodi-binary-build
description: >
  Build a Kodi binary add-on that installs on the Kodi versions you meant, on the
  systems your users have. Use when building a PVR, inputstream, screensaver or
  visualisation add-on, when a .so fails to load on a user's box but works on
  yours, or when CI produces a zip that will not install. Covers the ABI floor
  being set by the build host rather than the code, and the stale files a rebuild
  leaves behind.
license: CC-BY-SA-4.0
metadata:
  category: binary-addon
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64, Windows x86_64"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Building binary add-ons

The Kodi add-on superbuild works, and then produces artifacts that fail on other
people's machines for reasons invisible on yours.

## Use Kodi's depends system; do not hand-roll the cmake

Start here, because the alternative is expensive and looks reasonable at every
individual step.

```
<kodi-source>/tools/depends/target/binary-addons/
```

Point that at your add-on and it handles the toolchain file, the cmake modules,
the dependency builds and the library ordering. It needs the **full Kodi source
tree** for the version you are targeting — which you already need for the headers.

The failure mode worth naming: hand-crafting `KodiConfig.cmake`, copying cmake
modules across piecemeal, building FFmpeg separately, and then fixing link
ordering by hand. Each step is individually plausible and the whole thing is work
the depends system already does. It is easy to do this *with the full Kodi source
already cloned and unused*.

## The ABI floor is set by the build host, not by your code

This is the one that costs the most time. A trivial `.so` using only
`std::vector`, `std::string` and `make_shared`, built with
`-static-libstdc++ -static-libgcc` on **glibc 2.42**, still requires:

| Symbol | From |
|---|---|
| `__isoc23_strtoul@GLIBC_2.38` | a C23 symbol the headers substitute in |
| `arc4random@GLIBC_2.36` | the static unwinder |
| `_dl_find_object@GLIBC_2.35` | the static unwinder |

Building the same source on **Ubuntu 22.04 (glibc 2.35)** removes all of them.
Nothing in your code changed; the headers did.

**Pin a container, not a runner label.** Runner labels get retired and
`ubuntu-latest` silently remaps to a newer image with a newer glibc — so a build
that worked for a year starts producing binaries your users cannot load, with a
green CI run.

Then assert it, rather than trusting the pin:

```sh
readelf --dyn-syms build/addon.so \
  | grep -oE 'GLIBC_[0-9.]+' | sort -Vu | tail -1
# fail if above your floor
```

Also assert the `.so` links **no** `libstdc++` or `libgcc_s` if you meant to
static-link them.

## The superbuild forwards compiler flags but not linker flags

`CMAKE_C_FLAGS` and `CMAKE_CXX_FLAGS` reach the inner add-on build.
**`CMAKE_EXE_LINKER_FLAGS` and friends do not.**

The working injection point is `LDFLAGS`, which the inner add-on CMake reads on
its **first configure**. Set it in the environment before configuring, and verify
afterwards with `readelf` — because if it did not take effect, nothing says so
and the binary simply carries dynamic dependencies you thought you had removed.

## A rebuild does not remove anything

Two independent staleness traps compound:

- **The output zip is updated in place by `zip -r`**, and existing entries are
  never removed.
- **The Kodi add-on build's install step never deletes** previously installed
  files.

So when a branch *removes* a packaged file, that file survives in both the zip
and the install tree. The old module is still importable and may still be used.

**Delete the output zip and `<kodi-src>/build/addons/<addon>/` before building**
whenever the file set has changed. A same-shape rebuild is unaffected, which is
why this stays hidden until a rename.

## What you need on a Linux build host

```
kodi-addons-dev  libjsoncpp-dev  m4  autoconf  automake  libtool  autopoint
```

The superbuild needs a Kodi **source tree** matching the target version, and
builds external dependencies itself.

## Version substitution

Use `addon.xml.in` with the version substituted by CMake, so the manifest and the
build cannot disagree. And remember that `@ADDON_DEPENDS@` is filled from the
headers you built against — see
[`kodi-versions-abi`](../kodi-versions-abi/SKILL.md), where an unpinned Kodi ref
changes your declared ABI with no commit of your own.

## Gating on API version differences

Detect the API version from the headers in CMake and gate with a preprocessor
symbol, rather than branching on a Kodi version number:

```cmake
# e.g. PVR API 9 (Kodi 22) changed GetChannelStreamProperties' signature
add_compile_definitions($<$<BOOL:${HAS_PVR_API_V9}>:KODI_PVR_API_V9>)
```

Signatures do change between majors; a version check tells you less than a
capability check and breaks on backports.

## Windows portability

- `gmtime_r` / `timegm` need `gmtime_s` / `_mkgmtime` shims.
- Static lzma needs `LZMA_API_STATIC` under `if(WIN32)`.
- **`%lu` for `time_t` truncates on Windows x64** — `time_t` is 64-bit while
  `long` is 32-bit. Use `%lld` with an explicit cast.

## Two C++ traps that kill the whole Kodi process

Both were real crashes, and neither is add-on-local:

- **An exception escaping into Kodi crosses a C ABI boundary.** jsoncpp's
  `asInt()`, `asInt64()` and `asUInt64()` throw `Json::LogicError`. Concretely: a
  server reporting a negative free-space value, inside Kodi's `GetDriveSpace`
  callback. Use range-checked helpers and put an **exception firewall at every
  entry point** Kodi calls.
- **Assigning to a joinable `std::thread` calls `std::terminate()`.** A
  connection handler that fired on *every* transition to CONNECTED crashed the
  whole process after one failed health check followed by recovery.

Two more that hang rather than crash: never hold a model mutex across an HTTP
GET, because Kodi's UI-path callbacks block on the same mutex; and return
cross-thread settings strings **by value**, since a caller holding a reference
across a settings reload has a use-after-free.

## Persisted hashes are an upgrade contract

If you persist a hash — channel UIDs, EPG ids — its value is a contract with
every existing install. Changing the algorithm silently reassigns everything.

One real case: three near-identical djb2 copies computed in **signed int**
(signed overflow is undefined on any long input) and finished with `std::abs`
(undefined for `INT_MIN`). The consolidated `uint32_t` version was verified
**bit-identical over 2 million random strings**, deliberately preserving `char`
sign-extension, precisely because those UIDs live in Kodi's PVR database.

Fixing undefined behaviour is correct. Changing the output is not.

## What fails silently

- A newer build host raises your glibc floor with no source change.
- `LDFLAGS` not taking effect leaves dynamic dependencies you thought were gone.
- A removed file survives in the zip and the install tree.
- An escaped exception crosses the C ABI as undefined behaviour.
- A "cleanup" of a hash function reassigns every persisted id.

## Open questions

- The glibc symbol list is from one toolchain pairing. The general rule holds,
  but the exact symbols will differ elsewhere — assert the floor rather than
  matching this list.
- Whether the superbuild forwards linker flags in Kodi 22 has not been retested.

## See also

- [`kodi-android-ndk`](../kodi-android-ndk/SKILL.md) — cross-compiling for Android
- [`kodi-versions-abi`](../kodi-versions-abi/SKILL.md) — which Kodi will accept it
- [`kodi-addon-release`](../kodi-addon-release/SKILL.md) — shipping the result
