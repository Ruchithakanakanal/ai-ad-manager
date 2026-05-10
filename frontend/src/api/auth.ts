import apiClient from './client'

export const login = (data: any) => {
  return apiClient
    .post('/login', data)   // 👈 backend endpoint
    .then(res => res.data)
}