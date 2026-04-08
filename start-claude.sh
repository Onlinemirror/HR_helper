#!/bin/bash
# Claude Code launcher (Linux / WSL)
# Run every time to start Claude

BASE_URL="https://litellm-proxy-ai-cp.acsolutions.ai"
CONFIG_FILE="$(dirname "$0")/claude-config.txt"

echo ""
echo "=== Starting Claude Code ==="
echo ""

# Load saved settings if available
SAVED_KEY=""
SAVED_MODEL=""
if [ -f "$CONFIG_FILE" ]; then
    SAVED_KEY=$(grep "^KEY=" "$CONFIG_FILE" 2>/dev/null | cut -d= -f2-)
    SAVED_MODEL=$(grep "^MODEL=" "$CONFIG_FILE" 2>/dev/null | cut -d= -f2-)
fi

# Ask for API key
if [ -n "$SAVED_KEY" ]; then
    MASKED="${SAVED_KEY:0:4}****"
    echo "Saved API key: $MASKED"
    read -p "Press Enter to use saved key, or type a new one: " USER_INPUT
    if [ -n "$USER_INPUT" ]; then
        API_KEY="$USER_INPUT"
    else
        API_KEY="$SAVED_KEY"
    fi
else
    while true; do
        read -p "Enter your API key: " API_KEY
        [ -n "$API_KEY" ] && break
        echo "API key cannot be empty."
    done
fi

# Ask for model
if [ -n "$SAVED_MODEL" ]; then
    echo "Saved model: $SAVED_MODEL"
    read -p "Press Enter to use saved model, or type a new one: " USER_INPUT
    if [ -n "$USER_INPUT" ]; then
        MODEL="$USER_INPUT"
    else
        MODEL="$SAVED_MODEL"
    fi
else
    while true; do
        read -p "Enter model name (e.g. claude-finance): " MODEL
        [ -n "$MODEL" ] && break
        echo "Model name cannot be empty."
    done
fi

# Save settings
printf "KEY=%s\nMODEL=%s\n" "$API_KEY" "$MODEL" > "$CONFIG_FILE"

# Check claude is installed
if ! command -v claude &>/dev/null; then
    echo ""
    echo "ERROR: Claude Code not found. Please run install-claude.sh first."
    exit 1
fi

# Set env vars and launch
echo ""
export ANTHROPIC_BASE_URL="$BASE_URL"
export ANTHROPIC_API_KEY="$API_KEY"

echo "ANTHROPIC_BASE_URL = $BASE_URL"
echo "ANTHROPIC_API_KEY  = [hidden]"
echo "Model              = $MODEL"
echo ""
echo "Launching Claude Code..."
echo ""

claude --model "$MODEL" --tools none
