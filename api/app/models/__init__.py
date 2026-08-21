"""SQLAlchemy models. Importing this package registers all tables on Base."""

from app.models.analytics import (
    Alert,
    AlertRule,
    Anomaly,
    Diagnosis,
    PricingProfile,
    Workload,
)
from app.models.auth import ApiKey, AuditLog, RefreshToken, User
from app.models.inference import (
    BatchMetric,
    Deployment,
    InferenceMetric,
    InferenceRequest,
    MLModel,
)
from app.models.telemetry import Gpu, GpuMetric, GpuProcess, SystemMetric

__all__ = [
    "Alert",
    "AlertRule",
    "Anomaly",
    "ApiKey",
    "AuditLog",
    "BatchMetric",
    "Deployment",
    "Diagnosis",
    "Gpu",
    "GpuMetric",
    "GpuProcess",
    "InferenceMetric",
    "InferenceRequest",
    "MLModel",
    "PricingProfile",
    "RefreshToken",
    "SystemMetric",
    "User",
    "Workload",
]
