# DeadMile AI — Production Deployment Guide

This guide turns DeadMile from a demo stack into a **deployable product foundation**. Full SaaS (billing, multi-tenant auth, live DAT feeds) is Phase 2 — this doc covers what is implemented today and how to run it in production.

---

## What “production-ready” means in this repo

| Capability | Status |
|------------|--------|
| Per-fleet cost profile (fuel, CPM, fees, MPG) | ✅ `/carrier/profile` + Fleet Settings UI |
| Profitability uses fleet costs | ✅ Passed to profitability engine |
| API key auth (optional) | ✅ `API_GATEWAY_KEY` + `X-API-Key` header |
| No fake data on API failure | ✅ `NEXT_PUBLIC_APP_MODE=production` |
| Search audit trail | ✅ `search_audit` table |
| Live load board (DAT/Truckstop) | ❌ Phase 2 — plug in via load ingestion |
| User login / multi-tenant | ❌ Phase 2 |
| Mobile app | ❌ Phase 2 — responsive web works today |

---

## 1. Run database migration (required once)

On existing databases, apply production tables:

```bash
make db-migrate-prod
```

This creates:

- `carrier_profiles` — your fleet’s real operating costs  
- `api_keys` — for future hashed key storage  
- `search_audit` — logs every load search  

---

## 2. Configure production environment

Copy and edit `.env`:

```bash
cp .env.example .env
```

**Critical production variables:**

```env
ENVIRONMENT=production
API_GATEWAY_KEY=your-long-random-secret-here
POSTGRES_PASSWORD=strong-password-here
NEXT_PUBLIC_APP_MODE=production

# Set at Docker BUILD time for frontend:
NEXT_PUBLIC_API_URL=https://your-domain.com/api
```

Generate an API key:

```bash
openssl rand -hex 32
```

---

## 3. Fleet Settings (drivers / dispatchers)

1. Open **Fleet Settings** in the nav (or `/settings`)
2. Enter your real numbers:
   - Fuel $/gal, driver $/mi, insurance, maintenance, tolls
   - Dispatch & factoring %
   - Loaded / empty MPG
3. Click **Save Fleet Profile**

All load searches and net profit calculations now use **your costs**, not industry defaults.

In production mode, paste your `API_GATEWAY_KEY` in the settings page (stored in browser localStorage).

---

## 4. Deploy with Docker

```bash
# Full stack (ingestion, Kafka, Temporal, monitoring)
make demo

# Apply production schema
make db-migrate-prod

# Seed loads (after placing data in data/text/)
make seed
make seed-vectors
make train-models
```

**Recommended production topology:**

- Put **Nginx** (port 8888) in front — TLS termination at your load balancer  
- Do **not** expose Postgres/Redis/Kafka ports publicly  
- Set strong passwords for Postgres, MinIO, Grafana  
- Rotate `OPENAI_API_KEY` and `API_GATEWAY_KEY` regularly  

---

## 5. API authentication

When `API_GATEWAY_KEY` is set, all routes except `/health` require:

```http
X-API-Key: your-long-random-secret-here
```

Example:

```bash
curl -H "X-API-Key: $API_GATEWAY_KEY" \
  http://localhost:8010/carrier/profile
```

---

## 6. Roadmap to full product (Phase 2)

Priority order for a real commercial launch:

1. **Live load feed** — DAT, Truckstop, or broker API → replace synthetic `data/text`  
2. **Real routing** — PCMiler / HERE for miles and tolls  
3. **OAuth / fleet accounts** — Supabase Auth, Auth0, or Cognito  
4. **Multi-carrier tenants** — carrier_id per organization  
5. **Book load workflow** — rate con, broker contact, HOS check  
6. **Mobile PWA** — installable, offline location cache  
7. **Billing** — Stripe per truck/month  

---

## 7. Monitoring

| Service | URL |
|---------|-----|
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |
| API metrics | http://localhost:8010/metrics |
| Temporal UI | http://localhost:8081 |

Set alerts on: API error rate, agent latency, Postgres connections, Redis memory.

---

## 8. Support checklist before going live with a fleet

- [ ] `make db-migrate-prod` run on production DB  
- [ ] Fleet profile saved with real costs  
- [ ] `ENVIRONMENT=production` and `NEXT_PUBLIC_APP_MODE=production`  
- [ ] `API_GATEWAY_KEY` set and distributed to users  
- [ ] Postgres password changed from default  
- [ ] OpenAI / map keys in secrets manager, not in git  
- [ ] Loads seeded or live feed connected  
- [ ] Test: Dry Van search → change to Reefer → Update Search  

---

Built for owner-operators who need **net profit**, not gross rate theater.
