from contextlib import asynccontextmanager
from decimal import Decimal

import bcrypt
from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from .config import DATABASE_MODE, DATABASE_URL, SESSION_COOKIE, SESSION_SECRET
from .db import Base, engine, get_db
from .models import Action, Afterprint, Blank, BlankAfterprint, BlankImagesetter, User, Order, OrderCompile, OrderMarkup, OrderOtherWork, OrderPrepress, OrderRedaction
from .navigation import build_navigation
from .orders import blank_metadata, create_order, list_metadata, orders_query, resolve_price, serialize_history, serialize_order, serialize_order_detail


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Typography Backend",
    description="Compatibility backend for the legacy typography application.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie=SESSION_COOKIE,
    max_age=120 * 60,
    same_site="lax",
)


def current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return db.scalar(
        select(User)
        .options(joinedload(User.role))
        .where(User.id == user_id, User.fired.is_(False))
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system/database", tags=["system"])
def database_status() -> dict[str, str]:
    return {"mode": DATABASE_MODE, "url": DATABASE_URL.split("@")[-1] if DATABASE_MODE == "mysql" else DATABASE_URL}


@app.get("/", tags=["compatibility"])
def root(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse("/orders" if current_user(request, db) else "/auth/login", status_code=303)


@app.get("/api/session", tags=["auth"])
@app.get("/session", tags=["auth"], include_in_schema=False)
def session_info(request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user(request, db)
    return {
        "authenticated": user is not None,
        "user": ({"id": user.id, "name": user.name, "surname": user.surname, "email": user.email} if user else None),
        "menu": build_navigation(user),
    }


@app.get("/auth/users", tags=["auth"])
@app.get("/api/auth/users", tags=["auth"], include_in_schema=False)
def login_users(db: Session = Depends(get_db)) -> dict[str, str]:
    users = db.scalars(select(User).where(User.fired.is_(False)).order_by(User.surname, User.name)).all()
    return {user.email: f"{user.surname or ''} {user.name}".strip() for user in users}


@app.post("/auth/login", tags=["auth"])
@app.post("/api/auth/login", tags=["auth"], include_in_schema=False)
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email, User.fired.is_(False)))
    valid = user is not None and bcrypt.checkpw(password.encode(), user.password.encode())
    if not valid:
        return JSONResponse({"message": "Неверные учетные данные."}, status_code=422)
    request.session["user_id"] = user.id
    return RedirectResponse("/orders", status_code=303)


@app.post("/auth/logout", tags=["auth"])
@app.post("/api/auth/logout", tags=["auth"], include_in_schema=False)
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=303)


def order_filters(request: Request, **values) -> dict:
    stored = request.session.get("orders_filter", {})
    if values:
        stored.update({key: value for key, value in values.items() if value not in (None, "", [])})
    return stored


