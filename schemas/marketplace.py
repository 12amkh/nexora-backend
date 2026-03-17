from datetime import datetime
from typing import Any

from pydantic import BaseModel

from schemas.agent import AgentResponse


class MarketplaceItemResponse(BaseModel):
    id: int
    owner_user_id: int
    source_agent_id: int
    title: str
    description: str
    agent_type: str
    config: dict[str, Any]
    is_published: bool
    created_at: datetime
    updated_at: datetime
    owner_name: str


class MarketplacePublishResponse(MarketplaceItemResponse):
    pass


class MarketplaceImportResponse(BaseModel):
    marketplace_item_id: int
    agent: AgentResponse
