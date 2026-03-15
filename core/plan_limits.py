from __future__ import annotations

from typing import Final, Literal, TypedDict

PlanName = Literal["free", "starter", "pro", "business", "enterprise"]


class PlanLimits(TypedDict):
    max_agents: int | None
    max_schedules: int | None
    max_messages_per_month: int | None


PLAN_LIMITS: Final[dict[PlanName, PlanLimits]] = {
    "free": {
        "max_agents": 3,
        "max_schedules": 0,
        "max_messages_per_month": 100,
    },
    "starter": {
        "max_agents": 5,
        "max_schedules": 3,
        "max_messages_per_month": 5000,
    },
    "pro": {
        "max_agents": 20,
        "max_schedules": 10,
        "max_messages_per_month": 50000,
    },
    "business": {
        "max_agents": 100,
        "max_schedules": 50,
        "max_messages_per_month": 500000,
    },
    "enterprise": {
        "max_agents": None,
        "max_schedules": None,
        "max_messages_per_month": None,
    },
}

DEFAULT_PLAN: Final[PlanName] = "free"


def normalize_plan(plan: str | None) -> str:
    # Normalize user input and safely fall back to the free tier.
    normalized = (plan or DEFAULT_PLAN).strip().lower()
    return normalized if normalized in PLAN_LIMITS else DEFAULT_PLAN


def get_plan_limits(plan: str | None) -> dict:
    # Return a copy so callers cannot mutate the shared defaults.
    return dict(PLAN_LIMITS[normalize_plan(plan)])


def get_plan_limit(plan: str | None, key: str):
    # Unknown keys safely return the free-plan value when available.
    limits = get_plan_limits(plan)
    if key in limits:
        return limits[key]
    return PLAN_LIMITS[DEFAULT_PLAN].get(key)


def is_unlimited(plan: str | None, key: str) -> bool:
    # Unlimited plan limits are represented by None.
    return get_plan_limit(plan, key) is None