def orders_response(
    request: Request,
    db: Session,
    page: int,
    per_page: int,
    sort: str,
    order: str,
    filters: dict,
) -> dict:
    user = current_user(request, db)
    if user is None:
        return {"error": "unauthorized"}
    per_page = per_page if 1 <= per_page <= 100 else 30
    page = max(page, 1)
    statement = orders_query(db, filters, sort, order)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(statement.offset((page - 1) * per_page).limit(per_page)).unique().all()
    return {
        "title": "Заказы",
        "items": [serialize_order(item) for item in items],
        "pagination": {"page": page, "per_page": per_page, "total": total, "last_page": max((total + per_page - 1) // per_page, 1)},
        "sort": sort if sort in {"id", "title", "order_type", "bill_id", "user_id", "customer_id", "status_id", "printing", "order_date", "total"} else "id",
        "order": order if order in {"asc", "desc"} else "desc",
        "filter": filters,
        "metadata": list_metadata(db),
    }


@app.get("/api/orders", tags=["orders"])
@app.get("/orders", tags=["compatibility"], include_in_schema=False)
def orders(
    request: Request,
    page: int = Query(1),
    per_page: int = Query(30),
    sort: str = Query("id"),
    order: str = Query("desc"),
    db: Session = Depends(get_db),
):
    result = orders_response(request, db, page, per_page, sort, order, order_filters(request))
    if result.get("error"):
        return RedirectResponse("/auth/login", status_code=303)
    return result


@app.post("/api/orders/filter", tags=["orders"])
@app.post("/orders/filter", tags=["compatibility"], include_in_schema=False)
def filter_orders(
    request: Request,
    filter_status: list[int] | None = Form(None),
    filter_date_from: str | None = Form(None),
    filter_date_to: str | None = Form(None),
    filter_number: str | None = Form(None),
    filter_bill: str | None = Form(None),
    filter_manager: str | None = Form(None),
    filter_customer: str | None = Form(None),
    filter_type: str | None = Form(None),
    filter_text: str | None = Form(None),
    flush: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if current_user(request, db) is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if flush:
        request.session.pop("orders_filter", None)
    else:
        request.session["orders_filter"] = {
            "filter_status": filter_status or [],
            "filter_date_from": filter_date_from or "",
            "filter_date_to": filter_date_to or "",
            "filter_number": filter_number or "",
            "filter_bill": filter_bill or "",
            "filter_manager": filter_manager or "",
            "filter_customer": filter_customer or "",
            "filter_type": filter_type or "",
            "filter_text": filter_text or "",
        }
    return {"status": "ok", "filter": request.session.get("orders_filter", {})}


@app.get("/api/orders/add/{order_type}", tags=["orders"])
def order_create_metadata(order_type: str, request: Request, db: Session = Depends(get_db)):
    if current_user(request, db) is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return {"order_type": order_type, "defaults": {"printing": 1 if order_type == "wide" else 1000}, "metadata": list_metadata(db)}


@app.post("/api/orders/add/{order_type}", tags=["orders"])
def order_create(
    order_type: str,
    request: Request,
    order_title: str = Form("Новый заказ"),
    order_format: str = Form(""),
    order_printing: int = Form(1000),
    order_volume: str = Form(""),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    item = create_order(db, user.id, order_type, {"title": order_title, "format": order_format, "printing": order_printing, "volume": order_volume})
    db.add(Action(user_id=user.id, module="Заказы", item_id=item.id, comment="Создан заказ", url=f"orders/{item.id}"))
    db.commit()
    return {"id": item.id, "location": f"/orders/{item.id}"}


@app.get("/api/orders/{order_id}", tags=["orders"])
def order_detail(order_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    item = db.get(Order, order_id)
    if item is None or (item.deleted_at is not None and not user.has_permission("view_trashed")):
        return JSONResponse({"error": "not_found"}, status_code=404)
    return serialize_order_detail(db, item, user.has_permission("view_trashed"))


@app.get("/api/orders/{order_id}/history", tags=["orders"])
def order_history(order_id: int, request: Request, db: Session = Depends(get_db)):
    if current_user(request, db) is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if db.get(Order, order_id) is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"items": serialize_history(db, order_id)}


@app.put("/api/orders/{order_id}", tags=["orders"])
@app.post("/api/orders/{order_id}", tags=["orders"], include_in_schema=False)
def order_update(order_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(Order, order_id)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if item is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    original = {"status_id": item.status_id, "user_id": item.user_id, "printing": item.printing, "total": item.total}
    values = payload.get("order", payload)
    for source, target in [("title", "title"), ("format", "format"), ("volume", "volume"), ("printing", "printing"), ("status_id", "status_id"), ("width", "width"), ("height", "height"), ("customer_id", "customer_id"), ("user_id", "user_id"), ("bill_id", "bill_id"), ("total", "total"), ("comment", "comment"), ("files", "files")]:
        if source in values:
            setattr(item, target, values[source])
    for date_field in ("order_date", "prod_date", "deadline"):
        if date_field in values:
            setattr(item, date_field, __import__("datetime").datetime.strptime(values[date_field], "%Y-%m-%d").date() if values[date_field] else None)
    for markup in values.get("markups", []):
        markup_item = db.scalar(select(OrderMarkup).where(OrderMarkup.order_id == order_id, OrderMarkup.markup_type == markup.get("type"), OrderMarkup.deleted_at.is_(None)))
        if markup_item:
            if "value" in markup:
                markup_item.value = markup["value"]
            if "active" in markup:
                markup_item.active = bool(markup["active"])
    if item.order_type == "wide":
        item.format = f"{item.width}x{item.height}"
        item.volume = str((item.width or 0) * (item.height or 0))
    comments = []
    if original["status_id"] != item.status_id:
        comments.append(f"Статус заказа изменен на {item.status.title if item.status else item.status_id}")
    if original["user_id"] != item.user_id:
        manager = db.get(User, item.user_id)
        comments.append(f"Менеджер заказа изменен на {manager.surname} {manager.name}" if manager else "Менеджер заказа изменен")
    if original["printing"] != item.printing:
        comments.append(f"Тираж заказа изменен c {original['printing']} на {item.printing}")
    if original["total"] != item.total:
        comments.append(f"Стоимость заказа изменена c {original['total']} на {item.total}")
    for comment in comments:
        db.add(Action(user_id=user.id, module="Заказы", item_id=item.id, comment=comment, url=f"orders/{item.id}"))
    db.commit()
    return serialize_order_detail(db, item)


@app.post("/api/orders/{order_id}/copy", tags=["orders"])
def order_copy(order_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    user = current_user(request, db)
    source = db.get(Order, order_id)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if source is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    item = create_order(db, user.id, source.order_type, {"title": payload.get("title", source.title), "format": payload.get("format", source.format), "printing": payload.get("printing", source.printing), "volume": payload.get("volume", source.volume), "total": source.total}, source)
    db.add(Action(user_id=user.id, module="Заказы", item_id=item.id, comment=f"Заказ скопирован с заказа №{source.id}", url=f"orders/{item.id}"))
    db.commit()
    return {"id": item.id, "location": f"/orders/{item.id}"}


@app.delete("/api/orders/{order_id}", tags=["orders"])
def order_delete(order_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(Order, order_id)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if item is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if item.deleted_at is not None and user.has_permission("delete_trashed"):
        db.delete(item)
    else:
        item.deleted_at = __import__("datetime").datetime.utcnow()
        db.add(Action(user_id=user.id, module="Заказы", item_id=item.id, comment="Заказ удален", url=f"orders/{item.id}"))
    db.commit()
    return {"status": "ok"}


@app.post("/api/orders/{order_id}/restore", tags=["orders"])
def order_restore(order_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(Order, order_id)
    if user is None or not user.has_permission("restore_trashed"):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if item is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    item.deleted_at = None
    db.add(Action(user_id=user.id, module="Заказы", item_id=item.id, comment="Заказ восстановлен", url=f"orders/{item.id}"))
    db.commit()
    return {"status": "ok"}


OPERATION_MODELS = {
    "prepresses": (OrderPrepress, "prepress_id"),
    "compiles": (OrderCompile, "compile_id"),
    "others": (OrderOtherWork, "other_work_id"),
    "redactions": (OrderRedaction, "redaction_id"),
}


@app.post("/api/orders/{order_id}/{operation}", tags=["orders"])
def operation_create(order_id: int, operation: str, request: Request, payload: dict, db: Session = Depends(get_db)):
    if operation == "blanks":
        return blank_create(order_id, request, payload, db)
    user = current_user(request, db)
    model_info = OPERATION_MODELS.get(operation)
    order = db.get(Order, order_id)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if model_info is None or order is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    model, foreign_key = model_info
    related_id = payload.get(foreign_key)
    if not related_id:
        return JSONResponse({"error": f"{foreign_key} is required"}, status_code=422)
    values = {"order_id": order_id, foreign_key: related_id, "quantity": payload.get("quantity", 1), "price_id": payload.get("price_id")}
    if model is OrderCompile:
        values["fitting"] = payload.get("fitting")
    item = model(**values)
    db.add(item)
    db.commit()
    return {"id": item.id, "status": "ok"}


@app.patch("/api/orders/{order_id}/{operation}/{item_id}", tags=["orders"])
def operation_update(order_id: int, operation: str, item_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    if operation == "blanks":
        return blank_update(order_id, item_id, request, payload, db)
    user = current_user(request, db)
    model_info = OPERATION_MODELS.get(operation)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if model_info is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    item = db.get(model_info[0], item_id)
    if item is None or item.order_id != order_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    for key in (model_info[1], "quantity", "price_id", "fitting"):
        if key in payload:
            setattr(item, key, payload[key])
    db.commit()
    return {"id": item.id, "status": "ok"}


@app.delete("/api/orders/{order_id}/{operation}/{item_id}", tags=["orders"])
def operation_delete(order_id: int, operation: str, item_id: int, request: Request, db: Session = Depends(get_db)):
    if operation == "blanks":
        return blank_delete(order_id, item_id, request, db)
    user = current_user(request, db)
    model_info = OPERATION_MODELS.get(operation)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if model_info is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    item = db.get(model_info[0], item_id)
    if item is None or item.order_id != order_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    item.deleted_at = __import__("datetime").datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@app.get("/api/orders/{order_id}/blanks", tags=["orders"])
def blanks(order_id: int, request: Request, db: Session = Depends(get_db)):
    if current_user(request, db) is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if db.get(Order, order_id) is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    items = db.scalars(select(Blank).where(Blank.order_id == order_id, Blank.deleted_at.is_(None)).order_by(Blank.id)).all()
    return {"items": [serialize_blank(item, db) for item in items], "metadata": blank_metadata(db), "calculation": "stored_cost"}


@app.post("/api/orders/{order_id}/blanks", tags=["orders"])
def blank_create(order_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if db.get(Order, order_id) is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    item = Blank(order_id=order_id, title=payload.get("title", "Новая заготовка"), printer_id=payload.get("printer_id") or 0, printer_process_id=payload.get("printer_process_id"), paper_id=payload.get("paper_id"), material_id=payload.get("material_id"), cutting=payload.get("cutting", 1), width=payload.get("width", 0), height=payload.get("height", 0), colors_front=payload.get("colors_front", 1), colors_back=payload.get("colors_back", 0), details_per_sheet=payload.get("details_per_sheet"), pages_per_sheet=payload.get("pages_per_sheet"), details_per_blank=payload.get("details_per_blank", 1), different_details=payload.get("different_details", 1), comments=payload.get("comments", ""), paper_price=payload.get("paper_price", 0), cost=payload.get("cost", 0))
    db.add(item)
    db.flush()
    imagesetter = BlankImagesetter(blank_id=item.id, plates=payload.get("plates", 0), fix=bool(payload.get("fix_plates", False)))
    setattr(imagesetter, "self", bool(payload.get("self_print", False)))
    db.add(imagesetter)
    for afterprint in payload.get("afterprints", []):
        db.add(BlankAfterprint(blank_id=item.id, afterprint_id=afterprint.get("id"), active=bool(afterprint.get("active", False)), parameters=afterprint.get("parameters", "")))
    db.add(Action(user_id=user.id, module="Заказы", item_id=order_id, comment=f"Добавлена заготовка: {item.title}", url=f"orders/{order_id}#blanks"))
    db.commit()
    return {"id": item.id, "status": "ok"}


@app.patch("/api/orders/{order_id}/blanks/{blank_id}", tags=["orders"])
def blank_update(order_id: int, blank_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(Blank, blank_id)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if item is None or item.order_id != order_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    fields = ("title", "printer_id", "printer_process_id", "paper_id", "material_id", "cutting", "width", "height", "colors_front", "colors_back", "details_per_sheet", "pages_per_sheet", "details_per_blank", "different_details", "comments", "paper_price", "cost")
    for field in fields:
        if field in payload:
            setattr(item, field, payload[field])
    image = db.scalar(select(BlankImagesetter).where(BlankImagesetter.blank_id == item.id))
    if image:
        image.plates = payload.get("plates", image.plates)
        image.self = payload.get("self_print", image.self)
        image.fix = payload.get("fix_plates", image.fix)
    for afterprint in payload.get("afterprints", []):
        row = db.scalar(select(BlankAfterprint).where(BlankAfterprint.blank_id == item.id, BlankAfterprint.afterprint_id == afterprint.get("id")))
        if row is None:
            row = BlankAfterprint(blank_id=item.id, afterprint_id=afterprint.get("id"), parameters=afterprint.get("parameters", ""))
            db.add(row)
        row.active = bool(afterprint.get("active", False))
        row.parameters = afterprint.get("parameters", row.parameters or "")
    db.add(Action(user_id=user.id, module="Заказы", item_id=order_id, comment=f"Изменена заготовка: {item.title}", url=f"orders/{order_id}#blanks"))
    db.commit()
    return {"status": "ok"}


@app.get("/api/orders/{order_id}/blanks/{blank_id}", tags=["orders"])
def blank_detail(order_id: int, blank_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(Blank, blank_id)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if item is None or item.order_id != order_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"item": serialize_blank(item, db), "metadata": blank_metadata(db), "calculation": "stored_cost"}


@app.get("/api/prices/{priceable_type}/{priceable_id}", tags=["pricing"])
def price_lookup(priceable_type: str, priceable_id: int, request: Request, quantity: int = Query(0), price_date: str | None = Query(None), currency: str = Query("RUB"), db: Session = Depends(get_db)):
    if current_user(request, db) is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    effective = __import__("datetime").datetime.strptime(price_date, "%Y-%m-%d").date() if price_date else None
    result = resolve_price(db, priceable_type, priceable_id, quantity, effective, currency)
    result["amount"] = str(result["amount"])
    result["rate"] = str(result["rate"])
    return result


@app.post("/api/orders/{order_id}/blanks/{blank_id}/recalculate", tags=["pricing"])
def blank_recalculate(order_id: int, blank_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(Blank, blank_id)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if item is None or item.order_id != order_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    result = {"paper": {"amount": "0", "found": False}, "material": {"amount": "0", "found": False}, "cost": str(item.cost or 0), "status": "stored_cost"}
    if item.paper_id:
        result["paper"] = {k: str(v) if isinstance(v, Decimal) else v for k, v in resolve_price(db, "App\\Paper", item.paper_id, 0, None, "RUB").items()}
    if item.material_id:
        result["material"] = {k: str(v) if isinstance(v, Decimal) else v for k, v in resolve_price(db, "App\\Material", item.material_id, 0, None, "RUB").items()}
    if result["paper"].get("found"):
        item.paper_price = result["paper"]["amount"]
        db.commit()
    result["message"] = "Generic price lookup migrated; printer and afterprint formulas remain pending."
    return result


@app.delete("/api/orders/{order_id}/blanks/{blank_id}", tags=["orders"])
def blank_delete(order_id: int, blank_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(Blank, blank_id)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if item is None or item.order_id != order_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    item.deleted_at = __import__("datetime").datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@app.delete("/api/orders/{order_id}/blanks/{blank_id}/permanent", tags=["orders"])
def blank_permanent_delete(order_id: int, blank_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(Blank, blank_id)
    if user is None or not user.has_permission("delete_trashed"):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if item is None or item.order_id != order_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    db.query(BlankAfterprint).filter(BlankAfterprint.blank_id == item.id).delete()
    db.query(BlankImagesetter).filter(BlankImagesetter.blank_id == item.id).delete()
    db.delete(item)
    db.commit()
    return {"status": "ok"}


@app.post("/api/orders/{order_id}/blanks/{blank_id}/copy", tags=["orders"])
def blank_copy(order_id: int, blank_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    source = db.get(Blank, blank_id)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if source is None or source.order_id != order_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    values = {field: getattr(source, field) for field in ("title", "printer_id", "printer_process_id", "paper_id", "material_id", "cutting", "width", "height", "colors_front", "colors_back", "details_per_sheet", "pages_per_sheet", "details_per_blank", "different_details", "comments", "paper_price", "cost")}
    values["title"] = f"{source.title} (копия)"
    clone = Blank(order_id=order_id, **values)
    db.add(clone)
    db.flush()
    image = db.scalar(select(BlankImagesetter).where(BlankImagesetter.blank_id == source.id))
    if image:
        clone_image = BlankImagesetter(blank_id=clone.id, plates=image.plates, fix=image.fix)
        setattr(clone_image, "self", getattr(image, "self", False))
        db.add(clone_image)
    for row in db.scalars(select(BlankAfterprint).where(BlankAfterprint.blank_id == source.id, BlankAfterprint.deleted_at.is_(None))).all():
        db.add(BlankAfterprint(blank_id=clone.id, afterprint_id=row.afterprint_id, active=row.active, parameters=row.parameters, price=row.price))
    db.commit()
    return {"id": clone.id, "status": "ok"}


@app.post("/api/orders/{order_id}/blanks/{blank_id}/restore", tags=["orders"])
def blank_restore(order_id: int, blank_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(Blank, blank_id)
    if user is None or not user.has_permission("restore_trashed"):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if item is None or item.order_id != order_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    item.deleted_at = None
    db.commit()
    return {"status": "ok"}
