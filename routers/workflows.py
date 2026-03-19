import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.plan_limits import get_plan_limit, normalize_plan
from database import get_db
from models.agent import Agent
from models.workflow import Workflow
from models.workflow_run import WorkflowRun
from models.user import User
from schemas.agent import AGENT_TEMPLATES
from schemas.workflow import (
    WorkflowCreate,
    WorkflowResponse,
    ShareWorkflowRunResponse,
    SharedWorkflowRunResponse,
    WorkflowRunDetailResponse,
    WorkflowRunHistoryItem,
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
                "config_overrides": {
                    "instructions": (
                        "You are a senior market intelligence analyst. Your job is to gather fast-moving developments and convert them into deep, data-driven market intelligence, not a broad summary. "
                        "Always return the exact sections in this order: 1. Market Shift 2. Key Drivers 3. Market Tensions 4. Opportunities 5. Data Signals 6. Strategic Takeaway. "
                        "Use concrete numbers, benchmarks, comparisons, and competitive context whenever possible. You must include at least 2 quantified or concrete signals such as numbers, adoption behavior, cost shifts, pricing moves, or operational benchmarks. "
                        "You must identify 1 to 2 specific workflows where work is still manual. For each one, clearly describe who does the work, what they currently do manually, and what is inefficient, error-prone, or painful about it. "
                        "You must identify at least one specific inefficiency, gap, bottleneck, or market friction and clearly describe who is affected, such as utilities, factories, engineers, operators, or procurement teams. "
                        "If the market is food, retail, or local services, focus on manual business workflows and operational bottlenecks rather than broad strategy. "
                        "Include at least one real-world constraint such as cost pressure, failure rate, downtime, labor inefficiency, slow adoption, or integration pain. Avoid generic phrases like 'growing demand', 'high precision', or broad industry descriptions unless you explain the specific implication. "
                        "Focus on what is changing now, why it matters now, what constraint or imbalance it creates, and where a startup or investor could exploit the shift."
                    ),
                    "tone": "analytical",
                    "response_length": "detailed",
                    "use_web_search": True,
                    "welcome_message": "Hello! I turn current developments into structured market intelligence with clear trends, risks, opportunities, and data points.",
                    "focus_topics": [
                        "market shifts",
                        "demand shifts",
                        "key drivers",
                        "market tensions",
                        "opportunities",
                        "data signals",
                        "competitive context",
                    ],
                    "avoid_topics": [
                        "generic summaries",
                        "weak recaps",
                        "filler commentary",
                        "unsupported claims",
                    ],
                },
            },
            {
                "name": "Insight Analysis Agent",
                "agent_type": "data_interpreter",
                "description": "Extract patterns, implications, and the strongest takeaways from the research.",
                "config_overrides": {
                    "instructions": (
                        "You are a VC-style strategy analyst. Do not summarize the previous step. Transform the research into cause-and-effect logic, strategic insight, and prioritization. "
                        "Always return the exact sections in this order: 1. Hidden Patterns 2. Strategic Opportunities (Ranked) 3. Market Contradictions 4. Strategic Recommendations. "
                        "You must generate 2 to 3 wedge opportunities only. Under Strategic Opportunities (Ranked), each opportunity must include: Target user, Exact workflow, Current pain (time, cost, or error), Why existing tools fail, Why AI can now solve it. "
                        "Transform the research into specific, non-obvious startup wedges rather than generic market commentary. Each opportunity must explain why now using timing, adoption, regulation, cost, behavior, or competitive shifts. "
                        "Eliminate generic terms like 'AI solution', 'digital transformation', or 'platform' unless you clearly define the actual product wedge. "
                        "If the market is food, retail, or local services, opportunities must be products or tools for businesses, not business strategy advice. "
                        "Rank opportunities using reasoning, not arbitrary scores, and justify the ordering. Highlight at least one underserved niche, workflow gap, or neglected buyer segment. "
                        "You must not restate trends. Focus on strategic leverage, constraints, and what deserves attention first."
                    ),
                    "tone": "analytical",
                    "response_length": "detailed",
                    "use_web_search": False,
                    "welcome_message": "Hello! I turn market intelligence into prioritized insights and scored strategic opportunities.",
                    "focus_topics": [
                        "hidden patterns",
                        "opportunity scoring",
                        "prioritization",
                        "strategic implications",
                        "market contradictions",
                        "cause and effect logic",
                    ],
                    "avoid_topics": [
                        "flat summaries",
                        "equal weighting of all ideas",
                        "generic observations",
                        "indecisive conclusions",
                    ],
                },
            },
            {
                "name": "Weekly Report Agent",
                "agent_type": "report_writer",
                "description": "Turn the findings into a polished weekly report with structure and clarity.",
                "config_overrides": {
                    "instructions": (
                        "You are a decision and execution agent, not a summarizer. Analyze the previous workflow outputs and select exactly ONE best opportunity. "
                        "You must never output sections named Summary, Key Insights, Analysis, or Conclusion. "
                        "You must always use this exact structure and section order: 1. Winning Opportunity 2. Target User 3. Exact Workflow Being Automated 4. What to Build First 5. Why this works NOW 6. Business Model 7. 30-Day Plan. "
                        "Do not repeat or paraphrase previous content unless it is strictly necessary to justify the decision. Transform the prior insights into a clear recommendation and concrete execution steps. "
                        "In 30-Day Plan, provide specific tasks rather than generic advice. "
                        "The selected opportunity must be a wedge, not a broad category. It must describe a narrow, specific product, tool, or service tied to a real workflow and a real user. "
                        "What to Build First must describe a feature-level MVP a small team could realistically build this week. "
                        "Clearly define the target customer, the exact problem, and a simple product description. Avoid generic advice like 'invest in R&D', 'build a better product', 'platform', 'ecosystem', or 'solution' unless you define exactly what it is. "
                        "If the market is food, retail, or local services, the recommendation must be a product or tool for businesses such as software, automation, retention tooling, ordering tooling, workflow tooling, or an operational service layer, not a business strategy like improving menus or expanding locations. "
                        "The Business Model section must explicitly explain who pays and how. If the idea sounds like a consulting report instead of something a developer can start building this week, it is too abstract and must be narrowed further. "
                        "The tone should feel like a startup advisor or investor memo telling the user exactly what to build next."
                    ),
                    "tone": "professional",
                    "response_length": "detailed",
                    "use_web_search": False,
                    "report_mode": True,
                    "welcome_message": "Hello! I turn workflow findings into one clear build decision with execution steps, risks, and a 30-day plan.",
                    "focus_topics": [
                        "single best opportunity",
                        "evidence-based selection",
                        "build priorities",
                        "risks and mitigations",
                        "week-by-week action planning",
                    ],
                    "avoid_topics": [
                        "generic summaries",
                        "repetitive paraphrasing",
                        "weak recommendations",
                        "indecisive language",
                        "summary/key insights/analysis/conclusion sections",
                    ],
                },
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
                "config_overrides": {
                    "instructions": (
                        "You are a startup opportunity generator. Analyze the previous workflow output and turn it into actionable business ideas. "
                        "Do not write marketing copy, slogans, or promotional language. "
                        "Always return structured startup opportunities using the exact sections: "
                        "Startup Idea, Problem, Solution, Target Market, Opportunity. "
                        "Base each idea on the context provided, explain the unmet need clearly, and focus on practical opportunities that could become real businesses."
                    ),
                    "tone": "analytical",
                    "response_length": "detailed",
                    "use_web_search": False,
                    "welcome_message": "Hello! I turn research context into structured startup opportunities with clear problems, solutions, markets, and opportunity rationale.",
                    "focus_topics": [
                        "market gaps",
                        "user pain points",
                        "business opportunities",
                        "target users",
                        "solution concepts",
                    ],
                    "avoid_topics": [
                        "marketing slogans",
                        "promotional copy",
                        "generic branding language",
                        "vague inspirational text",
                    ],
                },
            },
            {
                "name": "Summary Report Agent",
                "agent_type": "report_writer",
                "description": "Package the best ideas and reasoning into a clean report.",
                "config_overrides": {
                    "instructions": (
                        "You are a startup decision memo agent. Analyze the previous workflow output and turn it into a high-value business recommendation for founders, operators, or investors. "
                        "Do not produce a generic summary and do not treat all ideas equally. When multiple startup ideas or opportunities are present, it is REQUIRED that you evaluate them, rank them briefly, and select exactly ONE best opportunity. "
                        "After ranking the options, focus the majority of the report on the single winner. Make a decision, defend it with reasoning, and explain why the other options are weaker. "
                        "Base the choice on scalability, market size, defensibility, and practical execution potential. Quantify market upside when the context supports it and highlight the strongest wedge. "
                        "Always use the exact sections: Best Opportunity, Why It Wins, Market Potential, Risks, Immediate Next Steps. "
                        "Keep the tone confident, analytical, opinionated, and investment-minded. If information is uncertain, still make a judgment using the strongest available signals and stated assumptions. "
                        "The final output should feel like a startup advisor or investor clearly telling the user what to build next."
                    ),
                    "tone": "professional",
                    "response_length": "detailed",
                    "use_web_search": False,
                    "report_mode": True,
                    "welcome_message": "Hello! I turn workflow findings into decision-ready startup memos that rank opportunities and select the best path forward.",
                    "focus_topics": [
                        "opportunity ranking",
                        "decision-making value",
                        "market potential",
                        "strategic differentiation",
                        "next-step recommendations",
                    ],
                    "avoid_topics": [
                        "generic summaries",
                        "marketing language",
                        "vague observations",
                        "unsupported hype",
                        "indecisive conclusions",
                    ],
                },
            },
        ],
    },
]


