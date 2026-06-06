import apiClient from './client'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface FacebookAdAccount {
  id: string
  account_id?: string
  name?: string
  account_status?: number
  currency?: string
}

export interface FacebookStatus {
  connected: boolean
  configured?: boolean
  fb_user_name?: string | null
  fb_user_id?: string | null
  ad_account_id?: string | null
  ad_accounts?: FacebookAdAccount[]
}

// ─── API calls ───────────────────────────────────────────────────────────────

export async function getFacebookStatus(): Promise<FacebookStatus> {
  const response = await apiClient.get('/facebook/status')
  return response.data
}

export async function getFacebookOAuthUrl(): Promise<{ url: string }> {
  const response = await apiClient.get('/facebook/oauth-url')
  return response.data
}

export async function selectFacebookAdAccount(
  adAccountId: string
): Promise<FacebookStatus> {
  const response = await apiClient.post('/facebook/select-ad-account', {
    ad_account_id: adAccountId,
  })
  return response.data
}

export async function disconnectFacebook(): Promise<FacebookStatus> {
  const response = await apiClient.post('/facebook/disconnect')
  return response.data
}
