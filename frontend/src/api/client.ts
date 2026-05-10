import axios, {
  AxiosInstance,
  InternalAxiosRequestConfig,
  AxiosResponse,
} from 'axios'

// ─── BASE URL ─────────────────────────────────────────────
const API_BASE_URL =
  import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ─── TOKEN STORAGE (FIXED) ───────────────────────────────
// Now supports BOTH memory + localStorage for refresh stability

let inMemoryToken: string | null = null

const TOKEN_KEY = 'token'

export function setToken(token: string | null): void {
  inMemoryToken = token

  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function getToken(): string | null {
  if (inMemoryToken) return inMemoryToken

  const stored = localStorage.getItem(TOKEN_KEY)
  if (stored) {
    inMemoryToken = stored
  }

  return inMemoryToken
}

// ─── UNAUTHORIZED HANDLER ───────────────────────────────
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler
}

// ─── AXIOS INSTANCE ───────────────────────────────────────
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ─── REQUEST INTERCEPTOR ─────────────────────────────────
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getToken()

    if (token) {
      config.headers = config.headers ?? {}
      config.headers.Authorization = `Bearer ${token}`
    }

    console.log("API CALL:", `${config.baseURL ?? ''}${config.url ?? ''}`)

    return config
  },
  (error) => Promise.reject(error)
)

// ─── RESPONSE INTERCEPTOR ────────────────────────────────
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error) => {
    console.error("API ERROR:", error?.response?.status, error?.config?.url)

    if (error.response?.status === 401) {
      setToken(null)
      if (onUnauthorized) onUnauthorized()
    }

    return Promise.reject(error)
  }
)

export default apiClient
