#!/usr/bin/env bash
# Installs Greg on a Linux server, start to finish. Safe to run again.
#
#   ./install.sh                  setup window, then install what you picked
#   ./install.sh --yes            ask nothing: best preset for this machine,
#                                 keys taken from your environment
#   ./install.sh --preset max     max, balanced, light or cloud
#   ./install.sh --no-setup       skip the window, install your last choices
#   ./install.sh --skip-models    do not download local models this time
#   ./install.sh --skip-tools     do not download the tool servers this time
#
# Keys are typed into the setup window (hidden) or picked up from your
# environment, for example:
#   NVIDIA_API_KEY=nvapi-... ANTHROPIC_API_KEY=sk-ant-... ./install.sh --yes
# They end up in ~/.greg/.env, readable only by you. Never pass a key as an
# argument: arguments are saved in your shell history.

set -euo pipefail
cd "$(dirname "$0")"

YES=0; PRESET=""; RUN_SETUP=1; SKIP_MODELS=0; SKIP_TOOLS=0
while [ $# -gt 0 ]; do
  case "$1" in
    -y|--yes) YES=1 ;;
    --preset) PRESET="${2:-}"; shift ;;
    --preset=*) PRESET="${1#*=}" ;;
    --no-setup) RUN_SETUP=0 ;;
    --skip-models) SKIP_MODELS=1 ;;
    --skip-tools) SKIP_TOOLS=1 ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

GREG_HOME_DIR="${GREG_HOME:-$HOME/.greg}"
LOCAL_BIN="$HOME/.local/bin"
NODE_DIR="$HOME/.local/share/greg/node"
export PATH="$LOCAL_BIN:$PATH"
WARNINGS=()

