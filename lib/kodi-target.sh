# shellcheck shell=bash
# Resolve a named Kodi target into KODI_* variables.
#
# Sourced by the kodi-* helpers in bin/. Not executable, not a command.
#
# Targets live in ~/.config/kodi-drive/targets.env (mode 0600) so that no host,
# port, or credential ever appears in a repo, a CLAUDE.md, or an agent's output.
# See targets.env.example.
#
# Precedence, highest first:
#   1. KODI_HOST / KODI_PORT / ... already set in the environment
#   2. the target named by $KODI_TARGET, else $KODI_TARGET_DEFAULT
#   3. built-in defaults (localhost:8080, Kodi's own documented defaults)
#
# Licence: GPL-2.0-or-later

kd_config_file() {
    printf '%s/kodi-drive/targets.env' "${XDG_CONFIG_HOME:-$HOME/.config}"
}

# Uppercase and sanitise a target name into the variable-name token.
# "living-room" -> "LIVING_ROOM"
kd_token() {
    printf '%s' "$1" | tr '[:lower:]-' '[:upper:]_' | tr -cd 'A-Z0-9_'
}

kd_load_target() {
    local cfg token
    cfg="$(kd_config_file)"

    if [ -f "$cfg" ]; then
        # Warn but continue: a wrong mode is worth flagging, not fatal, and the
        # helpers still work from environment variables alone.
        local mode
        mode="$(stat -c%a "$cfg" 2>/dev/null || stat -f%Lp "$cfg" 2>/dev/null || echo '')"
        case "$mode" in
            600|400) ;;
            '') ;;
            *) echo "kodi-drive: $cfg is mode $mode; it holds credentials." \
                    "Run: chmod 600 '$cfg'" >&2 ;;
        esac
        # shellcheck disable=SC1090
        . "$cfg"
    fi

    : "${KODI_TARGET:=${KODI_TARGET_DEFAULT:-}}"

    if [ -n "${KODI_TARGET:-}" ]; then
        token="$(kd_token "$KODI_TARGET")"
        # Copy KODI_<TOKEN>_HOST -> KODI_HOST, and so on, but never clobber a
        # value the caller set explicitly on the command line.
        local key src dest
        for key in TRANSPORT HOST PORT USER PASS ESPORT ADDR LOG SHOTS; do
            src="KODI_${token}_${key}"
            dest="KODI_${key}"
            if [ -z "${!dest:-}" ] && [ -n "${!src:-}" ]; then
                printf -v "$dest" '%s' "${!src}"
                export "${dest?}"
            fi
        done
    fi

    # Kodi's own documented defaults, so a fresh local install works with no config.
    : "${KODI_TRANSPORT:=http}"
    : "${KODI_HOST:=127.0.0.1}"
    : "${KODI_PORT:=8080}"
    : "${KODI_USER:=kodi}"
    : "${KODI_PASS:=kodi}"
    : "${KODI_ESPORT:=9777}"
    : "${KODI_LOG:=$HOME/.kodi/temp/kodi.log}"
    export KODI_TRANSPORT KODI_HOST KODI_PORT KODI_USER KODI_PASS KODI_ESPORT KODI_LOG
}

# POST a JSON-RPC request. Body on stdout, diagnostics on stderr.
kd_rpc() {
    curl -fsS --max-time "${KODI_RPC_TIMEOUT:-10}" \
        -u "$KODI_USER:$KODI_PASS" \
        -H 'Content-Type: application/json' \
        -d "$1" \
        "http://$KODI_HOST:$KODI_PORT/jsonrpc"
}

# Fail early with an actionable message rather than a curl exit code, because
# "connection refused" here almost always means one specific misconfiguration.
kd_require_rpc() {
    if ! kd_rpc '{"jsonrpc":"2.0","method":"JSONRPC.Ping","id":1}' >/dev/null 2>&1; then
        cat >&2 <<EOF
kodi-drive: cannot reach Kodi JSON-RPC at $KODI_HOST:$KODI_PORT

Check, in this order:
  1. Kodi is running.
  2. Settings > Services > Control > "Allow remote control via HTTP" is ON.
     It is OFF by default, and this is the usual cause.
  3. The port matches (Kodi's default is 8080).
  4. Credentials match, if "Require authentication" is on.

Configure the target in $(kd_config_file) — see targets.env.example.
To find a Kodi on the network instead, use the kodi-connect skill.
EOF
        return 1
    fi
}
