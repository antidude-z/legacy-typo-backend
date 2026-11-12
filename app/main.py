from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import secrets
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from itsdangerous import URLSafeTimedSerializer, BadSignature

import bcrypt
from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from .config import APP_URL, DATABASE_MODE, DATABASE_URL, REMEMBER_DAYS, RESET_MAIL_DIR, RESET_MAIL_MODE, RESET_TOKEN_MINUTES, SESSION_COOKIE, SESSION_SECRET, SESSION_SECURE
from .db import Base, engine, get_db
from .schema import upgrade_local_schema
from .models import Action, Afterprint, AfterprintStage, Blank, BlankAfterprint, BlankImagesetter, Compile, CompileStage, Material, OtherWork, Paper, Prepress, Price, Printer, PrinterProcess, PrinterProcessStage, Redaction, Service, User, Order, OrderCompile, OrderMarkup, OrderOtherWork, OrderPrepress, OrderRedaction, PasswordReset
from .navigation import build_navigation
from .orders import blank_metadata, calculate_afterprint, calculate_blank, calculate_order, calculate_printer, create_order, list_metadata, orders_query, resolve_price, serialize_history, serialize_order, serialize_order_detail
from .payroll import register_payroll_routes
from .csrf import CSRF_COOKIE, CSRFMiddleware, token_for_session


@asynccontextmanager
async def lifespan(_: FastAPI):
    upgrade_local_schema()
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
    https_only=SESSION_SECURE,
)
app.add_middleware(CSRFMiddleware)


def current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    user = db.scalar(
        select(User)
        .options(joinedload(User.role))
        .where(User.id == user_id, User.fired.is_(False), User.deleted_at.is_(None))
    )
    if user is not None:
        version = request.session.get("password_version")
        if version is None or secrets.compare_digest(version, hashlib.sha256(user.password.encode()).hexdigest()):
            return user
        request.session.clear()
    remember = request.cookies.get("typography_remember")
    if not remember:
        return None
    try:
        remember = URLSafeTimedSerializer(SESSION_SECRET, salt="remember").loads(remember, max_age=REMEMBER_DAYS * 86400)
        if not isinstance(remember, str):
            return None
    except BadSignature:
        return None
    digest = hashlib.sha256(remember.encode()).hexdigest()
    user = db.scalar(select(User).options(joinedload(User.role)).where(
        User.remember_token == digest, User.fired.is_(False), User.deleted_at.is_(None)
    ))
    if user:
        request.session["user_id"] = user.id
        request.session["password_version"] = hashlib.sha256(user.password.encode()).hexdigest()
    return user


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system/database", tags=["system"])
def database_status() -> dict[str, str]:
    return {"mode": DATABASE_MODE, "url": DATABASE_URL.split("@")[-1] if DATABASE_MODE == "mysql" else DATABASE_URL}


PRICEABLE_TYPES = {
    "services": (Service, "App\\Service"),
    "paper": (Paper, "App\\Paper"),
    "print": (PrinterProcessStage, "App\\PrinterProcessStage"),
    "materials": (Material, "App\\Material"),
    "afterprint": (AfterprintStage, "App\\AfterprintStage"),
    "prepress": (Prepress, "App\\Prepress"),
    "redaction": (Redaction, "App\\Redaction"),
    "compile": (Compile, "App\\Compile"),
    "compiles": (CompileStage, "App\\CompileStage"),
}


def priceable_info(kind: str):
    return PRICEABLE_TYPES.get(kind)


PRICE_TITLES = {
    "services": "услуги подрядчиков", "paper": "бумагу", "print": "этап печати",
    "materials": "материалы", "afterprint": "постпечать", "prepress": "работы по дизайну/препресс",
    "redaction": "работы по редактуре", "compile": "работы по сборке", "compiles": "этапы сборки",
}


