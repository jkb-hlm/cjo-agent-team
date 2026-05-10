"""Shared configuration for CJO automations."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from automations dir first, fall back to parent cjo-team dir
_env_local = Path(__file__).parent / ".env"
_env_parent = Path(__file__).parent.parent / ".env"
load_dotenv(_env_local if _env_local.exists() else _env_parent)

# --- etracker ---
ETRACKER_TOKEN = os.getenv("ETRACKER_TOKEN")
ETRACKER_FUNNEL_ID = os.getenv("ETRACKER_ATTRIBUTION_FUNNEL_ID")

# --- GA4 ---
GA4_KEY_FILE = os.getenv("GA4_KEY_FILE")
GA4_PROPERTY_WEB = os.getenv("GA4_PROPERTY_WEBSHOP")
GA4_PROPERTY_APP = os.getenv("GA4_PROPERTY_APP")

# --- AB Tasty ---
ABTASTY_CLIENT_ID = os.getenv("ABTASTY_CLIENT_ID")
ABTASTY_CLIENT_SECRET = os.getenv("ABTASTY_CLIENT_SECRET")
ABTASTY_ACCOUNT_ID = os.getenv("ABTASTY_ACCOUNT_ID")

# --- Anthropic ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# --- PostgreSQL (VPS) ---
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")
PG_DATABASE = os.getenv("PG_DATABASE", "n8n")
PG_SCHEMA = "cjo"

# --- Slack ---
SLACK_WEBHOOK_CJO = os.getenv("SLACK_WEBHOOK_CJO")  # #cjo-data channel
SLACK_WEBHOOK_EXPERIMENTATION = os.getenv("SLACK_WEBHOOK_EXPERIMENTATION")

# --- Paths ---
VAULT_PATH = os.getenv("VAULT_PATH", str(Path.home() / "MAIN" / "vault"))
