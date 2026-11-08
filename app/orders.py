from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from .models import Bill, Customer, Order, OrderStatus, User


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