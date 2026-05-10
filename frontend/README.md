# AI Campaign Dashboard — Frontend

React dashboard for the AI-Powered Facebook Campaign Optimization platform. Built with Vite + React + TypeScript.

## Features

- **Login page** — authenticates via `POST /auth/login`, stores JWT in memory (never localStorage)
- **Dashboard overview** — aggregated KPI widgets + campaign table
- **Campaigns list** — card grid of all campaigns with latest metrics
- **Campaign detail** — time-series line charts (recharts) for impressions, clicks, spend, CTR, CPC, ROAS + AI recommendations panel
- **Recommendations** — actionable cards with Apply button (Analyst/Admin only; hidden for Viewer)
- **Alerts** — view existing alert configs; create new ones (Analyst/Admin only)
- **Role-based UI** — role extracted from JWT payload; controls hidden/shown accordingly
- **Global 401 handling** — any API call returning 401 clears the token and redirects to login

## Tech Stack

| Tool | Purpose |
|---|---|
| [Vite](https://vitejs.dev/) | Build tool & dev server |
| [React 18](https://react.dev/) | UI framework |
| [TypeScript](https://www.typescriptlang.org/) | Type safety |
| [React Router v6](https://reactrouter.com/) | Client-side routing |
| [Axios](https://axios-http.com/) | HTTP client with interceptors |
| [Recharts](https://recharts.org/) | Time-series line charts |

## Setup

### Prerequisites

- Node.js 18+ and npm 9+

### Install & run

```bash
# From the frontend/ directory
npm install
npm run dev
```

The dev server starts at `http://localhost:3000`.

### Build for production

```bash
npm run build
# Output in frontend/dist/
```

### Environment variables

Copy `.env.example` to `.env.local` and set your API URL:

```bash
cp .env.example .env.local
```

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Base URL of the FastAPI backend |

## Project Structure

```
frontend/
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
└── src/
    ├── main.tsx              # Entry point
    ├── App.tsx               # Router setup
    ├── api/
    │   ├── client.ts         # Axios instance + JWT interceptors
    │   ├── auth.ts           # POST /auth/login
    │   ├── campaigns.ts      # Campaign & metrics endpoints
    │   ├── dashboard.ts      # GET /dashboard/summary
    │   └── alerts.ts         # Alert config endpoints
    ├── context/
    │   └── AuthContext.tsx   # JWT state, role extraction, login/logout
    ├── components/
    │   ├── ProtectedRoute.tsx
    │   ├── NavBar.tsx
    │   ├── LoadingSpinner.tsx
    │   └── ErrorMessage.tsx
    ├── pages/
    │   ├── LoginPage.tsx
    │   ├── DashboardLayout.tsx
    │   ├── OverviewPage.tsx       # KPI summary + campaigns table
    │   ├── CampaignsPage.tsx      # Campaign card grid
    │   ├── CampaignDetailPage.tsx # Charts + recommendations
    │   └── AlertsPage.tsx         # Alert list + create form
    ├── styles/
    │   └── global.css
    └── types/
        └── index.ts          # Shared TypeScript types
```

## Authentication & Security

- JWT is stored **in React state only** — never written to `localStorage` or `sessionStorage`
- The Axios request interceptor attaches `Authorization: Bearer <token>` to every request
- The Axios response interceptor catches any `401` response, clears the token, and redirects to `/login`
- Role is extracted from the JWT payload (`role` claim or `cognito:groups`)

## Role-Based UI

| Feature | Viewer | Analyst | Admin |
|---|---|---|---|
| View campaigns & metrics | ✅ | ✅ | ✅ |
| View recommendations | ✅ | ✅ | ✅ |
| Apply recommendations | ❌ | ✅ | ✅ |
| Trigger data fetch | ❌ | ✅ | ✅ |
| Create alert configs | ❌ | ✅ | ✅ |
| View alert configs | ✅ | ✅ | ✅ |

## Deployment

The production build (`npm run build`) outputs static files to `dist/`. These can be uploaded to an S3 bucket and served via CloudFront (see `infrastructure/` for CDK stacks).

Set `VITE_API_URL` to your API Gateway endpoint URL before building:

```bash
VITE_API_URL=https://api.example.com npm run build
```