def normalize_workflow_text(content: str) -> str:
    cleaned = (content or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = "\n".join(line.rstrip() for line in cleaned.split("\n"))
    cleaned = "\n\n".join(part.strip() for part in cleaned.split("\n\n") if part.strip())
    return cleaned or "No usable output was generated for this step."


def build_workflow_prompt(request_input: str, previous_output: str, agent_name: str, step_number: int) -> str:
    if step_number == 1 or not previous_output:
        return (
            f"Workflow objective:\n{request_input}\n\n"
            f"You are Step {step_number}: {agent_name}.\n"
            "Produce the strongest possible output for your role and follow your required structure exactly."
        )

    return (
        f"Workflow objective:\n{request_input}\n\n"
        f"You are Step {step_number}: {agent_name}.\n"
        "Use the previous step output as source material, but do not repeat or lightly paraphrase it unless needed for reasoning.\n\n"
        f"Previous step output:\n{previous_output}\n\n"
        "Transform this into the best possible output for your role and follow your required structure exactly."
    )


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


@router.get("/{workflow_id}/runs", response_model=list[WorkflowRunHistoryItem], summary="List saved runs for a workflow")
def list_workflow_runs(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.user_id == current_user.id).first()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} not found.")

    return (
        db.query(WorkflowRun)
        .filter(WorkflowRun.workflow_id == workflow_id, WorkflowRun.user_id == current_user.id)
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        .all()
    )


