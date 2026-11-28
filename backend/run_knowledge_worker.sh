#!/bin/sh
set -eu
umask 077
backend_dir="${ALT_IA_BACKEND_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"
state_dir="${ALT_IA_KNOWLEDGE_HOST_DIR:-$HOME/.local/share/alt-ia/knowledge}"
secret_dir="${ALT_IA_SECRET_HOST_DIR:-$HOME/.config/alt-ia}"
model_dir="${ALT_IA_MODEL_HOST_DIR:-$HOME/.cache/alt-ia-models}"
image="${ALT_IA_KNOWLEDGE_IMAGE:-alt-ia-knowledge:20261128}"
mkdir -p "$model_dir"
chmod 700 "$model_dir"
docker run -d --name alt-ia-knowledge --restart unless-stopped \
  --user "$(id -u):$(id -g)" --cpus=2 --memory=4g --pids-limit=192 \
  --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m --shm-size=256m \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e HF_HOME=/var/cache/alt-ia-models/huggingface -e HF_HUB_DISABLE_XET=1 \
  -v "$backend_dir:/app:ro" -w /app \
  -v "$state_dir:/var/lib/alt-ia/knowledge" \
  -v "$model_dir:/var/cache/alt-ia-models" \
  -v "$secret_dir/nvidia-key:/run/secrets/alt-ia-key:ro" \
  -v "$secret_dir/knowledge-key:/run/secrets/alt-ia-knowledge-key:ro" \
  "$image"