if [ -t 1 ]; then BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'; OFF=$'\033[0m'
else BOLD=""; DIM=""; RED=""; GREEN=""; OFF=""; fi
step() { printf '\n%s== %s%s\n' "$BOLD" "$*" "$OFF"; }
ok()   { printf '   %sok%s    %s\n' "$GREEN" "$OFF" "$*"; }
skip() { printf '   %sskip  %s%s\n' "$DIM" "$*" "$OFF"; }
warn() { printf '   %sFIX%s   %s\n' "$RED" "$OFF" "$*"; WARNINGS+=("$*"); }
die()  { printf '\n%s%s%s\n' "$RED" "$*" "$OFF" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
step "1 of 6  Basics"
[ "$(uname -s)" = "Linux" ] || warn "This script is written for Linux. On $(uname -s) some steps may not work."
have curl || die "curl is needed and is not installed. Install it with your package manager and run this again."

if ! have uv; then
  echo "   installing uv (it manages Python for Greg)"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || die "Could not install uv. See https://docs.astral.sh/uv/"
  export PATH="$LOCAL_BIN:$HOME/.cargo/bin:$PATH"
fi
have uv || die "uv was installed but is not on PATH. Open a new terminal and run this again."
ok "uv $(uv --version | awk '{print $2}')"

uv sync --quiet || die "Could not install Greg's Python packages."
uv tool install --quiet --force --editable . || die "Could not install the greg command."
have greg || die "The greg command was installed to $LOCAL_BIN but that is not on your PATH. Add it and run this again."
ok "greg command installed"

mkdir -p "$GREG_HOME_DIR"
chmod 700 "$GREG_HOME_DIR"

# ---------------------------------------------------------------------------
step "2 of 6  Setup"
if [ "$RUN_SETUP" = 1 ]; then
  setup_args=(--from-installer)
  [ "$YES" = 1 ] && setup_args+=(--yes)
  [ -n "$PRESET" ] && setup_args+=(--preset "$PRESET")
  set +e
  GREG_HOME="$GREG_HOME_DIR" greg setup "${setup_args[@]}"
  code=$?
  set -e
  [ "$code" = 3 ] && { echo; echo "Setup cancelled. Nothing was installed."; exit 0; }
  [ "$code" = 0 ] || die "Setup did not finish."
else
  skip "using your last choices"
fi

PLAN_FILE="$GREG_HOME_DIR/setup-plan"
[ -f "$PLAN_FILE" ] || die "No saved choices found. Run ./install.sh without --no-setup first."
PLAN_PRESET=""; PLAN_INSTALL_OLLAMA=0; PLAN_PULL_MODELS=""; PLAN_INSTALL_NODE=0
PLAN_INSTALL_CLAUDE=0; PLAN_INSTALL_VOICE=0; PLAN_SYNC_TOOLS=0; PLAN_ENABLE_SERVICE=0
# The plan is read line by line and never run as code. Only known names with
# plain values are accepted.
while IFS='=' read -r key value; do
  case "$key" in
    PRESET|INSTALL_OLLAMA|PULL_MODELS|INSTALL_NODE|INSTALL_CLAUDE|INSTALL_VOICE|SYNC_TOOLS|ENABLE_SERVICE)
      [[ "$value" =~ ^[A-Za-z0-9_.:/\ -]*$ ]] || die "The saved plan looks damaged. Run ./install.sh again."
      printf -v "PLAN_$key" '%s' "$value" ;;
  esac
done < "$PLAN_FILE"
ok "preset: ${PLAN_PRESET:-unknown}"

# ---------------------------------------------------------------------------
step "3 of 6  Models"
if [ "$SKIP_MODELS" = 1 ]; then
  skip "models (--skip-models)"
else
  if [ "$PLAN_INSTALL_OLLAMA" = 1 ] && ! have ollama; then
    echo "   installing Ollama (it may ask for your password)"
    if curl -fsSL https://ollama.com/install.sh | sh; then ok "Ollama installed"
    else warn "Ollama did not install. Get it from https://ollama.com, then run ./install.sh --no-setup"; fi
  fi
  if [ -n "$PLAN_PULL_MODELS" ]; then
    if have ollama; then
      # Make sure the Ollama server is answering before pulling.
      if ! ollama list >/dev/null 2>&1; then
        nohup ollama serve >"$GREG_HOME_DIR/ollama.log" 2>&1 &
        for _ in $(seq 1 30); do ollama list >/dev/null 2>&1 && break; sleep 1; done
      fi
      for model in $PLAN_PULL_MODELS; do
        echo "   pulling $model"
        if ollama pull "$model"; then ok "$model"; else warn "Could not pull $model. Later: ollama pull $model"; fi
      done
    else
      warn "Ollama is not installed, so no local models were pulled."
    fi
  else
    skip "no local models for this preset"
  fi
fi

# ---------------------------------------------------------------------------
step "4 of 6  Node and Claude Code"
install_node() {
  local arch base sums file tmp
  case "$(uname -m)" in
    x86_64) arch=x64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) return 1 ;;
  esac
  base="https://nodejs.org/dist/latest-v24.x"
  sums="$(curl -fsSL "$base/SHASUMS256.txt")" || return 1
  file="$(printf '%s\n' "$sums" | awk -v want="linux-$arch.tar.xz" 'index($2, want) && $2 ~ /^node-v/ {print $2; exit}')"
  [ -n "$file" ] || return 1
  tmp="$(mktemp -d)"
  curl -fsSL "$base/$file" -o "$tmp/$file" || { rm -rf "$tmp"; return 1; }
  # Check the download against the published checksum before unpacking it.
  (cd "$tmp" && printf '%s\n' "$sums" | grep -F "  $file" | sha256sum -c - >/dev/null 2>&1) || { rm -rf "$tmp"; return 1; }
  rm -rf "$NODE_DIR"; mkdir -p "$NODE_DIR" "$LOCAL_BIN"
  tar -xJf "$tmp/$file" -C "$NODE_DIR" --strip-components=1 || { rm -rf "$tmp"; return 1; }
  rm -rf "$tmp"
  for bin in node npm npx; do ln -sf "$NODE_DIR/bin/$bin" "$LOCAL_BIN/$bin"; done
}

node_major() { "$1" -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0; }
if [ -x "$NODE_DIR/bin/node" ] && [ "$(node_major "$NODE_DIR/bin/node")" -ge 24 ]; then
  ok "Node $("$NODE_DIR/bin/node" --version) (installed earlier)"
elif [ "$PLAN_INSTALL_NODE" = 1 ]; then
  echo "   installing Node 24 into $NODE_DIR"
  if install_node; then ok "Node $("$NODE_DIR/bin/node" --version)"
  else warn "Node did not install. Get Node 24 from https://nodejs.org, then run ./install.sh --no-setup"; fi
else
  skip "Node"
fi
# Prefer the Node installed above for everything that follows.
[ -d "$NODE_DIR/bin" ] && export PATH="$NODE_DIR/bin:$PATH"

if [ "$PLAN_INSTALL_CLAUDE" = 1 ] && ! have claude; then
  if have npm; then
    echo "   installing Claude Code"
    if npm install -g @anthropic-ai/claude-code >/dev/null 2>&1; then
      # npm puts it next to its Node. Link it where your shell looks.
      have claude && ln -sf "$(command -v claude)" "$LOCAL_BIN/claude"
      ok "Claude Code installed"
    else
      warn "Claude Code did not install. Later: npm install -g @anthropic-ai/claude-code"
    fi
  else
    warn "Claude Code needs npm, which is missing. Greg will use its own coder for now."
  fi
