import { useState } from 'react'
import axios from 'axios'
import apiClient from '../api/client'
import styles from './OverviewPage.module.css'

interface GeneratedCampaign {
  id?: number
  product: string
  audience: string
  platform: string
  budget: string
  timing?: string
  strategy: string
  performance_score: number
  headline: string
  primary_text: string
  call_to_action: string
}

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (detail) return JSON.stringify(detail)
    return error.message
  }

  return error instanceof Error ? error.message : 'Something went wrong'
}

export function CreateCampaignPage() {

  const [product, setProduct] = useState('')
  const [goal, setGoal] = useState('Increase Sales')
  const [tone, setTone] = useState('Exciting')

  const [loading, setLoading] = useState(false)
  const [publishing, setPublishing] = useState(false)

  const [result, setResult] = useState<GeneratedCampaign | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // ---------------------------------------------------
  // Generate AI Campaign
  // ---------------------------------------------------

  async function generateCampaign() {
    const trimmedProduct = product.trim()

    if (!trimmedProduct) {
      setErrorMessage('Please enter a product name.')
      return
    }

    try {

      setLoading(true)
      setMessage(null)
      setErrorMessage(null)

      const response = await apiClient.post(
        '/generate-ad',
        {
          product: trimmedProduct,
          goal,
          tone
        }
      )

      const generated = response.data.campaign
        ? { ...response.data.campaign, id: response.data.id, product: response.data.product }
        : response.data

      setResult(generated)
      setMessage('Campaign generated and saved successfully.')

    } catch (error) {

      console.error(error)

      setErrorMessage(`Failed to generate campaign: ${getErrorMessage(error)}`)

    } finally {

      setLoading(false)

    }
  }

  // ---------------------------------------------------
  // Publish To Facebook
  // ---------------------------------------------------

  async function publishCampaign() {
    if (!result) return

    try {

      setPublishing(true)
      setMessage(null)
      setErrorMessage(null)

      const response = await apiClient.post(
        '/publish-facebook',
        {
          name: result.headline || `${result.product} Campaign`,
          status: 'PAUSED'
        }
      )

      console.log(response.data)

      setMessage('Campaign published to Facebook successfully.')

    } catch (error) {

      console.error(error)

      setErrorMessage(`Facebook publish failed: ${getErrorMessage(error)}`)

    } finally {

      setPublishing(false)

    }
  }

  return (

    <div className={styles.page}>

      <h1 className={styles.heading}>
        Create AI Campaign
      </h1>

      <div className={styles.tableSection}>

        {/* PRODUCT */}

        <div style={{ marginBottom: '20px' }}>

          <label>Product</label>

          <input
            type="text"
            value={product}
            onChange={(e) => setProduct(e.target.value)}
            placeholder="Enter product name"
            style={{
              width: '100%',
              padding: '12px',
              marginTop: '8px'
            }}
          />

        </div>

        {/* GOAL */}

        <div style={{ marginBottom: '20px' }}>

          <label>Campaign Goal</label>

          <select
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            style={{
              width: '100%',
              padding: '12px',
              marginTop: '8px'
            }}
          >

            <option>Increase Sales</option>

            <option>Brand Awareness</option>

            <option>Lead Generation</option>

          </select>

        </div>

        {/* TONE */}

        <div style={{ marginBottom: '20px' }}>

          <label>Ad Tone</label>

          <select
            value={tone}
            onChange={(e) => setTone(e.target.value)}
            style={{
              width: '100%',
              padding: '12px',
              marginTop: '8px'
            }}
          >

            <option>Exciting</option>

            <option>Professional</option>

            <option>Luxury</option>

            <option>Friendly</option>

          </select>

        </div>

        {/* GENERATE BUTTON */}

        <button
          onClick={generateCampaign}
          disabled={loading || !product.trim()}
          style={{
            padding: '14px 24px',
            fontSize: '16px',
            cursor: 'pointer'
          }}
        >

          {loading
            ? 'Generating...'
            : 'Generate AI Campaign'}

        </button>

      </div>

      {message && (
        <div className={styles.tableSection} style={{ marginTop: '20px' }}>
          {message}
        </div>
      )}

      {errorMessage && (
        <div className={styles.tableSection} style={{ marginTop: '20px', color: '#fecaca' }}>
          {errorMessage}
        </div>
      )}

      {/* RESULT */}

      {result && (

        <div
          className={styles.tableSection}
          style={{ marginTop: '30px' }}
        >

          <h2>Generated Campaign</h2>

          <p><strong>Product:</strong> {result.product}</p>

          <p><strong>Audience:</strong> {result.audience}</p>

          <p><strong>Platform:</strong> {result.platform}</p>

          <p><strong>Budget:</strong> {result.budget}</p>

          <p><strong>Timing:</strong> {result.timing}</p>

          <p><strong>Strategy:</strong> {result.strategy}</p>

          <p><strong>Score:</strong> {result.performance_score}</p>

          <p><strong>Headline:</strong> {result.headline}</p>

          <p><strong>Primary Text:</strong> {result.primary_text}</p>

          <p><strong>CTA:</strong> {result.call_to_action}</p>

          {/* FACEBOOK BUTTON */}

          <button
            onClick={publishCampaign}
            disabled={publishing}
            style={{
              marginTop: '20px',
              padding: '14px 24px',
              fontSize: '16px',
              cursor: 'pointer'
            }}
          >

            {publishing
              ? 'Publishing...'
              : 'Publish To Facebook'}

          </button>

        </div>

      )}

    </div>
  )
}
