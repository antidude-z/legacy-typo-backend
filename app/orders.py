from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from .models import (
    Bill, Compile, Customer, Order, OrderCompile, OrderMarkup, OrderOtherWork,
    OrderPrepress, OrderRedaction, OrderStatus, OtherWork, Prepress, Redaction, User,
)


ORDER_TYPES = {
    "book": "Книги, брошюры",
    "poly": "Полиграфия",
    "souvenir": "Сувенирная продукция",
    "wide": "Широкоформатная печать",
}
SORTABLE_COLUMNS = {"id", "title", "order_type", "bill_id", "user_id", "customer_id", "status_id", "printing", "order_date", "total"}


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def list_metadata(db: Session) -> dict:
    statuses = db.scalars(select(OrderStatus).where(OrderStatus.deleted_at.is_(None)).order_by(OrderStatus.sequence)).all()
    managers = db.scalars(select(User).where(User.fired.is_(False)).order_by(User.surname, User.name)).all()
    customers = db.scalars(select(Customer).where(Customer.deleted_at.is_(None)).order_by(Customer.title)).all()
    return {
        "statuses": [{"id": item.id, "title": item.title} for item in statuses],
        "managers": [{"id": item.id, "title": f"{item.surname or ''} {item.name}".strip()} for item in managers],
        "customers": [{"id": item.id, "title": item.title} for item in customers],
        "types": [{"id": key, "title": value} for key, value in ORDER_TYPES.items()],
    }


def orders_query(
    db: Session,
    filters: dict,
    sort: str,
    order: str,
):
    sort = sort if sort in SORTABLE_COLUMNS else "id"
    order = order if order in {"asc", "desc"} else "desc"
    statement: Select = select(Order).options(
        joinedload(Order.status), joinedload(Order.manager), joinedload(Order.customer), joinedload(Order.bill)
    )
    if not filters.get("view_trashed"):
        statement = statement.where(Order.deleted_at.is_(None))
    if filters.get("filter_status"):
        statement = statement.where(Order.status_id.in_(filters["filter_status"]))
    if filters.get("filter_date_from"):
        statement = statement.where(Order.order_date >= _date(filters["filter_date_from"]))
    if filters.get("filter_date_to"):
        statement = statement.where(Order.order_date <= _date(filters["filter_date_to"]))
    if filters.get("filter_text"):
        statement = statement.where(Order.title.ilike(f"%{filters['filter_text']}%"))
    if filters.get("filter_type"):
        statement = statement.where(Order.order_type == filters["filter_type"])
    if filters.get("filter_manager"):
        statement = statement.where(Order.user_id == int(filters["filter_manager"]))
    if filters.get("filter_customer"):
        statement = statement.where(Order.customer_id == int(filters["filter_customer"]))
    if filters.get("filter_number"):
        statement = statement.where(Order.id.like(f"%{filters['filter_number']}%"))
    if filters.get("filter_bill"):
        bill_ids = select(Bill.id).where(Bill.number.ilike(f"{filters['filter_bill']}%"))
        statement = statement.where(Order.bill_id.in_(bill_ids))
    column = getattr(Order, sort)
    statement = statement.order_by(column.asc() if order == "asc" else column.desc())
    return statement


def serialize_order(item: Order) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "type": ORDER_TYPES.get(item.order_type, item.order_type or ""),
        "order_type": item.order_type,
        "bill": ({"number": item.bill.number, "date": item.bill.bill_date.isoformat() if item.bill.bill_date else None, "paid": item.bill.paid, "closed": item.bill.closed, "filed": item.bill.filed} if item.bill else None),
        "manager": f"{item.manager.surname or ''} {item.manager.name}".strip() if item.manager else "",
        "customer": item.customer.title if item.customer else "",
        "status": item.status.title if item.status else "",
        "printing": item.printing,
        "order_date": item.order_date.isoformat() if item.order_date else None,
        "total": str(item.total if item.total is not None else Decimal("0.00")),
        "deleted": item.deleted_at is not None,
    }


MARKUP_TYPES = {
    "book": ["design", "redaction", "paper", "imagesetter", "print", "afterprint", "compile", "other_works", "manager"],
    "poly": ["design", "paper", "imagesetter", "print", "afterprint", "compile", "other_works", "manager"],
    "wide": ["design", "paper", "print", "afterprint", "compile", "other_works", "manager"],
    "souvenir": ["design", "paper", "imagesetter", "print", "afterprint", "compile", "other_works", "manager"],
}


def create_order(db: Session, user_id: int, order_type: str, values: dict, source: Order | None = None) -> Order:
    order_type = order_type if order_type in MARKUP_TYPES else "poly"
    default_printing = 1 if order_type == "wide" else 1000
    order = Order(
        title=values.get("title") or "Новый заказ",
        order_type=order_type,
        status_id=int(values.get("status_id") or 1),
        bill_id=int(values.get("bill_id") or 0),
        printing=int(values.get("printing") or default_printing),
        volume=values.get("volume") or "",
        format=values.get("format") or "",
        width=values.get("width") or 0,
        height=values.get("height") or 0,
        order_date=_date(values.get("order_date")) or date.today(),
        user_id=int(values.get("user_id") or user_id),
        customer_id=int(values["customer_id"]) if values.get("customer_id") else None,
        total=values.get("total") or (source.total if source else 0),
    )
    if order_type == "wide":
        order.format = f"{order.width}x{order.height}"
        order.volume = str((order.width or 0) * (order.height or 0))
    db.add(order)
    db.flush()
    for markup_type in MARKUP_TYPES[order_type]:
        db.add(OrderMarkup(order_id=order.id, markup_type=markup_type, value=10, active=False))
    return order


def serialize_operation(item, title_field: str, title: str) -> dict:
    related = getattr(item, title_field, None)
    return {"id": item.id, "title": getattr(related, "title", ""), "quantity": item.quantity, "section": title, "deleted": item.deleted_at is not None}


def serialize_order_detail(db: Session, order: Order, include_deleted: bool = False) -> dict:
    def active(model):
        query = select(model).where(model.order_id == order.id)
        if not include_deleted:
            query = query.where(model.deleted_at.is_(None))
        return db.scalars(query).all()
    markups = db.scalars(select(OrderMarkup).where(OrderMarkup.order_id == order.id, OrderMarkup.deleted_at.is_(None))).all()
    return {
        "order": serialize_order(order),
        "metadata": list_metadata(db),
        "markups": [{"type": item.markup_type, "value": str(item.value), "active": item.active} for item in markups],
        "operations": {
            "prepresses": [serialize_operation(item, "prepress", "design") for item in active(OrderPrepress)],
            "compiles": [serialize_operation(item, "compile", "compile") for item in active(OrderCompile)],
            "other_works": [serialize_operation(item, "other_work", "other_works") for item in active(OrderOtherWork)],
            "redactions": [serialize_operation(item, "redaction", "redaction") for item in active(OrderRedaction)],
        },
        "calculation": {"total": str(order.total or 0), "status": "stored_total", "message": "Legacy calculation dependencies are not yet migrated."},
    }