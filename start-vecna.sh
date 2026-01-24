#!/bin/bash
# ===================================================================
# VECNA HIVE-MIND STARTUP SCRIPT
# ===================================================================
# Checks infrastructure, sets up venv if needed, and starts vecna.
#
# Usage:
#   ./start-vecna.sh          # Start vecna interactive shell
#   ./start-vecna.sh chat     # Run vecna chat
#   ./start-vecna.sh <cmd>    # Run vecna <cmd>
# ===================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_ACTIVATE="$VENV_DIR/bin/activate"

# Minimal banner
echo -e "${CYAN}⟁ VECNA${NC} ${DIM}starting...${NC}"

# -------------------------------------------------------------------
# 1. Check/Load .env
# -------------------------------------------------------------------
if [ -f ".env" ]; then
    set -a; source .env; set +a
else
    echo -e "${YELLOW}⚠${NC} No .env file (optional)"
fi

# -------------------------------------------------------------------
# 2. Check Docker
# -------------------------------------------------------------------
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker not running"
    exit 1
fi

# -------------------------------------------------------------------
# 3. Start containers if needed
# -------------------------------------------------------------------
POSTGRES_RUNNING=$(docker ps --filter "name=vecna-postgres" --filter "status=running" -q 2>/dev/null)
REDIS_RUNNING=$(docker ps --filter "name=vecna-redis" --filter "status=running" -q 2>/dev/null)

if [ -z "$POSTGRES_RUNNING" ] || [ -z "$REDIS_RUNNING" ]; then
    echo -e "${DIM}  Starting containers...${NC}"
    docker compose -f docker-compose.memory.yml up -d > /dev/null 2>&1
    
    # Wait for healthy (max 30s)
    for i in {1..30}; do
        POSTGRES_HEALTHY=$(docker ps --filter "name=vecna-postgres" --filter "health=healthy" -q 2>/dev/null)
        REDIS_HEALTHY=$(docker ps --filter "name=vecna-redis" --filter "health=healthy" -q 2>/dev/null)
        [ -n "$POSTGRES_HEALTHY" ] && [ -n "$REDIS_HEALTHY" ] && break
        sleep 1
    done
fi

# Verify healthy
POSTGRES_HEALTHY=$(docker ps --filter "name=vecna-postgres" --filter "health=healthy" -q 2>/dev/null)
REDIS_HEALTHY=$(docker ps --filter "name=vecna-redis" --filter "health=healthy" -q 2>/dev/null)

if [ -z "$POSTGRES_HEALTHY" ]; then
    echo -e "${RED}✗${NC} PostgreSQL unhealthy"
    exit 1
fi

if [ -z "$REDIS_HEALTHY" ]; then
    echo -e "${RED}✗${NC} Redis unhealthy"
    exit 1
fi

echo -e "${GREEN}✓${NC} Infrastructure ready"

# -------------------------------------------------------------------
# 4. Setup venv if needed
# -------------------------------------------------------------------
NEEDS_INSTALL=false

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${DIM}  Creating venv...${NC}"
    python3 -m venv "$VENV_DIR"
    NEEDS_INSTALL=true
fi

if [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${RED}✗${NC} Venv broken, recreating..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
    NEEDS_INSTALL=true
fi

# -------------------------------------------------------------------
# 5. Check/Install dependencies
# -------------------------------------------------------------------
check_package() {
    "$VENV_PYTHON" -c "import $1" 2>/dev/null
}

if [ "$NEEDS_INSTALL" = true ] || ! check_package "vecna" || ! check_package "psycopg2" || ! check_package "aiohttp"; then
    echo -e "${DIM}  Installing dependencies...${NC}"
    source "$VENV_ACTIVATE"
    pip install --upgrade pip > /dev/null 2>&1
    pip install -e ".[postgres,embeddings,local]" > /dev/null 2>&1
    pip install aiohttp psycopg2-binary > /dev/null 2>&1
fi

# Final check
if ! "$VENV_PYTHON" -c "import vecna" 2>/dev/null; then
    echo -e "${RED}✗${NC} Failed to install vecna"
    exit 1
fi

echo -e "${GREEN}✓${NC} Vecna ready"

# -------------------------------------------------------------------
# 6. Migrate config if needed
# -------------------------------------------------------------------
MIGRATION_OUTPUT=$("$VENV_PYTHON" -c "
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
from vecna.config.loader import load_config
load_config(force_reload=True)
" 2>&1)

# Show migration message if it happened
if echo "$MIGRATION_OUTPUT" | grep -q "Migrating"; then
    echo -e "${CYAN}↻${NC} Config migrated to v2 (Copilot-only)"
fi

# -------------------------------------------------------------------
# 7. Check Copilot auth
# -------------------------------------------------------------------
AUTH_STATUS=$("$VENV_PYTHON" -c "
from vecna.auth import CopilotAuth
auth = CopilotAuth()
print('ok' if auth.is_authenticated() else 'no')
" 2>/dev/null || echo "no")

if [ "$AUTH_STATUS" != "ok" ]; then
    echo -e "${YELLOW}⚠${NC} Copilot not authenticated ${DIM}(run: vecna auth login)${NC}"
fi

echo ""

# -------------------------------------------------------------------
# 8. Run vecna
# -------------------------------------------------------------------
source "$VENV_ACTIVATE"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

if [ $# -eq 0 ]; then
    exec vecna
else
    exec vecna "$@"
fi
