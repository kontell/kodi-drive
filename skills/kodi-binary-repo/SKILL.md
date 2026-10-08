---
name: kodi-binary-repo
description: >
  What Kodi's official binary add-on repository builds, for which platforms, and
  what makes a build reach users. Use when preparing a C++ add-on for
  xbmc/repo-binary-addons, deciding which platforms your own CI has to cover,
  or working out why a platform is missing or a new version has not appeared.
  Covers the two-file definition, the builder's platform and deploy lists, the
  tag that triggers a deploy, and the Kodi branch it compiles against.
license: CC-BY-SA-4.0
metadata:
  category: shipping
  verified-kodi: "22.0rc1 Piers"
  verified-platform: "Linux x86_64"
  verified-date: "2026-10-08"
  verified-method: "sourced"
---

# The official binary add-on repository

A Python add-on is submitted by copying its source into a repository. A binary
add-on is submitted as a pointer, and Team Kodi's builder then compiles your
repository for platforms you have never built on. Being listed means being built
for all of them, so what that builder does is the specification your own CI has
to meet first.

## A submission is two files

[`xbmc/repo-binary-addons`](https://github.com/xbmc/repo-binary-addons) has one
branch per Kodi version. An add-on is a directory holding:

```
<id>/<id>.txt        <id> <git url> <ref>
<id>/platforms.txt   all
```

```
pvr.iptvsimple https://github.com/kodi-pvr/pvr.iptvsimple Piers
pvr.waipu https://github.com/flubshi/pvr.waipu Piers
```

Observed on the `Piers` branch: 90 definitions, 88 of them naming a ref called
`Piers` and two naming `master`. So the convention is a branch in *your*
repository named for the Kodi version. The source stays where it is, and being
outside the `xbmc` and `kodi-pvr` organisations is no bar: `pvr.waipu` is.

The wiki's [Submitting Add-ons](https://kodi.wiki/view/Submitting_Add-ons) page
lists the Python and skin repositories and not this one. The pull requests that
add binary add-ons contain exactly those two files.

## What the builder compiles, and what it ships

An add-on's `Jenkinsfile` is one line, `buildPlugin(version: "Piers")`. That
function is
[`vars/buildPlugin.groovy`](https://github.com/xbmc/pipeline-library/blob/master/vars/buildPlugin.groovy)
in `xbmc/pipeline-library`; the line numbers below are at commit `902a3be`
(2025-12-27).

| Platform | Built | Deployed |
|---|---|---|
| `android-armv7`, `android-aarch64` | yes | yes |
| `osx-x86_64`, `osx-arm64` | yes | yes |
| `windows-i686`, `windows-x86_64` | yes | yes |
| `windows-arm64` | from Piers on | yes |
| `ios-aarch64`, `tvos-aarch64` | yes | **no** |

That is `PLATFORMS_VALID` (lines 21-41) and `PLATFORMS_DEPLOY` (lines 43-51).

**There is no Linux and no Windows Store.** Neither is in the list. Observed
from the other side: the directory index of `mirrors.kodi.tv/addons/piers/`
carries those seven deployed suffixes and no others. Linux users get binary
add-ons from their distribution — Debian packages `kodi-pvr-iptvsimple`, for one.
`pvr.iptvsimple` does compile a `Win64-UWP` configuration, in its
`azure-pipelines.yml` rather than here.

**`platforms.txt` does not narrow this build.** The builder writes its own
definition with `platforms.txt` set to `all` (line 161). The list is narrowed
only by a `platforms:` argument in the `Jenkinsfile` (line 67). The
`platforms.txt` you submit is read elsewhere: by `cmake/addons` when add-ons are
built from the definitions (`cmake/addons/CMakeLists.txt:331-333` at
`22.0rc1-Piers`).

## A build is not a release: deploying needs a tag

```groovy
if (platform in deploy && env.TAG_NAME != null)     // line 200
```

Every build archives its zip (line 197). Only a build of a **git tag** uploads to
the mirror. A push to the version branch is compiled on every platform and goes
no further, so a branch head that is not release-ready shows up as red builds on
their side and not as a broken add-on on users' machines.

The branch named for the newest Kodi version is also rebuilt weekly with no push
at all (line 58).

## It compiles against a branch head, and not always the one you expect

```groovy
kodiBranch = version == KODI_CURRENT_DEV_VERSION ? "master" : version   // line 109
```

`KODI_CURRENT_DEV_VERSION` is the last key of `VERSIONS_VALID` (lines 11-17),
and the map's own comment says it "has to be updated after a new version is
branched in the xbmc repo". Whatever you pin in your own CI, this builder uses
the head of an `xbmc` branch.

At `902a3be` the last key is `Piers`, so a Piers add-on is compiled against
`master`. By then `xbmc` already had a `Piers` branch, and `master`'s
`version.txt` read 23.0 ALPHA1. The interface versions written into the built
`addon.xml` come from whichever headers were compiled against — see
[`kodi-versions-abi`](../kodi-versions-abi/SKILL.md).

## Acceptance is at Team Kodi's discretion

Observed in the repository's pull requests in October 2026. The most recent new
add-on, `imagedecoder.svg`, was opened on 21 August 2026 and merged on the 25th.
In between, its repository was transferred into the `xbmc` organisation, and a
maintainer ran an automated security scan and posted the findings on the pull
request. A request to add two third-party PVR clients had been open since May
2023; its only maintainer reply, in August 2026, asked whether it was still
wanted.

## What fails silently

- A push to the version branch builds everywhere and ships nowhere. Without a
  tag there is no deploy, and nothing says so.
- A platform your CI never compiled fails for the first time on their builder.
- A `platforms.txt` exclusion does not stop the per-add-on build from compiling
  that platform.

## Open questions

- Whether Team Kodi's Jenkins runs `pipeline-library`'s default branch, and
  whether it was producing Piers builds against `master` at the time, was not
  checked — only the repository was read, not the Jenkins instance.
- `pvr.waipu` sits outside the organisations and carries a `Jenkinsfile`. What
  triggers its builds was not established.
- Kodi recognises the `ios-aarch64` and `tvos-aarch64` tags, and the builder
  archives those zips without deploying them. Whether a stock iOS or tvOS
  install can load an add-on library that arrives after the app was signed was
  not tested.

## See also

- [`kodi-binary-build`](../kodi-binary-build/SKILL.md) — building for these
  platforms yourself, before they do
- [`kodi-apple-targets`](../kodi-apple-targets/SKILL.md) — the SDK and minimum
  OS version the builder uses for each Apple target, and how to match them
- [`kodi-versions-abi`](../kodi-versions-abi/SKILL.md) — which Kodi accepts the
  result, and what a branch head does to that
- [`kodi-contributing`](../kodi-contributing/SKILL.md) — the add-on rules, which
  apply to binary add-ons as well
- [`kodi-addon-release`](../kodi-addon-release/SKILL.md) — releasing through a
  repository of your own
