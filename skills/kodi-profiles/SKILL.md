---
name: kodi-profiles
description: >
  Switch Kodi profiles from a script, and enable add-ons in the profile you
  actually meant. Use when isolating a problem in a clean profile, running A/B
  comparisons between add-on sets, or when Profiles.LoadProfile returns OK but
  nothing changes. Covers the silent failures in LoadProfile, the modal that
  blocks switching outright, and why Addons.SetAddonEnabled can install into the
  wrong profile without any error.
license: CC-BY-SA-4.0
metadata:
  category: diagnosis
  verified-kodi: "21.3 Omega, 22 Piers, 22.0rc1 Piers"
  verified-platform: "Linux x86_64"
  verified-date: "2026-10-22"
  verified-method: "observed"
---

# Driving Kodi profiles

A separate profile is the best tool for isolating a problem — most "Kodi is
broken" reports are one bad add-on, and a clean profile proves it in minutes. But
the JSON-RPC surface for profiles reports success far more readily than it
delivers it.

## `Profiles.LoadProfile` returns `"OK"` without switching

The call returns `"OK"` immediately. That is an acknowledgement that the request
was accepted, **not** that the profile changed.

If the outgoing profile has an add-on whose service will not stop, the switch
never completes, and the RPC result gives no hint whatsoever. Kodi is now wedged
between profiles.

**Always confirm, and treat a timeout as wedged rather than slow:**

```sh
kodi-remote get Profiles.LoadProfile '{"profile":"test"}'

for i in $(seq 1 20); do
  current=$(kodi-remote get Profiles.GetCurrentProfile)
  case "$current" in *'"test"'*) echo "switched"; break ;; esac
  sleep 1
done
```

**Call `Profiles.GetCurrentProfile` with no parameters.** Asking for `label`
looks natural and fails: `Profiles.Fields.Profile` enumerates only `thumbnail`
and `lockmode`, so `'{"properties":["label"]}'` is rejected with `Invalid
params` on both 21.3 and 22. `label` needs no requesting — it is
`Item.Details.Base.label`, `required: true`, and is always in the result.

The failure mode is the reason it matters here. A read-back that errors every
iteration never matches, so the loop above runs its full 20 seconds and reports
a healthy switch as wedged — a false negative inside the check written to catch
a false positive.

Once wedged, restarting Kodi is usually the only fix — see
[`kodi-process-control`](../kodi-process-control/SKILL.md), and note the wrapper
trap there, because a half-killed Kodi makes this much worse.

## A modal dialog blocks switching entirely

A Yes/No dialog (window `10100`) open on the current profile prevents
`LoadProfile` from completing at all.

This matters for ordering: **any automation that switches profiles must already
have its dialog-answering thread running before it issues the switch**, not
started afterwards in response to a hang. By the time you notice the hang, the
switch has already failed and the dialog is holding it.

Check for one before switching:

```sh
kodi-remote get GUI.GetProperties '{"properties":["currentwindow"]}'
```

## A JSON-RPC request in flight deadlocks the switch on Kodi 22

`LoadProfile` stops the web server with `MHD_stop_daemon`, which joins every
connection thread. A connection thread handling `XBMC.GetInfoBooleans` or
`XBMC.GetInfoLabels` is inside `CApplicationMessenger::SendMsg`, waiting for
the app thread, which is the thread joining it. Neither wait has a timeout.
Observed on 22.0rc1 Piers (Linux Flatpak) with `gdb -p` from the host;
`set sysroot /proc/<pid>/root` before `attach` finds the Flatpak's libraries:

```
Thread 1 "kodi.bin":  __pthread_clockjoin_ex -> MHD_stop_daemon -> CWebServer::Stop
   -> CNetworkServices::StopWebserver -> CNetworkServices::Stop(bool)
   -> CProfileManager::LoadProfile
Thread N "MHD-connection" (ten of them):  pthread_cond_wait
   -> CApplicationMessenger::SendMsg -> JSONRPC::CXBMCOperations::GetInfoBooleans
   -> CJSONRPC::MethodCall -> CHTTPJsonRpcHandler::HandleRequest
   -> CWebServer::AnswerToConnection
```

The poller was a shell loop on the box sampling `XBMC.GetInfoBooleans` every
3 s with a 20 s client timeout. A timed-out request leaves its connection
thread blocked all the same, so the pile grows with every poll. The log
signature is the app thread's last line being `stopping zeroconf publishing`
with no `CWebserver[8080]: Stopped` after it, while other threads keep
logging. `JSONRPC.Ping` still answers, because it never touches the app
thread, so a ping is not a liveness check for the UI; `XBMC.GetInfoLabels`
is, and it times out. Only SIGKILL clears it (`flatpak kill tv.kodi.Kodi` on
a Flatpak).

Upstream: xbmc/xbmc#29127, a Kodi 22 regression. The lock patch proposed
there covers the database path and not this `SendMsg` one.

Stop every poller before switching, and confirm the switch finished before
polling again.

### Same lock, second door: a switch during live TV on a timeshift buffer

`PrepareLoadProfile` runs inside that `m_critical`, and `CPVRManager::Stop`
stops playback from there (`xbmc/pvr/PVRManager.cpp:406`: `TMSG_MEDIA_STOP`,
sent by the app thread and so handled inline). `CVideoPlayer::CloseFile` then
joins the player thread. Observed on 22.0rc1 with a PVR channel playing through
inputstream.ffmpegdirect's timeshift buffer, `gdb -p` as above:

