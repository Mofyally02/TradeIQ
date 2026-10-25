from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, Database
from app.platform_models import AuditLog, TraderProfile, UserPreference
from app.schemas import (
    PreferenceRead,
    PreferenceUpdate,
    ProfileRead,
    ProfileUpdate,
)

router = APIRouter(tags=["Profile and settings"])


@router.get("/me", response_model=ProfileRead)
def read_profile(current_user: CurrentUser, db: Database) -> ProfileRead:
    profile = db.get(TraderProfile, current_user.id)
    return ProfileRead(
        id=current_user.id,
        email=current_user.email,
        created_at=current_user.created_at,
        experience_level=profile.experience_level if profile else None,
        goals=profile.goals if profile else None,
        preferred_instruments=profile.preferred_instruments if profile else [],
        preferred_sessions=profile.preferred_sessions if profile else [],
    )


@router.patch("/me", response_model=ProfileRead)
def update_profile(
    payload: ProfileUpdate,
    current_user: CurrentUser,
    db: Database,
) -> ProfileRead:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")
    email = changes.pop("email", None)
    if email is not None:
        current_user.email = str(email)
    profile_fields = {
        key: changes[key]
        for key in (
            "experience_level",
            "goals",
            "preferred_instruments",
            "preferred_sessions",
        )
        if key in changes
    }
    profile = db.get(TraderProfile, current_user.id)
    if profile is None and profile_fields:
        profile = TraderProfile(user_id=current_user.id)
        db.add(profile)
    if profile is not None:
        for key, value in profile_fields.items():
            setattr(profile, key, value)
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="profile.updated",
            entity_type="user",
            entity_id=str(current_user.id),
            source="user",
        )
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email address is already in use") from error
    db.refresh(current_user)
    return read_profile(current_user, db)


@router.get("/preferences", response_model=PreferenceRead)
def read_preferences(current_user: CurrentUser, db: Database) -> UserPreference:
    preference = db.get(UserPreference, current_user.id)
    if preference is None:
        preference = UserPreference(user_id=current_user.id)
        db.add(preference)
        db.commit()
        db.refresh(preference)
    return preference


@router.patch("/preferences", response_model=PreferenceRead)
def update_preferences(
    payload: PreferenceUpdate,
    current_user: CurrentUser,
    db: Database,
) -> UserPreference:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one preference to update")
    timezone = changes.get("timezone")
    if timezone is not None:
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise HTTPException(status_code=422, detail="Timezone is not recognized") from error
    preference = db.get(UserPreference, current_user.id)
    if preference is None:
        preference = UserPreference(user_id=current_user.id)
        db.add(preference)
    for key, value in changes.items():
        setattr(preference, key, value)
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="preferences.updated",
            entity_type="user_preferences",
            entity_id=str(current_user.id),
            source="user",
            details={"fields": ",".join(changes)},
        )
    )
    db.commit()
    db.refresh(preference)
    return preference