def price_reference_label(db: Session, kind: str, row) -> str:
    parts = []
    if kind == "print":
        process = db.get(PrinterProcess, row.printer_process_id)
        printer = db.get(Printer, process.printer_id) if process else None
        parts = [printer.title if printer else "", process.title if process else ""]
    elif kind == "afterprint":
        parent = db.get(Afterprint, row.afterprint_id)
        parts = [parent.title if parent else ""]
    elif kind == "compiles":
        parent = db.get(Compile, row.compile_id)
        parts = [parent.title if parent else ""]
    return " - ".join(part for part in [*parts, row.title] if part)


def require_price_permission(request: Request, db: Session, permission: str) -> User | JSONResponse:
    user = current_user(request, db)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if not user.has_permission(permission):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return user


def serialize_price(price: Price) -> dict:
    return {"id": price.id, "amount": str(price.amount), "currency": price.currency, "actual_since": price.actual_since.isoformat() if price.actual_since else None, "actual_from": price.actual_from, "item": price.item or ""}


def validated_price(payload: dict) -> dict:
    amount = Decimal(str(payload["amount"]))
    if not amount.is_finite() or payload["currency"] not in {"RUB", "USD", "EUR"}:
        raise ValueError("Invalid price")
    threshold = Decimal(str(payload["actual_from"]))
    if not threshold.is_finite() or threshold != threshold.to_integral_value():
        raise ValueError("Invalid quantity threshold")
    raw_date = payload["actual_since"]
    try:
        effective = __import__("datetime").datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        effective = __import__("datetime").datetime.strptime(raw_date, "%d.%m.%Y").date()
    return {"amount": amount, "currency": payload["currency"], "actual_from": int(threshold), "actual_since": effective}