```
Thread 1 "kodi.bin":   std::thread::join -> CThread::StopThread -> CVideoPlayer::CloseFile
   -> CApplication::StopPlaying -> CApplicationMessenger::SendMsg
   -> PVR::CPVRManager::Stop -> CProfileManager::LoadProfile
Thread "VideoPlayer":  pthread_mutex_lock -> ffmpegdirect::TimeshiftStream::DemuxRead
   -> CDVDDemuxClient::Read -> CVideoPlayer::ReadPacket -> CVideoPlayer::Process
Thread "VideoPlayer":  __futex_lock_pi64 -> CProfileManager::GetUserDataFolder
   -> CSpecialProtocol::TranslatePath -> XFILE::CFile::Exists
   -> ADDON::Interface_Filesystem::file_exists -> ffmpegdirect::TimeshiftSegment::TimeshiftSegment
   -> ffmpegdirect::TimeshiftBuffer::AddPacket -> ffmpegdirect::TimeshiftStream::DoReadWrite
```

The timeshift writer holds ffmpegdirect's stream mutex while it adds a packet
(`src/stream/TimeshiftStream.cpp:98-99` at `22.2.7-Piers`), and opening a new
segment checks `kodi::vfs::FileExists` on a path under the default
`special://userdata/addon_data/inputstream.ffmpegdirect/timeshift`
(`src/stream/TimeshiftSegment.cpp:35`). `special://userdata` translates through
`CProfileManager::GetUserDataFolder` (`xbmc/filesystem/SpecialProtocol.cpp:156`),
which blocks on the lock the app thread holds. The demux read waits for the
stream mutex, the player thread never reaches its stop, and the join never
returns. The log signature is the app thread's last line being
`VideoPlayer: waiting for threads to exit`. Seen twice in a row on the same box;
both ended with SIGKILL.

So on Kodi 22, stop playback before switching profiles when a timeshifted
channel is playing.

## `Addons.SetAddonEnabled` applies to the loaded profile

There is no profile argument. The call acts on whichever profile is currently
loaded — so enabling an add-on while on the wrong profile silently enables it
somewhere it does not belong.

In an A/B comparison this destroys arm isolation with no visible error: both arms
end up with the same add-on set and the results look merely uninteresting rather
than wrong.

**Verify against the target profile's own database rather than trusting the call:**

```sh
sqlite3 "$HOME/.kodi/userdata/profiles/<profile>/Database/Addons33.db" \
  "SELECT addonID, enabled FROM installed WHERE addonID='plugin.video.example';"
```

The master profile's database is at `~/.kodi/userdata/Database/Addons33.db`;
per-profile ones live under `userdata/profiles/<name>/Database/`.

## Editing a non-active profile's add-on state directly

A profile that is not loaded can have its add-on enablement changed by writing to
its `Addons33.db`:

```sh
sqlite3 "$HOME/.kodi/userdata/profiles/<profile>/Database/Addons33.db" \
  "UPDATE installed SET enabled=1 WHERE addonID='plugin.video.example';"
```

This is the way out when profile switching is itself the broken thing. Kodi reads
the file when it loads that profile.

Only touch a profile Kodi does not currently have open, and copy the `-wal` and
`-shm` files alongside the `.db` if you are snapshotting rather than editing —
reading the `.db` alone gives a stale view.

## What fails silently

- `LoadProfile` returns `"OK"` for a switch that never happens.
- A modal blocks the switch with no error surfaced to the caller.
- `SetAddonEnabled` succeeds against the wrong profile and reports success.
- `JSONRPC.Ping` answers from a Kodi whose app thread is deadlocked in
  `LoadProfile`; the UI is dead and the log keeps ticking.
- A switch while a timeshifted PVR channel plays: Kodi stops the player inside
  the profile lock and the join never returns.
- All three produce a plausible-looking run rather than a failure, which is why
  every one of them needs an explicit read-back.

## Open questions

- After a switch on 22.0rc1 the PVR manager served the previous profile's
  channel and group ids: a fresh start on the master profile gave one channel
  id 66 and groups 2, 4, 5; after master -> OR -> master the same channel was
  23 and the groups 1 to 6, which are the OR profile's database ids.
  `PrepareLoadProfile` calls `pvrManager.Stop()` and not `Unload()`, so the
  loaded channel groups survive the switch. Whether they are then persisted
  into the new profile's database was not isolated; the OR profile's database
  did hold 33 channels for a client that has no server configured there.

- Whether `LoadProfile` wedges identically when the blocking add-on is a
  *service* versus a *plugin* has not been isolated — the observed cases were
  services that would not stop.
- The `Addons33` schema number is Kodi-21-specific. Kodi 22 may renumber it;
  check the actual filename before assuming the path.
- Whether Kodi caches any part of a non-active profile's add-on state in memory,
  which would make a direct `Addons33.db` edit take effect late or not at all,
  has not been tested.

## See also

- [`kodi-process-control`](../kodi-process-control/SKILL.md) — restarting a
  wedged Kodi without leaving two running
- [`kodi-library-data`](../kodi-library-data/SKILL.md) — Kodi's other databases,
  and which operations destroy data
