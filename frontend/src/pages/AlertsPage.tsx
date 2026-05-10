import React, { useEffect, useState } from 'react'
import { getAlerts, createAlert } from '../api/alerts'
import { getCampaigns } from '../api/campaigns'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorMessage } from '../components/ErrorMessage'
import { useAuth } from '../context/AuthContext'
import type { AlertConfig, Campaign, CreateAlertRequest, AlertDirection } from '../types'
import styles from './AlertsPage.module.css'

const METRIC_OPTIONS = ['ctr', 'cpc', 'roas', 'spend', 'impressions', 'clicks', 'conversions']

// ─── Alert Card ──────────────────────────────────────────────────────────────

function AlertCard({ alert }: { alert: AlertConfig }) {
  return (
    <div className={styles.alertCard}>
      <div className={styles.alertHeader}>
        <span className={styles.alertMetric}>{alert.metric.toUpperCase()}</span>
        <span
          className={`${styles.alertDirection} ${alert.direction === 'above' ? styles.above : styles.below}`}
        >
          {alert.direction === 'above' ? '▲ above' : '▼ below'} {alert.threshold}
        </span>
      </div>
      <div className={styles.alertMeta}>
        <span className={styles.alertLabel}>Campaign:</span>
        <span className={styles.alertValue}>{alert.campaign_id}</span>
      </div>
      <div className={styles.alertMeta}>
        <span className={styles.alertLabel}>SNS Topic:</span>
        <span className={styles.alertValue} title={alert.sns_topic_arn}>
          {alert.sns_topic_arn.split(':').pop()}
        </span>
      </div>
    </div>
  )
}

// ─── Create Alert Form ───────────────────────────────────────────────────────

interface CreateAlertFormProps {
  campaigns: Campaign[]
  onCreated: (alert: AlertConfig) => void
}

function CreateAlertForm({ campaigns, onCreated }: CreateAlertFormProps) {
  const [campaignId, setCampaignId] = useState('')
  const [metric, setMetric] = useState('ctr')
  const [threshold, setThreshold] = useState('')
  const [direction, setDirection] = useState<AlertDirection>('below')
  const [snsTopicArn, setSnsTopicArn] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(false)

    const thresholdNum = parseFloat(threshold)
    if (isNaN(thresholdNum)) {
      setError('Threshold must be a valid number.')
      return
    }

    const payload: CreateAlertRequest = {
      campaign_id: campaignId,
      metric,
      threshold: thresholdNum,
      direction,
      sns_topic_arn: snsTopicArn,
    }

    setSubmitting(true)
    try {
      const created = await createAlert(payload)
      onCreated(created)
      setSuccess(true)
      // Reset form
      setCampaignId('')
      setMetric('ctr')
      setThreshold('')
      setDirection('below')
      setSnsTopicArn('')
    } catch {
      setError('Failed to create alert. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <h3 className={styles.formTitle}>Create Alert</h3>

      <div className={styles.formGrid}>
        <div className={styles.field}>
          <label htmlFor="alert-campaign" className={styles.label}>
            Campaign
          </label>
          <select
            id="alert-campaign"
            className={styles.select}
            value={campaignId}
            onChange={(e) => setCampaignId(e.target.value)}
            required
            disabled={submitting}
          >
            <option value="">Select a campaign…</option>
            {campaigns.map((c) => (
              <option key={c.campaign_id} value={c.campaign_id}>
                {c.campaign_name}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="alert-metric" className={styles.label}>
            Metric
          </label>
          <select
            id="alert-metric"
            className={styles.select}
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            disabled={submitting}
          >
            {METRIC_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m.toUpperCase()}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="alert-direction" className={styles.label}>
            Direction
          </label>
          <select
            id="alert-direction"
            className={styles.select}
            value={direction}
            onChange={(e) => setDirection(e.target.value as AlertDirection)}
            disabled={submitting}
          >
            <option value="below">Below threshold</option>
            <option value="above">Above threshold</option>
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="alert-threshold" className={styles.label}>
            Threshold
          </label>
          <input
            id="alert-threshold"
            type="number"
            step="any"
            className={styles.input}
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            placeholder="e.g. 0.02"
            required
            disabled={submitting}
          />
        </div>

        <div className={`${styles.field} ${styles.fieldFull}`}>
          <label htmlFor="alert-sns" className={styles.label}>
            SNS Topic ARN
          </label>
          <input
            id="alert-sns"
            type="text"
            className={styles.input}
            value={snsTopicArn}
            onChange={(e) => setSnsTopicArn(e.target.value)}
            placeholder="arn:aws:sns:us-east-1:123456789012:my-topic"
            required
            disabled={submitting}
          />
        </div>
      </div>

      {error && (
        <div className={styles.formError} role="alert">
          {error}
        </div>
      )}

      {success && (
        <div className={styles.formSuccess} role="status">
          Alert created successfully.
        </div>
      )}

      <button
        type="submit"
        className={styles.submitBtn}
        disabled={submitting || !campaignId || !threshold || !snsTopicArn}
      >
        {submitting ? 'Creating…' : 'Create Alert'}
      </button>
    </form>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export function AlertsPage() {
  const { canWrite } = useAuth()
  const [alerts, setAlerts] = useState<AlertConfig[]>([])
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [alertsData, campaignsData] = await Promise.all([
        getAlerts(),
        getCampaigns(),
      ])
      setAlerts(alertsData)
      setCampaigns(campaignsData)
    } catch {
      setError('Failed to load alerts.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleAlertCreated = (alert: AlertConfig) => {
    setAlerts((prev) => [alert, ...prev])
  }

  if (loading) return <LoadingSpinner message="Loading alerts…" />
  if (error) return <ErrorMessage message={error} onRetry={load} />

  return (
    <div className={styles.page}>
      <h1 className={styles.heading}>Alert Configuration</h1>

      {/* Create form — Analyst/Admin only */}
      {canWrite && (
        <section className={styles.formSection}>
          <CreateAlertForm campaigns={campaigns} onCreated={handleAlertCreated} />
        </section>
      )}

      {/* Existing alerts */}
      <section aria-label="Existing Alerts">
        <h2 className={styles.sectionTitle}>Your Alerts</h2>

        {alerts.length === 0 ? (
          <p className={styles.empty}>
            {canWrite
              ? 'No alerts configured yet. Create one above.'
              : 'No alerts configured.'}
          </p>
        ) : (
          <div className={styles.alertsGrid}>
            {alerts.map((a, i) => (
              <AlertCard key={`${a.campaign_id}-${a.metric}-${i}`} alert={a} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
