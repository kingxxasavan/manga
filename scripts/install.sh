#!/usr/bin/env bash
# Sets Greg up on a Linux server. Safe to run again.
#   ./scripts/install.sh            core install
#   ./scripts/install.sh --voice    also install voice
set -euo pipefail
cd "$(dirname "$0")/.."
HOME_DIR="${GREG_HOME:-$HOME/.greg}"
VOICE=0; [ "${1:-}" = "--voice" ] && VOICE=1
say() { printf '\n== %s\n' "$*"; }

say "Checking what is on this machine"
if ! command -v uv >/dev/null; then
  echo "Installing uv (Python package manager)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
NODE_MAJOR=0
command -v node >/dev/null && NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 24 ]; then
  echo "NOTE: Node 24 or newer is needed for the npm tool servers (found: ${NODE_MAJOR})."
  echo "      Install it from https://nodejs.org, then run: greg tools sync"
fi

say "Installing Greg"
if [ "$VOICE" = 1 ]; then uv sync --extra voice; else uv sync; fi
uv tool install --force --editable . >/dev/null
mkdir -p "$HOME_DIR"
if [ ! -f .env ] && [ ! -f "$HOME_DIR/.env" ]; then
  cp .env.example "$HOME_DIR/.env" && chmod 600 "$HOME_DIR/.env"
  echo "Created $HOME_DIR/.env. Put your keys in it."
fi

say "Models"
if command -v ollama >/dev/null; then
  for model in qwen3:8b qwen3:4b qwen2.5-coder:7b nomic-embed-text; do
    ollama pull "$model" || echo "Could not pull $model, run it by hand later."
  done
else
  echo "Ollama is not installed. Either install it (https://ollama.com) or put"
  echo "NVIDIA_API_KEY in $HOME_DIR/.env to use Nvidia's hosted models."
fi

say "Claude Code (for code creation)"
if command -v claude >/dev/null; then
  claude mcp add --scope user greg-memory -- greg mcp >/dev/null 2>&1 \
    && echo "Claude can now look up your preferences while it codes." \
    || echo "greg-memory is already registered with Claude."
else
  echo "Not installed. Greg will use its own coder. To add Claude later:"
  echo "  npm install -g @anthropic-ai/claude-code && ./scripts/install.sh"
fi

if [ "$VOICE" = 1 ]; then
  say "Voice"
  uv tool install piper-tts >/dev/null
  uvx --from piper-tts python -m piper.download_voices en_US-lessac-medium --data-dir "$HOME_DIR/voices"
fi

if [ "$NODE_MAJOR" -ge 24 ]; then
  say "Tool servers (downloads the pinned versions, takes a few minutes the first time)"
  greg tools sync || echo "Some tool servers did not start. Greg works without them. See above."
fi

say "Done"
echo "Check everything:   greg doctor"
echo "Tell Greg about you: greg aboutme"
echo "Start chatting:      greg"
