#!/usr/bin/env python3
"""Telegram Glance bridge — HTTP service between the G2 app and Telegram.

GET  /unread            -> [{from, text, time, chatId, msgId}] (unread DMs, most recent first, max 10)
POST /reply {chatId, text} -> {ok: true, msgId} (sends a message)
GET  /health            -> {ok: true}

MTProto: on-demand connections only (connect -> fetch/send -> disconnect),
never held open. Refuses to connect during the 09:45-09:55 check-in window
so it can never collide with the daily SGK check-in cron's MTProto session.
Listens on 127.0.0.1:18091 (same machine as the simulator/dev server).

Run: ~/workspace/wool-radar/tg-bots/venv/bin/python bridge/bridge.py
"""
import asyncio
import datetime
import json
import os
import subprocess
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telethon import TelegramClient

SESSION = os.path.expanduser("~/workspace/wool-radar/tg-bots/alexchen-in91.session")
API_ID = 35028169
HOST, PORT = "127.0.0.1", 18091
CHECKIN_START = datetime.time(9, 45)
CHECKIN_END = datetime.time(9, 55)
PROXY = "http://127.0.0.1:18086"
DEEPGRAM_URL = "https://api.deepgram.com/v1/listen?model=nova-2&language=en&smart_format=true"


_secret_cache: dict = {}


def get_secret(asset: str) -> str:
    if asset in _secret_cache:
        return _secret_cache[asset]
    out = subprocess.run(
        [
            "python3",
            os.path.expanduser("~/workspace/identity-vault/automation/get.py"),
            "--identity", "anon-01",
            "--asset", asset,
            "--used-for", "telegram glance bridge",
        ],
        capture_output=True, text=True, check=True,
    )
    _secret_cache[asset] = out.stdout.strip()
    return _secret_cache[asset]


def get_api_hash():
    for line in get_secret("telegram-alexchen-mtproto-api").splitlines():
        if line.startswith("api_hash:"):
            return line.split(":", 1)[1].strip()
    raise ValueError("api_hash not found in vault secret")


def pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    """Wrap raw s16le mono PCM in a 44-byte WAV header (Deepgram rejects
    bare L16 on this path but accepts the same bytes as audio/wav)."""
    import struct
    n = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + n, b"WAVE", b"fmt ", 16, 1, 1, rate, rate * 2, 2, 16,
        b"data", n,
    )
    return header + pcm


def transcribe_pcm(pcm: bytes) -> str:
    """Batch STT via Deepgram (persona's $200 account, key in-memory only)."""
    key = get_secret("deepgram-alexchen-api-key")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"https": PROXY, "http": PROXY})
    )
    req = urllib.request.Request(
        DEEPGRAM_URL,
        data=pcm_to_wav(pcm),
        headers={
            "Authorization": f"Token {key}",
            "Content-Type": "audio/wav",
        },
        method="POST",
    )
    with opener.open(req, timeout=30) as resp:
        d = json.loads(resp.read())
    try:
        return d["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError):
        return ""


def in_checkin_window() -> bool:
    now = datetime.datetime.now().time()
    return CHECKIN_START <= now <= CHECKIN_END


def display_text(text: str) -> str:
    """Glasses-safe text: the LVGL font has ASCII + CJK ideographs + common
    CJK punctuation, but NOT emoji, geometric shapes, box-drawing, dingbats
    or other symbols (they render as blocks). Keep only the safe ranges."""
    def keep(ch: str) -> bool:
        o = ord(ch)
        if o < 0x80:
            return True  # ASCII
        if 0x4E00 <= o <= 0x9FFF:
            return True  # CJK Unified Ideographs
        if 0x3000 <= o <= 0x303F:
            return True  # CJK symbols/punctuation
        if 0xFF00 <= o <= 0xFFEF:
            return True  # fullwidth forms
        if o in (0x00B7, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026):
            return True  # middot, em dash, quotes, ellipsis
        return False
    out = "".join(ch if keep(ch) else " " for ch in text)
    return " ".join(out.split())


async def fetch_unread():
    """Most recent unread 1:1 DMs, newest first."""
    client = TelegramClient(SESSION, API_ID, get_api_hash())
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("MTProto session not authorized")
        dialogs = await client.get_dialogs(limit=50)
        dms = [d for d in dialogs if d.is_user and d.unread_count > 0]
        dms.sort(key=lambda d: (d.message.date if d.message else d.date), reverse=True)
        out = []
        for d in dms[:10]:
            msg = d.message
            text = display_text(msg.message or "") if msg else ""
            when = msg.date if msg else d.date
            out.append({
                "from": d.name or (d.entity.username or "?"),
                "text": text,
                "time": when.strftime("%H:%M") if when else "",
                "chatId": d.id,
                "msgId": msg.id if msg else None,
                "unread": d.unread_count,
            })
        return out
    finally:
        await client.disconnect()


async def send_reply(chat_id: int, text: str) -> int:
    client = TelegramClient(SESSION, API_ID, get_api_hash())
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("MTProto session not authorized")
        sent = await client.send_message(chat_id, text)
        return sent.id
    finally:
        await client.disconnect()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True})
            return
        if self.path == "/unread":
            if in_checkin_window():
                self._json(503, {"error": "checkin window, try later"})
                return
            try:
                msgs = asyncio.run(fetch_unread())
                self._json(200, msgs)
            except Exception as e:
                self._json(500, {"error": str(e)[:200]})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/transcribe":
            try:
                n = int(self.headers.get("Content-Length", 0))
                pcm = self.rfile.read(n) or b""
                if len(pcm) < 3200:  # <0.1s of audio: nothing to transcribe
                    self._json(200, {"text": ""})
                    return
                text = transcribe_pcm(pcm)
                self._json(200, {"text": text})
            except Exception as e:
                self._json(500, {"error": str(e)[:200]})
            return
        if self.path == "/reply":
            if in_checkin_window():
                self._json(503, {"error": "checkin window, try later"})
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n) or b"{}")
                chat_id = int(data["chatId"])
                text = str(data["text"]).strip()
                if not text:
                    raise ValueError("empty text")
                msg_id = asyncio.run(send_reply(chat_id, text))
                self._json(200, {"ok": True, "msgId": msg_id})
            except Exception as e:
                self._json(500, {"error": str(e)[:200]})
            return
        self._json(404, {"error": "not found"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Telegram Glance bridge on http://{HOST}:{PORT} (pid {os.getpid()})", flush=True)
    srv.serve_forever()
