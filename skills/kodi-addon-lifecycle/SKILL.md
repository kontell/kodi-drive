---
name: kodi-addon-lifecycle
description: >
  Survive being started, stopped, updated and superseded. Use when writing or
  debugging a Kodi service add-on, when Kodi will not quit, when settings writes
  vanish, or when an add-on update leaves two generations running at once. Covers
  what abortRequested actually means, why Kodi's five-second kill is not a kill,
  and the window where xbmcaddon.Addon() raises.
license: CC-BY-SA-4.0
metadata:
  verified:
    kodi: ["21.3 Omega"]
    platform: ["Linux x86_64", "Android TV"]
    date: "2026-08-13"
    method: observed
---

# The add-on lifecycle

A Kodi service does not get a clean start and a clean stop. It gets bounced,
updated over, superseded, and asked to stop in ways that do not guarantee it
ever does.

## `abortRequested` means Kodi is shutting down

It does **not** mean "this add-on is being bounced". It is raised on Kodi exit, on
a profile switch, and on an add-on bounce — but you cannot use it to distinguish
them, and treating it as a bounce signal is wrong.

Fold `Monitor.abortRequested()` into every abort predicate you have, because it
is raised **before** your `_shutdown` runs.

## "script didn't stop in 5 seconds" is not a kill

Kodi logs `script didn't stop in 5 seconds - let's kill it`, and then does not
kill it. It raises `abortRequested` and waits.

Kodi will not finalise a script while a thread that script created is still
alive — you will see `waiting on thread <id>`. Meanwhile your replacement has
already started, so **two object graphs and two sets of database connections run
side by side** for the rest of the old one's retry ladder.

## A stop flag in a window property does not reach orphan threads

This one looks fixed when it is not. A window property is shared across
generations, so the **replacement service lowers the flag about ten seconds into
the old one's teardown** — and the orphan's next retry check reads "carry on".

Measured, A/B, same shutdown path:

| Stop mechanism | Time to actually stop |
|---|---|
| Window property | **124 s** |
| Generation-owned `threading.Event` | **29 s** |

Two fixes that look identical in a diff; one does nothing. Own your stop flag in
the generation that created the threads.

A related failure: one stuck teardown left a shared "stop" property raised
forever, so **every later library thread exited at its first guard until Kodi was
restarted** — one warning line, no dialog, no retry.

## Two service generations overlap during an update

An add-on update raises `abortRequested` on the running service and starts its
replacement **without waiting for the old one to finish**. Measured overlap: about
ten seconds.

Consequences worth designing for:

- Window properties are shared across generations, so the outgoing service's
  teardown writes land on the live one.
- A teardown must check whether it has been **superseded** before writing shared
  state.
- Re-assert state on a tick rather than trusting an edge — no fix you ship can
  reach an *older* build's teardown retroactively.

## `xbmcaddon.Addon()` raises during an update

Kodi unloads an add-on before replacing any of its files
(`CAddonInstallJob::DoWork`) while every thread that add-on started keeps
running. For that window the constructor raises
`RuntimeError: Unknown addon id`.

A routine repository update opens this window as readily as a manual reinstall.

Three corollaries:

- **An empty setting read is ambiguous** — "store unavailable" and "user cleared
  it" look identical. Use a load canary.
- **A setting write in that window is silently dropped.**
- Read a whole record off **one** `Addon` object rather than making N
  `getSetting` calls, so you cannot straddle the window mid-read. It is also
  faster: each construction costs ~2.9 ms.

The same failure has a worse shape if it lands inside an exception handler. A
settings read that raised inside a `log()` call inside a service loop's own
`except` block killed the loop before it closed its window — and **a registered
window with no owner pins the whole UI**, recoverable only by restarting Kodi.

## Shutdown paths that wedge Kodi

- **`ThreadPoolExecutor.shutdown(wait=True)` waits forever** if a consumer
  abandoned a generator whose workers block on a semaphore only that consumer
  releases. Symptom: Kodi freezes on quit. A `finally` must cancel pending work
  and drain the semaphore.
- **HTTP retry ladders outlive the budget.** A default 3 retries with a 6 s
  connect timeout held a stopping thread for 125 s against a ~147 s budget.
  Fold the abort predicate into the retry loop.
- **A bare blocking `put` on a full queue** is how a slow writer becomes a Kodi
  that will not quit. Poll with a timeout and honour the stop flag.
- A stalled call **inside a held lock** parks every other thread on a bare
  `acquire()`, so the stack you need is not the one that looks busy.

## Diagnosing a teardown that will not finish

Dump every thread's stack when a join goes long — and **dump it twice**. Blocked
and merely-slow are indistinguishable from one dump and obvious from two.

Log it at warning level, not debug: the person whose box is wedged has no reason
to be running with debug logging on.

## What fails silently

- The five-second "kill" does not kill.
- A window-property stop flag is lowered by the wrong generation.
- A setting write during an update is dropped with no error.
- An orphan thread keeps its own database connections and keeps working.
- A stuck teardown can leave a shared flag raised until Kodi restarts.

## Open questions

- The ~10 s generation overlap was measured on one machine during a repository
  update; whether it scales with add-on size or thread count is unknown.
- Whether Kodi 22 changed the unload-then-replace ordering in
  `CAddonInstallJob::DoWork` has not been checked.

## See also

- [`kodi-plugin-handles`](../kodi-plugin-handles/SKILL.md) — the other way an
  add-on hangs something
- [`kodi-announcements`](../kodi-announcements/SKILL.md) — the shared thread your
  callbacks arrive on
- [`kodi-freeze-diagnosis`](../kodi-freeze-diagnosis/SKILL.md) — when it is Kodi
  rather than your add-on
