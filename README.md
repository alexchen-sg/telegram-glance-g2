# Telegram Glance — Even Realities G2

**Heads Up: Even Realities Hackathon — Messaging & News track (Best Telegram integration)**

Your most important Telegram message, at a glance. Read it, reply by voice,
never take out your phone.

## The problem

Telegram is where the messages that matter arrive — but checking them means
stopping what you're doing, pulling out your phone, unlocking it, and opening
the app. For one important message, that's a 30-second interruption.

## What it does

Telegram Glance is a G2 glasses app that shows **one thing**: your most
important unread Telegram message.

- **Read** — sender, time, and the message, glanceable on the 576×288 lens.
  One message per screen, a few words, nothing else.
- **Cycle** — tap (or scroll the R1 ring) to move to the next unread message.
  The list refreshes every cycle, so new messages appear as they arrive.
- **Write** — speak your reply; it is transcribed and sent back on Telegram.
  No phone, no typing. *(ASR reply — in progress)*
- **Exit** — double-tap, always.

## How it works

- **G2 app**: Vite + TypeScript, `@evenrealities/even_hub_sdk`. One
  `TextContainer` (576×288) for the message card; tap / scroll / double-tap
  events drive the inbox. Builds to a single `.ehpk` via `evenhub pack`.
- **Bridge** (`bridge/`): a small local service that talks to Telegram via the
  user's own MTProto session (on-demand connections, never held open) and
  exposes `GET /unread` and `POST /reply` to the glasses app. The app falls
  back to demo data when the bridge is unreachable, so the simulator demo
  always works.
- **Voice reply**: mic audio via the SDK (`audioControl` / `audioEvent`),
  transcribed, sent with `POST /reply`.

## Run it (no glasses needed)

```bash
npm install
npm run dev          # Vite dev server on http://127.0.0.1:5173
npm run simulate     # Even Hub simulator renders the glasses display
npm run pack         # build + package to .ehpk
```

The simulator runs the app exactly as the lenses would — the screenshot in
the repo is the live simulator output.

## Submission

- Repo: https://github.com/alexchen-sg/telegram-glance-g2 *(to be published)*
- Demo video: `demo.mp4` (70s, simulator capture, 1280×800) — inbox → tap-cycle → voice-reply recording screen
- Track: Messaging & News — Telegram only.
- Built during the hackathon (Nov 23–29, 2026).

## Rules compliance

- Uses only Telegram (an app listed in the Messaging & News track).
- No financial advice, no holding user funds.
- Respects Telegram's terms: the bridge uses the user's own account session,
  on-demand connections, no automation of other people's accounts.

## What's in here

| File | Purpose |
|---|---|
| `index.html` | WebView host. Viewport meta tag locks zoom; CSS kills iOS double-tap zoom + rubber-band scroll. |
| `src/main.ts` | Glanceable inbox: fetches unreads from the bridge, cycles on tap/scroll. |
| `app.json` | Even Hub manifest (`com.alexchen.telegramglance`). |
| `tsconfig.json` | Standard Vite vanilla-ts config. |
| `vite.config.ts` | Dev server on port 5173, host binding for LAN QR access. |
