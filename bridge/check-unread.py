#!/usr/bin/env python3
"""Quick MTProto liveness check for the Telegram Glance bridge.

Connects (short-lived) with the persona's vaulted MTProto session, verifies
authorization, and lists unread dialogs (sender, unread count, last message
preview). Prints metadata only — no secrets, no full message bodies.
Run: ~/workspace/wool-radar/tg-bots/venv/bin/python bridge/check-unread.py
"""
import asyncio
import os
import subprocess
import sys

from telethon import TelegramClient

SESSION = os.path.expanduser("~/workspace/wool-radar/tg-bots/alexchen-in91.session")
API_ID = 35028169


def get_api_hash():
    out = subprocess.run(
        [
            "python3",
            os.path.expanduser("~/workspace/identity-vault/automation/get.py"),
            "--identity", "anon-01",
            "--asset", "telegram-alexchen-mtproto-api",
            "--used-for", "telegram glance bridge check",
        ],
        capture_output=True, text=True, check=True,
    )
    for line in out.stdout.splitlines():
        if line.startswith("api_hash:"):
            return line.split(":", 1)[1].strip()
    raise ValueError("api_hash not found in vault secret")


async def main():
    api_hash = get_api_hash()
    client = TelegramClient(SESSION, API_ID, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            print("NOT AUTHORIZED")
            return 1
        me = await client.get_me()
        print(f"AUTHORIZED as @{me.username} ({me.id})")
        dialogs = await client.get_dialogs(limit=30)
        unread = [d for d in dialogs if d.unread_count > 0]
        print(f"dialogs: {len(dialogs)}, unread dialogs: {len(unread)}")
        for d in unread[:8]:
            name = (d.name or "?")[:30]
            last = (d.message.message or "") if d.message else ""
            last = " ".join(last.split())[:70]
            print(f"  [{d.unread_count}] {name} | {last}")
        return 0
    finally:
        await client.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
