"""Resolve a named Kodi target into settings, for the Python helpers in bin/.

The shell counterpart is lib/kodi-target.sh; both read the same file so a target
configured once works for every helper.

Targets live in ~/.config/kodi-drive/targets.env (mode 0600) so that no host,
port, or credential ever appears in a repo, a CLAUDE.md, or an agent's output.

Licence: GPL-2.0-or-later
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Kodi's own documented defaults, so a fresh local install works unconfigured.
DEFAULTS = {
    "TRANSPORT": "http",
    "HOST": "127.0.0.1",
    "PORT": "8080",
    "USER": "kodi",
    "PASS": "kodi",
    "ESPORT": "9777",
}

KEYS = ("TRANSPORT", "HOST", "PORT", "USER", "PASS", "ESPORT", "ADDR", "LOG", "SHOTS")

_ASSIGN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def config_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "kodi-drive" / "targets.env"


def token(name: str) -> str:
    """'living-room' -> 'LIVING_ROOM', matching kd_token in the shell library."""
    return re.sub(r"[^A-Z0-9_]", "", name.upper().replace("-", "_"))


def _parse(path: Path) -> dict[str, str]:
    """Read shell-style KEY=VALUE assignments.

    Deliberately not a shell: this file holds credentials, and executing it to
    read it would be a poor trade. Quote stripping and ~ / $HOME expansion cover
    everything the format needs.
    """
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _ASSIGN.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if value and value[0] in "\"'" and value[-1] == value[0] and len(value) > 1:
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        value = value.replace("$HOME", str(Path.home()))
        if value.startswith("~"):
            value = str(Path(value).expanduser())
        out[key] = value
    return out


def load(target: str | None = None) -> dict[str, str]:
    """Return resolved settings. Environment always wins over the config file."""
    cfg = config_file()

    if cfg.exists():
        try:
            mode = cfg.stat().st_mode & 0o777
            if mode not in (0o600, 0o400):
                print(f"kodi-drive: {cfg} is mode {mode:o}; it holds credentials. "
                      f"Run: chmod 600 '{cfg}'", file=sys.stderr)
        except OSError:
            pass

    filevars = _parse(cfg)
    name = (target
            or os.environ.get("KODI_TARGET")
            or filevars.get("KODI_TARGET_DEFAULT", ""))

    resolved = dict(DEFAULTS)
    if name:
        tok = token(name)
        for key in KEYS:
            value = filevars.get(f"KODI_{tok}_{key}")
            if value:
                resolved[key] = value

    # An explicit KODI_HOST in the environment beats anything configured.
    for key in KEYS:
        value = os.environ.get(f"KODI_{key}")
        if value:
            resolved[key] = value

    resolved.setdefault("LOG", str(Path.home() / ".kodi" / "temp" / "kodi.log"))
    resolved["TARGET"] = name
    return resolved
