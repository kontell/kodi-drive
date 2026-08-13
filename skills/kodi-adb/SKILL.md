---
name: kodi-adb
description: >
  Drive Kodi on Android and Android TV over ADB — screenshots, logs, installing a
  build, restarting the app, and pulling databases. Use when the Kodi you need is
  a TV box, a stick, or a phone, or when a bug only reproduces on Android. Covers
  which local tools have no remote equivalent, why deleting files under
  Android/data fails while pushing succeeds, and the shell escaping that silently
  answers zero.
license: CC-BY-SA-4.0
metadata:
  category: access
  verified-kodi: "21.3 Omega"
  verified-platform: "Android TV"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Driving Kodi over ADB

Everything about *technique* transfers from a local Kodi — blind navigation,
focus defaults, screenshot review, state over pixels. **None of the local tooling
does.** There is no EventServer, no `~/.kodi`, and no local filesystem to reach.

Reaching for `kodi-shot` against an Android box fails with nothing to explain
why, so establish the channel first.

## Connect

```sh
adb connect <ADB_HOST>:<ADB_PORT>
adb devices
```

**The port rotates on Android 11+ wireless debugging** — it changes on every
reboot, and often more often than that. Reconnect and re-read it; never hardcode
it into a script or a config file. `kodi-discover` reports currently-connected
devices.

Kodi's data directory on Android:

```
/storage/emulated/0/Android/data/org.xbmc.kodi/files/.kodi
```

## Local tool to remote equivalent

| Local | Over ADB |
|---|---|
| `kodi-shot` | `adb -s $D exec-out screencap -p > shot.png` — full resolution, downscale with `magick` before reading |
| `kodi-remote up/down/ok` | JSON-RPC `Input.Up` / `Input.Down` / `Input.Select` / `Input.Back` / `Input.ContextMenu` |
| `kodi-builtin '...'` | **no equivalent** — no EventServer. Use `Addons.ExecuteAddon` and `GUI.ActivateWindow` |
| `kodi-logtail` | `adb -s $D shell "grep ... $K/temp/kodi.log"` |
| `~/.kodi/userdata` | `$K/userdata` — `adb pull`, and **take the `-wal`** |
| `RestartApp()` | `am force-stop` then `monkey -p org.xbmc.kodi -c android.intent.category.LAUNCHER 1` |

JSON-RPC works the same as locally once the web server is on, so most of
[`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) applies unchanged.

## Is it stopped, or is it wedged?

A JSON-RPC call against a stopped Kodi **hangs until the timeout rather than
refusing**, which reads exactly like a wedged box. One call separates them:

```sh
adb -s $D shell pidof org.xbmc.kodi
```

And rather than guessing the port and credentials:

```sh
adb -s $D shell "grep -A5 services.webserver $K/userdata/guisettings.xml"
```

## Installing a build: push works, delete does not

Under `Android/data/…`, `adb shell rm -rf` on an add-on directory returns
**Permission denied for every file**, while `adb push` of the same tree succeeds.

So an install is an **overwrite in place**: files that exist in the old build and
not the new one **survive**.

That is harmless for a same-shape rebuild and quietly wrong after a rename or a
deletion — the old module is still importable, and the add-on may keep using it.
When the file set changes, verify what is actually on the box rather than
trusting the push.

```sh
adb -s $D shell am force-stop org.xbmc.kodi
adb -s $D push dist-unzipped/<addon.id> "$K/addons/"
adb -s $D shell "monkey -p org.xbmc.kodi -c android.intent.category.LAUNCHER 1"
```

## Two things that cost time

**Compound greps get their escaping mangled.** A `grep -c 'a\|b\|c'` sent through
`adb shell` silently answers `0` — which reads exactly like "the file did not
update". Check one pattern per call when the answer matters.

**Restarting the app is the full-restart path**, so it also clears the add-on
string cache. A newly added `30xxx` string id renders after this and not after a
mere add-on enable/disable bounce. See
[`kodi-process-control`](../kodi-process-control/SKILL.md).

## What fails silently

- A rotated wireless-debugging port makes a working config fail to connect.
- JSON-RPC against a stopped Kodi hangs instead of refusing.
- `rm -rf` under `Android/data` denies permission per file, so a loop reports
  partial success and leaves the tree intact.
- A push leaves deleted files in place with no indication.
- `adb shell` mangles compound grep escaping and returns `0`.

## Open questions

- The permission behaviour under `Android/data` was observed on an Android TV
  device without root. Rooted devices, and `/sdcard` paths outside `Android/data`,
  have not been checked and may behave differently.
- Whether `screencap` captures DRM-protected video surfaces (rather than a black
  rectangle) has not been tested — assume it does not.
- Pulling a native backtrace from an unrooted device is possible via
  `adb bugreport` and its `VM TRACES JUST NOW` section, but that path is not yet
  written up here.

## See also

- [`kodi-connect`](../kodi-connect/SKILL.md) — finding the device in the first place
- [`kodi-addon-driving`](../kodi-addon-driving/SKILL.md) — `Addons.ExecuteAddon`,
  which replaces builtins here
- [`kodi-test-rig`](../kodi-test-rig/SKILL.md) — using a phone as a throwaway
  Kodi for testing
