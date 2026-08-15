---
name: jellyfin-test-server
description: >
  Stand up a disposable Jellyfin server from source — exact version, no root, no
  Docker, first-run wizard completed over the API. Use when a Jellyfin client
  add-on or server plugin needs a real server to develop against, when a bug
  only reproduces on a specific server version, or when a test needs instances
  it can create and destroy by script. Covers the API-only setup, folder-drop
  plugin installs, and the in-process restart that silently refuses to re-read
  a replaced plugin DLL.
license: CC-BY-SA-4.0
metadata:
  category: adjacent
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-15"
  verified-method: observed
---

# A disposable Jellyfin server from source

Testing a Jellyfin client add-on or server plugin against the household's real
server means every mistake lands on a box people watch things on. The packaged
alternatives all fight you: distro packages want root and systemd and pin you to
one version, and Docker wants a running daemon. Running the server **from
source** avoids all of it — any tag or branch, state in a directory you own,
boots in seconds, and `rm -rf` of one directory is a factory reset. Everything
below was verified against Jellyfin 10.11.11 with .NET SDK 9.0.316.

## Build once

```sh
git clone https://github.com/jellyfin/jellyfin.git    # or a worktree off an existing clone
cd jellyfin && git checkout v10.11.11                 # any tag or release branch
dotnet build -c Release Jellyfin.Server/Jellyfin.Server.csproj
```

Jellyfin 10.11 targets `net9.0`, so a .NET 9 SDK is required. A warm rebuild is
~2.5 min; the output you run is
`Jellyfin.Server/bin/Release/net9.0/jellyfin.dll`.

## Run with isolated state

```sh
D=$HOME/jf-instance          # one directory = one instance
dotnet Jellyfin.Server/bin/Release/net9.0/jellyfin.dll \
  --nowebclient --datadir "$D/data" --cachedir "$D/cache" --logdir "$D/log"
```

- **`--nowebclient` is load-bearing.** Without it the server checks for
  jellyfin-web content, logs an error, and exits with code 1
  (`Jellyfin.Server/Program.cs`, the `webContentPath` check). With the flag you
  need no jellyfin-web checkout at all; every client and test talks HTTP to
  `:8096`.
- A fresh datadir answers `GET /System/Info/Public` within a few seconds, with
  `"StartupWizardCompleted":false`.
- The instance writes only under `$D`: `data/config/*.xml`, `data/data/` (the
  databases), `data/plugins/`, and `log/log_YYYYMMDD.log`. Deleting `$D` is a
  factory reset; copying it is a snapshot.

## First-run wizard over the API

No web client means no browser wizard. The `/Startup` endpoints take an
identity header and no token — this exact sequence was verified end-to-end on a
virgin datadir:

```sh
B=http://127.0.0.1:8096
H='X-Emby-Authorization: MediaBrowser Client="setup", Device="cli", DeviceId="setup-1", Version="1.0"'

curl "$B/Startup/Configuration" -H "$H"                        # 200
curl -X POST "$B/Startup/Configuration" -H "$H" \
  -H 'Content-Type: application/json' \
  -d '{"UICulture":"en-US","MetadataCountryCode":"US","PreferredMetadataLanguage":"en"}'   # 204
curl "$B/Startup/User" -H "$H"                                 # 200 — keep this GET; see Open questions
curl -X POST "$B/Startup/User" -H "$H" \
  -H 'Content-Type: application/json' \
  -d '{"Name":"admin","Password":"<ADMIN_PW>"}'                # 204
curl -X POST "$B/Startup/Complete" -H "$H"                     # 204
```

Then authenticate and administer everything by token:

```sh
TOKEN=$(curl -s -X POST "$B/Users/AuthenticateByName" -H "$H" \
  -H 'Content-Type: application/json' \
  -d '{"Username":"admin","Pw":"<ADMIN_PW>"}' | jq -r .AccessToken)
A="Authorization: MediaBrowser Token=\"$TOKEN\""

curl -X POST "$B/Users/New" -H "$A" -H 'Content-Type: application/json' \
  -d '{"Name":"bot-a","Password":"<BOT_PW>"}'                  # extra users for multi-client tests
```

