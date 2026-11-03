from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, Database
from app.api.performance import _date_window
from app.platform_models import AgentInsight, UserPreference
from app.services import agent
from app.services.performance import verify_owned_account

router = APIRouter(prefix="/agent", tags=["Trading agent"])

InsightStatus = Literal["new", "seen", "accepted", "dismissed", "experiment_running", "resolved"]
Feedback = Literal["useful", "not_useful", "wrong", "already_knew"]


class InsightUpdate(BaseModel):
    status: InsightStatus | None = None
    feedback: Feedback | None = None


@router.post("/run")
def run_agent(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    """Recompute the agent's analysis for the signed-in user and refresh stored insights."""
    if account_id is not None and not verify_owned_account(db, current_user.id, account_id):
        raise HTTPException(status_code=404, detail="Trading account not found")
    preference = db.get(UserPreference, current_user.id)
    start, end, zone = _date_window(
        start_date, end_date, timezone or (preference.timezone if preference else "UTC")
    )
    return agent.run_agent(db, current_user.id, account_id, start, end, zone)


@router.patch("/insights/{insight_id}")
def update_insight(
    insight_id: UUID, payload: InsightUpdate, current_user: CurrentUser, db: Database
) -> dict[str, Any]:
    row = db.scalar(
        select(AgentInsight).where(
            AgentInsight.id == str(insight_id), AgentInsight.user_id == current_user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    if payload.status is None and payload.feedback is None:
        raise HTTPException(status_code=422, detail="Provide a status or feedback")
    if payload.status is not None:
        row.status = payload.status
    if payload.feedback is not None:
        row.feedback = payload.feedback
    db.commit()
    return agent.serialize(row)
