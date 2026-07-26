import { useState } from 'react'

const QUERY_URL = import.meta.env.VITE_QUERY_URL ?? 'http://localhost:8002'

type Span = {
  traceId: string
  spanId: string
  parentSpanId?: string
  service: string
  resource: string
  start: number
  duration: number
  error: number
  meta?: Record<string, string>
}

function buildTree(spans: Span[]): Map<string | null, Span[]> {
  const map = new Map<string | null, Span[]>()
  for (const span of spans) {
    const parent = span.parentSpanId ?? null
    if (!map.has(parent)) map.set(parent, [])
    map.get(parent)!.push(span)
  }
  return map
}

function WaterfallRow({
  span,
  minStart,
  totalNs,
  depth,
  children,
}: {
  span: Span
  minStart: number
  totalNs: number
  depth: number
  children: React.ReactNode
}) {
  const left = ((span.start - minStart) / totalNs) * 100
  const width = Math.max((span.duration / totalNs) * 100, 0.3)
  const ms = (span.duration / 1_000_000).toFixed(1)

  return (
    <>
      <tr style={{ opacity: span.error ? 0.85 : 1 }}>
        <td style={{ paddingLeft: 8 + depth * 16 }}>
          <span style={{ color: span.error ? 'var(--red)' : 'var(--accent)' }}>
            {span.service}
          </span>
          <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>{span.resource}</span>
        </td>
        <td style={{ color: 'var(--text-muted)', fontSize: 11 }}>{span.spanId.slice(0, 8)}</td>
        <td>
          <div style={{ position: 'relative', height: 16, background: 'var(--bg3)', borderRadius: 2 }}>
            <div
              style={{
                position: 'absolute',
                left: `${left}%`,
                width: `${width}%`,
                height: '100%',
                background: span.error ? 'var(--red)' : 'var(--accent)',
                borderRadius: 2,
                opacity: 0.8,
              }}
            />
          </div>
        </td>
        <td style={{ color: span.error ? 'var(--red)' : undefined }}>{ms} ms</td>
        <td>{span.error ? <span style={{ color: 'var(--red)' }}>ERR</span> : <span style={{ color: 'var(--green)' }}>OK</span>}</td>
      </tr>
      {children}
    </>
  )
}

function renderTree(
  tree: Map<string | null, Span[]>,
  parentId: string | null,
  minStart: number,
  totalNs: number,
  depth: number
): React.ReactNode[] {
  const kids = tree.get(parentId) ?? []
  return kids.map((span) => (
    <WaterfallRow key={span.spanId} span={span} minStart={minStart} totalNs={totalNs} depth={depth}>
      {renderTree(tree, span.spanId, minStart, totalNs, depth + 1)}
    </WaterfallRow>
  ))
}

export default function TraceWaterfall() {
  const [traceId, setTraceId] = useState('')
  const [spans, setSpans] = useState<Span[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function search() {
    if (!traceId.trim()) return
    setLoading(true)
    setError(null)
    setSpans(null)
    try {
      const res = await fetch(`${QUERY_URL}/traces/${traceId.trim()}`)
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data = await res.json()
      setSpans(data.spans)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const minStart = spans ? Math.min(...spans.map((s) => s.start)) : 0
  const maxEnd = spans ? Math.max(...spans.map((s) => s.start + s.duration)) : 0
  const totalNs = maxEnd - minStart || 1
  const tree = spans ? buildTree(spans) : null

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input
          value={traceId}
          onChange={(e) => setTraceId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && search()}
          placeholder="Trace ID"
          style={{ flex: 1 }}
        />
        <button onClick={search} disabled={loading}>
          {loading ? 'Loading…' : 'Search'}
        </button>
      </div>

      {error && <div style={{ color: 'var(--red)', marginBottom: 8 }}>{error}</div>}

      {tree && spans && (
        <table>
          <thead>
            <tr>
              <th>Service / Resource</th>
              <th>Span ID</th>
              <th>Timeline</th>
              <th>Duration</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {renderTree(tree, null, minStart, totalNs, 0)}
          </tbody>
        </table>
      )}

      {spans?.length === 0 && (
        <div style={{ color: 'var(--text-muted)' }}>No spans found for this trace.</div>
      )}
    </div>
  )
}
