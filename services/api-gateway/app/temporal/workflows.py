"""Load chain optimization Temporal workflow."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        calculate_profit_activity,
        score_chains_activity,
        search_loads_activity,
    )
    from app.temporal.models import ChainParams, ChainResult


def _build_chain(hops: list[tuple[dict, dict]], params: ChainParams) -> dict:
    loads = []
    for load, profit in hops:
        merged = {**profit, "dest_lat": load.get("dest_lat"), "dest_lng": load.get("dest_lng")}
        loads.append(merged)
    return {
        "loads": loads,
        "cumulative_net_profit": round(sum(l.get("net_profit", 0) for l in loads), 2),
        "total_miles": round(sum(l.get("total_miles", 0) for l in loads), 1),
        "estimated_days": min(params.days, params.num_hops),
        "hops": [
            {
                "load_id": l.get("load_id"),
                "origin": l.get("origin"),
                "destination": l.get("destination"),
                "net_profit": l.get("net_profit"),
                "deadhead_miles": l.get("deadhead_to_pickup", 0),
                "equipment": l.get("equipment", params.equipment),
            }
            for l in loads
        ],
    }


@workflow.defn
class LoadChainWorkflow:
    @workflow.run
    async def run(self, params: ChainParams) -> ChainResult:
        retry = RetryPolicy(maximum_attempts=3)

        initial_loads = await workflow.execute_activity(
            search_loads_activity,
            args=[params.start_lat, params.start_lng, params.equipment, 250],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )

        scored_loads: list[dict[str, Any]] = []
        for load in initial_loads[:10]:
            profit = await workflow.execute_activity(
                calculate_profit_activity,
                args=[load["load_id"], params.start_lat, params.start_lng],
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=retry,
            )
            scored_loads.append({**load, "profit": profit})

        chains: list[dict] = []
        top_k = sorted(scored_loads, key=lambda x: x["profit"].get("composite_score", 0), reverse=True)[:5]

        for hop1 in top_k:
            hop1_profit = hop1["profit"]
            hop2_loads = await workflow.execute_activity(
                search_loads_activity,
                args=[hop1.get("dest_lat", params.start_lat), hop1.get("dest_lng", params.start_lng), params.equipment, 200],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry,
            )

            for hop2 in hop2_loads[:5]:
                hop2_profit = await workflow.execute_activity(
                    calculate_profit_activity,
                    args=[hop2["load_id"], hop1.get("dest_lat", params.start_lat), hop1.get("dest_lng", params.start_lng)],
                    start_to_close_timeout=timedelta(seconds=15),
                    retry_policy=retry,
                )

                if params.num_hops >= 3:
                    hop3_loads = await workflow.execute_activity(
                        search_loads_activity,
                        args=[hop2.get("dest_lat", 0), hop2.get("dest_lng", 0), params.equipment, 200],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=retry,
                    )
                    for hop3 in hop3_loads[:3]:
                        hop3_profit = await workflow.execute_activity(
                            calculate_profit_activity,
                            args=[hop3["load_id"], hop2.get("dest_lat", 0), hop2.get("dest_lng", 0)],
                            start_to_close_timeout=timedelta(seconds=15),
                            retry_policy=retry,
                        )
                        chains.append(_build_chain([(hop1, hop1_profit), (hop2, hop2_profit), (hop3, hop3_profit)], params))
                else:
                    chains.append(_build_chain([(hop1, hop1_profit), (hop2, hop2_profit)], params))

        scored_chains = await workflow.execute_activity(
            score_chains_activity,
            args=[chains, params.start_lat, params.start_lng, params.prefer_return_to_start],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )

        return ChainResult(chains=scored_chains[:3], total_evaluated=len(chains))
