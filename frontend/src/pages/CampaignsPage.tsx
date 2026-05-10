import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCampaigns, triggerFetch } from '../api/campaigns'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorMessage } from '../components/ErrorMessage'
import { useAuth } from '../context/AuthContext'
import type { Campaign } from '../types'
import styles from './CampaignsPage.module.css'

function fmt(n: number, decimals = 2): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: decimals })
}

function fmtCurrency(n: number): string {
  return '$' + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n: number): string {
  return (n * 100).toFixed(2) + '%'
}

export function CampaignsPage() {
  const { canWrite } = useAuth()
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fetching, setFetching] = useState(false)
  const [fetchMsg, setFetchMsg] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getCampaigns()
      setCampaigns(data)
    } catch {
      setError('Failed to load campaigns.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleFetch = async () => {
    setFetching(true)
    setFetchMsg(null)
    try {
      await triggerFetch()
      setFetchMsg('Data fetch triggered successfully. Refresh in a moment.')
    } catch {
      setFetchMsg('Failed to trigger fetch.')
    } finally {
      setFetching(false)
    }
  }

  if (loading) return <LoadingSpinner message="Loading campaigns…" />
  if (error) return <ErrorMessage message={error} onRetry={load} />

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.heading}>Campaigns</h1>
        {canWrite && (
          <button
            className={styles.fetchBtn}
            onClick={handleFetch}
            disabled={fetching}
          >
            {fetching ? 'Fetching…' : '⟳ Fetch Latest Data'}
          </button>
        )}
      </div>

      {fetchMsg && (
        <div className={styles.fetchMsg} role="status">
          {fetchMsg}
        </div>
      )}

      {campaigns.length === 0 ? (
        <p className={styles.empty}>No campaigns found.</p>
      ) : (
        <div className={styles.grid}>
          {campaigns.map((c) => {
            const m = c.latest_metrics
            return (
              <div key={c.campaign_id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <h2 className={styles.cardTitle}>{c.campaign_name}</h2>
                  <span className={styles.cardDate}>{m.date}</span>
                </div>

                <div className={styles.metrics}>
                  <div className={styles.metric}>
                    <span className={styles.metricLabel}>Impressions</span>
                    <span className={styles.metricValue}>{fmt(m.impressions, 0)}</span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.metricLabel}>Clicks</span>
                    <span className={styles.metricValue}>{fmt(m.clicks, 0)}</span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.metricLabel}>Spend</span>
                    <span className={styles.metricValue}>{fmtCurrency(m.spend)}</span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.metricLabel}>CTR</span>
                    <span className={styles.metricValue}>{fmtPct(m.ctr)}</span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.metricLabel}>CPC</span>
                    <span className={styles.metricValue}>{fmtCurrency(m.cpc)}</span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.metricLabel}>ROAS</span>
                    <span className={styles.metricValue}>{fmt(m.roas)}x</span>
                  </div>
                </div>

                <Link
                  to={`/dashboard/campaigns/${c.campaign_id}`}
                  className={styles.detailLink}
                >
                  View Details →
                </Link>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
