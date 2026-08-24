---
name: kodi-android-standby
description: >
  What Kodi on Android TV keeps doing while the TV is in standby, and what it
  stops doing. Use when a burst of stale notifications appears the moment the TV
  wakes, when a PVR or service add-on never sees a sleep event, when a socket
  that was healthy all evening is found dead in the morning, or before writing
  an add-on that toasts from a background thread. Covers the GUI pump that stops
  with the surface while every add-on thread keeps running, the toast queue that
  has no cap and no expiry, and the sleep broadcast that a TV can simply not send.
license: CC-BY-SA-4.0
metadata:
  category: diagnosis
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Android TV 14 (Sony Bravia)"
  verified-date: "2026-08-22"
  verified-method: observed
---

# Android TV standby

Turn on a TV that has been in standby all night with Kodi running, and the first
thing on screen is a run of "Lost connection" / "Connected" toasts, one after
another, from an add-on whose server was fine the whole time. The add-on's log
shows nothing new at wake. The PVR add-ons on the same box show an `OnSystemWake`
with no `OnSystemSleep` before it. None of that is the add-on misbehaving: it is
what standby looks like from inside Kodi on Android, where the screen going away
stops the GUI and nothing else.

Source lines below are Piers (22.0b1), with Omega (21.3) in parentheses where
they differ. The observations are from one Sony Bravia on Android 14 running
Piers, read over ADB ([`kodi-adb`](../kodi-adb/SKILL.md)).

## The GUI stops; everything else keeps running

Android destroys Kodi's rendering surface when the activity goes to the
background, and Kodi ties GUI processing to that surface:

- `CXBMCApp::surfaceDestroyed` calls `SetRenderGUI(false)`, and the surface
  callbacks are the only Android call sites that set it back to `true` —
  `xbmc/platform/android/activity/XBMCApp.cpp:1788` and `:1779`
  (Omega `:1886`, `:1877`).
- `CApplication::FrameMove` runs the window manager, and with it every dialog's
  `FrameMove`, only inside `if (processGUI && renderGUI)` —
  `xbmc/application/Application.cpp:1545`, `:1562`, `:1589` (Omega `:1824`,
  `:1841`, `:1868`).

Nothing else is gated. Python service threads, PVR client threads, the JSON-RPC
web server and the EPG/timer update loops all run as normal. Observed across a
fourteen-hour standby: a service add-on's sync thread logged database activity
every few minutes, a PVR client polled its timers every 60 s (765 polls), and
the web server logged JSON-RPC requests from another machine at 09:53 — while
the log had no `surfaceCreated` between `00:47` and `14:42`.

So "the TV is off" means "the GUI is frozen with a live process behind it", and
anything an add-on hands to the GUI in that time waits.

## Toasts queue without limit and replay at wake

`xbmcgui.Dialog().notification()` lands in `CGUIDialogKaiToast::QueueNotification`
(`xbmc/interfaces/legacy/Dialog.cpp:347`, Omega `:346`), and that queue is a
plain `std::queue` with no cap and no expiry (`xbmc/dialogs/GUIDialogKaiToast.h:37`).

Two details of `CGUIDialogKaiToast` decide what the user sees at wake:

- **Only an identical consecutive toast is dropped.** `AddToQueue` compares the
  new toast with the *last queued one* on type, icon, caption and description
  and returns if all four match (`GUIDialogKaiToast.cpp:77-82`, Omega `:76-81`).
  Two messages that alternate — "lost", "connected", "lost", "connected" — never
  match their predecessor and all go in.
- **A backlog replays at about one toast per second, not one per display
  time.** `DoWork` pops the next toast as soon as the *previous* toast's
  `messageTime` has elapsed and its fade label has finished scrolling
  (`GUIDialogKaiToast.cpp:101-112`). `messageTime` is the minimum-message-time
  parameter, 1000 ms by default (`GUIDialogKaiToast.h:16`); the `time` a Python
  caller passes is `displayTime`, which only governs when the dialog closes once
  the queue is empty (`:167-184`).

`DoWork` is driven from `Application.cpp:1550` (Omega `:1829`), inside the
`renderGUI` guard above — so the queue does not move while the surface is gone.

