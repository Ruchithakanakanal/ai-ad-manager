import { useEffect, useState } from 'react'
import apiClient from '../api/client'
import styles from './OverviewPage.module.css'

// ─── Campaign Type ───────────────────────────────────

interface Campaign {
  id: number
  product: string
  audience: string
  platform: string
  budget: string
  performance_score: number
  headline: string
}

// ─── KPI Widget ──────────────────────────────────────

interface KpiWidgetProps {
  label: string
  value: string
  icon: string
}

function KpiWidget({
  label,
  value,
  icon,
}: KpiWidgetProps) {

  return (
    <div className={styles.kpiCard}>

      <span className={styles.kpiIcon}>
        {icon}
      </span>

      <div>
        <div className={styles.kpiValue}>
          {value}
        </div>

        <div className={styles.kpiLabel}>
          {label}
        </div>
      </div>

    </div>
  )
}

// ─── Page ────────────────────────────────────────────

export function OverviewPage() {

  const [campaigns, setCampaigns] = useState<Campaign[]>([])

  // ---------------------------------------------------
  // Fetch Campaigns
  // ---------------------------------------------------

  useEffect(() => {

    async function fetchCampaigns() {

      try {

        const response = await apiClient.get('/campaigns')

        setCampaigns(response.data)

      } catch (error) {

        console.error('Failed to load campaigns', error)

      }
    }

    fetchCampaigns()

  }, [])

  // ---------------------------------------------------
  // Dashboard KPI Values
  // ---------------------------------------------------

  const totalCampaigns = campaigns.length

  // ---------------------------------------------------
  // UI
  // ---------------------------------------------------

  return (

    <div className={styles.page}>

      <h1 className={styles.heading}>
        AI Campaign Dashboard
      </h1>

      {/* KPI SECTION */}

      <section className={styles.kpiGrid}>

        <KpiWidget
          label="Total Campaigns"
          value={String(totalCampaigns)}
          icon="📁"
        />

        <KpiWidget
          label="AI Generated"
          value="100%"
          icon="🤖"
        />

        <KpiWidget
          label="Platform"
          value="Meta Ads"
          icon="📢"
        />

        <KpiWidget
          label="Backend"
          value="FastAPI"
          icon="⚡"
        />

      </section>

      {/* TABLE SECTION */}

      <section className={styles.tableSection}>

        <div className={styles.sectionHeader}>

          <h2 className={styles.sectionTitle}>
            Generated Campaigns
          </h2>

        </div>

        <div className={styles.tableWrapper}>

          <table className={styles.table}>

            <thead>

              <tr>
                <th>Product</th>
                <th>Audience</th>
                <th>Platform</th>
                <th>Budget</th>
                <th>Score</th>
                <th>Headline</th>
              </tr>

            </thead>

            <tbody>

              {campaigns.map((c) => (

                <tr key={c.id}>

                  <td>{c.product}</td>

                  <td>{c.audience}</td>

                  <td>{c.platform}</td>

                  <td>{c.budget}</td>

                  <td>{c.performance_score}</td>

                  <td>{c.headline}</td>

                </tr>

              ))}

            </tbody>

          </table>

        </div>

      </section>

    </div>
  )
}