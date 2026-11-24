import {
  waitForEvenAppBridge,
  TextContainerProperty,
  CreateStartUpPageContainer,
  TextContainerUpgrade,
  OsEventTypeList,
} from '@evenrealities/even_hub_sdk'

// Telegram Glance — the one Telegram message that matters, at a glance.
// Read: tap cycles unread messages.
// Write: scroll the R1 ring to start/stop a voice reply (mic -> Deepgram
// STT via the bridge -> transcript -> scroll to send, tap to discard).
// Double-tap exits. Data: GET <bridge>/unread, POST <bridge>/reply,
// POST <bridge>/transcribe. Falls back to demo data when the bridge is
// unreachable (simulator demo).

const BRIDGE = (import.meta as any).env?.VITE_BRIDGE_URL ?? 'http://127.0.0.1:18091'

type Msg = { from: string; text: string; time: string; chatId?: number; msgId?: number }

const DEMO: Msg[] = [
  { from: 'Daos Hub', text: 'Demo Day is Dec 3 — your slot is 14:20 GST. Remote demo confirmed.', time: '09:41' },
  { from: 'TVM Ventures', text: 'Finalists pitch to partner VCs right after Demo Day. Good luck!', time: '09:12' },
  { from: 'Even Realities', text: 'Your G2 app passed review. It is live on Even Hub.', time: '08:58' },
]

type Mode = 'browse' | 'recording' | 'confirm' | 'sent'

function truncate(s: string, n: number): string {
  const flat = s.replace(/\s+/g, ' ').trim()
  return flat.length > n ? flat.slice(0, n - 1) + '…' : flat
}

function render(msgs: Msg[], i: number, mode: Mode, draft: string): string {
  if (mode === 'recording') return 'Recording…\n\nSpeak your reply.\n\nScroll again to stop.'
  if (mode === 'confirm') {
    return `Reply to ${msgs[i]?.from ?? ''}:\n\n${truncate(draft, 120)}\n\nScroll: send · Tap: discard`
  }
  if (mode === 'sent') return 'Sent ✓\n\nBack to your inbox…'
  if (msgs.length === 0) return 'Telegram Glance\n\nNo unread messages.\nYou are all caught up.'
  const m = msgs[i]
  const head = `${m.from} · ${m.time}`
  const body = truncate(m.text, 120)
  const foot = `${i + 1}/${msgs.length} · tap: next · scroll: reply · double-tap: exit`
  return `${head}\n\n${body}\n\n${foot}`
}

async function fetchUnread(): Promise<Msg[]> {
  try {
    const r = await fetch(`${BRIDGE}/unread`, { signal: AbortSignal.timeout(3000) })
    if (!r.ok) return DEMO
    const d = (await r.json()) as Msg[]
    return Array.isArray(d) && d.length > 0 ? d : DEMO
  } catch {
    return DEMO
  }
}

const bridge = await waitForEvenAppBridge()

let msgs = await fetchUnread()
let idx = 0
let mode: Mode = 'browse'
let draft = ''
let pcmChunks: Uint8Array[] = []

const mainText = new TextContainerProperty({
  xPosition: 0,
  yPosition: 0,
  width: 576,
  height: 288,
  borderWidth: 0,
  borderColor: 5,
  paddingLength: 4,
  containerID: 1,
  containerName: 'main',
  content: render(msgs, idx, mode, draft),
  isEventCapture: 1,
})

const result = await bridge.createStartUpPageContainer(
  new CreateStartUpPageContainer({
    containerTotalNum: 1,
    textObject: [mainText],
  }),
)

console.log('Page created:', result === 0 ? 'success' : `failed (${result})`)

function show() {
  bridge.textContainerUpgrade(
    new TextContainerUpgrade({
      containerID: 1,
      containerName: 'main',
      content: render(msgs, idx, mode, draft),
    }),
  )
}

async function startRecording() {
  pcmChunks = []
  mode = 'recording'
  show()
  await bridge.audioControl(true)
}

async function stopRecordingAndTranscribe() {
  await bridge.audioControl(false)
  // Concatenate PCM chunks (s16le @ 16kHz mono from the G2 mic).
  const total = pcmChunks.reduce((n, c) => n + c.length, 0)
  const pcm = new Uint8Array(total)
  let off = 0
  for (const c of pcmChunks) {
    pcm.set(c, off)
    off += c.length
  }
  pcmChunks = []
  if (total < 3200) {
    mode = 'browse'
    show()
    return
  }
  try {
    const r = await fetch(`${BRIDGE}/transcribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'audio/l16' },
      body: pcm,
      signal: AbortSignal.timeout(30000),
    })
    const d = (await r.json()) as { text?: string }
    draft = (d.text ?? '').trim()
    mode = draft ? 'confirm' : 'browse'
  } catch {
    mode = 'browse'
  }
  show()
}

async function sendReply() {
  const m = msgs[idx]
  if (!m?.chatId || !draft) {
    mode = 'browse'
    show()
    return
  }
  try {
    await fetch(`${BRIDGE}/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chatId: m.chatId, text: draft }),
      signal: AbortSignal.timeout(15000),
    })
  } catch {
    // Send failed — keep the draft on screen by returning to browse.
  }
  draft = ''
  mode = 'sent'
  show()
  window.setTimeout(() => {
    mode = 'browse'
    show()
  }, 1500)
}

function eventTypeOf(envelope?: { eventType?: OsEventTypeList }): OsEventTypeList | null {
  if (!envelope) return null
  return envelope.eventType ?? OsEventTypeList.CLICK_EVENT
}

const unsubscribe = bridge.onEvenHubEvent((event) => {
  // Mic PCM frames arrive here — accumulate while recording.
  const pcm = event.audioEvent?.audioPcm as Uint8Array | undefined
  if (pcm && mode === 'recording') pcmChunks.push(pcm)

  const sysType = eventTypeOf(event.sysEvent)
  const textType = eventTypeOf(event.textEvent)

  if (sysType === OsEventTypeList.DOUBLE_CLICK_EVENT || textType === OsEventTypeList.DOUBLE_CLICK_EVENT) {
    bridge.audioControl(false)
    bridge.shutDownPageContainer(1)
    return
  }

  const isScroll =
    sysType === OsEventTypeList.SCROLL_TOP_EVENT ||
    textType === OsEventTypeList.SCROLL_TOP_EVENT ||
    sysType === OsEventTypeList.SCROLL_BOTTOM_EVENT ||
    textType === OsEventTypeList.SCROLL_BOTTOM_EVENT
  const isTap = sysType === OsEventTypeList.CLICK_EVENT || textType === OsEventTypeList.CLICK_EVENT

  if (isScroll) {
    if (mode === 'browse') {
      startRecording()
    } else if (mode === 'recording') {
      stopRecordingAndTranscribe()
    } else if (mode === 'confirm') {
      sendReply()
    }
    return
  }

  if (isTap) {
    if (mode === 'confirm') {
      // Discard the draft.
      draft = ''
      mode = 'browse'
      show()
      return
    }
    if (mode !== 'browse') return
    idx = (idx + 1) % msgs.length
    if (idx === 0) {
      fetchUnread().then((fresh) => {
        msgs = fresh
        idx = 0
        show()
      })
    }
    show()
    return
  }

  if (sysType === OsEventTypeList.SYSTEM_EXIT_EVENT || sysType === OsEventTypeList.ABNORMAL_EXIT_EVENT) {
    bridge.audioControl(false)
    unsubscribe()
  }
})
