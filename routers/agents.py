# routers/agents.py

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models.user import User
from models.agent import Agent
from models.conversation import Conversation
from schemas.agent import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    AgentTemplateResponse,
    AGENT_TEMPLATES,
    AGENT_TYPE_DESCRIPTIONS,
    AgentType,
)
from services.usage_service import UsageService
from utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents",
    tags=["Agents"]
)

# ── Plan Limits ───────────────────────────────────────────────────────────────────
# free     → 3 agents   ($0/month)   — hook them in
# starter  → 5 agents   ($19/month)  — entry paid tier
# pro      → 20 agents  ($49/month)  — main revenue tier
# business → 100 agents ($149/month) — teams and power users
# when Stripe is added, current_user.plan updates automatically on payment
PLAN_AGENT_LIMITS = {
    "free":     3,
    "starter":  5,
    "pro":      20,
    "business": 100,
}


def get_agent_limit(plan: str) -> int:
    return PLAN_AGENT_LIMITS.get(plan, 3)  # default to free if unknown plan


# ── List Agent Types ──────────────────────────────────────────────────────────────
@router.get(
    "/types",
    summary="Get all available agent types and their descriptions",
)
def list_agent_types():
    return [
        {
            "agent_type":  agent_type,
            "description": AGENT_TYPE_DESCRIPTIONS.get(agent_type, ""),
        }
        for agent_type in AGENT_TEMPLATES.keys()
    ]


# ── Get Template for Agent Type ───────────────────────────────────────────────────
@router.get(
    "/templates/{agent_type}",
    response_model=AgentTemplateResponse,
    summary="Get the default config template for a specific agent type",
)
def get_agent_template(agent_type: AgentType):
    template = AGENT_TEMPLATES.get(agent_type)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No template found for agent type '{agent_type}'.",
        )

    return AgentTemplateResponse(
        agent_type=agent_type,
        template=template,
        description=AGENT_TYPE_DESCRIPTIONS.get(agent_type, ""),
    )


# ── Create Agent ──────────────────────────────────────────────────────────────────
@router.post(
    "/create",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new AI agent",
)
def create_agent(
    agent: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing_count = db.query(Agent).filter(
        Agent.user_id == current_user.id
    ).count()

    limit = get_agent_limit(current_user.plan)

    if existing_count >= limit:
        logger.warning(
            f"User {current_user.id} hit agent limit "
            f"({existing_count}/{limit}) on plan '{current_user.plan}'"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"You have reached the maximum number of agents ({limit}) "
                f"for your {current_user.plan} plan. "
                f"Please upgrade to create more agents."
            ),
        )

    base_config = AGENT_TEMPLATES.get(agent.agent_type, AGENT_TEMPLATES["custom"]).copy()
    if agent.config:
        base_config.update(agent.config)
    base_config["agent_type"] = agent.agent_type

    new_agent = Agent(
        name=agent.name.strip(),
        description=agent.description.strip() if agent.description else "",
        config=base_config,
        user_id=current_user.id,
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)

    logger.info(
        f"Agent created: '{new_agent.name}' type='{agent.agent_type}' "
        f"(id={new_agent.id}) by user {current_user.id}"
    )
    UsageService.record_agent_created(db, current_user.id, new_agent.id)
    return new_agent


# ── List Agents ───────────────────────────────────────────────────────────────────
@router.get(
    "/list",
    response_model=List[AgentResponse],
    summary="List all agents for the current user (paginated)",
)
def list_agents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip:  int = Query(default=0,  ge=0,  description="Number of agents to skip"),
    limit: int = Query(default=10, ge=1, le=100, description="Max agents to return"),
):
    agents = db.query(Agent).filter(
        Agent.user_id == current_user.id
    ).offset(skip).limit(limit).all()

    logger.info(f"User {current_user.id} listed agents (skip={skip}, limit={limit}, returned={len(agents)})")
    return agents


# ── Get One Agent ─────────────────────────────────────────────────────────────────
@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get a single agent by ID",
)
def get_agent(
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.user_id == current_user.id,
    ).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with id {agent_id} not found.",
        )
    return agent


# ── Update Agent ──────────────────────────────────────────────────────────────────
@router.put(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Update an agent's name, description, or config",
)
def update_agent(
    agent_id: int,
    agent_data: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.user_id == current_user.id,
    ).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with id {agent_id} not found.",
        )

    if agent_data.name is not None:
        agent.name = agent_data.name.strip()
    if agent_data.description is not None:
        agent.description = agent_data.description.strip()
    if agent_data.config is not None:
        existing_config = agent.config or {}
        existing_config.update(agent_data.config)
        agent.config = existing_config

    db.commit()
    db.refresh(agent)

    logger.info(f"Agent updated: id={agent_id} by user {current_user.id}")
    return agent


# ── Delete Agent ──────────────────────────────────────────────────────────────────
@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete an agent and all its conversation history",
)
def delete_agent(
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.user_id == current_user.id,
    ).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with id {agent_id} not found.",
        )

    agent_name = agent.name

    deleted_conversations = db.query(Conversation).filter(
        Conversation.agent_id == agent_id
    ).delete()

    db.delete(agent)
    db.commit()

    logger.info(
        f"Agent deleted: '{agent_name}' id={agent_id} by user {current_user.id} "
        f"({deleted_conversations} conversations also removed)"
    )

    return {"message": f"Agent '{agent_name}' and all its history deleted successfully."}
