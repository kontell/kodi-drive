#!/usr/bin/env python3
"""Mirror upstream agent-facing documents, and report when they drift.

Kodi's own AGENTS.md is normative for anything we contribute upstream, and it is
explicitly a document the team intends to expand. A skill that paraphrases it goes
stale silently, so the rule here is the repo's usual one: link to the canonical
copy, and keep a verbatim snapshot only so that drift is detectable.

The snapshots are byte-identical to upstream, which makes the check a single blob
hash comparison rather than a diff nobody reads.

    python3 scripts/sync-upstream-docs.py --check    # exit 1 if upstream moved
    python3 scripts/sync-upstream-docs.py --update   # refresh snapshot + manifest

`--check` needs no credentials, but anonymous GitHub API calls are rate limited to
60/hour per IP. Set GITHUB_TOKEN when running it in CI.
"""

from __future__ import annotations

import argparse
import base64
import difflib
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "upstream" / "manifest.json"

# Add a row to mirror another upstream document. Keep `local` under docs/upstream/
# so the "never hand-edit these" rule in that directory's README covers it.
DOCS = [
    {
        "repo": "xbmc/xbmc",
        "path": "AGENTS.md",
        "local": "docs/upstream/xbmc-AGENTS.md",
        "why": "Kodi's rules for AI agents contributing to the project.",
    },
]


def blob_sha(data: bytes) -> str:
    """Git's blob hash, so the value is comparable with the API's `sha` field."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def fetch(repo: str, path: str) -> tuple[bytes, str, str]:
    """Return (content, blob sha, html url) for a file on the default branch."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "kodi-drive-sync",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    content = base64.b64decode(payload["content"])
    return content, payload["sha"], payload["html_url"]


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="report drift and exit 1 if any snapshot is stale")
    mode.add_argument("--update", action="store_true",
                      help="refresh the snapshots and the manifest")
    args = ap.parse_args()

    manifest = load_manifest()
    drifted: list[str] = []
    failed: list[str] = []

    for doc in DOCS:
        key = f"{doc['repo']}:{doc['path']}"
        local = ROOT / doc["local"]

        try:
            content, sha, html_url = fetch(doc["repo"], doc["path"])
        except urllib.error.HTTPError as exc:
            # A 404 is itself news: upstream renamed or removed the document.
            failed.append(f"{key}: HTTP {exc.code} {exc.reason}")
            continue
        except OSError as exc:
            failed.append(f"{key}: {exc}")
            continue

        have = local.read_bytes() if local.exists() else b""

        if args.update:
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(content)
            manifest[key] = {
                "upstream": html_url,
                "local": doc["local"],
                "blob_sha": sha,
                "why": doc["why"],
            }
            state = "unchanged" if have == content else "updated"
            print(f"{state}: {doc['local']} ({sha[:12]})")
            continue

        recorded = manifest.get(key, {}).get("blob_sha")
        if blob_sha(have) == sha and recorded == sha:
            print(f"current: {doc['local']} ({sha[:12]})")
            continue

        drifted.append(key)
        print(f"\nDRIFT: {key} has changed upstream", file=sys.stderr)
        print(f"  upstream: {html_url}", file=sys.stderr)
        print(f"  snapshot: {doc['local']}", file=sys.stderr)
        print(f"  recorded {recorded or '(none)'} -> upstream {sha}", file=sys.stderr)
        diff = difflib.unified_diff(
            have.decode("utf-8", "replace").splitlines(),
            content.decode("utf-8", "replace").splitlines(),
            fromfile=f"snapshot/{doc['path']}", tofile=f"upstream/{doc['path']}",
            lineterm="",
        )
        for line in diff:
            print(f"  {line}", file=sys.stderr)

    if args.update:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(f"wrote {MANIFEST.relative_to(ROOT)}")
        return 1 if failed else 0

    if failed:
        for line in failed:
            print(f"ERROR: {line}", file=sys.stderr)
    if drifted or failed:
        print("\nRun: python3 scripts/sync-upstream-docs.py --update", file=sys.stderr)
        print("then re-read the skills that cite it — the pointer may now be wrong.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