fi
if have claude; then
  # Lets Claude look up your About Me and preferences while it writes your code.
  if claude mcp add --scope user greg-memory -- greg mcp >/dev/null 2>&1; then ok "Claude can read your preferences"
  else ok "Claude already knows where your preferences are"; fi
else
  skip "Claude Code (Greg codes with its own model)"
fi

# ---------------------------------------------------------------------------
step "5 of 6  Voice, tools and background service"
if [ "$PLAN_INSTALL_VOICE" = 1 ]; then
  echo "   installing voice (this downloads speech models)"
  if uv tool install --quiet --force --editable ".[voice]" && uv tool install --quiet piper-tts; then
    voice_dir="$GREG_HOME_DIR/voices"
    mkdir -p "$voice_dir"
    if uvx --quiet --from piper-tts python -m piper.download_voices en_US-lessac-medium --data-dir "$voice_dir" >/dev/null 2>&1
    then
      ok "voice installed"
      # The microphone side needs one system library that only root can add.
      if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
        warn "To use the microphone here, also run: sudo apt install libportaudio2"
      fi
    else warn "The voice file did not download. Later: uvx --from piper-tts python -m piper.download_voices en_US-lessac-medium --data-dir $voice_dir"; fi
  else
    warn "Voice did not install. Text chat is not affected."
  fi
else
  skip "voice"
fi

if [ "$SKIP_TOOLS" = 1 ]; then
  skip "tool servers (--skip-tools)"
elif [ "$PLAN_SYNC_TOOLS" = 1 ]; then
  echo "   downloading tool servers at their pinned versions"
  if GREG_HOME="$GREG_HOME_DIR" greg tools sync; then ok "tool servers ready"
  else warn "Some tool servers did not start. Greg works without them. Later: greg tools sync"; fi
else
  skip "tool servers"
fi

if [ "$PLAN_ENABLE_SERVICE" = 1 ]; then
  if have systemctl && systemctl --user show-environment >/dev/null 2>&1; then
    mkdir -p "$HOME/.config/systemd/user"
    cp scripts/greg.service "$HOME/.config/systemd/user/greg.service"
    systemctl --user daemon-reload
    GREG_HOME="$GREG_HOME_DIR" greg stop >/dev/null 2>&1 || true  # the service takes over
    if systemctl --user enable --now greg >/dev/null 2>&1; then
      loginctl enable-linger "$USER" >/dev/null 2>&1 || true
      ok "Greg runs in the background now (logs: journalctl --user -u greg -f)"
    else
      warn "The background service did not start. See: systemctl --user status greg"
    fi
  else
    warn "No user systemd on this machine, so no background service. Greg starts when you open the chat."
  fi
else
  skip "background service (Greg starts when you open the chat)"
fi

# ---------------------------------------------------------------------------
step "6 of 6  Checkup"
# If you skipped the tool servers, the checkup must not download them behind
# your back, so it runs with them switched off.
checkup_tools=1
{ [ "$SKIP_TOOLS" = 1 ] || [ "$PLAN_SYNC_TOOLS" != 1 ]; } && checkup_tools=0
GREG_HOME="$GREG_HOME_DIR" GREG_OUTSIDE_TOOLS="$checkup_tools" greg doctor || true
# The checkup starts a server to test against. Stop it again so the next
# `greg` starts fresh with your normal settings. A background service is left alone.
[ "$PLAN_ENABLE_SERVICE" = 1 ] || GREG_HOME="$GREG_HOME_DIR" greg stop >/dev/null 2>&1 || true

echo
if [ ${#WARNINGS[@]} -gt 0 ]; then
  printf '%sInstalled, with %d thing(s) to fix:%s\n' "$BOLD" "${#WARNINGS[@]}" "$OFF"
  for w in "${WARNINGS[@]}"; do printf '  %s\n' "$w"; done
else
  printf '%sInstalled.%s\n' "$BOLD" "$OFF"
fi
cat <<EOF

Next:
  greg aboutme     tell Greg who you are
  greg train       practice run: talk to it your way and see what it learns
  greg             chat

If your shell says "greg: command not found", add this to ~/.bashrc and open a
new terminal:
  export PATH="\$HOME/.local/bin:\$PATH"
EOF
