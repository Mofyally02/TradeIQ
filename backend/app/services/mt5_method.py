from sqlalchemy.orm import Session

from app.models import User
from app.platform_models import PlatformSetting

METHODS = ("metaapi", "ea")
DEFAULT_KEY = "default_mt5_method"


def default_method(db: Session) -> str:
    setting = db.get(PlatformSetting, DEFAULT_KEY)
    return setting.value if setting is not None and setting.value in METHODS else "metaapi"


def set_default_method(db: Session, method: str) -> None:
    setting = db.get(PlatformSetting, DEFAULT_KEY)
    if setting is None:
        db.add(PlatformSetting(key=DEFAULT_KEY, value=method))
    else:
        setting.value = method


def effective_method(db: Session, user: User) -> str:
    if user.mt5_method in METHODS:
        return user.mt5_method
    return default_method(db)
