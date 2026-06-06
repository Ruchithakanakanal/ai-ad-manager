import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorMessage } from '../components/ErrorMessage'
import {
  getFacebookStatus,
  getFacebookOAuthUrl,
  disconnectFacebook,
  selectFacebookAdAccount,
  type FacebookStatus,
} from '../api/facebook'
import styles from './ConnectFacebookPage.module.css'

export function ConnectFacebookPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const [status, setStatus] = useState<FacebookStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [banner, setBanner] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)

  // ─── Load connection status ──────────────────────────────────────────────
  const loadStatus = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getFacebookStatus()
      setStatus(data)
    } catch {
      setError('Could not load your Facebook connection status.')
    } finally {
      setLoading(false)
    }
  }

  // ─── Handle OAuth redirect result (?fb=connected|error) ──────────────────
  useEffect(() => {
    const fb = searchParams.get('fb')
    if (fb === 'connected') {
      setBanner({ type: 'success', text: 'Facebook account connected successfully.' })
    } else if (fb === 'error') {
      setBanner({
        type: 'error',
        text: searchParams.get('message') || 'Failed to connect Facebook account.',
      })
    }
    if (fb) {
      // Clean the query params so a refresh doesn't repeat the banner.
      searchParams.delete('fb')
      searchParams.delete('message')
      setSearchParams(searchParams, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    loadStatus()
  }, [])

  // ─── Start the Facebook OAuth flow ───────────────────────────────────────
  const handleConnect = async () => {
    setConnecting(true)
    setBanner(null)
    try {
      const { url } = await getFacebookOAuthUrl()
      window.location.href = url
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setBanner({
        type: 'error',
        text:
          detail ||
          'Facebook is not configured yet. Please try again later.',
      })
      setConnecting(false)
    }
  }

  const handleDisconnect = async () => {
    setConnecting(true)
    setBanner(null)
    try {
      const data = await disconnectFacebook()
      setStatus(data)
      setBanner({ type: 'success', text: 'Facebook account disconnected.' })
    } catch {
      setBanner({ type: 'error', text: 'Failed to disconnect. Please try again.' })
    } finally {
      setConnecting(false)
    }
  }

  const handleSelectAdAccount = async (adAccountId: string) => {
    try {
      const data = await selectFacebookAdAccount(adAccountId)
      setStatus(data)
      setBanner({ type: 'success', text: 'Active ad account updated.' })
    } catch {
      setBanner({ type: 'error', text: 'Failed to update ad account.' })
    }
  }

  const isConnected = status?.connected === true

  return (
    <div className={styles.page}>
      <h2 className={styles.heading}>Connect Facebook</h2>
      <p className={styles.subtitle}>
        Link your Facebook business account to manage and publish ad campaigns.
        Each user connects their own account.
      </p>

      {banner && (
        <div
          className={`${styles.banner} ${
            banner.type === 'success' ? styles.bannerSuccess : styles.bannerError
          }`}
        >
          {banner.text}
        </div>
      )}

      {loading ? (
        <LoadingSpinner />
      ) : error ? (
        <ErrorMessage message={error} onRetry={loadStatus} />
      ) : (
        <div className={styles.card}>
          {isConnected ? (
            <>
              <div className={styles.statusRow}>
                <span className={styles.connectedBadge}>● Connected</span>
                <span className={styles.accountName}>
                  {status?.fb_user_name || 'Facebook account'}
                </span>
              </div>

              {status?.ad_accounts && status.ad_accounts.length > 0 ? (
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="ad-account">
                    Active ad account
                  </label>
                  <select
                    id="ad-account"
                    className={styles.select}
                    value={status.ad_account_id || ''}
                    onChange={(e) => handleSelectAdAccount(e.target.value)}
                  >
                    {status.ad_accounts.map((acc) => (
                      <option key={acc.id} value={acc.id}>
                        {acc.name ? `${acc.name} (${acc.id})` : acc.id}
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <p className={styles.note}>
                  No ad accounts were found for this Facebook account.
                </p>
              )}

              <button
                className={styles.disconnectBtn}
                onClick={handleDisconnect}
                disabled={connecting}
              >
                {connecting ? 'Working…' : 'Disconnect'}
              </button>
            </>
          ) : (
            <>
              <p className={styles.note}>
                You haven&apos;t connected a Facebook account yet.
              </p>
              <button
                className={styles.connectBtn}
                onClick={handleConnect}
                disabled={connecting}
              >
                <span className={styles.fbIcon}>f</span>
                {connecting ? 'Redirecting…' : 'Connect with Facebook'}
              </button>
              {status?.configured === false && (
                <p className={styles.note}>
                  Note: the Facebook app is not configured on the server yet.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
