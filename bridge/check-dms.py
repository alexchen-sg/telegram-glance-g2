#!/usr/bin/env python3
"""List unread 1:1 DMs only (the messages that matter) — bridge filter check."""
import asyncio, os, subprocess, sys
from telethon import TelegramClient
SESSION = os.path.expanduser("~/workspace/wool-radar/tg-bots/alexchen-in91.session")
API_ID = 35028169
def get_api_hash():
    out = subprocess.run(["python3", os.path.expanduser("~/workspace/identity-vault/automation/get.py"),
        "--identity", "anon-01", "--asset", "telegram-alexchen-mtproto-api",
        "--used-for", "telegram glance bridge check"], capture_output=True, text=True, check=True)
    for line in out.stdout.splitlines():
        if line.startswith("api_hash:"):
            return line.split(":", 1)[1].strip()
    raise ValueError("api_hash not found")
async def main():
    client = TelegramClient(SESSION, API_ID, get_api_hash())
    await client.connect()
    try:
        if not await client.is_user_authorized():
            print("NOT AUTHORIZED"); return 1
        dialogs = await client.get_dialogs(limit=50)
        dms = [d for d in dialogs if d.is_user and d.unread_count > 0]
        print(f"unread DMs: {len(dms)}")
        for d in dms[:10]:
            last = (d.message.message or "") if d.message else ""
            last = " ".join(last.split())[:70]
            print(f"  [{d.unread_count}] @{d.entity.username or d.name} | {last}")
        return 0
    finally:
        await client.disconnect()
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
