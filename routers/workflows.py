import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.plan_limits import get_plan_limit, normalize_plan
from database import get_db
from models.agent import Agent
from models.workflow import Workflow
from models.user import User
from schemas.agent import AGENT_TEMPLATES
from schemas.workflow import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowRunStep,
    WorkflowTemplateResponse,
    WorkflowTemplateStep,
    WorkflowUpdate,
)
from utils.agent_runner import run_agent as call_agent
from utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workflows",
    tags=["Workflows"],
)

WORKFLOW_TEMPLATES = [
    {
        "id": "trend-insight-weekly-report",
        "title": "Trend Research → Insight Analysis → Weekly Report",
        "description": "Research fast-moving developments, synthesize what matters, then package the strongest signals into a report.",
        "steps": [
            {
                "name": "Trend Research Agent",
                "agent_type": "news_monitor",
                "description": "Collect the most important recent developments and signal shifts.",
            },
            {
                "name": "Insight Analysis Agent",
                "agent_type": "data_interpreter",
                "description": "Extract patterns, implications, and the strongest takeaways from the research.",
            },
            {
                "name": "Weekly Report Agent",
                "agent_type": "report_writer",
                "description": "Turn the findings into a polished weekly report with structure and clarity.",
            },
        ],
    },
    {
        "id": "competitor-strategy-action-plan",
        "title": "Competitor Research → Strategy Analysis → Action Plan",
        "description": "Research competitors, analyze what their moves mean, then convert that into next actions for your team.",
        "steps": [
            {
                "name": "Competitor Research Agent",
                "agent_type": "competitor_analyst",
                "description": "Surface changes in positioning, pricing, messaging, and product moves.",
            },
            {
                "name": "Strategy Analysis Agent",
                "agent_type": "data_interpreter",
                "description": "Interpret what the competitor findings mean for your product or go-to-market strategy.",
            },
            {
                "name": "Action Plan Agent",
                "agent_type": "report_writer",
                "description": "Create a concrete plan with recommended actions, priorities, and rationale.",
            },
        ],
    },
    {
        "id": "market-research-startup-summary",
        "title": "Market Research → Startup Idea Generation → Summary Report",
        "description": "Map the market first, generate stronger startup ideas from the signal, and close with a concise summary.",
        "steps": [
            {
                "name": "Market Research Agent",
                "agent_type": "market_researcher",
                "description": "Build a practical market picture using trends, segments, and demand signals.",
            },
            {
                "name": "Startup Idea Generator",
                "agent_type": "content_writer",
                "description": "Generate stronger startup directions based on the market context and gaps.",
            },
            {
                "name": "Summary Report Agent",
                "agent_type": "report_writer",
                "description": "Package the best ideas and reasoning into a clean report.",
            },
        ],
    },
]


def serialize_template(template: dict) -> WorkflowTemplateResponse:
    return WorkflowTemplateResponse(
        id=template["id"],
        title=template["title"],
        description=template["description"],
        steps=[WorkflowTemplateStep(**step) for step in template["steps"]],
    )


def validate_workflow_agents(db: Session, user_id: int, agent_ids: list[int]) -> list[Agent]:
    agents = (
        db.query(Agent)
        .filter(Agent.user_id == user_id, Agent.id.in_(agent_ids))
        .all()
    )
    agent_map = {agent.id: agent for agent in agents}
    missing = [agent_id for agent_id in agent_ids if agent_id not in agent_map]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"One or more workflow agents were not found: {', '.join(str(item) for item in missing)}.",
        )
    return [agent_map[agent_id] for agent_id in agent_ids]


@router.get("/templates", response_model=list[WorkflowTemplateResponse], summary="List built-in workflow templates")
def list_workflow_templates():
    return [serialize_template(template) for template in WORKFLOW_TEMPLATES]


