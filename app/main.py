from contextlib import asynccontextmanager

import bcrypt
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from .config import DATABASE_MODE, DATABASE_URL, SESSION_COOKIE, SESSION_SECRET
from .db import Base, engine, get_db
from .models import User
from .navigation import build_navigation


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


@app.get("/orders", tags=["compatibility"])
def orders(request: Request, db: Session = Depends(get_db)):
    if current_user(request, db) is None:
        return RedirectResponse("/auth/login", status_code=303)
    return {"title": "Заказы", "status": "not_migrated", "message": "Orders feature is pending parity port."}
