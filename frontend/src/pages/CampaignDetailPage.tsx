import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import {
  getCampaignMetrics,
  getCampaignRecommendations,
  applyRecommendation,
} from '../api/campaigns'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorMessage } from '../components/ErrorMessage'
import { useAuth } from '../context/AuthContext'
import type { CampaignMetrics, Recommendation } from '../types'
import styles from './CampaignDetailPage.module.css'

// ─── Chart helpers ───────────────────────────────────────────────────────────

interface ChartConfig {
  key: keyof CampaignMetrics
  label: string
  color: string
  formatter?: (v: number) => string
}

const CHARTS: ChartConfig[][] = [
  [
    { key: 'impressions', label: 'Impressions', color: '#6366f1' },
    { key: 'clicks', label: 'Clicks', color: '#22d3ee' },
  ],
  [
    { key: 'spend', label: 'Spend ($)', color: '#f59e0b', formatter: (v) => '$' + v.toFixed(2) },
    { key: 'conversions', label: 'Conversions', color: '#10b981' },
  ],
  [
    { key: 'ctr', label: 'CTR', color: '#a78bfa', formatter: (v) => (v * 100).toFixed(2) + '%' },
    { key: 'cpc', label: 'CPC ($)', color: '#fb923c', formatter: (v) => '$' + v.toFixed(2) },
  ],
  [
    { key: 'roas', label: 'ROAS', color: '#34d399', formatter: (v) => v.toFixed(2) + 'x' },
  ],
]

// ─── Recommendation Card ─────────────────────────────────────────────────────

interface RecCardProps {
  rec: Recommendation
  canApply: boolean
  onApply: (id: string) => void
  applying: boolean
}

function RecCard({ rec, canApply, onApply, applying }: RecCardProps) {
  const confidence = Math.round(rec.confidence_score * 100)
  const isLowConfidence = rec.confidence_score < 0.6

  return (
    <div className={`${styles.recCard} ${rec.applied ? styles.recApplied : ''}`}>
      <div className={styles.recHeader}>
        <span className={styles.recGoal}>{rec.goal}</span>
        <span
          className={`${styles.recConfidence} ${isLowConfidence ? styles.lowConf : ''}`}
          title="Confidence score"
        >
          {confidence}% confidence
        </span>
        {rec.applied && <span className={styles.appliedBadge}>✓ Applied</span>}
      </div>

      <p className={styles.recAction}>{rec.action}</p>

      <div className={styles.recValues}>
        <div className={styles.recValue}>
          <span className={styles.recValueLabel}>Current</span>
          <span className={styles.recValueNum}>{rec.current_value.toFixed(4)}</span>
        </div>
        <span className={styles.recArrow} aria-hidden="true">→</span>
        <div className={styles.recValue}>
          <span className={styles.recValueLabel}>Suggested</span>
          <span className={styles.recValueNum}>{rec.suggested_value.toFixed(4)}</span>
        </div>
      </div>

      <p className={styles.recReasoning}>{rec.reasoning}</p>

      <div className={styles.recFooter}>
        <span className={styles.recDate}>
          {new Date(rec.generated_at).toLocaleString()}
        </span>
        {canApply && !rec.applied && (
          <button
            className={styles.applyBtn}
            onClick={() => onApply(rec.recommendation_id)}
            disabled={applying}
            aria-label={`Apply recommendation: ${rec.action}`}
          >
            {applying ? 'Applying…' : 'Apply'}
          </button>
        )}
      </div>
    </div>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { canWrite } = useAuth()

  const [metrics, setMetrics] = useState<CampaignMetrics[]>([])
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [applyingId, setApplyingId] = useState<string | null>(null)
  const [applyMsg, setApplyMsg] = useState<string | null>(null)

  const load = async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [metricsData, recsData] = await Promise.all([
        getCampaignMetrics(id),
        getCampaignRecommendations(id),
      ])
      setMetrics(metricsData)
      setRecommendations(recsData)
    } catch {
      setError('Failed to load campaign data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  const handleApply = async (recommendationId: string) => {
    if (!id) return
    setApplyingId(recommendationId)
    setApplyMsg(null)
    try {
      await applyRecommendation(id, recommendationId)
      setRecommendations((prev) =>
        prev.map((r) =>
          r.recommendation_id === recommendationId ? { ...r, applied: true } : r
        )
      )
      setApplyMsg('Recommendation applied successfully.')
    } catch {
      setApplyMsg('Failed to apply recommendation.')
    } finally {
      setApplyingId(null)
    }
  }

  if (loading) return <LoadingSpinner message="Loading campaign details…" />
  if (error) return <ErrorMessage message={error} onRetry={load} />

  const campaignName = metrics[0]?.campaign_name ?? id

  // Prepare chart data — sort by date ascending
  const chartData = [...metrics]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((m) => ({ ...m, date: m.date }))

  return (
    <div className={styles.page}>
      {/* Breadcrumb */}
      <nav className={styles.breadcrumb} aria-label="Breadcrumb">
        <Link to="/dashboard/campaigns" className={styles.breadcrumbLink}>
          Campaigns
        </Link>
        <span className={styles.breadcrumbSep} aria-hidden="true"> / </span>
        <span className={styles.breadcrumbCurrent}>{campaignName}</span>
      </nav>

      <h1 className={styles.heading}>{campaignName}</h1>

      {/* Time-series Charts */}
      <section aria-label="Performance Charts" className={styles.chartsSection}>
        <h2 className={styles.sectionTitle}>Performance Over Time</h2>

        {chartData.length === 0 ? (
          <p className={styles.empty}>No metrics data available.</p>
        ) : (
          <div className={styles.chartsGrid}>
            {CHARTS.map((group, gi) => (
              <div key={gi} className={styles.chartCard}>
                <h3 className={styles.chartTitle}>
                  {group.map((c) => c.label).join(' & ')}
                </h3>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a2a4a" />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: '#888', fontSize: 11 }}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: '#888', fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={group[0].formatter}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#1a1a2e',
                        border: '1px solid #2a2a4a',
                        borderRadius: 8,
                        color: '#e0e0e0',
                        fontSize: 12,
                      }}
                      formatter={(value: number, name: string) => {
                        const cfg = group.find((c) => c.label === name)
                        return [cfg?.formatter ? cfg.formatter(value) : value, name]
                      }}
                    />
                    <Legend
                      wrapperStyle={{ fontSize: 12, color: '#888' }}
                    />
                    {group.map((cfg) => (
                      <Line
                        key={cfg.key}
                        type="monotone"
                        dataKey={cfg.key}
                        name={cfg.label}
                        stroke={cfg.color}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Recommendations */}
      <section aria-label="Recommendations" className={styles.recsSection}>
        <h2 className={styles.sectionTitle}>AI Recommendations</h2>

        {applyMsg && (
          <div className={styles.applyMsg} role="status">
            {applyMsg}
          </div>
        )}

        {recommendations.length === 0 ? (
          <p className={styles.empty}>No recommendations available yet.</p>
        ) : (
          <div className={styles.recsGrid}>
            {recommendations.map((rec) => (
              <RecCard
                key={rec.recommendation_id}
                rec={rec}
                canApply={canWrite}
                onApply={handleApply}
                applying={applyingId === rec.recommendation_id}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