Observed: a Jellyfin client service add-on on the Bravia toasts on every
websocket open and close. Its socket recycled 16 times during the standby window
(next section), queueing 16 warning toasts and 17 info toasts — the first
"connected", 30 s after Kodi started, also came after the surface was gone —
that Kodi could not show. The user's report at wake was "repeated
connected/disconnected messages"; that the burst *was* this backlog is
inferred — the log has no websocket event after the wake, and the queue is the
only place those toasts could have waited — but the mechanism itself is sourced
above.

The fix belongs in the add-on, not the user's settings. A toast fired from a
background thread describes the moment it was raised, and on an Android TV that
moment may be hours before it is drawn. Toast a *state*, not an *edge*:
suppress "lost" until the connection has stayed down for a grace period, and
"connected" unless a "lost" was actually shown. A `notifyConnection`-style
opt-out is a courtesy, not a fix.

Run the grace on a loop the add-on already has — the service's
`waitForAbort(1)` tick — not on a `threading.Timer` armed per edge. The timer
is a second clock on its own thread, and everything it needs is overhead the
tick form does not: a cancel protocol, a generation stamp to outvote a callback
that has already left `cancel()`'s reach, a shutdown hook, and a thread that
holds the service alive — and it leaks out of any test that triggers a
disconnect for some other reason. A timestamp stamped on disconnect, cleared on
connect and checked once a second is the whole machine. Decide *and* toast under
one lock: with the toast raised after the lock is released, a reconnect landing
in that gap announces "connected" first and the stale "lost" queues behind it,
so the last notice the user sees is wrong (inferred from a review of the first
implementation and a test that reproduces the ordering, 2026-08-24).

## `OnSystemSleep` is a broadcast the TV may never send

The whole Android sleep path hangs on one intent. Kodi registers
`ACTION_SCREEN_OFF` alongside `ACTION_SCREEN_ON` (`XBMCApp.cpp:262`, `:268`;
Omega `:259`, `:265`), and the receiver lives until `onDestroy`
(`XBMCApp.cpp:408`). On `SCREEN_OFF`, `CXBMCApp::OnSleep` sets the power syscall
to suspended (`:1292-1343`, Omega `:1398-1461`); `CAndroidPowerSyscall::PumpPowerEvents`
turns that into `CPowerManager::OnSleep` (`AndroidPowerSyscall.cpp:35`), which
announces `System.OnSleep` to Python monitors and calls `OnSleep` on the PVR
manager, which calls every client's `OnSystemSleep` (`PowerManager.cpp:194`,
`:207`). `SCREEN_ON` does the same in reverse, ending in `OnSystemWake`
(`AndroidPowerSyscall.cpp:39`).

Observed on the Bravia across the fourteen-hour standby, every intent Kodi
received, in full:

```
00:47:09 CXBMCApp::onReceive - Got intent. Action: android.intent.action.BATTERY_CHANGED
00:47:09 CXBMCApp::onReceive - Got intent. Action: android.net.conn.CONNECTIVITY_CHANGE
14:42:29 CXBMCApp::onReceive - Got intent. Action: android.intent.action.SCREEN_ON
```

No `SCREEN_OFF`, so no `Got device sleep intent`, no `PumpPowerEvents: OnSleep
called`, and neither PVR client logged its `OnSystemSleep` handler. At wake,
`PumpPowerEvents: OnWake called` was logged and both PVR clients logged
`OnWake` — an `OnSystemWake` with no matching sleep — after which the PVR
manager re-fetched channel groups and channels from every client.

Consequences for add-on authors:

- A PVR add-on's "suspended" flag, the pattern inherited from `pvr.iptvsimple`'s
  `ConnectionManager`, is never set on such a TV. Its health-check loop keeps
  pinging through standby, and any "do not notify while suspended" logic never
  engages. Do not rely on sleep to quiet a PVR add-on on Android.
- `OnSystemWake` must be safe to receive without a preceding `OnSystemSleep`.
- A Python service waiting for `System.OnSleep` in `onNotification` to pause
  work will wait forever on this TV; `System.OnWake` still arrives.

Why this TV withholds `SCREEN_OFF` is an open question below. The safe
assumption is that it can happen, because the alternative is code that only
works on the boxes that happen to send it.

## Standby quietly kills idle sockets

