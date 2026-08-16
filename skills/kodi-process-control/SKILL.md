---
name: kodi-process-control
description: >
  Stop, restart, and measure a Kodi process without killing your own shell or
  measuring the wrong one. Use when scripting a restart, running an unattended
  benchmark, sampling Kodi's memory or CPU, or when a "stopped" Kodi keeps coming
  back. Covers the /usr/bin/kodi wrapper that relaunches the binary, why pkill -f
  is dangerous here, and how to measure add-on cost as a delta.
license: CC-BY-SA-4.0
metadata:
  category: diagnosis
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Controlling and measuring the Kodi process

Every trap here lets a script report success, or destroy something, with no error.
They cost real hours during an unattended benchmark run.

## `pkill -f` will kill your own shell

`pkill -f <pattern>` matches full command lines — **including the command line of
the shell running the pkill**. Your own invocation contains the pattern, so you
match yourself, and the shell dies (exit 143) before the signal reaches Kodi.

Measured on a live box, `pgrep -f kodi.bin` returned four pids:

```
2592029  /bin/bash -c ... pgrep -x kodi.bin ...   <- an earlier shell
2593245  /usr/lib/x86_64-linux-gnu/kodi/kodi.bin  <- the actual target
2615013  /bin/bash -c ... pgrep -f "kodi.bin" ... <- the shell issuing the command
2615045  sh -c pgrep -f "kodi.bin" ...            <- itself
```

Three of the four are shells. `pgrep -x kodi.bin` returned exactly one: `2593245`.

**Always resolve to a PID with `pgrep -x`, then signal that PID.**

```sh
pid=$(pgrep -x kodi.bin) && [ -n "$pid" ] && kill "$pid"
```

This applies to any pattern that appears in your own command line, not just Kodi —
it bit a `benchproxy.py` helper the same way.

## Killing `kodi.bin` does not stop Kodi

On Linux, `/usr/bin/kodi` is a `/bin/sh` wrapper that **relaunches the binary**.
Kill only `kodi.bin` and the wrapper starts a replacement, leaving you with two
Kodis fighting over port 8080 — which presents as JSON-RPC answering
intermittently from an instance that ignores your changes.

Two processes, verified:

```
pgrep -x kodi      -> 2592030   /bin/sh /usr/bin/kodi        (wrapper, 1 MB RSS)
pgrep -x kodi.bin  -> 2593245   .../kodi/kodi.bin            (real Kodi, 487 MB RSS)
```

Stop the wrapper first, then the binary:

```sh
wrapper=$(pgrep -x kodi     || true)
binary=$(pgrep -x kodi.bin  || true)
[ -n "$wrapper" ] && kill "$wrapper"
[ -n "$binary"  ] && kill "$binary"
```

Prefer a clean shutdown where you can — `kodi-remote get Application.Quit` — and
fall back to signals only when Kodi is wedged.

## Restarting cleanly, and what a restart resets that a bounce does not

Kodi respawns itself — no relaunch command needed, because the wrapper above is
what catches the exit:

```sh
kodi-builtin 'RestartApp()'   # Kodi exits 65; the wrapper loops and relaunches
```

**Wait for it properly. JSON-RPC answers early**, before the skin and add-on
services are up, so a ping that succeeds does not mean the box is ready:

```sh
for i in $(seq 1 30); do
  kodi-remote get JSONRPC.Ping >/dev/null 2>&1 && break
  sleep 2
done
sleep 10   # let the skin and add-on services finish starting
```

A new `pgrep -x kodi.bin` pid confirms the restart actually happened.

**An add-on bounce is not a restart.** Disabling and re-enabling an add-on
restarts its *service*, but Kodi caches each add-on's **language strings**
(`resources/language/**/strings.po`) for the whole process lifetime. Newly added
`30xxx` string ids therefore render **blank** until a full restart.

Measured on Omega 21.3, one id, one file on disk, three readings: blank when the
add-on was reinstalled, blank again after a disable/enable bounce, and correct
after Kodi genuinely restarted. Nothing about the file changed between them.

When a new string shows empty despite a correct `strings.po`, that is the cache,
not a bug in your file.

**A skin's strings are not in that category.** A newly added skin id rendered on
screen straight after `ReloadSkin()`, in a process whose pid had not changed for
hours — so a skin can gain a string and use it in the same session, while an
add-on cannot. (Skin `<res>` is the opposite way round: `addon.xml` is parsed
only at skin load, so a resolution change does need a restart.)

**`System.RestartApp` over JSON-RPC can answer and do nothing.** It returned
without error on Omega 21.3 and left the same pid running with its uptime
unbroken; a subsequent check found the string still blank, which is what exposed
it. Whatever you use, confirm with the pid rather than with the call's reply or
a ping — a ping is answered by the process you were trying to replace.

Restarts are heavier than a bounce and reset playback and navigation state, so
reach for one only when a bounce genuinely will not do. On a box with multiple
profiles, a restart can also land on the profile chooser or the default profile
rather than the one you were on — check `Profiles.GetCurrentProfile` afterwards
and switch back if needed. See [`kodi-profiles`](../kodi-profiles/SKILL.md),
because that switch has its own failure modes.

## Sampling the wrong process reads ~1 MB

`pgrep -f kodi.bin` matches the wrapper and any shell, so a memory sample taken
through it reports the **wrapper's** ~1 MB RSS and 0.0% CPU. That is a plausible
small number, not an obvious error, so it survives review and quietly makes a
whole benchmark meaningless.

```sh
pid=$(pgrep -x kodi.bin)
awk '/VmRSS/{print $2/1024 " MB"}' "/proc/$pid/status"
```

## Measure an add-on as a delta, never an absolute

Kodi's own resident set was **487 MB** on this box with the add-on under test
disabled. Any absolute RSS figure is therefore mostly measuring Kodi, and small
differences between add-ons vanish into it.

Sample a baseline with the add-on disabled, immediately before enabling it, and
report the difference. "Immediately" matters — Kodi's own footprint drifts with
library scans, artwork caching, and idle time.

## What fails silently

- `pkill -f` killing the caller looks like the script simply ending.
- A relaunched second Kodi answers JSON-RPC, so connectivity checks pass while
  your changes appear to have no effect.
- Sampling the wrapper produces a small, believable number rather than an error.
- `System.RestartApp` over JSON-RPC returns cleanly whether or not it restarts
  anything, and the ping that follows is answered by the process you meant to
  replace.

## Open questions

- The wrapper behaviour was verified on a Debian-packaged Kodi. Flatpak, snap,
  LibreELEC, and Windows builds have different process trees and have not been
  checked — do not assume `pgrep -x kodi` finds a wrapper there, or that one exists.
- Why `System.RestartApp` over JSON-RPC was a no-op on the Debian-packaged Omega
  21.3 box is not established. The `RestartApp()` builtin documented above was
  not tried in the same session, so whether the two paths differ is untested.
- Whether `Application.Quit` over JSON-RPC also stops the wrapper, or whether the
  wrapper relaunches after a clean quit, has not been tested.

## See also

- [`kodi-profiles`](../kodi-profiles/SKILL.md) — profile switching, which wedges
  in ways that leave a restart as the only fix
- [`kodi-logs`](../kodi-logs/SKILL.md) — confirming what a restart actually did
