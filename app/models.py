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


class Printer(Base):
    __tablename__ = "printers"
    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    production = Column(String(20), nullable=True)
    need_imagesetter = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)


class PrinterProcess(Base):
    __tablename__ = "printer_processes"
    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    printer_id = Column(Integer, ForeignKey("printers.id"), nullable=True)
    together = Column(Integer, nullable=False, default=1)
    colors = Column(Integer, nullable=False, default=1)
    colors_front = Column(Integer, nullable=True)
    colors_back = Column(Integer, nullable=True)
    rejection = Column(Integer, nullable=True)
    waste = Column(Integer, nullable=False, default=0)
    resolution = Column(Integer, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    printer = relationship("Printer")


class PrinterProcessStage(Base):
    __tablename__ = "printer_process_stages"
    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    printer_process_id = Column(Integer, ForeignKey("printer_processes.id"), nullable=False)
    together = Column(Integer, nullable=False, default=1)
    colors = Column(Integer, nullable=False, default=1)
    waste = Column(Integer, nullable=False, default=0)
    weight = Column(Integer, nullable=False, default=0)
    deleted_at = Column(DateTime, nullable=True)
    printer_process = relationship("PrinterProcess")


class PaperType(Base):
    __tablename__ = "paper_types"
    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class PaperFormat(Base):
    __tablename__ = "paper_formats"
    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    deleted_at = Column(DateTime, nullable=True)


class Paper(Base):
    __tablename__ = "papers"
    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    type_id = Column(Integer, ForeignKey("paper_types.id"), nullable=True)
    format_id = Column(Integer, ForeignKey("paper_formats.id"), nullable=True)
    weight = Column(Integer, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    paper_type = relationship("PaperType")
    paper_format = relationship("PaperFormat")


class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class Blank(Base):
    __tablename__ = "blanks"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    title = Column(String(50), nullable=False)
    printer_id = Column(Integer, ForeignKey("printers.id"), nullable=True)
    printer_process_id = Column(Integer, ForeignKey("printer_processes.id"), nullable=True)
    cutting = Column(Integer, nullable=True, default=1)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)
    width = Column(Numeric(8, 2), nullable=True)
    height = Column(Numeric(8, 2), nullable=True)
    paper_price = Column(Numeric(10, 2), nullable=True, default=0)
    colors_front = Column(Integer, nullable=False, default=1)
    colors_back = Column(Integer, nullable=False, default=0)
    details_per_sheet = Column(Integer, nullable=True)
    pages_per_sheet = Column(Integer, nullable=True)
    details_per_blank = Column(Integer, nullable=True)
    different_details = Column(Integer, nullable=True)
    comments = Column(Text, nullable=True)
    cost = Column(Numeric(10, 2), nullable=True, default=0)
    deleted_at = Column(DateTime, nullable=True)
    printer = relationship("Printer")
    paper = relationship("Paper")
    material = relationship("Material")


class BlankImagesetter(Base):
    __tablename__ = "blank_imagesetters"
    id = Column(Integer, primary_key=True)
    blank_id = Column(Integer, ForeignKey("blanks.id"), nullable=False)
    plates = Column(Integer, default=0)
    self = Column(Boolean, default=False)
    fix = Column(Boolean, default=False)


class Afterprint(Base):
    __tablename__ = "afterprints"
    id = Column(Integer, primary_key=True)
    title = Column(String(50), nullable=False)
    production = Column(String(20), nullable=True)
    tooltip = Column(String(255), nullable=True)
    deleted_at = Column(DateTime, nullable=True)


class AfterprintParameter(Base):
    __tablename__ = "afterprint_parameters"
    id = Column(Integer, primary_key=True)
    afterprint_id = Column(Integer, ForeignKey("afterprints.id"), nullable=False)
    title = Column(String(50), nullable=False)
    value = Column(String(50), nullable=True)
    parameter_type = Column(String(20), nullable=True)
    deleted_at = Column(DateTime, nullable=True)


class AfterprintParameterValue(Base):
    __tablename__ = "afterprint_parameter_values"
    id = Column(Integer, primary_key=True)
    afterprint_parameter_id = Column(Integer, ForeignKey("afterprint_parameters.id"), nullable=False)
    value = Column(String(50), nullable=False)
    weight = Column(Integer, nullable=True)
    deleted_at = Column(DateTime, nullable=True)


class BlankAfterprint(Base):
    __tablename__ = "blank_afterprints"
    id = Column(Integer, primary_key=True)
    blank_id = Column(Integer, ForeignKey("blanks.id"), nullable=False)
    afterprint_id = Column(Integer, ForeignKey("afterprints.id"), nullable=False)
    active = Column(Boolean, nullable=False, default=False)
    quantity = Column(Numeric(8, 2), nullable=False, default=0)
    parameters = Column(Text, nullable=True)
    price = Column(Numeric(8, 2), nullable=True, default=0)
    deleted_at = Column(DateTime, nullable=True)
    afterprint = relationship("Afterprint")


class AfterprintStage(Base):
    __tablename__ = "afterprint_stages"
    id = Column(Integer, primary_key=True)
    afterprint_id = Column(Integer, ForeignKey("afterprints.id"), nullable=False)
    title = Column(String(255), nullable=False)
    together = Column(Integer, nullable=False, default=1)
    waste = Column(Integer, nullable=False, default=0)
    min_paper_weight = Column(Integer, nullable=False, default=0)
    max_paper_weight = Column(Integer, nullable=True)
    weight = Column(Integer, nullable=False, default=0)
    fitting = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    afterprint = relationship("Afterprint")


class AfterprintStageMaterial(Base):
    __tablename__ = "afterprint_stage_materials"
    id = Column(Integer, primary_key=True)
    afterprint_stage_id = Column(Integer, ForeignKey("afterprint_stages.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    quantity = Column(Numeric(10, 4), nullable=False, default=0)
    deleted_at = Column(DateTime, nullable=True)
    material = relationship("Material")


class Rate(Base):
    __tablename__ = "rates"
    id = Column(Integer, primary_key=True)
    usd = Column(Numeric(10, 2), nullable=False, default=0)
    eur = Column(Numeric(10, 2), nullable=False, default=0)
    actual_since = Column(Date, nullable=True)
    deleted_at = Column(DateTime, nullable=True)


class Price(Base):
    __tablename__ = "prices"
    id = Column(Integer, primary_key=True)
    priceable_id = Column(Integer, nullable=False)
    priceable_type = Column(String(50), nullable=False)
    actual_since = Column(Date, nullable=True)
    actual_from = Column(Integer, nullable=False, default=0)
    item = Column(String(50), nullable=True)
    amount = Column(Numeric(10, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="RUB")
    deleted_at = Column(DateTime, nullable=True)
