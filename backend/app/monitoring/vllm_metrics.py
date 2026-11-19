"""Scrape a vLLM server's Prometheus endpoint for queue and KV-cache figures.

GPU inference usually runs on a separate machine. vLLM exposes its own scheduler metrics at
`<server>/metrics`, which lets the Infrastructure page show real load for remote GPU servers
without an agent on that machine.
"""

from dataclasses import dataclass

import httpx
from prometheus_client.parser import text_string_to_metric_families

from app.providers.http import join_url
from app.providers.vllm import server_root_url

# Metric names changed across vLLM releases (gpu_cache_usage_perc -> kv_cache_usage_perc).
_RUNNING = ("vllm:num_requests_running",)
_WAITING = ("vllm:num_requests_waiting",)
_KV_CACHE = ("vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc")


@dataclass(frozen=True)
class VLLMServerMetrics:
    reachable: bool
    requests_running: float | None = None
    requests_waiting: float | None = None
    kv_cache_usage_percent: float | None = None
    error: str | None = None


async def fetch_vllm_metrics(
    client: httpx.AsyncClient, endpoint_url: str, api_key: str | None, timeout: float
) -> VLLMServerMetrics:
    url = join_url(server_root_url(endpoint_url), "metrics")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = await client.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return VLLMServerMetrics(reachable=False, error=f"/metrics returned HTTP {exc.response.status_code}")
    except httpx.HTTPError as exc:
        return VLLMServerMetrics(reachable=False, error=f"/metrics unreachable ({type(exc).__name__})")
    return parse_vllm_metrics(response.text)


def parse_vllm_metrics(text: str) -> VLLMServerMetrics:
    totals: dict[str, float] = {}
    try:
        for family in text_string_to_metric_families(text):
            for sample in family.samples:
                totals[sample.name] = totals.get(sample.name, 0.0) + sample.value
    except ValueError as exc:
        return VLLMServerMetrics(reachable=True, error=f"Could not parse /metrics output: {exc}")

    kv_cache = _first_present(totals, _KV_CACHE)
    return VLLMServerMetrics(
        reachable=True,
        requests_running=_first_present(totals, _RUNNING),
        requests_waiting=_first_present(totals, _WAITING),
        # vLLM reports a 0-1 fraction despite the "perc" suffix.
        kv_cache_usage_percent=kv_cache * 100 if kv_cache is not None else None,
    )


def _first_present(totals: dict[str, float], names: tuple[str, ...]) -> float | None:
    for name in names:
        if name in totals:
            return totals[name]
    return None