## Installing a server plugin: drop a folder

No repository or zip needed. Create `"$D/data/plugins/<Name>_<version>/"`
containing the plugin DLL and a `meta.json` — these five fields are sufficient
on 10.11.11:

```json
{
  "guid": "<your-plugin-guid>",
  "name": "My Plugin",
  "version": "10.11.0.2",
  "targetAbi": "10.11.0.0",
  "status": "Active"
}
```

then `curl -X POST "$B/System/Restart" -H "$A"` — the restart is **in-process**
(same PID) and the server answers again in ~6–12 s with the plugin loaded.

**Build plugins against the oldest server patch you support.** .NET binds an
assembly reference upward but never downward: a plugin compiled against the
10.11.11 NuGet packages is refused by a 10.11.7 server ("references an
incompatible version of one of the shared libraries"), so pin
`Jellyfin.Controller`/`Jellyfin.Data` to `[10.11.0]`, not a float.

## What fails silently

- **The in-process restart never re-reads a replaced plugin DLL.** The runtime
  caches plugin images by *path* for the life of the process, so overwrite the
  DLL, `POST /System/Restart`, and the rebuilt host runs the **old bytes** —
  while logging `Loaded assembly ... from <path>` as if it had read the file.
  Verified by replacing a DLL with a build whose version and behaviour
  differed: the old version string kept appearing until the plugin was given a
  **new folder path** (`Name_<newversion>/`, which is what real catalogue
  upgrades create). New bytes need a new folder or a process restart.
- **A plugin that throws in `IHostedService.StopAsync` turns the API restart
  into a shutdown.** The stop-phase exception is caught by the server's startup
  handler, logged as `[FTL] Error while starting server`, the restart is
  abandoned, and the process exits with code **0**. From source you just see
  the process end; on a packaged systemd deployment the clean exit reads as
  success and the unit stays down. Reproduced with a 6-line throwing hosted
  service.
- **A datadir on NFS leaves tombstones.** Deleting or upgrading a *loaded*
  plugin folder fails with `Unable to delete ... Directory not empty` — the
  mapped DLL gets silly-renamed to `.nfs*` and the folder survives until the
  process dies. WARN-level and harmless, but scripts that assert the folder is
  gone will disagree. Keep instance state on a local filesystem when you can.
- **`pkill -f jellyfin.dll` can kill your own shell** — the pattern matches the
  script's own command line. Use the bracket trick, `pkill -f "jellyfin[.]dll"`,
  which matched only the server's two processes when verified. The same trap
  and fix for Kodi is in
  [`kodi-process-control`](../../skills/kodi-process-control/SKILL.md).

## Verifying it

```sh
D=$(mktemp -d) && dotnet .../jellyfin.dll --nowebclient \
  --datadir "$D/data" --cachedir "$D/cache" --logdir "$D/log" &
sleep 5 && curl -s http://127.0.0.1:8096/System/Info/Public
```

A fresh instance reports its version and `"StartupWizardCompleted":false`
within seconds. Total cost of the full recipe — boot, wizard, user, plugin,
restart — is under a minute once the server is built.

## Open questions

- Whether the two GETs in the wizard sequence are strictly required. The
  sequence was verified *with* them; skipping them is untested, and
  `GET /Startup/User` looks like it may materialise the initial user record
  that the POST then renames.
- Whether five `meta.json` fields remain sufficient beyond 10.11 — catalogue
  installs write about a dozen (category, owner, overview, timestamp,
  autoUpdate, assemblies, …), and which of those other server versions insist
  on has not been probed.

## See also

- [`jellyfin-client`](../jellyfin-client/SKILL.md) — the client-side knowledge
  this server exists to test
- [`kodi-process-control`](../../skills/kodi-process-control/SKILL.md) — safe
  process handling; the pkill trap in its Kodi form
- [`kodi-test-rig`](../../skills/kodi-test-rig/SKILL.md) — the same
  disposability philosophy for the Kodi side of the connection
- [Jellyfin server source](https://github.com/jellyfin/jellyfin) — tags for
  every release; link rather than restate
