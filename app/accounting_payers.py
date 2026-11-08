from datetime import datetime
from decimal import InvalidOperation

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Payer
from .reference_inventory import integer


FIELDS = [("title", "Название", "text"), ("profit", "Комиссия, %", "number"),
          ("phone", "Телефон", "text"), ("inn", "ИНН", "text"),
          ("address", "Адрес", "textarea"), ("description", "Описание", "textarea")]


def payer_values(payload):
    values = {}
    for key, _, _ in FIELDS:
        if key == "profit": continue
        value = payload.get(f"payer_{key}", payload.get(key, ""))
        limit = {"title": 100, "inn": 12, "phone": 200}.get(key)
        if not isinstance(value, str) or (key == "title" and not value.strip()) or (limit and len(value) > limit):
            raise HTTPException(422, f"Некорректное поле: {key}")
        values[key] = value
    try:
        values["profit"] = integer(payload.get("payer_profit", payload.get("profit")))
        if not -32768 <= values["profit"] <= 32767: raise ValueError()
    except (ValueError, TypeError, InvalidOperation):
        raise HTTPException(422, "Введите целую комиссию в допустимом диапазоне.")
    return values


def register_payer_routes(app, current_user):
    def actor(request, db):
        user = current_user(request, db)
        if user is None: raise HTTPException(401)
        return user

    def flags(user):
        return {"can_restore": user.has_permission("restore_trashed"),
                "can_delete_trashed": user.has_permission("delete_trashed")}

    def serialize(row):
        return {"id": row.id, "deleted": row.deleted_at is not None,
                **{key: getattr(row, key) for key, _, _ in FIELDS}}

    def row_for(identity, db):
        row = db.get(Payer, identity)
        if row is None: raise HTTPException(404)
        return row

    @app.get("/api/accounting/payers", tags=["accounting"])
    def index(request: Request, page: int = Query(1, ge=1), per_page: int = Query(30, ge=1), sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        user = actor(request, db)
        query = select(Payer)
        if not user.has_permission("view_trashed"): query = query.where(Payer.deleted_at.is_(None))
        sort = sort if sort in {"id", "title", "profit"} else "id"
        order = order if order in {"asc", "desc"} else "desc"
        column = getattr(Payer, sort)
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page - 1) * per_page).limit(per_page)).all()
        return {"items": [serialize(row) for row in rows], "fields": FIELDS, "page": page,
                "last_page": max(1, (total + per_page - 1) // per_page), "sort": sort, "order": order, **flags(user)}

    @app.get("/api/accounting/payers/form", tags=["accounting"])
    def form(request: Request, db: Session = Depends(get_db)):
        actor(request, db)
        return {"fields": FIELDS}

    @app.get("/api/accounting/payers/{identity}", tags=["accounting"])
    def detail(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request, db); row = row_for(identity, db)
        if row.deleted_at and not user.has_permission("view_trashed"): raise HTTPException(404)
        return {"item": serialize(row), "fields": FIELDS, **flags(user)}

    @app.post("/api/accounting/payers", tags=["accounting"])
    def create(request: Request, payload: dict, db: Session = Depends(get_db)):
        actor(request, db)
        row = Payer(**payer_values(payload)); db.add(row); db.commit()
        return {"id": row.id}

    @app.patch("/api/accounting/payers/{identity}", tags=["accounting"])
    def update(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        actor(request, db); row = row_for(identity, db)
        if row.deleted_at: raise HTTPException(404)
        for key, value in payer_values(payload).items(): setattr(row, key, value)
        db.commit(); return {"status": "ok"}

    @app.delete("/api/accounting/payers/{identity}", tags=["accounting"])
    def delete(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request, db); row = row_for(identity, db)
        if row.deleted_at:
            if not user.has_permission("delete_trashed"): raise HTTPException(403)
            db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status": "ok"}

    @app.post("/api/accounting/payers/{identity}/restore", tags=["accounting"])
    def restore(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request, db)
        if not user.has_permission("restore_trashed"): raise HTTPException(403)
        row = row_for(identity, db); row.deleted_at = None
        db.commit(); return {"status": "ok"}