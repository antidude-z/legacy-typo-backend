from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from .db import Base


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("role_id", ForeignKey("roles.id"), nullable=False),
    Column("permission_id", ForeignKey("permissions.id"), nullable=False),
)


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(String(50), primary_key=True)
    title = Column(String(100), nullable=False)
    module = Column(String(50), nullable=False)


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    permissions = relationship(
        "Permission",
        secondary=role_permissions,
        primaryjoin="Role.id == role_permissions.c.role_id",
        secondaryjoin="Permission.id == role_permissions.c.permission_id",
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    surname = Column(String(255), nullable=True)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(60), nullable=False)
    role_id = Column(ForeignKey("roles.id"), nullable=True)
    fired = Column(Integer, nullable=False, default=0)
    role = relationship("Role")

    def has_permission(self, permission_id: str) -> bool:
        return any(permission.id == permission_id for permission in (self.role.permissions if self.role else []))
