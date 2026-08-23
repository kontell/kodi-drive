---
name: kodi-adb
description: >
  Drive Kodi on Android and Android TV over ADB — screenshots, logs, installing a
  build, restarting the app, and pulling databases. Use when the Kodi you need is
  a TV box, a stick, or a phone, or when a bug only reproduces on Android. Covers
  which local tools have no remote equivalent, reaching an EventServer that binds
  IPv6 only and so ignores every builtin you send it, why deleting files under
  Android/data fails while pushing succeeds, and the shell escaping that silently
  answers zero.
license: CC-BY-SA-4.0
metadata:
  category: access
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Android TV, Android tablet, Android phone"
  verified-date: "2026-08-23"
  verified-method: "observed"
---

# Driving Kodi over ADB

Everything about *technique* transfers from a local Kodi — blind navigation,
focus defaults, screenshot review, state over pixels. **None of the local tooling
does.** There is no `~/.kodi` and no local filesystem to reach, and `kodi-builtin`
cannot reach the EventServer from your workstation — though the EventServer
itself is running. [Builtins over ADB](#builtins-over-adb) has the route in.

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
| `kodi-builtin '...'` | send the packet from the device to its own `::1` — see [Builtins over ADB](#builtins-over-adb) |
| `kodi-logtail` | `adb -s $D shell "grep ... $K/temp/kodi.log"` |
| `~/.kodi/userdata` | `$K/userdata` — `adb pull`, and **take the `-wal`** |
| `RestartApp()` | `am force-stop` then `monkey -p org.xbmc.kodi -c android.intent.category.LAUNCHER 1` |

JSON-RPC works the same as locally once the web server is on, so most of
[`kodi-jsonrpc`](../kodi-jsonrpc/SKILL.md) applies unchanged.

## Builtins over ADB

Android Kodi runs the EventServer. What fails is delivery: it binds **`udp6`
only**, and `kodi-builtin` sent from `AF_INET`. The datagram is discarded by the
kernel, and because this is fire-and-forget UDP nothing anywhere reports it —
`services.esenabled` reads `True`, the command exits 0, and the builtin never
runs. That symptom is indistinguishable from the EventServer being absent, which
is what this skill used to claim it was.

Check which stack it is on from the device rather than inferring it from a
builtin that did nothing:

```sh
adb -s $D shell 'netstat -lun' | grep 9777
#   udp6  0  0  [::]:9777  [::]:*     <- v6 only; an IPv4 packet is discarded
```

`netstat -lun` lists both stacks, so a plain `udp` row means IPv4 is bound too.

`bin/kodi-builtin` now resolves with `AF_UNSPEC`, so it reaches a v6-only
EventServer whenever the workstation has an IPv6 route to the device. On a
v4-only LAN it has none, and there is nothing to configure — the packet has to
originate on the device:

```sh
b64=$(python3 - "$BUILTIN" <<'PY'
import base64, struct, sys
payload = bytes([0x01]) + sys.argv[1].encode() + b"\x00"          # EXECBUILTIN
print(base64.b64encode(
    b"XBMC" + bytes([2, 0]) + struct.pack(">H", 0x0A)             # PT_ACTION
    + struct.pack(">I", 1) + struct.pack(">I", 1)
    + struct.pack(">H", len(payload)) + struct.pack(">I", 0xC0DE0001)
    + b"\x00" * 10 + payload).decode())
PY
)
adb -s $D shell "echo $b64 | base64 -d | timeout 1 nc -u -6 ::1 9777"
```

**`nc` does not exit after a UDP send**, so bound it *on the device* with
`timeout`. Without that the `adb shell` hangs indefinitely, long after the
builtin has already run — and killing the local `adb` does not retract it.

Worth the trouble because builtins are the only route to `SetProperty`,
`ClearProperty`, `RunScript(...)` with arguments, `Skin.SetString` and
`ReloadSkin`. JSON-RPC exposes none of them.

### Passing an argument that contains a comma

Builtin arguments split on commas, so a JSON payload needs quoting. A
double-quoted argument with `\"` escapes round-trips byte for byte:

```sh
SetProperty(my.prop,"[[0,\"first line\"],[3,\"second line\"]]",Home)
```

Read it back with JSON-RPC `XBMC.GetInfoLabels` on
`Window(Home).Property(my.prop)` to confirm it landed — never assume, since a
rejected builtin looks exactly like an accepted one.

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

### A new file may be refused outright — have Kodi create it

On a Bravia 4K AE2 (Android 14) the add-on directories are `drwxr-s---
u0_a233 ext_data_rw`: the `shell` user is in `ext_data_rw` but the directory
has no group write, so overwriting an existing `-rw-rw----` file lands while
creating one does not:

```
adb push tempo.py ".../addons/plugin.video.kofin/lib/kofin/syncplay/tempo.py"
adb: error: failed to copy '…/tempo.py' to '…/tempo.py': remote couldn't create file: Permission denied
```

A whole-tree push of a build that adds a file aborts at that file with
`adb: error: failed to read copy response`, leaving the files before it updated
and the rest not — a mixed tree that Kodi will happily load. A Galaxy Tab S5e
(Android 13) accepted the same tree, new files included; which of the two a
device is can only be found out by pushing and checksumming.

The way in is the process that owns the directory. Kodi's Python runs as the app
uid, so stage the new file on `/sdcard` with a three-line installer and have
Kodi run it over the EventServer:

```sh
adb -s $D push lib/kofin/syncplay/tempo.py /sdcard/stage/tempo.py
adb -s $D push _install.py /sdcard/stage/_install.py      # shutil.copyfile(src, dst); write md5 to /sdcard/stage/done
# RunScript(/sdcard/stage/_install.py) as an EventServer packet, sent from the device (see above)
adb -s $D shell "cat /sdcard/stage/done"                  # 9ed82c5f… — compare with the local md5sum
```

Once the file exists, later pushes overwrite it normally. Then push the rest of
the tree and compare a full `find -type f -exec md5sum {} +` against the local
tree, ignoring `__pycache__`; a mixed tree looks fine from every other angle.
Where a stage-and-`cat` from the shell is possible (the target file exists and
is group-writable), it is the cheaper route for an overwrite that silently
no-opped — and `cat /dev/null > target` first, because a push does not truncate.

### And a push can report success while writing nothing

Overwriting an **existing** file under `Android/data` sometimes reports success
and leaves the file byte for byte unchanged:

```sh
adb -s $D push app.db "$A/app.db"
# app.db: 1 file pushed, 0 skipped. 256.9 MB/s (11333632 bytes in 0.042s)
adb -s $D shell "md5sum $A/app.db"    # unchanged, after three such pushes
```

The throughput is the tell — 256–362 MB/s over wifi is not a transfer. Size and
mtime do not move either, so only the checksum shows it.

Creating a **new** file in that same directory fails loudly instead, which is the
easier case to notice:

```
adb: error: failed to copy 't1.txt' to '…/_probe.txt':
  remote couldn't create file: Permission denied
```

The identical overwrite onto plain `/sdcard`, outside `Android/data`, works.

It is not deterministic: earlier in the same session, pushes over the same two
files did land. So the rule is not "push is broken under `Android/data`" — it is
**never trust the success line, compare checksums**:

```sh
adb -s $D push local.py "$B/local.py"
[ "$(adb -s $D shell "md5sum $B/local.py" | awk '{print $1}' | tr -d '\r')" \
  = "$(md5sum local.py | awk '{print $1}')" ] || echo "PUSH DID NOT LAND"
```

When it has not landed, stage on `/sdcard` and copy on the device:

```sh
adb -s $D push local.py /sdcard/_stage.py
adb -s $D shell "cat /sdcard/_stage.py > $B/local.py"
adb -s $D shell "rm -f /sdcard/_stage.py"
```

That needs the target group-writable. Kodi's add-on files are `-rw-rw----` and
take it; an add-on's own data file under `addon_data` was `-rw-r-----`, where the
`cat` fails with `Permission denied` and there is no route in from the
workstation at all — the change has to be made by code running inside Kodi.


### It also does not truncate

A push that *does* land still writes in place without shortening the file, so a
shorter file leaves the previous tail behind:

```sh
adb -s $D shell "wc -c < $T"     # 597
adb -s $D push short.txt "$T"    # "1 file pushed" — 6 bytes
adb -s $D shell "wc -c < $T"     # 597, still
adb -s $D shell "tail -c 40 $T"  # the end of the file it was meant to replace
```

On a Python file that surfaces as a `SyntaxError` at a line number the file you
pushed does not have, which reads as a corrupt transfer rather than a
half-replaced one. The checksum comparison above catches this as well; the
one-line fix, where the target is writable, is to empty it first:

```sh
adb -s $D shell "cat /dev/null > $T" && adb -s $D push local/file "$T"
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
- A push over an existing file under `Android/data` can report success, at an
  impossible throughput, and write nothing at all.
- A push that does land does not truncate, so a shorter file leaves the previous
  tail in place and the file on the box is neither version.
- `adb shell` mangles compound grep escaping and returns `0`.
- An EventServer bound on `udp6` only discards every IPv4 builtin without a
  word, which reads as "this platform has no EventServer".
- `nc -u` on the device never exits, so an unbounded `adb shell` hangs after the
  builtin has already been delivered.

## Open questions

- The permission behaviour under `Android/data` was observed on an Android TV
  device without root. Rooted devices, and `/sdcard` paths outside `Android/data`,
  have not been checked and may behave differently.
- What decides whether an overwrite under `Android/data` lands or silently
  no-ops is unknown. It is not the file mode — the same `-rw-rw----` add-on file
  took a push once and refused the next — and it is not whether Kodi is running,
  since it refused with the app force-stopped. Only the checksum check is
  reliable.
- Creating a *new* file under `Android/data` is refused on some devices (a
  Bravia, Android 14) and accepted on others (a Galaxy Tab S5e, Android 13), with
  the same `drwxr-s---`-style ownership visible from the shell on both. Which
  variable separates them is untested; the RunScript route above works on
  either.
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
