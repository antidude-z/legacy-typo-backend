from datetime import datetime
from decimal import InvalidOperation
import bcrypt

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Role, User
from .reference_inventory import integer


def serialize(row):
    return {"id": row.id, "name": row.name, "surname": row.surname or "", "email": row.email,
            "phone": row.phone or "", "post": row.post or "", "role_id": row.role_id,
            "fired": bool(row.fired), "deleted": row.deleted_at is not None}


def register_user_reference_routes(app, current_user):
    def actor(request, db, permission=None):
        user = current_user(request, db)
        if not user: raise HTTPException(401)
        if permission and not user.has_permission(permission): raise HTTPException(403)
        return user

    def account(identity, db):
        row = db.get(User, identity)
        if not row: raise HTTPException(404)
        return row

    def flags(user):
        return {"can_create": user.has_permission("user_create"), "can_edit": user.has_permission("user_edit"),
                "can_restore": user.has_permission("restore_trashed"), "can_delete_trashed": user.has_permission("delete_trashed")}

    def values(payload, db, identity=None):
        result = {}
        errors = {}
        for key, limit in (("name",255), ("surname",50), ("phone",50), ("email",255), ("post",50)):
            value = payload.get(f"user_{key}", payload.get(key))
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                errors[f"user_{key}"] = "Поле обязательно; проверьте длину."
            else: result[key] = value
        if "email" in result:
            query = select(User.id).where(User.email == result["email"])
            if identity is not None: query = query.where(User.id != identity)
            if db.scalar(query) is not None: errors["user_email"] = "Этот e-mail уже используется."
        try:
            role_id = integer(payload.get("user_role", payload.get("role_id")))
            if not db.get(Role, role_id): raise ValueError()
            result["role_id"] = role_id
        except (ValueError, TypeError, InvalidOperation):
            errors["user_role"] = "Выберите существующую роль."
        change = payload.get("user_change_password", payload.get("change_password", False)) in (True,1,"1")
        if identity is None or change:
            password = payload.get("user_password", payload.get("password", ""))
            confirmation = payload.get("user_password_confirmation", payload.get("password_confirmation", ""))
            if not isinstance(password, str) or len(password) < 6 or len(password.encode("utf-8")) > 72 or password != confirmation:
                errors["user_password"] = "Пароль: минимум 6 символов, максимум 72 байта; повтор должен совпадать."
            else: result["password"] = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        fired = payload.get("user_fired", payload.get("fired", False))
        if fired not in (True,False,0,1,"0","1"): errors["user_fired"] = "Некорректный флаг."
        result["fired"] = int(identity is not None and fired in (True,1,"1"))
        if errors: raise HTTPException(422, errors)
        return result

    @app.get("/api/employee-references", tags=["references"])
    def index(request: Request, page: int = Query(1,ge=1), per_page: int = Query(30,ge=1), sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        user = actor(request, db)
        query = select(User)
        if not user.has_permission("view_trashed"): query = query.where(User.deleted_at.is_(None))
        column = getattr(User, sort if sort in {"id","surname","post","phone","email","fired"} else "id")
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page-1)*per_page).limit(per_page)).all()
        return {"items":[serialize(row) for row in rows], "page":page,"last_page":max(1,(total+per_page-1)//per_page), **flags(user)}

    @app.get("/api/employee-references/form", tags=["references"])
    def form(request: Request, db: Session = Depends(get_db)):
        actor(request,db,"user_create")
        return {"roles":[{"id":row.id,"title":row.title} for row in db.scalars(select(Role).order_by(Role.id)).all()]}

    @app.get("/api/employee-references/{identity}", tags=["references"])
    def detail(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request,db); row = account(identity,db)
        if row.deleted_at and not user.has_permission("view_trashed"): raise HTTPException(404)
        return {"item":serialize(row), "roles":[{"id":r.id,"title":r.title} for r in db.scalars(select(Role).order_by(Role.id)).all()] if user.has_permission("user_edit") else [], **flags(user)}

    @app.post("/api/employee-references", tags=["references"])
    def create(request: Request, payload: dict, db: Session = Depends(get_db)):
        actor(request,db,"user_create")
        row = User(**values(payload,db)); db.add(row); db.commit(); return {"id":row.id}

    @app.patch("/api/employee-references/{identity}", tags=["references"])
    def update(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        actor(request,db,"user_edit"); row = account(identity,db)
        if row.deleted_at: raise HTTPException(404)
        for key,value in values(payload,db,identity).items(): setattr(row,key,value)
        db.commit(); return {"status":"ok"}

    @app.delete("/api/employee-references/{identity}", tags=["references"])
    def delete(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request,db); row = account(identity,db)
        if row.deleted_at:
            if not user.has_permission("delete_trashed"): raise HTTPException(403)
            db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status":"ok"}

    @app.post("/api/employee-references/{identity}/restore", tags=["references"])
    def restore(identity: int, request: Request, db: Session = Depends(get_db)):
        actor(request,db,"restore_trashed"); row = account(identity,db)
        row.deleted_at = None; db.commit(); return {"status":"ok"}