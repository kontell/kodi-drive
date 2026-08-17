---
name: jellyfin-test-server
description: >
  Stand up a disposable Jellyfin server from source — exact version, no root, no
  Docker, first-run wizard completed over the API. Use when a Jellyfin client
  add-on or server plugin needs a real server to develop against, when a bug
  only reproduces on a specific server version, or when a test needs instances
  it can create and destroy by script. Covers the API-only setup, folder-drop
  plugin installs, the in-process restart that silently refuses to re-read a
  replaced plugin DLL, and what changes on Jellyfin v12 — where the legacy auth
  headers stop working by default and targetAbi is renumbered.
license: CC-BY-SA-4.0
metadata:
  category: adjacent
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-17"
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
# Authorization, NOT X-Emby-Authorization. The legacy header is rejected by
# default from v12 on — see "Jellyfin v12" below.
H='Authorization: MediaBrowser Client="setup", Device="cli", DeviceId="setup-1", Version="1.0"'

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

**Stage the artifacts you declare, not the publish directory.** Two traps in a
row here:

- `dotnet build` does **not** copy `PackageReference` assemblies for a library
  project, so a folder staged from `bin/Release/<tfm>/` contains the plugin DLL
  and none of its dependencies. The host then dies at DI time with
  `FileNotFoundException` naming the missing package. Use `dotnet publish`.
- But do **not** then copy all of `publish/`. It also contains
  `MediaBrowser.Controller.dll`, `MediaBrowser.Model.dll`, `Jellyfin.Data.dll`
  and friends, and those shadow the host's own assemblies inside the plugin's
  `AssemblyLoadContext`. Copy only your plugin plus its genuinely external
  dependencies.

**The version the server reports is the assembly's, not `meta.json`'s.** A folder
whose `meta.json` carries the new version `12.0.0.2` still shows the old number
in `GET /Plugins` if `AssemblyVersion` was not bumped with it — which also breaks
any release CI that asserts tag, `AssemblyVersion` and `meta.json` agree.

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
- **A plugin that throws while services are built takes the whole server down —
  on a cold start, not just a restart.** A bad plugin is not skipped in favour
  of a working server: the host throws during service construction and the
  process exits, so you have no server at all. Any script that installs a
  plugin should be prepared to move the folder aside and restart, or a bad
  build leaves you with nothing to debug against.
- **`/System/Info/Public` answers before the server has finished starting**, and
  an early reply is a valid JSON object with fields such as `ServerName` and
  `Version` simply absent. A readiness loop that polls for HTTP 200 and then
  reads a field races and throws. Gate on a field you need being present.
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

## Jellyfin v12

Verified on `v12.0-rc5` built from source with .NET SDK 10.0.300. The recipe
above still works; these are the differences that break it if you assume 10.11.

**10.12 and 12.0 are the same release, renamed.** There is no `v10.12` tag and
no `release-10.12.z` branch — the tags are `v12.0-rc1` onward and
`SharedVersion.cs` reads `12.0.0`. A checkout's stale `master` ref may still say
`10.12.0`, so read the tag, not the branch.

**Legacy authentication is off by default, and this is the one that bites.**
`ServerConfiguration.EnableLegacyAuthorization` lost its `= true` initializer, so
a fresh v12 install writes `false`. The gating code did not change — only the
default — which makes it invisible in a diff. Measured against a fresh instance:

| form | v12 default |
|---|---|
| `Authorization: MediaBrowser ..., Token="..."` | 200 |
| `?ApiKey=<token>` | 200 |
| `?api_key=<token>` | **401** |
| `X-Emby-Authorization:` header | **401** |
| `X-Emby-Token:` header | **401** |
| `Authorization: Emby ...` scheme name | **401** |

On the **WebSocket** endpoint the same rejection arrives as **403 on the
handshake** rather than 401, which reads like a routing fault instead of an auth
one. Any tooling still using the legacy forms needs updating, or the server
needs `EnableLegacyAuthorization` turned back on.

**Declare targetAbi `12.0.0.0`; the pre-rename spelling is a trap.** The check is
`_appVersion >= targetAbi` with `_appVersion` now `12.0.0`. A plugin built for the
old numbering declares targetAbi `10.12.0.0`, which fails that comparison and
lands as `NotSupported`. A plugin declaring the older abi `10.11.0.0` still
passes.

That same comparison is what makes shipping a v12 build **safe for existing
10.11 servers**: verified by dropping a byte-identical v12 plugin folder into a
running 10.11.11 instance — its routes were absent, nothing was loaded, the log
carried no errors, and the server ran normally. The catalogue filters by
`targetAbi` in the browse list, the version list and the install path, so a
10.11 server is never offered it either.

**Everything else that moved:**

- **`net10.0`**, and `global.json` pins `sdk 10.0.0` — a .NET 9 SDK is refused
  outright.
- Build `-c Release`. `Debug` enables `AnalysisMode=AllEnabledByDefault` with
  `TreatWarningsAsErrors`.
- **One `<datadir>/data/jellyfin.db`** (EF Core, SQLite). `library.db` is gone.
  Instance directories now carry marker files, so two servers pointed at
  overlapping directories are refused rather than silently corrupting.
- The wizard endpoints still work, with two changes: `POST /Startup/RemoteAccess`
  **dropped `EnableAutomaticPortMapping`**, and `POST /Startup/User` now returns
  **400 on an empty password**. Three of the five are now `[Obsolete]`.
- New CLI: `--restore-archive`, `--mode MediaServer|MigrateSystem|SeedSystem`.
- `Jellyfin.Controller` and `Jellyfin.Data` **are published on nuget.org for the
  rc line** (`12.0.0-rcN`), so a plugin can be built against v12 without a local
  feed. Pin exactly — the float rule above applies unchanged.

**Not a v12 change, but it costs a failed run:** there is no
`GET /LiveTv/TunerHosts` and no `GET /LiveTv/ListingProviders`. Both routes are
POST + DELETE only and a GET returns **405**. The configured set is readable only
from `GET /System/Configuration/livetv`, which is also where `RecordingPath` is
set. Identical in 10.11.

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
