import apiClient from '../api/client'

export async function publishFacebookCampaign(name: string, status = 'PAUSED') {

  const response = await apiClient.post(
    '/publish-facebook',
    {
      name,
      status,
    }
  )

  return response.data
}
