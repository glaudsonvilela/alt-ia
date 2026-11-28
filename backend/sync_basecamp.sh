#!/bin/sh
set -eu

account_id="${1:?informe o ID da conta Basecamp}"
case "$account_id" in
  *[!0-9]*|'') echo 'ID da conta inválido' >&2; exit 2 ;;
esac

state_dir="${ALT_IA_KNOWLEDGE_HOST_DIR:-$HOME/.local/share/alt-ia/knowledge}"
mkdir -p "$state_dir"
chmod 700 "$state_dir"
umask 077

/usr/bin/flock -n "$state_dir/sync.lock" \
  /usr/bin/docker exec --user "$(id -u):$(id -g)" alt-ia-api python -u /app/basecamp_import.py \
    --state-dir /var/lib/alt-ia/knowledge \
    --key-file /run/secrets/alt-ia-knowledge-key \
    sync --account "$account_id" >> "$state_dir/sync.log" 2>&1
