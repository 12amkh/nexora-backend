import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.agent import Agent
from models.workflow import Workflow
from models.user import User
from schemas.workflow import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowRunStep,
    WorkflowUpdate,
)
from utils.agent_runner import run_agent as call_agent
from utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workflows",
    tags=["Workflows"],
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
