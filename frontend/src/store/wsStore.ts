import { create } from 'zustand'

type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'
type WsCallback = (payload: unknown) => void

interface WsState {
  status: WsStatus
  connect: (token: string) => void
  disconnect: () => void
  subscribe: (type: string, callback: WsCallback) => () => void
}

let _ws: WebSocket | null = null
let _retryDelay = 1000
let _retryTimer: ReturnType<typeof setTimeout> | null = null
let _heartbeatTimer: ReturnType<typeof setTimeout> | null = null
let _token: string | null = null
const _listeners = new Map<string, Set<WsCallback>>()

function _clearTimers() {
  if (_retryTimer) { clearTimeout(_retryTimer); _retryTimer = null }
  if (_heartbeatTimer) { clearTimeout(_heartbeatTimer); _heartbeatTimer = null }
}

function _scheduleHeartbeatTimeout() {
  if (_heartbeatTimer) clearTimeout(_heartbeatTimer)
  _heartbeatTimer = setTimeout(() => {
    _ws?.close()
  }, 35_000)
}

export const useWsStore = create<WsState>((set) => ({
  status: 'disconnected',

  connect: (token: string) => {
    _token = token
    _retryDelay = 1000
    _openConnection(set)
  },

  disconnect: () => {
    _token = null
    _clearTimers()
    _ws?.close(1000, 'user disconnect')
    _ws = null
    set({ status: 'disconnected' })
  },

  subscribe: (type: string, callback: WsCallback) => {
    if (!_listeners.has(type)) _listeners.set(type, new Set())
    _listeners.get(type)!.add(callback)
    return () => _listeners.get(type)?.delete(callback)
  },
}))

function _openConnection(set: (partial: Partial<WsState>) => void) {
  if (!_token) return

  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/ws/events?token=${_token}`

  set({ status: _retryDelay > 1000 ? 'reconnecting' : 'connecting' })

  _ws = new WebSocket(url)

  _ws.onopen = () => {
    _retryDelay = 1000
    set({ status: 'connected' })
    _scheduleHeartbeatTimeout()
  }

  _ws.onmessage = (event: MessageEvent) => {
    try {
      const msg = JSON.parse(event.data as string) as { type: string; payload?: unknown }
      if (msg.type === 'ping') {
        _ws?.send(JSON.stringify({ type: 'pong' }))
        _scheduleHeartbeatTimeout()
        return
      }
      const callbacks = _listeners.get(msg.type)
      if (callbacks) callbacks.forEach((cb) => cb(msg.payload))
    } catch {
      // ignore malformed messages
    }
  }

  _ws.onclose = () => {
    _clearTimers()
    if (!_token) return
    set({ status: 'reconnecting' })
    _retryDelay = Math.min(_retryDelay * 2, 30_000)
    _retryTimer = setTimeout(() => _openConnection(set), _retryDelay)
  }

  _ws.onerror = () => {
    _ws?.close()
  }
}
