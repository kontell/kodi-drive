---
name: kodi-android-ndk
description: >
  Cross-compile a Kodi binary add-on and its dependencies for Android. Use when
  building a PVR or inputstream add-on for Android or Android TV, when a dependency
  builds x86 assembly under an ARM toolchain, or when configure tries to run a test
  binary and fails. Covers the four traps that hit in sequence and the NDK versions
  that actually work.
license: CC-BY-SA-4.0
metadata:
  category: binary-addon
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Android"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Cross-compiling for Android

Android is where the Kodi add-on superbuild's assumptions break, mostly in the
autotools dependencies rather than in your own code. These four hit in sequence —
fix one and you meet the next.

## 1. The NDK hides the target triple where configure cannot see it

NDK r19 and later set `CMAKE_C_COMPILER` to plain `clang`, with the target in
`CMAKE_C_COMPILER_TARGET`.

**FFmpeg's configure never reads `CMAKE_C_COMPILER_TARGET`**, so it configures for
the host.

Override the compiler to the NDK's **per-target wrapper**, which bakes the triple
in:

```sh
CC=armv7a-linux-androideabi21-clang
CXX=armv7a-linux-androideabi21-clang++
```

## 2. Autoconf dependencies try to *run* their test binaries

Without `--host`, a configure script assumes it can execute what it just
compiled. On a cross build that fails in confusing ways — often as a missing
feature rather than an error.

Pass `--host=<triple>` to every autotools dependency. That is what tells autoconf
it is cross-compiling.

## 3. `CPU` must be a CACHE variable

Kodi's `HandleDepends` does not forward `CPU` to the toolchain file, so setting
it normally has no effect and FFmpeg builds **x86 assembly under an ARM
compiler**. The symptom is an assembler error deep in a dependency, far from
anything you changed.

Set it as a CACHE variable in the toolchain file. This applies to **Linux ARM
too**, not only Android.

## 4. Dependencies autodetect the host's libraries

gnutls detects the build host's `libzstd` and then fails to link, because its
vendored fallback header lacks `ZSTD_CLEVEL_DEFAULT`.

```sh
--without-zstd --without-brotli
```

The general rule: **pin `PKG_CONFIG_LIBDIR`** to the cross-built dependency
directory so nothing can discover a host library at all. Leaving
`PKG_CONFIG_PATH` set is not sufficient — it adds to the search rather than
replacing it.

## `find_package` cannot see your dependencies

The NDK toolchain sets `CMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY`, which stops
`find_package` searching `CMAKE_PREFIX_PATH`.

Add your dependency prefix to `CMAKE_FIND_ROOT_PATH`, not to `CMAKE_PREFIX_PATH`.

## Parallel dependency races

A dependency that *optionally* uses another will detect it or not depending on
build order. Observed: libzvbi's configure found a bundled `libiconv.h` **only
when iconv happened to finish first**, then failed to link without `LIBS=-liconv`.

Under `-j` this is intermittent, which reads as a flaky build. Fix **both halves**
— declare the dependency ordering *and* pass the flag unconditionally.

## NDK version roulette

Newer is not better here:

| NDK | Outcome |
|---|---|
| r28c | changed toolchain layout, breaks CMake detection |
| r27c | missing clang at the expected path |
| **r25c** | works |

Pin the NDK version explicitly and treat changing it as a deliberate act with a
full rebuild behind it.

## What fails silently

- Configure builds for the host and produces a working-looking binary for the
  wrong architecture.
- A missing `--host` presents as an absent feature rather than an error.
- `CPU` not reaching the toolchain surfaces as an assembler error in a dependency.
- A host library discovered mid-build makes the failure order-dependent.
- `find_package` silently finding nothing, so a dependency is quietly omitted.

## Open questions

- The NDK table is from one Kodi superbuild version; later NDKs may have been
  accommodated upstream since. Check before assuming r25c is still required.
- Whether the `CPU` CACHE requirement has been fixed in Kodi 22's `HandleDepends`
  has not been retested.

## See also

- [`kodi-binary-build`](../kodi-binary-build/SKILL.md) — the rest of the build,
  and the ABI floor
- [`kodi-adb`](../kodi-adb/SKILL.md) — getting the result onto a device, where
  push works and delete does not
