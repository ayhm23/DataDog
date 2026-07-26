import { useMemo } from 'react'
import { LineChart, Line, Tooltip, ResponsiveContainer } from 'recharts'
import type { MetricUpdate } from '../hooks/useWebSocket'

export type SnapshotKey = `${string}::${string}`
export type Snapshot = MetricUpdate & { history: { t: number; rps: number; p95: number }[] }

interface Props {
  snapshots: Map<SnapshotKey, Snapshot>
}

function errColor(rate: number) {
  if (rate >= 0.2) return 'var(--critical)'
  if (rate >= 0.05) return 'var(--red)'
  if (rate >= 0.01) return 'var(--yellow)'
  return 'var(--green)'
}

function p95Color(ms: number) {
  if (ms >= 3000) return 'var(--critical)'
  if (ms >= 1000) return 'var(--orange)'
  if (ms >= 500) return 'var(--yellow)'
  return 'var(--green)'
}

export default function MetricsPanel({ snapshots }: Props) {
  const rows = useMemo(() => [...snapshots.values()].sort((a, b) =>
    a.service.localeCompare(b.service) || a.resource.localeCompare(b.resource)
  ), [snapshots])

  if (rows.length === 0) {
    return (
      <div style={{ padding: '32px', color: 'var(--text-muted)', textAlign: 'center' }}>
        Waiting for metrics… (start the ingestion service and send spans)
      </div>
    )
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Service</th>
          <th>Resource</th>
          <th>RPS</th>
          <th>Error Rate</th>
          <th>p95 (ms)</th>
          <th>Count</th>
          <th style={{ width: 120 }}>RPS trend</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((snap) => {
          const key: SnapshotKey = `${snap.service}::${snap.resource}`
          const errRate = snap.metrics.errorCount / Math.max(snap.metrics.requestCount, 1)
          return (
            <tr key={key}>
              <td style={{ color: 'var(--accent)' }}>{snap.service}</td>
              <td style={{ color: 'var(--text-muted)' }}>{snap.resource}</td>
              <td>{snap.metrics.throughputRps.toFixed(2)}</td>
              <td style={{ color: errColor(errRate) }}>
                {(errRate * 100).toFixed(1)}%
              </td>
              <td style={{ color: p95Color(snap.metrics.p95LatencyMs) }}>
                {snap.metrics.p95LatencyMs.toFixed(0)}
              </td>
              <td style={{ color: 'var(--text-muted)' }}>{snap.metrics.requestCount}</td>
              <td>
                <ResponsiveContainer width="100%" height={32}>
                  <LineChart data={snap.history}>
                    <Line type="monotone" dataKey="rps" dot={false} stroke="var(--accent)" strokeWidth={1.5} />
                    <Tooltip
                      contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', fontSize: 11 }}
                      formatter={(v) => [typeof v === 'number' ? v.toFixed(2) : String(v ?? ''), 'rps']}
                      labelFormatter={() => ''}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
