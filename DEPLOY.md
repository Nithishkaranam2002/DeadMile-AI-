# Deploy DeadMile AI to Production

This guide gets DeadMile live on a **public URL** with real routing miles and optional live load sync.

---

## What you get in production

| Feature | How |
|---------|-----|
| Single public URL | Nginx on port 80 (add Caddy/Cloudflare for HTTPS) |
| Real road miles | OSRM (free) — deadhead uses driving distance |
| Live loads | POST `/loads/live/upsert` or cron `scripts/sync_live_loads.py` |
| Auth | Google + email via NextAuth |
| Import | Paste / CSV / screenshot (no load board API required) |

---

## Option A — VPS (DigitalOcean, Hetzner, AWS EC2)

**Minimum:** 4 GB RAM, 2 vCPU, Ubuntu 22.04+

### 1. Server setup

```bash
# On your VPS
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER
# Log out and back in

git clone https://github.com/Nithishkaranam2002/DeadMile-AI-.git
cd DeadMile-AI-
cp .env.example .env
nano .env   # fill secrets (see below)
```

### 2. Required `.env` for production

```env
ENVIRONMENT=production
NEXT_PUBLIC_APP_MODE=production

# Strong passwords
POSTGRES_PASSWORD=your-strong-password
NEXTAUTH_SECRET=$(openssl rand -hex 32)
NEXTAUTH_URL=https://yourdomain.com

# Google OAuth — redirect: https://yourdomain.com/api/auth/callback/google
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Maps (MapTiler or Mapbox)
NEXT_PUBLIC_MAPTILER_KEY=...

# OpenAI (Import parsing)
OPENAI_API_KEY=sk-...

# Optional API protection
API_GATEWAY_KEY=$(openssl rand -hex 32)

# Real routing (OSRM public server — free, rate-limited)
ROUTING_PROVIDER=osrm
OSRM_URL=https://router.project-osrm.org
ROUTING_ENABLED=true

# Optional: live load feed URL (your broker API)
# LIVE_LOAD_API_URL=https://broker.example.com/api/loads
# LIVE_LOAD_API_KEY=...
# LIVE_LOAD_WEBHOOK_SECRET=...
```

### 3. Start production stack

```bash
make db-migrate-prod
make db-migrate-auth
make db-migrate-import
make db-migrate-live

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d \
  postgres redis qdrant api-gateway profitability-engine market-intelligence \
  agent-core frontend nginx

# Seed loads (first time)
make seed
```

App is at **http://YOUR_SERVER_IP** (port 80).

### 4. HTTPS with Caddy (recommended)

```bash
sudo apt install -y caddy
sudo nano /etc/caddy/Caddyfile
```

```caddy
yourdomain.com {
    reverse_proxy localhost:80
}
```

```bash
sudo systemctl reload caddy
```

Update `.env`:
```env
NEXTAUTH_URL=https://yourdomain.com
```

Rebuild frontend so runtime picks up URL:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build frontend
```

### 5. Cron — sync live loads every 15 min

```bash
crontab -e
```

```
*/15 * * * * cd /path/to/DeadMile-AI- && API_GATEWAY_URL=http://localhost:8010 python3 scripts/sync_live_loads.py >> /var/log/deadmile-sync.log 2>&1
```

---

## Option B — Railway / Render (PaaS)

DeadMile is multi-service (Postgres, Redis, 5+ apps). **VPS + Docker is simpler** than splitting across PaaS.

If using Railway:
1. Deploy **Postgres** + **Redis** plugins
2. Deploy **api-gateway**, **profitability-engine**, **market-intelligence**, **agent-core** as separate services
3. Deploy **frontend** with `NEXT_PUBLIC_API_URL=https://api.yourdomain.com`
4. Set all env vars from `.env.example`

---

## Live load feed

### Manual / webhook POST

```bash
curl -X POST https://yourdomain.com/api/loads/live/upsert \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: your-webhook-secret" \
  -d '{
    "source": "broker_x",
    "loads": [{
      "load_id": "BRK-12345",
      "origin_city": "Dallas",
      "origin_state": "TX",
      "dest_city": "Atlanta",
      "dest_state": "GA",
      "miles": 780,
      "rate": 2400,
      "equipment": "Dry Van"
    }]
  }'
```

### Pull from configured API

Set `LIVE_LOAD_API_URL` in `.env`, then:

```bash
curl -X POST https://yourdomain.com/api/loads/live/sync
# or: python3 scripts/sync_live_loads.py
```

### Check status

```bash
curl https://yourdomain.com/api/loads/live/status
```

---

## Real routing miles

Deadhead to pickup uses **OSRM** driving distance (cached 24h in Redis).

| Variable | Default | Purpose |
|----------|---------|---------|
| `ROUTING_PROVIDER` | `osrm` | `osrm`, `openrouteservice`, or `haversine` |
| `OSRM_URL` | public OSRM | Self-host OSRM for high volume |
| `ROUTING_ENABLED` | `true` | Set `false` to use haversine only |
| `RECALC_LOADED_MILES` | `false` | Set `true` to OSRM origin→dest lane miles |
| `OPENROUTESERVICE_API_KEY` | — | Free tier at openrouteservice.org (truck routing) |

---

## Post-deploy smoke test

```bash
curl https://yourdomain.com/api/health
curl https://yourdomain.com/api/loads/live/status
curl https://yourdomain.com/api/carrier/stats/drivers
```

Browser:
1. Open `/` → hero loads
2. Sign in → `/import` → paste loads → analyze
3. `/compare` → public, no login
4. `/settings` → set fleet costs

---

## Security checklist

- [ ] Change `POSTGRES_PASSWORD` from default
- [ ] Set `NEXTAUTH_SECRET` (32+ chars)
- [ ] Rotate Google OAuth secret if ever exposed
- [ ] Set `API_GATEWAY_KEY` for production API
- [ ] Set `LIVE_LOAD_WEBHOOK_SECRET` for upsert endpoint
- [ ] Do not expose Postgres/Redis ports publicly (prod compose hides them)
- [ ] Add privacy policy if collecting emails publicly

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| White page | Check frontend logs: `docker logs deadmile-frontend` |
| Google login fails | `NEXTAUTH_URL` must match exact domain + HTTPS |
| Import fails | Check `OPENAI_API_KEY` on api-gateway |
| Routing slow | OSRM public rate limit — set self-hosted `OSRM_URL` |
| No dashboard loads | Run `make seed` or POST live loads |

---

**You're production-ready when:** HTTPS works, Import analyzes pasted loads, and Fleet Settings saves your costs.