@app.get("/api/pricing/catalog/{kind}", tags=["pricing"])
def price_catalog(kind: str, request: Request, page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    info = priceable_info(kind)
    if info is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    model, _ = info
    query = select(model).where(model.deleted_at.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(model.id).offset((page - 1) * 50).limit(50)).all()
    return {"items": [{"id": row.id, "title": price_reference_label(db, kind, row), "current_price": str(resolve_price(db, info[1], row.id)["amount"])} for row in rows], "heading": f"Цены на {PRICE_TITLES[kind]}", "can_edit": user.has_permission("edit_price"), "page": page, "last_page": max(1, (total + 49) // 50)}


@app.post("/api/prices/{kind}/{item_id}/create", tags=["pricing"])
def price_create_default(kind: str, item_id: int, request: Request, db: Session = Depends(get_db)):
    # Legacy GET create saves a default row before showing the editor. The SPA
    # performs that mutation via POST, retaining browser URL and row semantics.
    return price_create(kind, item_id, request, {
        "amount": "0", "currency": "RUB", "actual_from": 0,
        "actual_since": __import__("datetime").date.today().isoformat(),
    }, db)


@app.get("/api/prices/{kind}/{item_id}/records/{price_id}", tags=["pricing"])
def price_record_detail(kind: str, item_id: int, price_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    info = priceable_info(kind)
    row = db.get(Price, price_id)
    reference = db.get(info[0], item_id) if info else None
    if not reference or not row or row.priceable_type != info[1] or row.priceable_id != item_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"price": serialize_price(row), "title": price_reference_label(db, kind, reference), "heading": f"Цена на {PRICE_TITLES[kind]}", "can_edit": user.has_permission("edit_price"), "can_delete": user.has_permission("delete_price")}


@app.get("/api/prices/{priceable_type}/{priceable_id}/records", tags=["pricing"])
def price_records(priceable_type: str, priceable_id: int, request: Request, sort: str = Query("id"), order: str = Query("desc"), page: int = Query(1, ge=1), per_page: int = Query(30, ge=1), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    info = priceable_info(priceable_type)
    if info is None or db.get(info[0], priceable_id) is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    column = getattr(Price, sort if sort in {"id", "amount", "currency", "actual_since", "actual_from"} else "id")
    query = select(Price).where(Price.priceable_type == info[1], Price.priceable_id == priceable_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    return {"items": [serialize_price(row) for row in rows], "title": price_reference_label(db, priceable_type, db.get(info[0], priceable_id)), "heading": f"Цены на {PRICE_TITLES[priceable_type]}", "priceable_type": priceable_type, "priceable_id": priceable_id, "page": page, "last_page": max(1, (total + per_page - 1) // per_page), "can_edit": user.has_permission("edit_price"), "can_delete": user.has_permission("delete_price")}


@app.post("/api/prices/{priceable_type}/{priceable_id}/records", tags=["pricing"])
def price_create(priceable_type: str, priceable_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    permission = require_price_permission(request, db, "edit_price")
    if isinstance(permission, JSONResponse):
        return permission
    info = priceable_info(priceable_type)
    if info is None or db.get(info[0], priceable_id) is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    try:
        values = validated_price(payload)
    except (KeyError, ValueError, TypeError, InvalidOperation):
        return JSONResponse({"error": "invalid_price"}, status_code=422)
    row = Price(priceable_id=priceable_id, priceable_type=info[1], **values, item="")
    db.add(row)
    db.commit()
    return serialize_price(row)


@app.patch("/api/prices/{priceable_type}/{priceable_id}/records/{price_id}", tags=["pricing"])
def price_update(priceable_type: str, priceable_id: int, price_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    permission = require_price_permission(request, db, "edit_price")
    if isinstance(permission, JSONResponse):
        return permission
    info = priceable_info(priceable_type)
    row = db.get(Price, price_id)
    if info is None or row is None or row.priceable_type != info[1] or row.priceable_id != priceable_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    try:
        values = validated_price(payload)
    except (KeyError, ValueError, TypeError, InvalidOperation):
        return JSONResponse({"error": "invalid_price"}, status_code=422)
    for field, value in values.items():
        setattr(row, field, value)
    db.commit()
    return serialize_price(row)


@app.delete("/api/prices/{priceable_type}/{priceable_id}/records/{price_id}", tags=["pricing"])
def price_delete(priceable_type: str, priceable_id: int, price_id: int, request: Request, db: Session = Depends(get_db)):
    permission = require_price_permission(request, db, "delete_price")
    if isinstance(permission, JSONResponse):
        return permission
    info = priceable_info(priceable_type)
    row = db.get(Price, price_id)
    if info is None or row is None or row.priceable_type != info[1] or row.priceable_id != priceable_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    # Price has no SoftDeletes trait in the original application.
    db.delete(row)
    db.commit()
    return {"status": "ok"}


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


@app.get("/api/csrf-token", tags=["auth"])
def csrf_token(request: Request):
    token = token_for_session(request)
    response = JSONResponse({"token": token})
    response.set_cookie(CSRF_COOKIE, token, httponly=False, secure=SESSION_SECURE, samesite="lax", max_age=120 * 60)
    return response


@app.get("/auth/users", tags=["auth"])
@app.get("/api/auth/users", tags=["auth"], include_in_schema=False)
def login_users(db: Session = Depends(get_db)) -> dict[str, str]:
    users = db.scalars(select(User).where(User.fired.is_(False), User.deleted_at.is_(None)).order_by(User.surname, User.name)).all()
    return {user.email: f"{user.surname or ''} {user.name}".strip() for user in users}


@app.post("/auth/login", tags=["auth"])
@app.post("/api/auth/login", tags=["auth"], include_in_schema=False)
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember: bool = Form(False),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email, User.fired.is_(False), User.deleted_at.is_(None)))
    try:
        valid = user is not None and len(password.encode()) <= 72 and bcrypt.checkpw(password.encode(), user.password.encode())
    except ValueError:
        valid = False
    if not valid:
        return JSONResponse({"message": "Неверные учетные данные."}, status_code=422)
    request.session["user_id"] = user.id
    request.session["password_version"] = hashlib.sha256(user.password.encode()).hexdigest()
    response = RedirectResponse("/orders", status_code=303)
    if remember:
        raw_token = secrets.token_urlsafe(32)
        user.remember_token = hashlib.sha256(raw_token.encode()).hexdigest()
        db.commit()
        signed_token = URLSafeTimedSerializer(SESSION_SECRET, salt="remember").dumps(raw_token)
        response.set_cookie("typography_remember", signed_token, max_age=REMEMBER_DAYS * 86400, httponly=True, secure=SESSION_SECURE, samesite="lax")
    return response


@app.post("/auth/logout", tags=["auth"])
@app.post("/api/auth/logout", tags=["auth"], include_in_schema=False)
def logout(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user:
        user.remember_token = None
        db.commit()
    request.session.clear()
    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie("typography_remember")
    return response


def _auth_error(message: str, fields: dict | None = None):
    return JSONResponse({"message": message, "errors": fields or {}}, status_code=422)


@app.post("/auth/register", tags=["auth"])
@app.post("/api/auth/register", tags=["auth"], include_in_schema=False)
def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirmation: str = Form(...),
    db: Session = Depends(get_db),
):
    if current_user(request, db):
        return JSONResponse({"message": "Вы уже вошли в систему."}, status_code=409)
    email = email.strip().lower()
    errors = {}
    if not name.strip() or len(name) > 255: errors["name"] = "Укажите имя."
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 255: errors["email"] = "Укажите корректный email."
    if db.scalar(select(User).where(User.email == email)): errors["email"] = "Этот email уже используется."
    if len(password) < 6 or len(password.encode()) > 72 or password != password_confirmation: errors["password"] = "Пароли должны совпадать: минимум 6 символов, максимум 72 байта UTF-8."
    if errors: return _auth_error("Проверьте форму регистрации.", errors)
    user = User(name=name.strip(), email=email, password=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())
    db.add(user); db.commit()
    request.session["user_id"] = user.id
    request.session["password_version"] = hashlib.sha256(user.password.encode()).hexdigest()
    return RedirectResponse("/orders", status_code=303)


def _reset_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def deliver_reset_mail(email: str, token: str):
    message = EmailMessage()
    message["To"] = email
    message["From"] = os.getenv("MAIL_FROM", "typography@localhost")
    message["Subject"] = "Password reset"
    message.set_content(f"Click here to reset your password: {APP_URL}/password/reset/{token}\n")
    if RESET_MAIL_MODE == "file":
        RESET_MAIL_DIR.mkdir(parents=True, exist_ok=True)
        # Random filenames avoid interpreting an email address as a filesystem path.
        with (RESET_MAIL_DIR / f"{secrets.token_hex(16)}.eml").open("x", encoding="utf-8") as file:
            file.write(message.as_string())
    elif RESET_MAIL_MODE == "smtp":
        with smtplib.SMTP(os.environ["MAIL_HOST"], int(os.getenv("MAIL_PORT", "587")), timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if os.getenv("MAIL_USERNAME"):
                smtp.login(os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"])
            smtp.send_message(message)
    else:
        raise RuntimeError("Password reset mail is not configured")


@app.post("/password/email", tags=["auth"])
@app.post("/api/password/email", tags=["auth"], include_in_schema=False)
def password_email(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    if current_user(request, db):
        return RedirectResponse("/orders", status_code=303)
    email = email.strip().lower()
    if len(email) > 255 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return _auth_error("Укажите корректный email.")
    if RESET_MAIL_MODE not in {"file", "smtp"}:
        return JSONResponse({"message": "Отправка почты не настроена."}, status_code=503)
    user = db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user:
        raw_token = secrets.token_urlsafe(48)
        existing = db.get(PasswordReset, email)
        if existing: db.delete(existing)
        db.add(PasswordReset(email=email, token=_reset_digest(raw_token), created_at=datetime.utcnow()))
        try:
            deliver_reset_mail(email, raw_token)
            db.commit()
        except (OSError, smtplib.SMTPException, RuntimeError, KeyError, ValueError):
            db.rollback()
            return JSONResponse({"message": "Не удалось отправить письмо. Повторите позднее."}, status_code=503)
    return {"message": "Если учетная запись существует, инструкция отправлена."}


@app.post("/password/reset", tags=["auth"])
@app.post("/api/password/reset", tags=["auth"], include_in_schema=False)
def password_reset(
    request: Request, token: str = Form(...), email: str = Form(...), password: str = Form(...), password_confirmation: str = Form(...), db: Session = Depends(get_db)
):
    if current_user(request, db):
        return RedirectResponse("/orders", status_code=303)
    row = db.get(PasswordReset, email.strip().lower())
    if not row or not secrets.compare_digest(row.token, _reset_digest(token)) or datetime.utcnow() - row.created_at > timedelta(minutes=RESET_TOKEN_MINUTES):
        return _auth_error("Ссылка для сброса пароля недействительна или устарела.")
    if len(password) < 6 or len(password.encode()) > 72 or password != password_confirmation:
        return _auth_error("Пароли должны совпадать и содержать минимум 6 символов.", {"password": "Неверный пароль."})
    user = db.scalar(select(User).where(User.email == email.strip().lower(), User.deleted_at.is_(None)))
    if not user: return _auth_error("Ссылка для сброса пароля недействительна.")
    user.password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user.remember_token = None
    db.delete(row); db.commit()
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


@app.get("/api/pricing/printers/{printer_id}/calculate", tags=["pricing"])
def printer_calculate(printer_id: int, request: Request, printing: int = Query(...), colors_front: int = Query(1), colors_back: int = Query(0), process_id: int | None = Query(None), price_date: str | None = Query(None), currency: str = Query("RUB"), db: Session = Depends(get_db)):
    if current_user(request, db) is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    effective = __import__("datetime").datetime.strptime(price_date, "%Y-%m-%d").date() if price_date else None
    result = calculate_printer(db, printer_id, printing, colors_front, colors_back, effective, process_id, currency)
    result["result"] = str(result["result"])
    for stage in result["details"]["stages"]:
        stage["price"] = str(stage["price"])
        stage["cost"] = str(stage["cost"])
    return result


@app.post("/api/orders/{order_id}/blanks/{blank_id}/recalculate", tags=["pricing"])
def blank_recalculate(order_id: int, blank_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(Blank, blank_id)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    if item is None or item.order_id != order_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    order = db.get(Order, order_id)
    if order is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    calculated = calculate_blank(db, item, order, "RUB")
    calculated["result"] = str(calculated["result"])
    calculated["cost"] = calculated["result"]
    return calculated


@app.post("/api/orders/{order_id}/recalculate", tags=["pricing"])
def order_recalculate(order_id: int, request: Request, db: Session = Depends(get_db)):
    if current_user(request, db) is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    order = db.get(Order, order_id)
    if order is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return calculate_order(db, order, "RUB")


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


# Resolve the user through this module at request time so dependency overrides
# and the existing session authentication contract work for reference routes.
from .permissions import register_permission_routes
register_permission_routes(app, lambda request, db: current_user(request, db))
from .reference_dictionaries import register_reference_routes
register_reference_routes(app, lambda request, db: current_user(request, db))
from .reference_printers import register_printer_routes
from .printer_children import register_printer_child_routes
register_printer_child_routes(app, lambda request, db: current_user(request, db))
register_printer_routes(app, lambda request, db: current_user(request, db))
from .reference_inventory import register_inventory_routes
from .reference_afterprints import register_afterprint_routes
register_afterprint_routes(app, lambda request, db: current_user(request, db))
from .reference_compiles import register_compile_routes
register_compile_routes(app, lambda request, db: current_user(request, db))
from .reference_works import register_work_routes
register_work_routes(app, lambda request, db: current_user(request, db))
from .reference_customers import register_customer_routes
register_customer_routes(app, lambda request, db: current_user(request, db))
from .reference_users import register_user_reference_routes
register_user_reference_routes(app, lambda request, db: current_user(request, db))
from .accounting_payers import register_payer_routes
register_payer_routes(app, lambda request, db: current_user(request, db))
from .accounting_bills import register_bill_routes
register_bill_routes(app, lambda request, db: current_user(request, db))
from .accounting_payments import register_payment_routes
register_payment_routes(app, lambda request, db: current_user(request, db))
from .reports import register_report_routes
register_report_routes(app, lambda request, db: current_user(request, db))
register_payroll_routes(app, lambda request, db: current_user(request, db))
register_inventory_routes(app, lambda request, db: current_user(request, db))
