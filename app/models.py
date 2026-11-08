from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Table, Text
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


class OrderStatus(Base):
    __tablename__ = "order_statuses"

    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    sequence = Column(Integer, nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True)
    number = Column(String(20), nullable=False)
    bill_date = Column(Date, nullable=True)
    paid = Column(Boolean, nullable=False, default=False)
    closed = Column(Boolean, nullable=False, default=False)
    filed = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    order_type = Column(String(20), nullable=True)
    status_id = Column(Integer, ForeignKey("order_statuses.id"), nullable=False)
    printing = Column(Integer, nullable=False, default=0)
    format = Column(String(50), nullable=True)
    order_date = Column(Date, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    total = Column(Numeric(10, 2), nullable=False, default=0)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)
    volume = Column(String(50), nullable=True)
    width = Column(Numeric(8, 2), nullable=True)
    height = Column(Numeric(8, 2), nullable=True)
    comment = Column(Text, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    status = relationship("OrderStatus")
    manager = relationship("User", foreign_keys=[user_id])
    customer = relationship("Customer")
    bill = relationship("Bill")
