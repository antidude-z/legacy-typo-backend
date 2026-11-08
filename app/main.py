from contextlib import asynccontextmanager

import bcrypt
from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from .config import DATABASE_MODE, DATABASE_URL, SESSION_COOKIE, SESSION_SECRET
from .db import Base, engine, get_db
from .models import User
from .navigation import build_navigation
from .orders import list_metadata, orders_query, serialize_order


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
