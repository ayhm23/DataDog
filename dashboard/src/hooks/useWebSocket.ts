import { useEffect, useRef, useState } from 'react'

export type MetricUpdate = {
  type: 'metric_update'
  timestamp: number
  service: string
  resource: string
  metrics: {
    requestCount: number
    errorCount: number
    p95LatencyMs: number
    throughputRps: number
  }
}

export type AnomalyAlert = {
  type: 'anomaly_alert'
  timestamp: number
  service: string
  resource: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  description: string
  value: number
  baseline: number
}

export type Heartbeat = { type: 'heartbeat'; timestamp: number }

export type WsMessage = MetricUpdate | AnomalyAlert | Heartbeat

export type WsStatus = 'connecting' | 'connected' | 'disconnected'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8080/ws'
const RECONNECT_MS = 3000

export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  const [status, setStatus] = useState<WsStatus>('connecting')
  const wsRef = useRef<WebSocket | null>(null)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    function connect() {
      if (cancelled) return
      setStatus('connecting')
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => { if (!cancelled) setStatus('connected') }

      ws.onmessage = (ev) => {
        try {
          const msg: WsMessage = JSON.parse(ev.data)
          if (!cancelled) onMessageRef.current(msg)
        } catch { /* ignore malformed frames */ }
      }

      ws.onerror = () => { ws.close() }

      ws.onclose = () => {
        if (!cancelled) {
          setStatus('disconnected')
          timer = setTimeout(connect, RECONNECT_MS)
        }
      }
    }

    connect()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
      wsRef.current?.close()
    }
  }, [])

  return status
}
