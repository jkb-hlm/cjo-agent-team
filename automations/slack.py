"""Slack posting utility for CJO automations."""

import json
import requests

from config import SLACK_WEBHOOK_CJO, SLACK_WEBHOOK_EXPERIMENTATION


def post(message: str, channel: str = "cjo"):
    """Post a message to Slack via webhook.

    Args:
        message: Markdown-formatted message text
        channel: 'cjo' for #cjo-data, 'experimentation' for #experimentation
    """
    webhook = SLACK_WEBHOOK_CJO if channel == "cjo" else SLACK_WEBHOOK_EXPERIMENTATION

    if not webhook:
        print(f"[slack] No webhook configured for '{channel}', printing to stdout:")
        print(message)
        return False

    payload = {
        "text": message,
        "unfurl_links": False,
        "unfurl_media": False,
    }

    resp = requests.post(webhook, json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"[slack] Error {resp.status_code}: {resp.text}")
        return False
    return True


def post_blocks(blocks: list[dict], text: str = "", channel: str = "cjo"):
    """Post a rich Block Kit message to Slack."""
    webhook = SLACK_WEBHOOK_CJO if channel == "cjo" else SLACK_WEBHOOK_EXPERIMENTATION

    if not webhook:
        print(f"[slack] No webhook for '{channel}', fallback text:")
        print(text)
        return False

    payload = {"blocks": blocks, "text": text}
    resp = requests.post(webhook, json=payload, timeout=10)
    return resp.status_code == 200
