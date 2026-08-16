---
name: kodi-plugin-handles
description: >
  Close your plugin handle, or hang the caller forever. Use when a library node,
  favourite, or widget never finishes loading, when Kodi appears to freeze on
  entering a plugin folder, or when writing a route that does an action rather
  than returning a listing. Explains why enabling reuselanguageinvoker turns a
  previously harmless bug into an unbounded hang.
license: CC-BY-SA-4.0
metadata:
  category: python-addon
  verified-kodi: "21.3 Omega"
  verified-platform: "Linux x86_64"
  verified-date: "2026-08-13"
  verified-method: "sourced"
---

# Every directory route must close its handle

A plugin route reached as a **directory** must call
`xbmcplugin.endOfDirectory(handle)` — including on the failure path. If it does
not, it hangs its caller, and the wait has no upper bound.

```python
def route(handle):
    try:
        ...
        xbmcplugin.addDirectoryItems(handle, items)
    finally:
        xbmcplugin.endOfDirectory(handle, succeeded=ok)
```

## Why the wait is unbounded

`CScriptRunner::WaitOnScriptResult` in
`xbmc/interfaces/generic/ScriptRunner.cpp` has two loops for the non-main-thread
case, and **the first has no timeout at all**:

```cpp
// wait for the script to finish or be cancelled
while (!IsCancelled() && CScriptInvocationManager::GetInstance().IsRunning(scriptId) &&
       !m_scriptDone.Wait(20ms))
  ;

// give the script 30 seconds to exit before we attempt to stop it
XbmcThreads::EndTime<> timer(30s);
while (!timer.IsTimePast() && ... )
  ;
```

The 30-second timer applies to the *second* loop — stopping a script that has
been asked to finish. The first loop polls `IsRunning(scriptId)` forever.

## Interpreter reuse is what makes this fatal

This bug used to fail fast. Without `<reuselanguageinvoker>`, the interpreter
died after each invocation, the script was marked done, and the caller was
released — so a missing `endOfDirectory` was survivable and often unnoticed.

With reuse enabled, **the invoker thread parks instead of exiting**. Kodi marks a
script done only from `CLanguageInvokerThread::OnExit`, which never comes. So
turning on interpreter reuse converts a latent bug into an unbounded hang, in
routes written before reuse existed.

Measured: 20 s and climbing, with no ceiling.

## Which callers actually wait

| Caller | Waits? |
|---|---|
| `RunPlugin(...)` | no |
| Context-item scripts | no |
| **Library nodes** | **yes** |
| **Favourites** | **yes** |
| Anything reaching the route via `GetDirectory` | **yes** |

So the hazard is not the routes you fire deliberately — it is the ones a user
reaches by browsing. An action route invoked with `RunPlugin` can leave its
handle open for years without anyone noticing, then hang the moment someone adds
it as a favourite.

## A route that opens a modal cannot be a library node

Kodi runs a node's `<path>` through `CDirectory::GetDirectory`, and a modal
dialog fights that fetch. The route will not complete.

Validate in the plugin process, fire one IPC message, and let a service own the
dialog on its own worker thread. See
[`kodi-addon-driving`](../kodi-addon-driving/SKILL.md).

## Node paths carry a trailing slash

A library node's `<path>` is a folder path, so Kodi writes it **with a trailing
slash**. A handler table keyed on `mode=syncplay` will miss `mode=syncplay/` and
silently serve the add-on root instead — which looks like the node being empty
or wrong, not like a routing bug.

**The slash lands on whichever query parameter comes last**, which is `mode`
only for routes that take no other. Stripping it off `mode` after parsing fixes
the single-parameter routes and leaves every other one broken, in a way that
looks like a server problem rather than a routing one.

Measured on Omega 21.3, two hand-made nodes in one folder:

| `<path>` | |
|---|---|
| `plugin://<ADDON>/?mode=continuewatching/` | lists its items — the slash is on `mode` |
| `plugin://<ADDON>/?mode=browse&view=<VIEW_ID>&type=movies&folder=all/` | fails |

The second reached the route with `folder="all/"`. That matched no node key, so
the listing fell through to its "drill into a container id" branch and asked the
server for an item called `all/` — a 400, a failed fetch, and a node that reads
as broken:

```
[addon] browse failed (movies/all/): GET http://<JELLYFIN_HOST>/Items -> 400
error <general>: GetDirectory - Error getting plugin://<ADDON>/?…&folder=all/
error <general>: GetDirectory - Error getting library://video/<folder>/test-02.xml/
```

The same path with the slash removed returned the whole library. So strip **one
trailing slash off the raw query string before parsing it**, not off `mode`
afterwards:

```python
params = dict(parse_qsl(query.lstrip("?").rstrip("/")))
```

Check first that no parameter of yours legitimately ends in a slash. A slash
parked on a dummy trailing parameter is harmless — verified — so it is only ever
the last value that has to tolerate it.

## What fails silently

- A missing `endOfDirectory` produces no error, no log line, and no timeout — the
  caller simply never returns.
- Enabling `reuselanguageinvoker` breaks routes that worked yesterday, with no
  change to those routes.
- A trailing slash routes to the add-on root rather than erroring — and when it
  lands on a parameter other than `mode`, the route runs and fails downstream,
  so the log blames the server rather than the path.
- An action route with an open handle is harmless until something waits on it.

## Open questions

- Whether Kodi 22 added a timeout to the first loop has not been checked against
  22 source; the citation above is from 21.3.
- The 20 s figure is simply where observation stopped, not a bound.

## See also

- [`kodi-addon-manifest`](../kodi-addon-manifest/SKILL.md) — enabling interpreter
  reuse correctly in the first place
- [`kodi-addon-driving`](../kodi-addon-driving/SKILL.md) — firing routes without
  the UI, and the IPC pattern for modals
- [`kodi-freeze-diagnosis`](../kodi-freeze-diagnosis/SKILL.md) — when the whole UI
  has stopped rather than one fetch
