from fastapi import APIRouter

from app.api.deps import CurrentUser, Database
from app.services.mt5_method import effective_method

router = APIRouter(prefix="/platform", tags=["Platform"])


@router.get("/mt5-method")
def mt5_method(current_user: CurrentUser, db: Database) -> dict[str, str]:
    """Which MT5 connection method the admin has enabled for this user."""
    return {"method": effective_method(db, current_user)}
