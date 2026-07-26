import { useCallback, useState } from 'react'
import { useWebSocket, type AnomalyAlert, type MetricUpdate, type WsMessage, type WsStatus } from './hooks/useWebSocket'
import MetricsPanel, { type Snapshot, type SnapshotKey } from './components/MetricsPanel'
import AlertFeed from './components/AlertFeed'
import TraceWaterfall from './components/TraceWaterfall'

const HISTORY_MAX = 40

type Tab = 'metrics' | 'traces'

const STATUS_COLOR: Record<WsStatus, string> = {
  connected: 'var(--green)',
  connecting: 'var(--yellow)',
  disconnected: 'var(--red)',
}

export default function App() {
  const [tab, setTab] = useState<Tab>('metrics')
  const [snapshots, setSnapshots] = useState<Map<SnapshotKey, Snapshot>>(new Map())
  const [alerts, setAlerts] = useState<AnomalyAlert[]>([])

  const handleMessage = useCallback((msg: WsMessage) => {
    if (msg.type === 'metric_update') {
      const update = msg as MetricUpdate
      const key: SnapshotKey = `${update.service}::${update.resource}`
      setSnapshots((prev) => {
        const next = new Map(prev)
        const existing = next.get(key)
        const histEntry = { t: update.timestamp, rps: update.metrics.throughputRps, p95: update.metrics.p95LatencyMs }
        const history = existing
          ? [...existing.history.slice(-(HISTORY_MAX - 1)), histEntry]
          : [histEntry]
        next.set(key, { ...update, history })
        return next
      })
    } else if (msg.type === 'anomaly_alert') {
      setAlerts((prev) => [msg as AnomalyAlert, ...prev].slice(0, 100))
    }
    // heartbeat: ignore
  }, [])

  const status = useWebSocket(handleMessage)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 16,
        padding: '8px 16px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg2)', flexShrink: 0,
      }}>
        <span style={{ fontWeight: 'bold', color: 'var(--accent)', fontSize: 14, letterSpacing: 1 }}>
          ◈ DATADOG CLONE
        </span>
        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>APM</span>

        <div style={{ flex: 1 }} />

        <div style={{ display: 'flex', gap: 12 }}>
          {(['metrics', 'traces'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                background: tab === t ? 'var(--bg3)' : 'transparent',
                border: tab === t ? '1px solid var(--accent)' : '1px solid transparent',
                color: tab === t ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              {t === 'metrics' ? 'Live Metrics' : 'Trace Lookup'}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: STATUS_COLOR[status], display: 'inline-block' }} />
          <span style={{ color: 'var(--text-muted)' }}>WS {status}</span>
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {tab === 'metrics' ? (
          <>
            {/* Metrics table */}
            <div style={{ flex: 1, overflow: 'auto' }}>
              <div style={{ padding: '10px 16px', color: 'var(--text-muted)', fontSize: 11, borderBottom: '1px solid var(--border)' }}>
                LIVE METRICS — {snapshots.size} service/resource pairs
              </div>
              <MetricsPanel snapshots={snapshots} />
            </div>

            {/* Alert feed */}
            <div style={{
              width: 320, borderLeft: '1px solid var(--border)',
              display: 'flex', flexDirection: 'column', overflow: 'hidden', flexShrink: 0,
            }}>
              <div style={{ padding: '10px 12px', color: 'var(--text-muted)', fontSize: 11, borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between' }}>
                <span>ALERTS</span>
                {alerts.length > 0 && (
                  <button style={{ padding: '1px 6px', fontSize: 10 }} onClick={() => setAlerts([])}>
                    clear
                  </button>
                )}
              </div>
              <div style={{ flex: 1, overflow: 'auto' }}>
                <AlertFeed alerts={alerts} />
              </div>
            </div>
          </>
        ) : (
          <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
            <div style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 12 }}>TRACE LOOKUP</div>
            <TraceWaterfall />
          </div>
        )}
      </div>
    </div>
  )
}
