import type { AnomalyAlert } from '../hooks/useWebSocket'

interface Props {
  alerts: AnomalyAlert[]
}

const SEV_COLOR: Record<string, string> = {
  low: 'var(--green)',
  medium: 'var(--yellow)',
  high: 'var(--orange)',
  critical: 'var(--critical)',
}

export default function AlertFeed({ alerts }: Props) {
  if (alerts.length === 0) {
    return (
      <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: 12 }}>
        No alerts
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      {alerts.map((a, i) => (
        <div
          key={i}
          style={{
            padding: '8px 12px',
            borderBottom: '1px solid var(--border)',
            borderLeft: `3px solid ${SEV_COLOR[a.severity] ?? 'var(--text-muted)'}`,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
            <span style={{ color: SEV_COLOR[a.severity], fontWeight: 'bold', fontSize: 11, textTransform: 'uppercase' }}>
              {a.severity}
            </span>
            <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
              {new Date(a.timestamp).toLocaleTimeString()}
            </span>
          </div>
          <div style={{ color: 'var(--accent)', fontSize: 12 }}>
            {a.service} / {a.resource}
          </div>
          <div style={{ color: 'var(--text)', marginTop: 2 }}>{a.description}</div>
        </div>
      ))}
    </div>
  )
}
