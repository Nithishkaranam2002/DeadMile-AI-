# DeadMile AI — Demo Script (5 minutes)

## Setup Before Demo

1. `make setup` — starts all 19 containers, seeds data, trains models
2. Open http://localhost:3000 in Chrome (dark mode preferred)
3. Open http://localhost:3001 in second tab (Grafana — optional, for Q&A)
4. Open http://localhost:8080 in third tab (Temporal UI — optional, for Q&A)

## Demo Flow

### Act 1: The Problem (30 seconds)

"95% of US trucking companies run fewer than 10 trucks on 3-6% margins.
Their biggest controllable cost? Empty miles — 15-20% of all truck miles earn nothing.
A driver finishes a delivery in Reno and has no idea what to haul next.
They pick a load that pays $3,000 but drops them in a dead market where they sit empty for 2 days.
Meanwhile, a $2,200 load to Atlanta would have netted them more because Atlanta has 10x the outbound loads."

### Act 2: The Solution (30 seconds)

"DeadMile AI is an AI agent that recommends the most PROFITABLE loads — not the highest paying ones.
It calculates true net profit after fuel, driver pay, insurance, tolls, and deadhead.
And critically, it scores where each load DROPS YOU — because ending up in a dead market costs more than the load pays."

### Act 3: Live Demo (3 minutes)

**Step 1: Enter location** (20 sec)

- Select "Dallas, TX" from location dropdown
- Equipment: "Dry Van"
- Max deadhead: 250 miles
- Click "Find My Best Loads"

**Step 2: Watch the agent think** (40 sec)

- Point out SSE streaming: "Watch the agent work in real-time"
- Agent searches loads → calculates P&L → checks markets → ranks
- Load cards appear with full cost breakdown
- Arcs animate on map showing recommended routes

**Step 3: Explain the math** (30 sec)

- Click "View Details" on top load
- Walk through the P&L: "Revenue $2,275, minus fuel $287, driver $448, insurance, tolls...
  NET profit: $892. That's a 39% margin."
- Point to destination market: "Drops in Chicago — Hot market, score 87.
  Plenty of outbound loads, estimated 25 miles deadhead to next pickup."

**Step 4: Compare loads** (20 sec)

- Show Load #1 vs Load #3 side by side
- "Load #3 pays $500 more gross, but it drops in El Paso — Dead market, score 12.
  After factoring in 180 miles of deadhead to the next load, Load #1 nets $340 MORE."

**Step 5: Multi-hop chain** (30 sec)

- Type: "Optimize my week — find me a 3-load chain"
- Show the chain: Dallas → Chicago → Atlanta → Dallas
- "3 loads, 5 days, $2,847 net. Weekly projection: $3,990."

**Step 6: Markets dashboard** (20 sec)

- Click "Markets" tab
- Show top 10 leaderboard: "Atlanta, Chicago, Dallas are the top markets"
- Toggle heatmap: "Green = hot, Red = dead. You can see the freight corridors."

**Step 7: What-If** (10 sec)

- Click "Simulator"
- Drag pin to Memphis: "What if I based my truck here? 34 available loads, $712 avg net."

### Act 4: Architecture (30 seconds)

"Under the hood: 7 microservices, 19 Docker containers.
LangGraph agent with 8 tools. PostGIS for spatial queries.
Kafka for load ingestion. Temporal for chain optimization.
XGBoost for rate prediction. Qdrant for semantic search.
Langfuse for observability — I can show you exactly WHY the agent picked each load."
(Show Grafana or Temporal UI if time permits)

### Act 5: Close (30 seconds)

"Small carriers lose $15,000-30,000 per truck per year to empty miles.
DeadMile AI turns that into profit by making every load decision data-driven.
We're using OpenAI GPT-4o-mini for inference, Tavily for real-time fuel data,
and the entire system runs on Docker Compose — one command to deploy."

## Q&A Prep

- **"How do you handle real-time data?"** → Tavily for fuel prices, Kafka for load ingestion
- **"How does the agent decide?"** → Show Langfuse trace
- **"Is this production-ready?"** → 19 containers, health checks, Prometheus monitoring, Grafana dashboards
- **"What about the ML models?"** → XGBoost rate predictor, K-Means market clustering
- **"How many loads can it handle?"** → PostGIS spatial indexes, Redis caching, batch processing — tested with 3000+ loads
- **"Does it learn?"** → Mem0 remembers driver preferences across sessions
