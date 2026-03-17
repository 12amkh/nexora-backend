import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.plan_limits import get_plan_limit, normalize_plan
from database import get_db
from models.agent import Agent
from models.marketplace_item import MarketplaceItem
from models.user import User
from schemas.marketplace import MarketplaceImportResponse, MarketplaceItemResponse, MarketplacePublishResponse
from services.usage_service import UsageService
from utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/marketplace",
    tags=["Marketplace"],
)


def serialize_marketplace_item(item: MarketplaceItem) -> MarketplaceItemResponse:
    return MarketplaceItemResponse(
        id=item.id,
        owner_user_id=item.owner_user_id,
        source_agent_id=item.source_agent_id,
        title=item.title,
        description=item.description,
        agent_type=item.agent_type,
        config=item.config or {},
        is_published=item.is_published,
        created_at=item.created_at,
        updated_at=item.updated_at,
        owner_name=item.owner.name if item.owner else "Nexora Creator",
    )


@router.get(
    "/items",
    response_model=list[MarketplaceItemResponse],
    summary="List public marketplace items",
)
def list_marketplace_items(
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, description="Optional text search for marketplace items"),
):
    query = (
        db.query(MarketplaceItem)
        .filter(MarketplaceItem.is_published.is_(True))
        .order_by(MarketplaceItem.updated_at.desc(), MarketplaceItem.id.desc())
    )

    if search:
        normalized = f"%{search.strip()}%"
        query = query.filter(
            (MarketplaceItem.title.ilike(normalized))
            | (MarketplaceItem.description.ilike(normalized))
            | (MarketplaceItem.agent_type.ilike(normalized))
        )

    items = query.all()
    logger.info("Marketplace items listed: search=%s returned=%s", search, len(items))
    return [serialize_marketplace_item(item) for item in items]


@router.get(
    "/agents/{agent_id}",
    response_model=MarketplaceItemResponse,
    summary="Get the marketplace listing for the current user's agent",
)
def get_agent_marketplace_item(
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(MarketplaceItem)
        .join(Agent, Agent.id == MarketplaceItem.source_agent_id)
        .filter(MarketplaceItem.source_agent_id == agent_id, Agent.user_id == current_user.id)
        .first()
    )

    if not item:
      raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND,
          detail=f"No marketplace listing found for agent {agent_id}.",
      )

    return serialize_marketplace_item(item)


@router.post(
    "/agents/{agent_id}/publish",
    response_model=MarketplacePublishResponse,
    summary="Publish or update an agent in the marketplace",
)
def publish_agent_to_marketplace(
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with id {agent_id} not found.",
        )

    item = db.query(MarketplaceItem).filter(MarketplaceItem.source_agent_id == agent_id).first()
    if not item:
        item = MarketplaceItem(
            owner_user_id=current_user.id,
            source_agent_id=agent.id,
            title=agent.name,
            description=agent.description or "Marketplace-ready Nexora agent template.",
            agent_type=(agent.config or {}).get("agent_type", "custom"),
            config=dict(agent.config or {}),
            is_published=True,
        )
        db.add(item)
    else:
        item.title = agent.name
        item.description = agent.description or "Marketplace-ready Nexora agent template."
        item.agent_type = (agent.config or {}).get("agent_type", "custom")
        item.config = dict(agent.config or {})
        item.is_published = True

    db.commit()
    db.refresh(item)
    logger.info("Marketplace item published: agent=%s user=%s item=%s", agent_id, current_user.id, item.id)
    return serialize_marketplace_item(item)


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_200_OK,
    summary="Unpublish a marketplace item",
)
def unpublish_marketplace_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(MarketplaceItem).filter(MarketplaceItem.id == item_id, MarketplaceItem.owner_user_id == current_user.id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marketplace item {item_id} not found.",
        )

    db.delete(item)
    db.commit()
    logger.info("Marketplace item removed: item=%s user=%s", item_id, current_user.id)
    return {"message": "Marketplace item unpublished successfully."}


@router.post(
    "/items/{item_id}/import",
    response_model=MarketplaceImportResponse,
    summary="Import a marketplace agent template into the current user's account",
)
def import_marketplace_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(MarketplaceItem).filter(MarketplaceItem.id == item_id, MarketplaceItem.is_published.is_(True)).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marketplace item {item_id} not found.",
        )

    existing_count = db.query(Agent).filter(Agent.user_id == current_user.id).count()
    normalized_plan = normalize_plan(current_user.plan)
    limit = get_plan_limit(normalized_plan, "max_agents")
    if limit is not None and existing_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"You have reached the maximum number of agents ({limit}) "
                f"for your {normalized_plan} plan. Please upgrade to import more agents."
            ),
        )

    new_agent = Agent(
        name=f"{item.title} Copy",
        description=item.description,
        config=dict(item.config or {}),
        user_id=current_user.id,
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    UsageService.record_agent_created(db, current_user.id, new_agent.id)

    logger.info("Marketplace item imported: item=%s user=%s new_agent=%s", item_id, current_user.id, new_agent.id)
    return MarketplaceImportResponse(marketplace_item_id=item.id, agent=new_agent)
