# Buildathon 2026 Submission Checklist

## Project Info

- **Project Name:** DeadMile AI
- **Problem Statement:** Statement 6 — Trucking Load Optimization Agent
- **Team:** Nithish Karanam

## Links

- **GitHub:** https://github.com/Nithishkaranam2002/DeadMile-AI-
- **Live Demo:** [if deployed to DigitalOcean]
- **Demo Video:** [record 5-min walkthrough using DEMO.md]

## Sponsor Integrations

- [x] OpenAI GPT-4o-mini — Primary LLM inference (LiteLLM-compatible alternates supported)
- [x] Tavily — Real-time fuel prices and market data

## Technical Highlights

- [x] 7 microservices, 19 Docker containers
- [x] LangGraph ReAct agent with 8 specialized tools
- [x] PostGIS spatial queries for load search
- [x] Full net profitability calculation (not just gross rate)
- [x] Destination market scoring (Hot → Dead)
- [x] Multi-hop load chain optimization (Temporal workflows)
- [x] XGBoost rate prediction model
- [x] K-Means market clustering
- [x] Qdrant semantic vector search
- [x] Mem0 driver preference memory
- [x] SSE real-time agent streaming
- [x] Deck.gl GPU-accelerated maps with heatmaps
- [x] Voice input (Web Speech API)
- [x] What-If simulator
- [x] Langfuse LLM observability
- [x] Prometheus + Grafana monitoring
- [x] Redis caching layer
- [x] Apache Kafka load ingestion pipeline

## Data

- 13 text files + 12 PDF broker sheets = ~2,500+ synthetic loads
- Covers major US freight markets
- 3 different load data formats parsed

## How to Run

```bash
git clone https://github.com/Nithishkaranam2002/DeadMile-AI-.git
cd DeadMile-AI-
cp .env.example .env
# Add OPENAI_API_KEY, TAVILY_API_KEY, and NEXT_PUBLIC_MAPBOX_TOKEN (or MAPTILER_KEY)
make setup
# Open http://localhost:3000
```

## Demo Script

See [DEMO.md](./DEMO.md) for the full 5-minute walkthrough.
