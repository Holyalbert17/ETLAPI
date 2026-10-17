from app.config import settings
from app.database import SessionLocal
from app.domain.models import User
from app.security import hash_password


def ensure_admin() -> None:
    if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
        return
    db = SessionLocal()
    try:
        exists = db.query(User).filter_by(username=settings.ADMIN_USERNAME).first()
        if exists:
            return
        db.add(
            User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                role="admin",
            )
        )
        db.commit()
    finally:
        db.close()
