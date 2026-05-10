import apiClient from './client'
import type { CampaignMetrics, Recommendation } from '../types'

// --------------------------------------------------
// Get All Campaigns
// --------------------------------------------------

export async function getCampaigns() {
  const response = await apiClient.get('/campaigns')
  return response.data
}

// --------------------------------------------------
// Get Single Campaign Metrics
// (Future Real Analytics)
// --------------------------------------------------

export async function getCampaignMetrics(campaignId: string): Promise<CampaignMetrics[]> {

  // Temporary mock response until real analytics API is built
  const campaignName = campaignId.replace(/[-_]/g, ' ')

  return [
    {
      campaign_id: campaignId,
      campaign_name: campaignName,
      date: '2026-05-01',
      impressions: 12000,
      clicks: 850,
      spend: 230,
      conversions: 64,
      ctr: 0.07,
      cpc: 0.27,
      roas: 3.5,
      reach: 9600,
      frequency: 1.25,
    },
    {
      campaign_id: campaignId,
      campaign_name: campaignName,
      date: '2026-05-08',
      impressions: 15600,
      clicks: 1120,
      spend: 310,
      conversions: 91,
      ctr: 0.072,
      cpc: 0.28,
      roas: 3.9,
      reach: 12400,
      frequency: 1.31,
    }
  ]
}

// --------------------------------------------------
// AI Recommendations
// (Future Optimization Engine)
// --------------------------------------------------

export async function getCampaignRecommendations(campaignId: string): Promise<Recommendation[]> {

  // Temporary mock AI recommendations

  return [
    {
      recommendation_id: `${campaignId}-budget`,
      campaign_id: campaignId,
      generated_at: new Date().toISOString(),
      goal: 'ROAS',
      action: 'Increase Instagram ad budget by 15%',
      current_value: 3.5,
      suggested_value: 3.9,
      confidence_score: 0.82,
      reasoning: 'Recent click and conversion rates are stable enough to support a modest budget increase.',
      applied: false,
    },
    {
      recommendation_id: `${campaignId}-audience`,
      campaign_id: campaignId,
      generated_at: new Date().toISOString(),
      goal: 'CTR',
      action: 'Test a younger interest-based audience segment',
      current_value: 0.07,
      suggested_value: 0.082,
      confidence_score: 0.74,
      reasoning: 'Fashion and wearable campaigns often improve engagement when creative is tuned for younger buyers.',
      applied: false,
    }
  ]
}

// --------------------------------------------------
// Apply Recommendation
// --------------------------------------------------

export async function applyRecommendation(
  campaignId: string,
  recommendationId: string
): Promise<void> {

  console.log(
    `Applying recommendation ${recommendationId} to campaign ${campaignId}`
  )
}

// --------------------------------------------------
// Trigger Fetch
// --------------------------------------------------

export async function triggerFetch(): Promise<void> {

  console.log("Fetching latest campaign data...")
}
