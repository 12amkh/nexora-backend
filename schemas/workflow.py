from datetime import datetime

from pydantic import BaseModel, field_validator


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    agent_ids: list[int]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str):
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workflow name cannot be empty.")
        if len(normalized) > 120:
            raise ValueError("Workflow name cannot exceed 120 characters.")
        return normalized

    @field_validator("agent_ids")
    @classmethod
    def validate_agent_ids(cls, value: list[int]):
        cleaned = [int(agent_id) for agent_id in value if int(agent_id) > 0]
        if not cleaned:
            raise ValueError("Add at least one agent to the workflow.")
        return cleaned


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    agent_ids: list[int] | None = None


class WorkflowResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str
    agent_ids: list[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunRequest(BaseModel):
    input: str

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str):
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workflow input cannot be empty.")
        if len(normalized) > 4000:
            raise ValueError("Workflow input cannot exceed 4000 characters.")
        return normalized


class WorkflowRunStep(BaseModel):
    agent_id: int
    agent_name: str
    prompt: str
    output: str


class WorkflowRunResponse(BaseModel):
    id: int | None = None
    workflow_id: int
    input: str
    final_output: str
    status: str = "completed"
    steps: list[WorkflowRunStep]
    created_at: datetime | None = None


class WorkflowRunHistoryItem(BaseModel):
    id: int
    workflow_id: int
    status: str
    input: str
    final_output: str
    error_message: str
    share_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunDetailResponse(WorkflowRunHistoryItem):
    steps: list[WorkflowRunStep]


class ShareWorkflowRunResponse(BaseModel):
    id: int
    share_id: str


class SharedWorkflowRunResponse(BaseModel):
    id: int
    workflow_id: int
    workflow_name: str
    title: str
    content: str
    steps: list[WorkflowRunStep]
    share_id: str
    created_at: datetime


class WorkflowTemplateStep(BaseModel):
    name: str
    agent_type: str
    description: str


class WorkflowTemplateResponse(BaseModel):
    id: str
    title: str
    description: str
    steps: list[WorkflowTemplateStep]
