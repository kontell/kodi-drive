#!/usr/bin/env python3
"""Keep private data out of kodi-drive.

Two modes:

  --detect   Fail if anything in the tree looks like a hostname, address, credential,
             or personal path. Runs in CI and as a pre-commit hook.

  --redact   Rewrite files through `.scrub-map.local`, replacing known private strings
             with stable placeholders. This is what makes migrating thousands of lines
             of real debugging notes tractable — the same host becomes the same
             placeholder everywhere, so the prose stays readable.

Why this exists: skills here are harvested from real sessions, and real sessions are
saturated with hostnames, tokens, and IPs. Kodi itself makes this worse — it logs full
stream URLs including `api_key=` at debug level, so any pasted log excerpt is
credential-bearing until proven otherwise.

Licence: GPL-2.0-or-later
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAP_FILE = REPO / ".scrub-map.local"

SCAN_SUFFIXES = {".md", ".yml", ".yaml", ".json", ".txt", ".py", ".sh", ".xml", ".toml"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
# This file necessarily contains the patterns it looks for.
SKIP_FILES = {"scrub.py", ".scrub-map.local", ".scrub-map.example"}


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern
    hint: str


def _re(p: str) -> re.Pattern:
    return re.compile(p, re.IGNORECASE)


# Addresses documentation is allowed to use:
#   127.x, 0.0.0.0        loopback and unspecified
#   192.0.2.x etc         RFC 5737 documentation ranges
#   239.255.255.250       the SSDP multicast group, named in kodi-discover
#   10.255.255.1          the conventional blackhole address, used deliberately
#                         to simulate an unreachable server with a clean timeout
#                         rather than an instant refusal
ALLOWED_IPS = _re(
    r"^(127\.\d+\.\d+\.\d+|0\.0\.0\.0|255\.255\.255\.\d+"
    r"|192\.0\.2\.\d+|198\.51\.100\.\d+|203\.0\.113\.\d+"
    r"|10\.0\.0\.(50|60)|10\.255\.255\.(1|255)|239\.255\.255\.250)$"
)
# Version strings, durations, and semver look like dotted quads to a naive regex.
IPV4 = _re(r"(?<![\w.])((?:\d{1,3}\.){3}\d{1,3})(?![\w.])")

# `.local` is both a mDNS TLD and a config-file convention, so the hostname rule needs
# its own allowlist. The trailing lookahead already kills `settings.local.json`; these
# are the bare-suffix cases that survive it.
# `.home` is deliberately absent: it collides with `Path.home`, `user.home`, and
# similar attribute access far more often than it catches a real router domain.
# The trailing `(?!\s*\()` covers the same class for the remaining suffixes —
# `foo.internal(...)` is a method call, not a host.
HOSTNAME = _re(r"\b[a-z0-9][a-z0-9-]*\.(local|lan|internal|xyz|duckdns\.org|"
               r"ddns\.net|hopto\.org|no-ip\.(?:com|org)|workers\.dev)\b"
               r"(?![.\w-])(?!\s*\()")
ALLOWED_HOSTS = _re(
    r"^(settings\.local|scrub-map\.local|claude\.local|mcp\.local|env\.local|"
    r"config\.local|example\.(?:com|org|net)|test\.local|"
    # Kodi's own scraper value for a path row, not a host.
    r"metadata\.local)$"
)

RULES = [
    Rule("mac-address",
         _re(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b"),
         "MAC address — use <MAC>"),
    Rule("bearer-token",
         _re(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*"),
         "bearer token — use <API_KEY>"),
    Rule("jwt",
         re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
         "JWT — use <API_KEY>"),
    Rule("api-key-param",
         _re(r"\b(api_?key|apikey|access_?token|auth_?token|x-emby-token|"
             r"x-mediabrowser-token)\s*[=:]\s*[\"']?[A-Za-z0-9._-]{12,}"),
         "credential in a query parameter or header — use <API_KEY>. "
         "Kodi logs these at debug level, so check pasted log excerpts too"),
    Rule("password",
         _re(r"\b(password|passwd|pwd|secret)\s*[=:]\s*[\"']?(?!<|\$|changeme|"
             r"your|xxx|\.\.\.)[^\s\"',]{6,}"),
         "password — use <PASSWORD> or a $VAR"),
    # A Kodi add-on repository ships `addons.xml.md5`, so a bare 32-hex string is
    # genuinely ambiguous here. Lines that name a digest are exempt; everything else
    # is treated as a possible Jellyfin/Emby api_key.
    Rule("hex-secret",
         re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{32}(?![0-9a-fA-F])"),
         "32-hex string — Jellyfin/Emby api_keys and GUIDs look exactly like this"),
    Rule("uuid",
         _re(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
         "UUID — item and user ids are identifying; use <ID>"),
    Rule("home-path",
         re.compile(r"(?<![\w/])(/home/(?!<)[a-z][a-z0-9_-]*|"
                    r"/Users/(?!<)[A-Za-z][A-Za-z0-9_-]*|"
                    r"C:\\\\Users\\\\(?!<)[A-Za-z][A-Za-z0-9_-]*)"),
         "home directory with a real username — use ~ or /home/<user>"),
    Rule("email",
         _re(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b"),
         "email address"),
    Rule("network-share",
         _re(r"\b(smb|nfs|afp)://(?!<)[a-z0-9]"),
         "network share path — use <SHARE>"),
    Rule("adb-endpoint",
         re.compile(r"\badb\s+connect\s+(?!<)[\w.]+:\d+"),
         "ADB endpoint — use <ADB_SERIAL> or $KODI_TARGET"),
]


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        yield path


# Four-part version numbers are everywhere in this domain — Jellyfin plugin
# versions (10.11.0.1), .NET assembly versions (1.0.0.0) — and every octet is
# under 256, so the numeric check cannot separate them from an address.
#
# The exemption is deliberately narrow: a version keyword must sit immediately
# before the number, not merely somewhere on the line. A line-level test hides
# real addresses in ordinary prose — "connect to 172.16.9.9 for the build server"
# was exempted by the word "build" during testing. The optional quotes admit the
# JSON spellings ("version": "10.11.0.2", "targetAbi": "10.11.0.0") that a
# Jellyfin plugin meta.json example is made of, and the backtick admits the same
# number written as Markdown inline code in prose (targetAbi `12.0.0.0`), which
# is how a skill body spells it. The immediately-before requirement is unchanged,
# so this admits a spelling, not a line-level guess.
VERSION_PREFIX = _re(r"(version|assembly|semver|abi|\bv)[\"'`]?\s*[:=]?\s*[\"'`]?$")


def scan_line(line: str) -> list[tuple[str, str, str]]:
    """Return (rule, match, hint) for each finding on this line."""
    out = []
    for m in IPV4.finditer(line):
        ip = m.group(1)
        octets = ip.split(".")
        if any(int(o) > 255 for o in octets):
            continue  # a version string, not an address
        if ALLOWED_IPS.match(ip):
            continue
        if VERSION_PREFIX.search(line[:m.start(1)]):
            continue
        out.append(("ip-address", ip,
                    "IP address — use <KODI_HOST>, or an RFC 5737 range "
                    "(192.0.2.x, 198.51.100.x, 203.0.113.x) for examples"))

    # Claude Code writes an `originSessionId:` UUID into every memory file it
    # creates, so scanning a memory directory otherwise reports a uuid finding on
    # nearly every file and drowns the real ones. It identifies a session, not a
    # person or a media item.
    if re.match(r"^\s*originSessionId\s*:", line):
        return out

    for m in HOSTNAME.finditer(line):
        if ALLOWED_HOSTS.match(m.group(0)):
            continue
        out.append(("private-hostname", m.group(0),
                    "looks like a personal or LAN hostname — use <KODI_HOST> "
                    "or <SERVER_URL>"))

    # A digest is exempt when the line names one, OR when the line has the shape
    # `md5sum` output: 32 hex, whitespace, a filename. Kodi add-on repositories
    # ship addons.xml.md5, and any checksum block is a bare list of hashes with
    # no "md5" on the individual lines, so the same-line test alone is not enough.
    digest_line = (
        re.search(r"\b(md5|sha1|sha256|sha512|checksum|digest|hash)\b",
                  line, re.IGNORECASE)
        or re.match(r"^\s*[0-9a-f]{32}\s+\*?[\w./-]+\s*$", line)
    )
    for rule in RULES:
        if rule.name == "hex-secret" and digest_line:
            continue
        for m in rule.pattern.finditer(line):
            out.append((rule.name, m.group(0), rule.hint))
    return out


def rel(path: Path) -> str:
    """Repo-relative where possible; absolute otherwise.

    Callers may point this at files outside the repo — a staged copy, a harvest
    directory on another machine — so this must not assume containment.
    """
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def mask(s: str) -> str:
    """Never print a suspected secret back out in full."""
    s = s.strip()
    if len(s) <= 12:
        return s
    return f"{s[:6]}…{s[-4:]} ({len(s)} chars)"


def detect(paths: list[Path], quiet: bool) -> int:
    findings = 0
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").split("\n")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(lines, 1):
            for rule, match, hint in scan_line(line):
                findings += 1
                print(f"{rel(path)}:{n}: {rule}: {mask(match)}")
                if not quiet:
                    print(f"    {hint}")
    if findings:
        print(f"\n{findings} finding(s). Nothing here may identify a person, machine, "
              f"or network.\nIf a finding is a false positive, adjust the rule in "
              f"scripts/scrub.py rather than working around it.")
        return 1
    print(f"clean: {len(paths)} file(s) scanned")
    return 0


def load_map() -> list[tuple[str, str]]:
    """Load `private-string<TAB>PLACEHOLDER` pairs, longest first.

    Longest-first matters: a hostname must be replaced before the bare domain it
    contains, or you get `<HOST>.example.com` instead of `<HOST>`.
    """
    if not MAP_FILE.exists():
        print(f"error: {MAP_FILE.name} not found. Copy .scrub-map.example and fill it in.\n"
              f"It is gitignored — it holds the private strings it maps FROM.",
              file=sys.stderr)
        sys.exit(2)
    pairs = []
    for raw in MAP_FILE.read_text(encoding="utf-8").split("\n"):
        line = raw.split("#", 1)[0].strip() if not raw.startswith("#") else ""
        if not line:
            continue
        if "\t" in line:
            src, _, dst = line.partition("\t")
        else:
            src, _, dst = line.partition("  ")
        src, dst = src.strip(), dst.strip()
        if src and dst:
            pairs.append((src, dst))
    return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def redact(paths: list[Path], dry_run: bool) -> int:
    pairs = load_map()
    if not pairs:
        print(f"error: {MAP_FILE.name} has no entries", file=sys.stderr)
        return 2

    changed = 0
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        original, counts = text, {}
        for src, dst in pairs:
            n = text.count(src)
            if n:
                text = text.replace(src, dst)
                counts[src] = n
        if text != original:
            changed += 1
            total = sum(counts.values())
            print(f"{'would rewrite' if dry_run else 'rewrote'} {rel(path)}: {total} replacement(s)")
            for src, n in sorted(counts.items(), key=lambda kv: -kv[1]):
                print(f"    {n:>5}  {mask(src)}")
            if not dry_run:
                path.write_text(text, encoding="utf-8")

    print(f"\n{changed} file(s) {'would be ' if dry_run else ''}changed")
    if not dry_run and changed:
        print("Now run --detect: the map only catches strings you knew about.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--detect", action="store_true",
                      help="fail on anything that looks private")
    mode.add_argument("--redact", action="store_true",
                      help="apply .scrub-map.local to the given files")
    ap.add_argument("paths", nargs="*", type=Path,
                    help="files or directories (default: whole repo)")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --redact, show changes without writing")
    ap.add_argument("--quiet", action="store_true",
                    help="with --detect, omit the per-finding hint")
    args = ap.parse_args()

    targets: list[Path] = []
    for p in (args.paths or [REPO]):
        p = p.resolve()
        targets.extend([p] if p.is_file() else list(iter_files(p)))

    if not targets:
        print("no files to scan")
        return 0

    return detect(targets, args.quiet) if args.detect else redact(targets, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
