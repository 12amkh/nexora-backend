import re
from typing import Iterable

from sqlalchemy.orm import Session

from models.agent_memory import AgentMemory

MAX_MEMORY_ITEMS = 8
MAX_MEMORY_CHARS = 4000
MAX_ENTRY_CHARS = 520


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _trim_text(value: str, limit: int) -> str:
    normalized = _normalize_text(value)
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _extract_section(content: str, section_name: str) -> str:
    pattern = rf"(?:^|\n)##?\s+{re.escape(section_name)}\s*\n(.*?)(?=\n##?\s+|\Z)"
    match = re.search(pattern, content, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _trim_text(match.group(1), 180)


def _extract_fallback_insights(content: str) -> str:
    paragraphs = [part.strip() for part in content.split("\n\n") if part.strip()]
    if not paragraphs:
        return ""
    return _trim_text(paragraphs[0], 180)


def _build_memory_entry(user_message: str, ai_response: str) -> str:
    request_summary = _trim_text(user_message, 120)
    summary = _extract_section(ai_response, "Summary")
    key_insights = _extract_section(ai_response, "Key Insights")
    conclusion = _extract_section(ai_response, "Conclusion")

    parts = [f"Request: {request_summary}"]
    if summary:
        parts.append(f"Summary: {summary}")
    if key_insights:
        parts.append(f"Insights: {key_insights}")
    if conclusion:
        parts.append(f"Conclusion: {conclusion}")

    if len(parts) == 1:
        fallback = _extract_fallback_insights(ai_response)
        if fallback:
            parts.append(f"Insight: {fallback}")

    return _trim_text(" | ".join(parts), MAX_ENTRY_CHARS)


def _split_memory_items(summary: str) -> list[str]:
    if not summary.strip():
        return []
    return [line[2:].strip() for line in summary.splitlines() if line.strip().startswith("- ")]


def _join_memory_items(items: Iterable[str]) -> str:
    joined = "\n".join(f"- {item}" for item in items if item.strip())
    return joined[:MAX_MEMORY_CHARS].rstrip()


def get_agent_memory_summary(db: Session, agent_id: int, user_id: int) -> str:
    memory = db.query(AgentMemory).filter(
        AgentMemory.agent_id == agent_id,
        AgentMemory.user_id == user_id,
    ).first()
    return memory.summary.strip() if memory and memory.summary else ""


def update_agent_memory(db: Session, agent_id: int, user_id: int, user_message: str, ai_response: str) -> AgentMemory | None:
    entry = _build_memory_entry(user_message, ai_response)
    if not entry:
        return None

    memory = db.query(AgentMemory).filter(
        AgentMemory.agent_id == agent_id,
        AgentMemory.user_id == user_id,
    ).first()

    existing_items = _split_memory_items(memory.summary if memory else "")
    next_items = [entry]
    next_items.extend(item for item in existing_items if item != entry)
    next_summary = _join_memory_items(next_items[:MAX_MEMORY_ITEMS])

    if memory:
        memory.summary = next_summary
    else:
        memory = AgentMemory(
            agent_id=agent_id,
            user_id=user_id,
            summary=next_summary,
        )
        db.add(memory)

    db.commit()
    db.refresh(memory)
    return memory
