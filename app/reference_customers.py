from datetime import datetime
from decimal import InvalidOperation

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Customer, CustomerGroup
from .reference_inventory import integer


FIELDS = [("title", "Название", "text"), ("customer_group_id", "Группа", "select"),
          ("phone", "Телефон", "text"), ("inn", "ИНН", "text"),
          ("address", "Адрес", "textarea"), ("description", "Описание", "textarea")]


def register_customer_routes(app, current_user):
    def user_for(request, db):
        user = current_user(request, db)
        if user is None: raise HTTPException(401)
        return user

    def permissions(user):
        return {"can_restore": user.has_permission("restore_trashed"), "can_delete_trashed": user.has_permission("delete_trashed")}

    def serialize(row):
        return {"id": row.id, "deleted": row.deleted_at is not None,
                "group_title": row.group.title if row.group and not row.group.deleted_at else "",
                **{key: getattr(row, key) for key, _, _ in FIELDS}}

    def options(db):
        return [{"id": row.id, "title": row.title} for row in db.scalars(select(CustomerGroup).where(CustomerGroup.deleted_at.is_(None)).order_by(CustomerGroup.id)).all()]

    def row_for(identity, db):
        row = db.get(Customer, identity)
        if row is None: raise HTTPException(404)
        return row

    def values(payload, db, existing=None):
        result = {}
        for key, _, _ in FIELDS:
            if key == "customer_group_id": continue
            value = payload.get(f"customer_{key}", payload.get(key, ""))
            limit = {"title":100, "inn":12, "phone":200}.get(key)
            if not isinstance(value, str) or (key == "title" and not value.strip()) or (limit and len(value) > limit):
                raise HTTPException(422, f"Некорректное поле: {key}")
            result[key] = value
        try:
            group_id = integer(payload.get("customer_group", payload.get("customer_group_id", 0)) or 0)
        except (ValueError, TypeError, InvalidOperation): raise HTTPException(422, "Выберите группу")
        if group_id:
            group = db.get(CustomerGroup, group_id)
            if (not group or group.deleted_at) and not (existing and existing.customer_group_id == group_id):
                raise HTTPException(422, "Группа не существует")
        result["customer_group_id"] = group_id or None
        return result

    @app.get("/api/customer-references", tags=["references"])
    def index(request: Request, page: int = Query(1, ge=1), per_page: int = Query(30, ge=1), sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        user = user_for(request, db)
        query = select(Customer)
        if not user.has_permission("view_trashed"): query = query.where(Customer.deleted_at.is_(None))
        column = getattr(Customer, sort if sort in {"id", "title", "customer_group_id"} else "id")
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page - 1) * per_page).limit(per_page)).all()
        return {"items": [serialize(row) for row in rows], "fields": FIELDS,
                "page": page, "last_page": max(1, (total + per_page - 1) // per_page), **permissions(user)}

    @app.get("/api/customer-references/form", tags=["references"])
    def form(request: Request, db: Session = Depends(get_db)):
        user_for(request, db)
        return {"fields": FIELDS, "groups": options(db)}

    @app.get("/api/customer-references/{identity}", tags=["references"])
    def detail(identity: int, request: Request, db: Session = Depends(get_db)):
        user = user_for(request, db); row = row_for(identity, db)
        if row.deleted_at and not user.has_permission("view_trashed"): raise HTTPException(404)
        return {"item": serialize(row), "fields": FIELDS, "groups": options(db), **permissions(user)}

    @app.post("/api/customer-references", tags=["references"])
    def create(request: Request, payload: dict, db: Session = Depends(get_db)):
        user_for(request, db)
        row = Customer(**values(payload, db)); db.add(row); db.commit()
        return {"id": row.id}

    @app.patch("/api/customer-references/{identity}", tags=["references"])
    def update(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        user_for(request, db); row = row_for(identity, db)
        if row.deleted_at: raise HTTPException(404)
        for key, value in values(payload, db, existing=row).items(): setattr(row, key, value)
        db.commit(); return {"status":"ok"}

    @app.delete("/api/customer-references/{identity}", tags=["references"])
    def delete(identity: int, request: Request, db: Session = Depends(get_db)):
        user = user_for(request, db); row = row_for(identity, db)
        if row.deleted_at:
            if not user.has_permission("delete_trashed"): raise HTTPException(403)
            db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status":"ok"}

    @app.post("/api/customer-references/{identity}/restore", tags=["references"])
    def restore(identity: int, request: Request, db: Session = Depends(get_db)):
        user = user_for(request, db)
        if not user.has_permission("restore_trashed"): raise HTTPException(403)
        row = row_for(identity, db); row.deleted_at = None
        db.commit(); return {"status":"ok"}