@router.get("/list", response_model=list[WorkflowResponse], summary="List workflows for the current user")
def list_workflows(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workflows = (
        db.query(Workflow)
        .filter(Workflow.user_id == current_user.id)
        .order_by(Workflow.updated_at.desc(), Workflow.id.desc())
        .all()
    )
    return workflows


@router.post("/create", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED, summary="Create a workflow")
def create_workflow(
    workflow: WorkflowCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    validate_workflow_agents(db, current_user.id, workflow.agent_ids)
    new_workflow = Workflow(
        user_id=current_user.id,
        name=workflow.name.strip(),
        description=workflow.description.strip(),
        agent_ids=workflow.agent_ids,
    )
    db.add(new_workflow)
    db.commit()
    db.refresh(new_workflow)
    return new_workflow


@router.post("/templates/{template_id}/apply", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED, summary="Create a workflow from a built-in template")
def apply_workflow_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = next((item for item in WORKFLOW_TEMPLATES if item["id"] == template_id), None)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow template '{template_id}' not found.")

    existing_count = db.query(Agent).filter(Agent.user_id == current_user.id).count()
    normalized_plan = normalize_plan(current_user.plan)
    limit = get_plan_limit(normalized_plan, "max_agents")
    required_agents = len(template["steps"])
    if limit is not None and existing_count + required_agents > limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Applying this template needs {required_agents} agents, but your {normalized_plan} plan allows {limit} total. "
                "Please upgrade or remove some agents first."
            ),
        )

    created_agent_ids: list[int] = []
    for step in template["steps"]:
        agent_type = step["agent_type"]
        base_config = dict(AGENT_TEMPLATES.get(agent_type, AGENT_TEMPLATES["custom"]))
        base_config["agent_type"] = agent_type
        new_agent = Agent(
            user_id=current_user.id,
            name=step["name"],
            description=step["description"],
            config=base_config,
            is_public=False,
        )
        db.add(new_agent)
        db.flush()
        created_agent_ids.append(new_agent.id)

    workflow = Workflow(
        user_id=current_user.id,
        name=template["title"],
        description=template["description"],
        agent_ids=created_agent_ids,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


@router.put("/{workflow_id}", response_model=WorkflowResponse, summary="Update a workflow")
def update_workflow(
    workflow_id: int,
    workflow_data: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.user_id == current_user.id).first()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} not found.")

    if workflow_data.name is not None:
        workflow.name = workflow_data.name.strip()
    if workflow_data.description is not None:
        workflow.description = workflow_data.description.strip()
    if workflow_data.agent_ids is not None:
        validate_workflow_agents(db, current_user.id, workflow_data.agent_ids)
        workflow.agent_ids = workflow_data.agent_ids

    db.commit()
    db.refresh(workflow)
    return workflow


@router.delete("/{workflow_id}", status_code=status.HTTP_200_OK, summary="Delete a workflow")
def delete_workflow(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.user_id == current_user.id).first()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} not found.")

    db.delete(workflow)
    db.commit()
    return {"message": "Workflow deleted successfully."}


@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse, summary="Run a workflow in sequence")
async def run_workflow(
    workflow_id: int,
    request: WorkflowRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.user_id == current_user.id).first()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} not found.")

    ordered_agents = validate_workflow_agents(db, current_user.id, workflow.agent_ids or [])
    previous_output = ""
    steps: list[WorkflowRunStep] = []

    for index, agent in enumerate(ordered_agents, start=1):
        agent_config = dict(agent.config or {})
        prompt = request.input.strip()
        if previous_output:
            prompt = (
                f"Original workflow input:\n{request.input.strip()}\n\n"
                f"Previous step output:\n{previous_output}\n\n"
                "Use the previous step output as context and continue the workflow."
            )

        output = await call_agent(
            user_message=prompt,
            conversation_history=[],
            agent_config=agent_config,
        )
        previous_output = output
        steps.append(
            WorkflowRunStep(
                agent_id=agent.id,
                agent_name=agent.name,
                prompt=prompt,
                output=output,
            )
        )
        logger.info("Workflow step completed: workflow=%s user=%s step=%s agent=%s", workflow_id, current_user.id, index, agent.id)

    return WorkflowRunResponse(
        workflow_id=workflow.id,
        input=request.input.strip(),
        final_output=previous_output,
        steps=steps,
    )
