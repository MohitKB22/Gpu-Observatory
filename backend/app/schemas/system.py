from pydantic import BaseModel

from app.schemas.common import DataSource


class SystemInfo(BaseModel):
    version: str
    environment: str
    demo_mode: bool
    default_data_source: DataSource
    public_demo: bool
    public_demo_source_url: str | None
    # Input limits the Playground should enforce (tighter in a public demo).
    max_prompt_chars: int
    max_tokens: int


class HealthResponse(BaseModel):
    status: str
    database: str
