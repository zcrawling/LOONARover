#!/usr/bin/env bash
set -euo pipefail
batch=$(mktemp)
trap 'rm -f "$batch"' EXIT
# Replace only this table, atomically; preserve SSH and existing firewall tables.
if nft list table inet loonar_link_policy >/dev/null 2>&1; then
  echo 'delete table inet loonar_link_policy' > "$batch"
fi
cat /usr/local/lib/loonar/network/policy.nft >> "$batch"
nft --check --file "$batch"
nft --file "$batch"
