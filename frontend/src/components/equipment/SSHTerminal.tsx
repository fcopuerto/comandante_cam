import { useEffect, useRef } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { useAuthStore } from '@/store/authStore'

interface Props {
  equipmentId: string
}

export default function SSHTerminal({ equipmentId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const token = useAuthStore((s) => s.accessToken)

  useEffect(() => {
    if (!containerRef.current || !token) return

    const term = new Terminal({
      cursorBlink: true,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      fontSize: 14,
      theme: { background: '#0f172a', foreground: '#e2e8f0', cursor: '#38bdf8' },
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.loadAddon(new WebLinksAddon())
    term.open(containerRef.current)
    fit.fit()
    termRef.current = term
    fitRef.current = fit

    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(
      `${wsProtocol}://${window.location.host}/ws/terminal/${equipmentId}?token=${token}`
    )
    wsRef.current = ws

    ws.onopen = () => term.write('\x1b[32mConnecting…\x1b[0m\r\n')
    ws.onmessage = (e) => term.write(e.data)
    ws.onclose = (e) =>
      term.write(`\r\n\x1b[33mConnection closed (${e.code})\x1b[0m\r\n`)
    ws.onerror = () => term.write('\r\n\x1b[31mWebSocket error\x1b[0m\r\n')

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(data)
    })

    const resizeObserver = new ResizeObserver(() => fit.fit())
    resizeObserver.observe(containerRef.current)

    return () => {
      resizeObserver.disconnect()
      ws.close()
      term.dispose()
    }
  }, [equipmentId, token])

  return (
    <div
      ref={containerRef}
      className="w-full h-full min-h-[400px] rounded-md overflow-hidden bg-[#0f172a] p-1"
    />
  )
}