The same service add-on keeps a websocket to its server with an application
keepalive every 30 s and detects silence after 75 s. Across the standby window
that detector fired **16 times**, ten to sixty minutes apart, each time followed
by a successful reconnect 15–80 s later — so the network was up, and the
established socket was what died:

```
13:39:53 websocket half-open: no traffic for 75s; recycling
13:40:56 websocket disconnected (None None)
13:41:47 websocket connected
```

Over the same hours, two other Kodi instances running the same add-on against
the same server — a wired Linux desktop and a Wi-Fi tablet, both awake — logged
**zero** half-open events. The TV was on Wi-Fi.

A dead socket that still accepts writes is the failure shape nothing at the
transport level reports. If an add-on holds a long-lived connection on an
Android TV, give it an inbound-liveness timer; do not wait for `recv()` to fail.
And note the interaction with the previous section: every one of those 16
recycles raised toasts into a GUI that was not running.

## What fails silently

- A toast raised while the surface is gone is not dropped and not shown. It is
  shown later, at ~1 s intervals, with no indication it is stale.
- `AddToQueue`'s duplicate check only collapses *consecutive identical* toasts.
  Any alternation defeats it.
- `SCREEN_OFF` not arriving produces no log line of any kind. The only evidence
  is the absence of `Got device sleep intent` before a `Got device wakeup intent`.
- A PVR add-on's `OnSystemSleep` never being called looks exactly like a PVR
  add-on that has no sleep handling.
- A TCP socket killed by standby keeps accepting sends.

## Verifying it

Over ADB, with `K` set to Kodi's data directory (see
[`kodi-adb`](../kodi-adb/SKILL.md)). One pattern per call — compound greps get
their escaping mangled in `adb shell`:

```sh
adb -s $D shell "grep -n 'surfaceDestroyed' $K/temp/kodi.log" | tail -3
adb -s $D shell "grep -n 'surfaceCreated'   $K/temp/kodi.log" | tail -3
adb -s $D shell "grep -n 'Got intent'       $K/temp/kodi.log"
adb -s $D shell "grep -n 'PumpPowerEvents'  $K/temp/kodi.log"
```

A `surfaceDestroyed` with no `surfaceCreated` until hours later is the GUI
stopped; `Got intent` shows whether `SCREEN_OFF` ever arrived; `PumpPowerEvents`
shows which of `OnSleep`/`OnWake` Kodi actually delivered.

To watch the toast backlog form, count an add-on's connection edges in the
window between those two surface events, then compare with what the user saw.

## Open questions

- Why this Bravia never broadcasts `ACTION_SCREEN_OFF` to Kodi is not known.
  Candidates are Sony's standby implementation and Android 14 background
  broadcast restrictions. It was observed on one TV; whether other Android TV
  devices behave the same way has not been checked, and a box that *does* send
  it would take the documented sleep path.
- What kills the idle socket is not established — the TV's Wi-Fi power saving
  and its "network standby" mode are the obvious suspects, and neither was
  toggled to confirm. The Wi-Fi tablet that saw no drops was awake, so the
  comparison separates "in standby" from "awake", not Wi-Fi from wired.
- No Python-visible way to read the render-GUI state was found —
  `grep -rn RENDERGUI xbmc/guilib/guiinfo/` is empty on Piers — so an add-on
  cannot ask "will this toast be drawn now?" before raising it. Coalescing in
  the add-on is the only route found.
- `ApplicationPowerHandling.cpp:94` and `:105` also flip `SetRenderGUI`; they
  were not traced and are not part of the Android surface path described here.

## See also

- [`kodi-adb`](../kodi-adb/SKILL.md) — reaching the log on the TV in the first place
- [`kodi-pvr-addon`](../kodi-pvr-addon/SKILL.md) — the client callbacks
  `OnSystemSleep`/`OnSystemWake` belong to
- [`kodi-announcements`](../kodi-announcements/SKILL.md) — `System.OnSleep` and
  `System.OnWake` as a Python monitor sees them
- [`kodi-idle-screensaver`](../kodi-idle-screensaver/SKILL.md) — putting the
  display to sleep deliberately, which is the other direction
- [`kodi-architecture`](../kodi-architecture/SKILL.md) — where `CApplication::FrameMove`
  sits in the app thread, and what else runs off it
- [`kodi-logs`](../kodi-logs/SKILL.md) — reading the log without reading all of it
