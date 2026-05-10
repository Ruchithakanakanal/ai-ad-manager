// ─── Auth ────────────────────────────────────────────────────────────────────

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  id_token: string
  token_type: string
}

export type UserRole = 'admin' | 'analyst' | 'viewer'

export interface JwtPayload {
  sub: string
  email?: string
  'cognito:groups'?: string[]
  role?: UserRole
  exp: number
  iat: number
}

// ─── Campaign Metrics ────────────────────────────────────────────────────────

export interface CampaignMetrics {
  campaign_id: string
  campaign_name: string
  date: string
  impressions: number
  clicks: number
  spend: number
  conversions: number
  ctr: number
  cpc: number
  roas: number
  reach: number
  frequency: number
}

export interface Campaign {
  campaign_id: string
  campaign_name: string
  latest_metrics: CampaignMetrics
}

// ─── Recommendations ─────────────────────────────────────────────────────────

export type OptimizationGoal = 'CTR' | 'CPC' | 'CONVERSION' | 'ROAS'

export interface Recommendation {
  recommendation_id: string
  campaign_id: string
  generated_at: string
  goal: OptimizationGoal
  action: string
  current_value: number
  suggested_value: number
  confidence_score: number
  reasoning: string
  applied: boolean
}

// ─── Dashboard Summary ───────────────────────────────────────────────────────

export interface DashboardSummary {
  total_campaigns: number
  total_spend: number
  total_impressions: number
  total_clicks: number
  total_conversions: number
  avg_ctr: number
  avg_cpc: number
  avg_roas: number
}

// ─── Alerts ──────────────────────────────────────────────────────────────────

export type AlertDirection = 'above' | 'below'

export interface AlertConfig {
  user_id: string
  campaign_id: string
  metric: string
  threshold: number
  direction: AlertDirection
  sns_topic_arn: string
}

export interface CreateAlertRequest {
  campaign_id: string
  metric: string
  threshold: number
  direction: AlertDirection
  sns_topic_arn: string
}
