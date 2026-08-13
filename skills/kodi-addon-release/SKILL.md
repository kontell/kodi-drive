---
name: kodi-addon-release
description: >
  Package and release a Kodi add-on without shipping a broken or incomplete zip.
  Use when setting up CI for an add-on, cutting a release, publishing to a
  repository, or working out why a release is missing a platform or carries the
  wrong version. Covers the GitHub Actions traps that produce a green build and a
  wrong artifact, and why packaging by include-list silently drops new files.
license: CC-BY-SA-4.0
metadata:
  category: shipping
  verified-kodi: "21.3 Omega, 22.0b1 Piers"
  verified-platform: "Linux x86_64, Android, Windows x86_64"
  verified-date: "2026-08-13"
  verified-method: "observed"
---

# Releasing an add-on

Every trap here produced a **green build and a wrong artifact**. None of them
failed loudly.

## A workflow-published release raises no `release` event

**The single most repeated lesson in this estate** — found independently in five
separate projects.

A release published by a workflow using the default `GITHUB_TOKEN` fires **no
`release` event**. Any downstream automation listening for it — a repository
updater, a `repository_dispatch` forwarder, a notification — never runs, and
nothing anywhere reports a problem.

GitHub does this deliberately, to stop workflows triggering workflows.

**Publish drafts by hand**, from the UI or with `gh` under your own credentials.
And keep a scheduled reconcile so a dropped dispatch degrades to latency rather
than permanent staleness.

## `upload-artifact` defaults to warning, not failing

`actions/upload-artifact` defaults to `if-no-files-found: warn`. A job whose build
produced nothing uploads nothing, logs a warning nobody reads, and **goes green**.

Real consequence: a release attached **10 assets from 12 green jobs**, and one
platform had never existed in the served repository for that entire release.

```yaml
- uses: actions/upload-artifact@v4
  with:
    if-no-files-found: error
```

And make the release job **refuse to draft** unless every expected artifact is
present. Counting is cheap; a missing platform is not.

## `actions/checkout` gives you the tag's tree, not yours

Every name grepped from the working tree — zip filename, release title, release
body — comes from **the commit the tag points at**, not from whatever you had
locally when you tagged.

Result, observed: a release tagged `v0.9.1`, titled "0.9.0", containing 0.9.0
zips. Entirely self-consistent, entirely wrong.

**Assert the tag matches `addon.xml`** in the workflow, and fail if it does not.

## Package by exclusion, not by inclusion

A build script listing the seven paths to include will silently omit everything
added since. One add-on shipped without a PNG its sleep-timer overlay drew,
because the file was added after the list was written.

Walk the tree and exclude dev-only paths instead. The failure mode reverses: you
ship something unnecessary rather than omitting something required.

Related: `git archive HEAD` can only package **committed** content, so a build
script built on it means uncommitted work cannot be tested as an installable zip
— there is no dev loop at all. Package the working tree, and *report* which files
git does not have committed.

The trade is real, though: packaging the working tree ships gitignored artefacts
too. One release carried 73 KB of somebody's test database into every install.
Keep the exclude list and `.gitattributes` `export-ignore` in step.

## `paths-ignore` on `pull_request` reports no checks at all

An all-ignored change produces **zero checks**, which breaks required-check
branch protection rather than passing it. Apply `paths-ignore` to pushes only.

## Windows and container runners

- **`zip` is not in Git Bash on `windows-2022`.** Use `7z a -tzip`, which is
  preinstalled and produces a standard zip.
- **`${{ github.workspace }}` is the host path.** Inside a container the workspace
  is bind-mounted at `/__w/...`, so absolute paths resolve to nothing (exit 127).
  The container's working directory *is* the workspace — use relative paths there.
- **On Windows, `${{ github.workspace }}` expands before bash sees it**, and bash
  eats the backslashes as escapes: `D:\a\proj\proj` becomes `Daprojproj`. Use
  `pwd -W` in Git Bash and quote every path argument.
- **Checkout before downloading artifacts** in a release job, or the download
  wipes the workspace.
- **Scope `contents: write` to the release job**, not the workflow, or the entire
  build matrix runs with write access.

## `<news>` suppresses the changelog fallback

A repository generator that falls back to `changelog.txt` will not do so if
`<news>` exists in `addon.xml`. A stale `<news>` therefore advertises the wrong
release notes indefinitely, and looks deliberate.

## Version and filename must not both be authoritative

If a zip's channel can be derived from both its version and a filename suffix,
they will eventually disagree. **Let one win, and refuse a name that disagrees
with itself** rather than resolving it silently — a mismatched artifact filed
into the wrong channel installs fine and is wrong.

## What fails silently

- A workflow-published release triggers nothing downstream.
- A job that built nothing uploads nothing and goes green.
- A version grepped from the tag's tree disagrees with the tag.
- An include-list drops every file added since it was written.
- `paths-ignore` on `pull_request` reports no checks rather than passing ones.

## Open questions

- The `GITHUB_TOKEN` behaviour is GitHub's documented design, but whether a
  fine-grained PAT with only `contents: write` also suppresses the event has not
  been tested here — only a personal token was confirmed to work.

## See also

- [`kodi-versions-abi`](../kodi-versions-abi/SKILL.md) — what version number to
  put on it, and which Kodi versions will accept it
- [`kodi-addon-manifest`](../kodi-addon-manifest/SKILL.md) — the `addon.xml` the
  tag has to match
- [Kodi wiki: Submitting Add-ons](https://kodi.wiki/view/Submitting_Add-ons) —
  the official repository process
