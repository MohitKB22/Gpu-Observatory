from pydantic import BaseModel

from app.schemas.common import DataSource


class SystemInfo(BaseModel):
    version: str
    environment: str
    demo_mode: bool
    default_data_source: DataSource


class HealthResponse(BaseModel):
    status: str
    database: str
