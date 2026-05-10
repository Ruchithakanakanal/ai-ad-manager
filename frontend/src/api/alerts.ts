import apiClient from './client'
import type { AlertConfig, CreateAlertRequest } from '../types'

export async function getAlerts(): Promise<AlertConfig[]> {
  const response = await apiClient.get<AlertConfig[]>('/alerts')
  return response.data
}

export async function createAlert(payload: CreateAlertRequest): Promise<AlertConfig> {
  const response = await apiClient.post<AlertConfig>('/alerts', payload)
  return response.data
}
