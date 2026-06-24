# DeadMile AI — Production Deployment Guide

DeadMile is a **free, production-deployable** load optimization app for owner-operators. This doc covers what's implemented and how to run it.

---

## What's implemented today

| Capability | Status |
|------------|--------|
| Per-fleet cost profile (fuel, CPM, fees, MPG) | ✅ `/carrier/profile` + Fleet Settings |
| Profitability uses fleet costs | ✅ Passed to profitability engine |
| **Load import** (paste, CSV, screenshot) | ✅ `/import` + GPT-4o parsing |
| **Load compare** (public share link) | ✅ `/compare` |
| **User auth** (Google + email) | ✅ NextAuth.js |
| **Import history** (saved analyses) | ✅ `import_history` table |
| **PWA** (installable mobile web) | ✅ manifest + service worker |
| API key auth (optional) | ✅ `API_GATEWAY_KEY` |
| No mock data on API failure | ✅ `NEXT_PUBLIC_APP_MODE=production` |
| Search audit trail | ✅ `search_audit` table |
| Live load board (DAT/Truckstop API) | ❌ Future — use Import paste today |
| Real routing miles (PCMiler/HERE) | ❌ Future — uses geodesic estimates |

---

## Database migrations (run once per environment)

```bash
make db-migrate-prod      # carrier profiles, audit
make db-migrate-auth      # user signup counter
make db-migrate-import    # saved import analyses
```

---

## Auth setup

```env
NEXTAUTH_SECRET=openssl-rand-hex-32
NEXTAUTH_URL=https://your-domain.com
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

Google OAuth redirect URI: `https://your-domain.com/api/auth/callback/google`

Email login works **without** Google credentials for development.

Per-user fleet profiles use `X-Carrier-Id` (set automatically after login).

---

## Import API

| Endpoint | Purpose |
|----------|---------|
| `POST /import/parse` | Paste load board text |
| `POST /import/csv` | CSV with origin, destination, miles, rate |
| `POST /import/screenshot` | PNG/JPG via GPT-4o vision |
| `POST /import/compare` | Two-load showdown (public) |
| `POST /import/history` | Save analysis |
| `GET /import/history` | List recent saves |

Requires `OPENAI_API_KEY` for best parsing (regex fallback for text).

---

## Production environment

```env
ENVIRONMENT=production
API_GATEWAY_KEY=your-long-random-secret
NEXT_PUBLIC_APP_MODE=production
NEXT_PUBLIC_API_URL=https://your-domain.com/api
```

```bash
make demo
make db-migrate-prod && make db-migrate-auth && make db-migrate-import
make seed
docker compose build frontend api-gateway profitability-engine
docker compose up -d frontend api-gateway profitability-engine
```

---

## Fleet Settings

1. Sign in → complete onboarding (or skip)
2. Open **Fleet Settings** (`/settings`)
3. Enter real fuel $/gal, driver $/mi, MPG, insurance
4. Set **home base** — used as default location on Import

Banner reminds users still on default costs.

---

## Roadmap (still free — no Stripe)

1. **Real routing miles** — PCMiler / HERE  
2. **Live load feed** — DAT / Truckstop API  
3. **Book load workflow** — rate con, HOS  
4. **Offline import cache** — PWA enhancement  

---

## Pre-launch checklist

- [ ] All migrations run (`prod`, `auth`, `import`)
- [ ] `NEXTAUTH_URL` matches public domain
- [ ] Google OAuth redirect configured
- [ ] Fleet profile tested with real costs
- [ ] Import tested with pasted DAT text
- [ ] `OPENAI_API_KEY` in secrets manager
- [ ] Postgres password rotated from default
- [ ] `.env` never committed to git

---

Built for owner-operators who need **net profit**, not gross rate theater.
