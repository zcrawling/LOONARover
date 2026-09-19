#!/usr/bin/env bash

set -u

GCS_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$GCS_ROOT/.runtime"
mkdir -p "$RUNTIME_DIR"

show_error() {
    local message=$1
    if command -v zenity >/dev/null 2>&1 && [[ -n "${DISPLAY:-}" ]]; then
        zenity --error --title="LOONAR" --text="$message" 2>/dev/null || true
    else
        printf '오류: %s\n' "$message" >&2
    fi
}

prompt_text() {
    local title=$1 message=$2 default_value=$3
    if command -v zenity >/dev/null 2>&1 && [[ -n "${DISPLAY:-}" ]]; then
        zenity --entry --title="$title" --text="$message" --entry-text="$default_value" 2>/dev/null
    else
        printf '%s [%s]: ' "$message" "$default_value" >&2
        local value
        IFS= read -r value
        printf '%s\n' "${value:-$default_value}"
    fi
}

valid_host() {
    [[ $1 =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]]
}

valid_ssh_target() {
    [[ $1 =~ ^[A-Za-z_][A-Za-z0-9_-]*@[A-Za-z0-9][A-Za-z0-9.-]*$ ]]
}
