from datetime import datetime

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
    prod_date = Column(Date, nullable=True)
    deadline = Column(Date, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    total = Column(Numeric(10, 2), nullable=False, default=0)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)
    volume = Column(String(50), nullable=True)
    width = Column(Numeric(8, 2), nullable=True)
    height = Column(Numeric(8, 2), nullable=True)
    comment = Column(Text, nullable=True)
    files = Column(Text, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    status = relationship("OrderStatus")
    manager = relationship("User", foreign_keys=[user_id])
    customer = relationship("Customer")
    bill = relationship("Bill")


class OrderMarkup(Base):
    __tablename__ = "order_markups"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    markup_type = Column(String(50), nullable=False)
    value = Column(Numeric(10, 2), nullable=False, default=10)
    active = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)


class Prepress(Base):
    __tablename__ = "prepresses"

    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class Compile(Base):
    __tablename__ = "compiles"

    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    production_book = Column(Boolean, default=False)
    production_poly = Column(Boolean, default=False)
    production_wide = Column(Boolean, default=False)
    production_souvenir = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)


class OtherWork(Base):
    __tablename__ = "other_works"

    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class Redaction(Base):
    __tablename__ = "redactions"

    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class OrderPrepress(Base):
    __tablename__ = "order_prepresses"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    prepress_id = Column(Integer, ForeignKey("prepresses.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    price_id = Column(Integer, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    prepress = relationship("Prepress")


class OrderCompile(Base):
    __tablename__ = "order_compiles"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    compile_id = Column(Integer, ForeignKey("compiles.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    fitting = Column(Integer, nullable=True)
    price_id = Column(Integer, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    compile = relationship("Compile")


class OrderOtherWork(Base):
    __tablename__ = "order_other_works"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    other_work_id = Column(Integer, ForeignKey("other_works.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    price_id = Column(Integer, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    other_work = relationship("OtherWork")


class OrderRedaction(Base):
    __tablename__ = "order_redactions"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    redaction_id = Column(Integer, ForeignKey("redactions.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    price_id = Column(Integer, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    redaction = relationship("Redaction")


class Action(Base):
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    module = Column(String(50), nullable=False)
    item_id = Column(Integer, nullable=False)
    comment = Column(String(255), nullable=False)
    url = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    user = relationship("User")
