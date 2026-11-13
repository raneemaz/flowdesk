import enum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.extensions import db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.security import hash_password, verify_password


class UserStatus(str, enum.Enum):
    """Global account status - independent of any organization membership
    (see Membership.status / EmployeeProfile for org-scoped status)."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(
            UserStatus,
            name="user_status",
            native_enum=True,
            # Without this, SQLAlchemy stores each member's NAME ("ACTIVE")
            # instead of its value ("active") - store the lowercase values.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=UserStatus.ACTIVE,
    )

    @validates("email")
    def _normalize_email(self, key, value):
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("email must not be empty")
        return normalized

    @validates("name")
    def _normalize_name(self, key, value):
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized

    def set_password(self, raw_password: str) -> None:
        self.password_hash = hash_password(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        return verify_password(self.password_hash, raw_password)

    def __repr__(self) -> str:
        return f"<User {self.email}>"
