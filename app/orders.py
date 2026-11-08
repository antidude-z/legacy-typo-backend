from datetime import date, datetime
from decimal import Decimal
from math import ceil
import json
import re

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload
from .php_serialization import dumps as php_dumps

from .models import (
    Action, Afterprint, AfterprintParameter, AfterprintParameterValue, AfterprintStage, AfterprintStageMaterial, Bill, Blank, BlankAfterprint, BlankImagesetter, Compile, CompileStage, CompileStageMaterial, Customer, Material, Order, OrderCompile, OrderMarkup, OrderOtherWork,
    OrderPrepress, OrderRedaction, OrderStatus, OtherWork, Paper, PaperFormat, PaperType, Prepress, Price, Printer, PrinterProcess, PrinterProcessStage, Rate, Redaction, Service, User,
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
    # Price::inCurrency() does not pass the historical price date to Rate::getRate().
    rate = currency_rate(db, price.currency, currency)
    return {"amount": Decimal(price.amount or 0) * rate, "currency": currency, "source_currency": price.currency, "rate": rate, "found": True, "price_id": price.id}


def calculate_printer(db: Session, printer_id: int, printing: int, colors_front: int, colors_back: int, order_date: date | None = None, process_id: int | None = None, currency: str = "RUB") -> dict:
    printer = db.get(Printer, printer_id)
    if printer is None:
        return {"result": Decimal("0"), "pl_count": printing, "details": {"title": "Без печати", "stages": []}, "status": "missing_printer"}
    processes = select(PrinterProcess).where(PrinterProcess.printer_id == printer_id, PrinterProcess.deleted_at.is_(None))
    if process_id:
        processes = processes.where(PrinterProcess.id == process_id)
    else:
        processes = processes.where(PrinterProcess.colors_front >= colors_front, PrinterProcess.colors_back >= colors_back).order_by(PrinterProcess.colors_front.asc(), PrinterProcess.colors_back.asc())
    process = db.scalar(processes)
    separate = False
    if process is None and not process_id:
        process = db.scalar(select(PrinterProcess).where(PrinterProcess.printer_id == printer_id, PrinterProcess.deleted_at.is_(None), PrinterProcess.colors_front <= colors_front).order_by(PrinterProcess.colors_front.desc()))
        separate = process is not None
    if process is None:
        return {"result": Decimal("0"), "pl_count": printing, "details": {"title": "Процесс печати не найден", "stages": []}, "status": "missing_process"}
    stages = db.scalars(select(PrinterProcessStage).where(PrinterProcessStage.printer_process_id == process.id, PrinterProcessStage.deleted_at.is_(None)).order_by(PrinterProcessStage.weight.desc() if not separate else PrinterProcessStage.weight.asc())).all()
    total = Decimal("0")
    pl_count = printing
    stage_details = []
    passes = [("front", colors_front), ("back", colors_back)] if separate else [("front_back", max(colors_front, colors_back))]
    for side, colors in passes:
        for stage in stages:
            stage_colors = max(stage.colors, 1)
            repeats = (colors + stage_colors - 1) // stage_colors if separate else 1
            pl_count += stage.waste * repeats
            together = max(stage.together, 1)
            payment_count = ((pl_count + together - 1) // together) * repeats
            price = resolve_price(db, "App\\PrinterProcessStage", stage.id, payment_count, order_date, currency)
            cost = price["amount"] * payment_count
            total += cost
            stage_details.append({"side": side, "title": stage.title, "pl_count": pl_count, "repeats": repeats, "together": together, "payment_count": payment_count, "price": str(price["amount"]), "cost": str(cost), "price_found": price["found"]})
    return {"result": total, "pl_count": pl_count, "details": {"title": ("Печать отдельно лица и оборота: " if separate else "Печать в один проход (лицо+оборот): ") + process.title, "stages": stage_details}, "status": "calculated" if all(item["price_found"] for item in stage_details) else "missing_prices"}


def calculate_afterprint(db: Session, blank: Blank, start_pl_count: int, afterprint_id: int, count_on_pl: int = 1, order_type: str = "poly", order_date: date | None = None, currency: str = "RUB") -> dict:
    afterprint = db.get(Afterprint, afterprint_id)
    if afterprint is None:
        return {"result": Decimal("0"), "pl_count": start_pl_count, "status": "missing_afterprint", "details": {"stages": []}}
    paper_weight = blank.paper.weight if blank.paper else None
    query = select(AfterprintStage).where(AfterprintStage.afterprint_id == afterprint_id, AfterprintStage.deleted_at.is_(None)).order_by(AfterprintStage.weight)
    if order_type != "wide" and paper_weight is not None:
        query = query.where(AfterprintStage.min_paper_weight <= paper_weight).where((AfterprintStage.max_paper_weight.is_(None)) | (AfterprintStage.max_paper_weight > paper_weight))
    stages = db.scalars(query).all()
    pl_count = start_pl_count
    total = Decimal("0")
    details = []
    missing_price = False
    for stage in stages:
        together = max(stage.together, 1)
        payment_count = ceil(Decimal(pl_count) / together) * Decimal(str(count_on_pl))
        pl_count += stage.waste * payment_count
        price = resolve_price(db, "App\\AfterprintStage", stage.id, payment_count, order_date, currency)
        stage_cost = price["amount"] * payment_count
        total += stage_cost
        missing_price = missing_price or not price["found"]
        materials = []
        for material in db.scalars(select(AfterprintStageMaterial).where(AfterprintStageMaterial.afterprint_stage_id == stage.id, AfterprintStageMaterial.deleted_at.is_(None))).all():
            quantity = Decimal(material.quantity or 0) * payment_count
            material_price = resolve_price(db, "App\\Material", material.material_id, int(quantity), order_date, currency)
            material_cost = material_price["amount"] * quantity
            # Legacy BlankAfterprint::calc reports materials but returns stage costs only.
            missing_price = missing_price or not material_price["found"]
            materials.append({"title": material.material.title if material.material else "", "quantity": str(quantity), "price": str(material_price["amount"]), "cost": str(material_cost), "price_found": material_price["found"]})
        details.append({"title": stage.title, "pl_count": pl_count, "together": together, "waste": stage.waste, "payment_count": payment_count, "price": str(price["amount"]), "cost": str(stage_cost), "price_found": price["found"], "materials": materials})
    return {"result": total, "pl_count": pl_count, "status": "missing_prices" if missing_price else "calculated", "details": {"title": afterprint.title, "stages": details}}


def afterprint_count(parameters: str | None) -> Decimal:
    """Read the first scalar parameter, as PHP array_shift(unserialize(...)) does.

    The deployed dump stores PHP scalar arrays; newer callers may send JSON or
    a plain numeric scalar. Never execute serialized objects or guess a value.
    """
    if not parameters:
        return Decimal("0")
    value = parameters.strip()
    if value.startswith("a:"):
        match = re.match(r'a:\d+:\{(?:i:-?\d+;|s:\d+:"[^"]*";)(?:s:\d+:"([^"]*)";|[id]:([^;]+);)', value)
        if not match:
            raise ValueError("Unsupported serialized afterprint parameter")
        value = match.group(1) if match.group(1) is not None else match.group(2)
    elif value.startswith(("{", "[")):
        parsed = json.loads(value)
        value = next(iter(parsed.values()), "") if isinstance(parsed, dict) else next(iter(parsed), "")
    return Decimal(str(value or "0"))


def calculate_wide_printer(db: Session, blank: Blank, count: int, on_date: date | None) -> dict:
    process = db.scalar(select(PrinterProcess).where(
        PrinterProcess.id == blank.printer_process_id,
        PrinterProcess.printer_id == blank.printer_id,
        PrinterProcess.deleted_at.is_(None),
    ))
    if process is None:
        return {"result": Decimal("0"), "pl_count": count, "status": "missing_process", "details": {"stages": []}}
    total, stages, missing = Decimal("0"), [], False
    for stage in db.scalars(select(PrinterProcessStage).where(
        PrinterProcessStage.printer_process_id == process.id,
        PrinterProcessStage.deleted_at.is_(None),
    ).order_by(PrinterProcessStage.weight.desc())).all():
        count += stage.waste
        payment_count = ceil(Decimal(count) * Decimal(blank.width or 0) * Decimal(blank.height or 0) / (stage.together or 1))
        price = resolve_price(db, "App\\PrinterProcessStage", stage.id, payment_count, on_date)
        cost = price["amount"] * payment_count
        total += cost
        missing |= not price["found"]
        stages.append({"title": stage.title, "pl_count": count, "payment_count": payment_count, "price": price["amount"], "cost": cost})
    return {"result": total, "pl_count": count, "status": "missing_prices" if missing else "calculated", "details": {"title": process.title, "stages": stages}}


def calculate_blank(db: Session, blank: Blank, order: Order, currency: str = "RUB", printing_override: int | None = None) -> dict:
    printing = int(order.printing or 0) if printing_override is None else printing_override
    details = {
        "title": blank.title, "printing": printing,
        "details_per_sheet": blank.details_per_sheet, "pages_per_sheet": blank.pages_per_sheet,
        "details_per_blank": blank.details_per_blank, "different_details": blank.different_details,
        "width": str(blank.width or 0), "height": str(blank.height or 0), "steps": [],
        "afterprint": [], "print": {}, "paper": {}, "imagesetter": {},
    }
    if order.order_type == "wide":
        steps = [printing]
        step_fractions = [Decimal("1")]
    elif order.order_type in {"poly", "book"}:
        divisor = int(blank.details_per_sheet or blank.pages_per_sheet or 0)
        different = max(int(blank.different_details or 1), 1)
        per_blank = max(int(blank.details_per_blank or 1), 1)
        if divisor <= 0:
            steps = []
            step_fractions = []
        else:
            count = different / divisor
            steps, step_fractions = [], []
            index = 0
            while index < count:
                fraction = Decimal(str(min(1, count - index)))
                if index > 0 and fraction <= Decimal("0.5"):
                    fraction = Decimal("0.5")
                elif index > 0:
                    fraction = Decimal("1")
                steps.append(ceil(float(fraction * per_blank / different * printing)))
                step_fractions.append(fraction)
                index += 1
    else:
        steps, step_fractions = [], []
    total = Decimal("0")
    components = {key: Decimal("0") for key in ("paper", "print", "afterprint", "imagesetter")}
    missing = []
    details["steps"] = list(steps)
    details["steps_count"] = max(sum(step_fractions), Decimal("1"))
    details["area"] = Decimal(blank.width or 0) * Decimal(blank.height or 0)
    resulting_steps = list(steps)

    for assignment in db.scalars(select(BlankAfterprint).where(BlankAfterprint.blank_id == blank.id, BlankAfterprint.active.is_(True), BlankAfterprint.deleted_at.is_(None)).order_by(BlankAfterprint.afterprint_id.desc())).all():
        after_details = []
        for index, count in enumerate(resulting_steps):
            count_on_pl = afterprint_count(assignment.parameters)
            calc = calculate_afterprint(db, blank, count, assignment.afterprint_id, count_on_pl, order.order_type or "poly", order.order_date, currency)
            total += calc["result"]
            components["afterprint"] += calc["result"]
            missing.extend([] if calc["status"] == "calculated" else [f"afterprint:{assignment.afterprint_id}"])
            resulting_steps[index] = calc["pl_count"]
            after_details.append(calc)
        details["afterprint"].append({"id": assignment.afterprint_id, "steps": after_details})

    printer_calc = {"result": Decimal("0"), "pl_count": resulting_steps[-1] if resulting_steps else printing, "status": "skipped"}
    if blank.printer_id:
        for index, count in enumerate(resulting_steps):
            printer_calc = calculate_wide_printer(db, blank, count, order.order_date) if order.order_type == "wide" else calculate_printer(db, blank.printer_id, count, blank.colors_front, blank.colors_back, order.order_date, None, currency)
            total += printer_calc["result"]
            components["print"] += printer_calc["result"]
            resulting_steps[index] = printer_calc["pl_count"]
            if printer_calc["status"] not in {"calculated", "skipped"}:
                missing.append(f"printer:{blank.printer_id}")
        details["print"] = printer_calc["details"]
    else:
        details["print"] = {"title": "Без печати", "stages": []}

    final_sheets = sum(resulting_steps)
    cutting = max(int(blank.cutting or 1), 1)
    if order.order_type == "wide":
        quantity = Decimal(final_sheets) * Decimal(str(blank.width or 0)) * Decimal(str(blank.height or 0))
        price = {"amount": Decimal(blank.paper_price or 0), "found": blank.material is not None}
        cost = price["amount"] * quantity
        details["paper"] = {"title": blank.material.title if blank.material else "", "material_count": str(quantity), "price": str(price["amount"]), "cost": str(cost)}
    else:
        quantity = Decimal(ceil(final_sheets / cutting))
        price = {"amount": Decimal(blank.paper_price or 0), "found": blank.paper is not None}
        cost = price["amount"] * quantity
        details["paper"] = {"title": blank.paper.title if blank.paper else "", "paper_list_count": str(quantity), "price": str(price["amount"]), "cost": str(cost)}
    total += cost
    components["paper"] = cost
    details["paper"]["print_list_count"] = final_sheets
    details["paper"]["cutting"] = cutting
    if not price["found"]:
        missing.append("paper_or_material")

    printer = db.get(Printer, blank.printer_id) if blank.printer_id else None
    if printer and printer.need_imagesetter:
        image = db.scalar(select(BlankImagesetter).where(BlankImagesetter.blank_id == blank.id))
        plates = int(image.plates if image else 0)
        service = db.scalar(select(Service).where(Service.kind == "imagesetter", Service.deleted_at.is_(None)).order_by(Service.id))
        image_price = resolve_price(db, "App\\Service", service.id, plates, order.order_date, currency) if service else {"amount": Decimal("0"), "found": False}
        image_cost = image_price["amount"] * plates
        total += image_cost
        components["imagesetter"] = image_cost
        details["imagesetter"] = {"plates": plates, "price": str(image_price["amount"]), "cost": str(image_cost)}
        if not image_price["found"]:
            missing.append("imagesetter")
    blank.cost = total
    db.commit()
    return {"result": total, **components, "status": "missing_prices" if missing else "calculated", "missing": sorted(set(missing)), "details": details}


def calculate_order_work(db: Session, order_id: int, component: str, currency: str = "RUB") -> dict:
    """Mirror Order::prepress_calc/redaction_calc: current price, count zero."""
    model, reference, relation, foreign_key, price_type = {
        "design": (OrderPrepress, Prepress, "prepress", "prepress_id", "App\\Prepress"),
        "redaction": (OrderRedaction, Redaction, "redaction", "redaction_id", "App\\Redaction"),
    }[component]
    rows = db.scalars(select(model).join(reference).where(
        model.order_id == order_id, model.deleted_at.is_(None), reference.deleted_at.is_(None),
    ).order_by(model.id)).all()
    total, details, missing = Decimal("0"), [], []
    for row in rows:
        identity = getattr(row, foreign_key)
        price = resolve_price(db, price_type, identity, 0, None, currency)
        quantity = Decimal(row.quantity)
        cost = quantity * price["amount"]
        total += cost
        if not price["found"]:
            missing.append(f"{component}:{identity}")
        details.append({
            "id": row.id, "title": getattr(row, relation).title,
            "quantity": str(quantity), "price": str(price["amount"]), "cost": str(cost),
            "formula": f"quantity * price = {quantity} * {price['amount']}",
            "price_found": price["found"],
        })
    return {"result": total, "details": details, "missing": missing}


def calculate_compilation(db: Session, order: Order, currency: str = "RUB") -> dict:
    """Mirror Order::compile_calc(), including its breakdown-only materials."""
    printing = int(order.printing or 0)
    total, details, missing = Decimal("0"), [], []
    rows = db.scalars(select(OrderCompile).join(Compile).where(
        OrderCompile.order_id == order.id, OrderCompile.deleted_at.is_(None),
        Compile.deleted_at.is_(None),
    ).order_by(OrderCompile.id)).all()
    for row in rows:
        reference = row.compile
        price = resolve_price(db, "App\\Compile", reference.id, 0, None, currency)
        printing += reference.fitting or 0
        quantity = Decimal(row.quantity)
        unit_price = price["amount"]
        cost = quantity * printing * unit_price
        total += cost
        if not price["found"]:
            missing.append(f"compile:{reference.id}")
        work_count = quantity * printing
        stages = []
        for stage in db.scalars(select(CompileStage).where(
            CompileStage.compile_id == reference.id, CompileStage.deleted_at.is_(None),
        ).order_by(CompileStage.id)).all():
            if stage.together == 0:
                raise ValueError(f"Compilation stage {stage.id} has zero together factor")
            payment_count = ceil(work_count / stage.together)
            work_count += stage.waste * work_count
            stage_detail = {
                "id": stage.id, "title": stage.title, "fitting": stage.fitting,
                "waste": stage.waste, "together": stage.together,
                "quantity": str(quantity), "work_count": str(work_count),
                "payment_count": payment_count, "materials": {},
            }
            for material in db.scalars(select(CompileStageMaterial).where(
                CompileStageMaterial.compile_stage_id == stage.id,
                CompileStageMaterial.deleted_at.is_(None),
            ).order_by(CompileStageMaterial.id)).all():
                # PHP reuses quantity/price here; preserve their resulting detail values.
                quantity = Decimal(material.quantity) * payment_count
                material_price = resolve_price(db, "App\\Material", material.material_id, quantity, order.order_date, currency)
                unit_price = material_price["amount"]
                if not material_price["found"]:
                    missing.append(f"material:{material.material_id}")
                entry = stage_detail["materials"].setdefault(material.material_id, {
                    "title": material.material.title if material.material else "",
                    "quantity": Decimal("0"), "price": str(unit_price), "cost": Decimal("0"),
                })
                entry["quantity"] += quantity
                entry["cost"] += quantity * unit_price
            for entry in stage_detail["materials"].values():
                entry["quantity"], entry["cost"] = str(entry["quantity"]), str(entry["cost"])
            stages.append(stage_detail)
        details.append({
            "id": row.id, "title": reference.title, "quantity": str(quantity),
            "printing": printing, "fitting": reference.fitting,
            "price": str(unit_price), "cost": str(cost), "stages": stages,
            "formula": f"quantity * printing * price = {quantity} * {printing} * {unit_price}",
        })
    return {"result": total, "printing": printing, "details": details, "missing": missing}


def calculate_other_work(db: Session, order_id: int, currency: str = "RUB") -> dict:
    """Use the assigned price directly, like OrderOtherWork::cost()."""
    total, details, missing = Decimal("0"), [], []
    rows = db.scalars(select(OrderOtherWork).where(
        OrderOtherWork.order_id == order_id, OrderOtherWork.deleted_at.is_(None),
    ).order_by(OrderOtherWork.id)).all()
    for row in rows:
        price = db.get(Price, row.price_id) if row.price_id is not None else None
        if price is None:
            missing.append(f"other_works:{row.id}:price:{row.price_id}")
        # Price does not use SoftDeletes in PHP: an assigned row is read directly.
        unit_price = Decimal(price.amount) * currency_rate(db, price.currency, currency) if price else Decimal("0")
        quantity = Decimal(row.quantity)
        cost = unit_price * quantity
        total += cost
        details.append({
            "id": row.id, "title": row.other_work.title if row.other_work else "",
            "price_id": row.price_id, "quantity": str(quantity),
            "price": str(unit_price), "cost": str(cost), "price_found": price is not None,
            "formula": f"quantity * price = {quantity} * {unit_price}",
        })
    return {"result": total, "details": details, "missing": missing}


def calculate_order(db: Session, order: Order, currency: str = "RUB") -> dict:
    """Aggregate order components using the legacy markup rules."""
    component_totals = {
        "design": Decimal("0"), "redaction": Decimal("0"), "paper": Decimal("0"),
        "imagesetter": Decimal("0"), "print": Decimal("0"), "afterprint": Decimal("0"),
        "compile": Decimal("0"), "other_works": Decimal("0"),
    }
    blank_details = {}
    missing = []
    work_details = {}
    for component in ("design", "redaction"):
        calculation = calculate_order_work(db, order.id, component, currency)
        component_totals[component] = calculation["result"]
        work_details[component] = calculation["details"]
        missing.extend(calculation["missing"])
    compilation = calculate_compilation(db, order, currency)
    component_totals["compile"] = compilation["result"]
    work_details["compile"] = compilation["details"]
    missing.extend(compilation["missing"])
    other_work = calculate_other_work(db, order.id, currency)
    component_totals["other_works"] = other_work["result"]
    work_details["other_works"] = other_work["details"]
    missing.extend(other_work["missing"])
    for blank in db.scalars(select(Blank).where(Blank.order_id == order.id, Blank.deleted_at.is_(None))).all():
        calculation = calculate_blank(db, blank, order, currency, compilation["printing"])
        blank_details[blank.id] = {"cost": str(calculation["result"]), "status": calculation["status"], "details": calculation["details"]}
        for key in ("paper", "imagesetter", "print", "afterprint"):
            component_totals[key] += calculation.get(key, Decimal("0"))
        missing.extend(calculation.get("missing", []))

    markup_types = {
        "book": ["design", "redaction", "paper", "imagesetter", "print", "afterprint", "compile", "other_works", "manager"],
        "poly": ["design", "paper", "imagesetter", "print", "afterprint", "compile", "other_works", "manager"],
        "wide": ["design", "paper", "print", "afterprint", "compile", "other_works", "manager"],
        "souvenir": ["design", "paper", "imagesetter", "print", "afterprint", "compile", "other_works", "manager"],
    }
    stored_markups = {item.markup_type: item for item in db.scalars(select(OrderMarkup).where(OrderMarkup.order_id == order.id, OrderMarkup.deleted_at.is_(None))).all()}
    markup_details = {}
    total_base = Decimal("0")
    total_total = Decimal("0")
    for markup_type in markup_types.get(order.order_type, markup_types["poly"]):
        markup = stored_markups.get(markup_type)
        value = Decimal(markup.value if markup is not None else 10)
        active = bool(markup.active) if markup is not None else False
        base = Decimal("0") if markup_type == "manager" or not active else component_totals.get(markup_type, Decimal("0"))
        total = base + base * value / Decimal("100")
        if markup_type != "manager":
            total_base += base
            total_total += total
        markup_details[markup_type] = {"active": active, "markup": str(value), "base": str(base), "total": str(total)}

    stored_total = Decimal(order.total or 0)
    manager_markup = Decimal("0") if total_total == 0 else Decimal("100") * (stored_total - total_total) / total_total
    printing = max(int(order.printing or 1), 1)
    pending = []
    result = {
        "result": str(total_total),
        "base": str(total_base),
        "item": str(total_total / printing),
        "manager_markup": str(manager_markup),
        "stored_total": str(stored_total),
        "production_printing": compilation["printing"],
        "status": "missing_prices" if missing else "calculated",
        "missing": sorted(set(missing)),
        "pending_components": pending,
        "components": {key: str(value) for key, value in component_totals.items()},
        "markups": markup_details,
        "blanks": blank_details,
        "work_details": work_details,
    }
    # Preserve the legacy top-level detail keys consumed by report templates.
    persisted_details = {
        "printing": order.printing,
        "design": work_details["design"], "redaction": work_details["redaction"],
        "compile": {row["id"]: row for row in work_details["compile"]},
        "other_works": work_details["other_works"],
        "blanks": {identity: {"details": row["details"], "cost": Decimal(row["cost"])} for identity, row in blank_details.items()},
        "markups": {key: {"active": int(row["active"]), "markup": Decimal(row["markup"]), "base": Decimal(row["base"]), "total": Decimal(row["total"])} for key, row in markup_details.items()},
    }
    order.calc_details = php_dumps(persisted_details)
    db.commit()
    return result