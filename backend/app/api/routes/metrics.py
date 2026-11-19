from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import SamplerDep
from app.monitoring.prometheus import (
    GPU_MEMORY_USED_BYTES,
    GPU_UTILIZATION_PERCENT,
    HOST_CPU_PERCENT,
    HOST_MEMORY_PERCENT,
    REGISTRY,
)

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics(sampler: SamplerDep) -> Response:
    sample = sampler.latest()
    HOST_CPU_PERCENT.set(sample.cpu_percent)
    HOST_MEMORY_PERCENT.set(sample.memory_percent)
    report = sampler.latest_gpu_report
    for device in report.devices if report else []:
        if device.utilization_percent is not None:
            GPU_UTILIZATION_PERCENT.labels(str(device.index)).set(device.utilization_percent)
        if device.memory_used_bytes is not None:
            GPU_MEMORY_USED_BYTES.labels(str(device.index)).set(device.memory_used_bytes)
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