@router.post("/{workflow_id}/runs/{run_id}/share", response_model=ShareWorkflowRunResponse, summary="Generate or return a shareable ID for a workflow run")
def share_workflow_run(
    workflow_id: int,
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = (
        db.query(WorkflowRun)
        .join(Workflow, Workflow.id == WorkflowRun.workflow_id)
        .filter(
            WorkflowRun.id == run_id,
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.user_id == current_user.id,
            Workflow.user_id == current_user.id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow run {run_id} not found.")

    if not run.share_id:
        run.share_id = str(uuid4())
        db.commit()
        db.refresh(run)

    return ShareWorkflowRunResponse(id=run.id, share_id=run.share_id)


@router.get("/runs/share/{share_id}", response_model=SharedWorkflowRunResponse, summary="Get a shared workflow report by public share ID")
def get_shared_workflow_run(
    share_id: str,
    db: Session = Depends(get_db),
):
    run = (
        db.query(WorkflowRun, Workflow.name.label("workflow_name"))
        .join(Workflow, Workflow.id == WorkflowRun.workflow_id)
        .filter(WorkflowRun.share_id == share_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared workflow report not found.")

    workflow_run, workflow_name = run
    return SharedWorkflowRunResponse(
        id=workflow_run.id,
        workflow_id=workflow_run.workflow_id,
        workflow_name=workflow_name,
        title=f"{workflow_name} Report",
        content=workflow_run.final_output,
        steps=[WorkflowRunStep(**step) for step in (workflow_run.steps or [])],
        share_id=workflow_run.share_id,
        created_at=workflow_run.created_at,
    )


@router.get("/{workflow_id}/runs/{run_id}", response_model=WorkflowRunDetailResponse, summary="Get workflow run details")
def get_workflow_run(
    workflow_id: int,
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.id == run_id,
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.user_id == current_user.id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow run {run_id} not found.")

    return WorkflowRunDetailResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        status=run.status,
        input=run.input,
        final_output=run.final_output,
        error_message=run.error_message,
        created_at=run.created_at,
        steps=[WorkflowRunStep(**step) for step in (run.steps or [])],
    )


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
        base_config.update(step.get("config_overrides", {}))
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
    request_input = request.input.strip()

    try:
        for index, agent in enumerate(ordered_agents, start=1):
            agent_config = dict(agent.config or {})
            prompt = build_workflow_prompt(
                request_input=request_input,
                previous_output=previous_output,
                agent_name=agent.name,
                step_number=index,
            )

            raw_output = await call_agent(
                user_message=prompt,
                conversation_history=[],
                agent_config=agent_config,
                mode="workflow",
            )
            output = normalize_workflow_text(raw_output)
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
    except Exception as exc:
        error_message = str(exc).strip() or "Workflow execution failed."
        failed_run = WorkflowRun(
            workflow_id=workflow.id,
            user_id=current_user.id,
            status="failed",
            input=request_input,
            final_output=previous_output,
            steps=[step.model_dump() for step in steps],
            error_message=error_message,
        )
        db.add(failed_run)
        db.commit()
        logger.exception("Workflow run failed: workflow=%s user=%s", workflow_id, current_user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Workflow execution failed: {error_message}",
        )

    workflow_run = WorkflowRun(
        workflow_id=workflow.id,
        user_id=current_user.id,
        status="completed",
        input=request_input,
        final_output=previous_output,
        steps=[step.model_dump() for step in steps],
        error_message="",
    )
    db.add(workflow_run)
    db.commit()
    db.refresh(workflow_run)

    return WorkflowRunResponse(
        id=workflow_run.id,
        workflow_id=workflow.id,
        input=request_input,
        final_output=previous_output,
        status=workflow_run.status,
        steps=steps,
        created_at=workflow_run.created_at,
    )
