from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from .models import (
    Action, Afterprint, AfterprintParameter, AfterprintParameterValue, Bill, Blank, BlankAfterprint, BlankImagesetter, Compile, Customer, Material, Order, OrderCompile, OrderMarkup, OrderOtherWork,
    OrderPrepress, OrderRedaction, OrderStatus, OtherWork, Paper, PaperFormat, PaperType, Prepress, Price, Printer, PrinterProcess, Rate, Redaction, User,
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
        "status_id": item.status_id,
        "bill": ({"number": item.bill.number, "date": item.bill.bill_date.isoformat() if item.bill.bill_date else None, "paid": item.bill.paid, "closed": item.bill.closed, "filed": item.bill.filed} if item.bill else None),
        "manager": f"{item.manager.surname or ''} {item.manager.name}".strip() if item.manager else "",
        "customer": item.customer.title if item.customer else "",
        "status": item.status.title if item.status else "",
        "printing": item.printing,
        "order_date": item.order_date.isoformat() if item.order_date else None,
        "prod_date": item.prod_date.isoformat() if item.prod_date else None,
        "deadline": item.deadline.isoformat() if item.deadline else None,
        "format": item.format,
        "volume": item.volume,
        "width": str(item.width) if item.width is not None else None,
        "height": str(item.height) if item.height is not None else None,
        "customer_id": item.customer_id,
        "manager_id": item.user_id,
        "bill_id": item.bill_id,
        "comment": item.comment or "",
        "files": item.files or "",
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
        prod_date=_date(values.get("prod_date")),
        deadline=_date(values.get("deadline")),
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


def serialize_history(db: Session, order_id: int) -> list[dict]:
    actions = db.scalars(
        select(Action).where(Action.item_id == order_id, Action.module == "Заказы", Action.deleted_at.is_(None)).order_by(Action.created_at.desc()).limit(20)
    ).all()
    return [{
        "id": action.id,
        "date": action.created_at.strftime("%d.%m.%Y %H:%M"),
        "user": f"{action.user.surname or ''} {action.user.name}".strip() if action.user else "",
        "comment": action.comment,
        "url": action.url,
    } for action in actions]


def blank_metadata(db: Session) -> dict:
    return {
        "printers": [{"id": x.id, "title": x.title, "need_imagesetter": bool(x.need_imagesetter)} for x in db.scalars(select(Printer).where(Printer.deleted_at.is_(None)).order_by(Printer.title)).all()],
        "printer_processes": [{"id": x.id, "title": x.title, "printer_id": x.printer_id} for x in db.scalars(select(PrinterProcess).where(PrinterProcess.deleted_at.is_(None)).order_by(PrinterProcess.title)).all()],
        "paper_types": [{"id": x.id, "title": x.title} for x in db.scalars(select(PaperType).where(PaperType.deleted_at.is_(None)).order_by(PaperType.title)).all()],
        "paper_formats": [{"id": x.id, "title": x.title} for x in db.scalars(select(PaperFormat).where(PaperFormat.deleted_at.is_(None)).order_by(PaperFormat.title)).all()],
        "papers": [{"id": x.id, "title": x.title, "type_id": x.type_id, "format_id": x.format_id, "weight": x.weight} for x in db.scalars(select(Paper).where(Paper.deleted_at.is_(None)).order_by(Paper.title)).all()],
        "materials": [{"id": x.id, "title": x.title} for x in db.scalars(select(Material).where(Material.deleted_at.is_(None)).order_by(Material.title)).all()],
        "afterprints": [{"id": x.id, "title": x.title, "tooltip": x.tooltip or "", "parameters": [{"id": p.id, "title": p.title, "value": p.value or "", "type": p.parameter_type or "text", "values": [{"id": v.id, "value": v.value} for v in db.scalars(select(AfterprintParameterValue).where(AfterprintParameterValue.afterprint_parameter_id == p.id, AfterprintParameterValue.deleted_at.is_(None)).order_by(AfterprintParameterValue.weight)).all()]} for p in db.scalars(select(AfterprintParameter).where(AfterprintParameter.afterprint_id == x.id, AfterprintParameter.deleted_at.is_(None))).all()]} for x in db.scalars(select(Afterprint).where(Afterprint.deleted_at.is_(None)).order_by(Afterprint.title)).all()],
    }


def serialize_blank(item: Blank, db: Session | None = None) -> dict:
    afterprints = []
    if db is not None:
        rows = db.scalars(select(BlankAfterprint).where(BlankAfterprint.blank_id == item.id, BlankAfterprint.deleted_at.is_(None))).all()
        afterprints = [{"id": row.afterprint_id, "title": row.afterprint.title if row.afterprint else "", "active": row.active, "parameters": row.parameters or ""} for row in rows]
    image = db.scalar(select(BlankImagesetter).where(BlankImagesetter.blank_id == item.id)) if db is not None else None
    return {"id": item.id, "title": item.title, "printer": item.printer.title if item.printer else "Без печати", "paper": item.paper.title if item.paper else (item.material.title if item.material else ""), "printer_id": item.printer_id, "printer_process_id": item.printer_process_id, "paper_id": item.paper_id, "material_id": item.material_id, "colors_front": item.colors_front, "colors_back": item.colors_back, "cutting": item.cutting, "width": str(item.width or 0), "height": str(item.height or 0), "details_per_sheet": item.details_per_sheet, "pages_per_sheet": item.pages_per_sheet, "details_per_blank": item.details_per_blank, "different_details": item.different_details, "comments": item.comments or "", "plates": image.plates if image else 0, "self_print": bool(getattr(image, "self", False)) if image else False, "fix_plates": bool(image.fix) if image else False, "afterprints": afterprints, "cost": str(item.cost or 0), "deleted": item.deleted_at is not None}


def currency_rate(db: Session, source: str, target: str, on_date: date | None = None) -> Decimal:
    if source == target:
        return Decimal("1")
    rate = db.scalar(select(Rate).where(Rate.deleted_at.is_(None), Rate.actual_since <= (on_date or date.today())).order_by(Rate.actual_since.desc()))
    if rate is None:
        return Decimal("1")
    usd = Decimal(rate.usd or 1) or Decimal("1")
    eur = Decimal(rate.eur or 1) or Decimal("1")
    table = {"RUB": {"RUB": Decimal("1"), "USD": Decimal("1") / usd, "EUR": Decimal("1") / eur}, "USD": {"RUB": usd, "USD": Decimal("1"), "EUR": usd / eur}, "EUR": {"RUB": eur, "USD": eur / usd, "EUR": Decimal("1")}}
    return table.get(source, {}).get(target, Decimal("1"))


def resolve_price(db: Session, priceable_type: str, priceable_id: int, quantity: int = 0, on_date: date | None = None, currency: str = "RUB") -> dict:
    effective = on_date or date.today()
    price = db.scalar(select(Price).where(Price.priceable_type == priceable_type, Price.priceable_id == priceable_id, Price.deleted_at.is_(None), Price.actual_since <= effective, Price.actual_from <= quantity).order_by(Price.actual_from.desc(), Price.actual_since.desc()))
    if price is None:
        return {"amount": Decimal("0"), "currency": currency, "source_currency": None, "rate": Decimal("1"), "found": False}
    rate = currency_rate(db, price.currency, currency, effective)
    return {"amount": Decimal(price.amount or 0) * rate, "currency": currency, "source_currency": price.currency, "rate": rate, "found": True, "price_id": price.id}