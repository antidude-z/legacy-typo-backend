"""The three small dictionaries used by legacy paper/material forms."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import CustomerGroup, Measure, PaperFormat, PaperType


DICTIONARIES = {
    "customer-group": {
        "model": CustomerGroup, "title": "Группы заказчиков", "new": "Новая группа заказчиков",
        "singular": "Группа заказчиков", "prefix": "customer_group", "draft": True,
        "fields": [("title", "Название", "text")],
    },
    "paper-type": {
        "model": PaperType, "title": "Виды бумаги", "new": "Новый вид бумаги",
        "singular": "Вид бумаги", "prefix": "paper_type", "draft": True,
        "fields": [("title", "Название", "text")],
    },
    "paper-format": {
        "model": PaperFormat, "title": "Форматы бумаги", "new": "Новый формат бумаги",
        "singular": "Формат бумаги", "prefix": "paper_format", "draft": True,
        "fields": [("title", "Название", "text"), ("width", "Ширина", "number"), ("height", "Высота", "number")],
    },
    "measures": {
        "model": Measure, "title": "Единицы измерения", "new": "Новая единица измерения",
        "singular": "Единица измерения", "prefix": "measure", "draft": False,
        "fields": [("title", "Название", "text"), ("short", "Сокращение", "text")],
    },
}


def metadata(config):
    return {key: config[key] for key in ("title", "new", "singular", "draft")} | {
        "fields": [{"key": key, "label": label, "type": field_type,
                    "name": f"{config['prefix']}_{key}"} for key, label, field_type in config["fields"]],
    }


def serialize(row, config):
    return {"id": row.id, "deleted": row.deleted_at is not None,
            **{key: getattr(row, key) for key, _, _ in config["fields"]}}


def validate(payload, config):
    values, errors = {}, {}
    for key, label, field_type in config["fields"]:
        name = f"{config['prefix']}_{key}"
        value = payload.get(name, payload.get(key))
        if value is None or isinstance(value, (bool, list, dict)) or not str(value).strip():
            errors[name] = f"Поле «{label}» обязательно."
        elif field_type == "number":
            try:
                numeric = Decimal(str(value))
                if not numeric.is_finite() or numeric != numeric.to_integral_value():
                    raise ValueError()
                values[key] = int(numeric)
            except (InvalidOperation, ValueError):
                errors[name] = f"Поле «{label}» должно содержать целое число."
        else:
            limit = 200 if config["model"] is CustomerGroup else 255 if config["model"] is Measure and key == "title" else 50
            if len(str(value)) > limit:
                errors[name] = f"Поле «{label}»: не более {limit} символов."
            else:
                values[key] = str(value)
    return values, errors


def register_reference_routes(app, current_user):
    def context(kind, request, db):
        user = current_user(request, db)
        if user is None:
            return None, JSONResponse({"error": "unauthorized"}, status_code=401)
        config = DICTIONARIES.get(kind)
        if config is None:
            return None, JSONResponse({"error": "not_found"}, status_code=404)
        return (user, config), None

    @app.get("/api/options/{kind}", tags=["references"])
    def index(kind: str, request: Request, sort: str = "id", order: str = "desc",
              page: int = Query(1, ge=1), per_page: int = Query(30, ge=1), db: Session = Depends(get_db)):
        ctx, error = context(kind, request, db)
        if error is not None:
            return error
        user, config = ctx
        model = config["model"]
        query = select(model)
        if not user.has_permission("view_trashed"):
            query = query.where(model.deleted_at.is_(None))
        allowed = {"id", *[key for key, _, _ in config["fields"]]}
        sort = sort if sort in allowed else "id"
        order = order if order in {"asc", "desc"} else "desc"
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        column = getattr(model, sort)
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc())
                          .offset((page - 1) * per_page).limit(per_page)).all()
        return {"metadata": metadata(config), "items": [serialize(row, config) for row in rows],
                "page": page, "per_page": per_page, "last_page": max(1, (total + per_page - 1) // per_page),
                "total": total, "sort": sort, "order": order,
                "can_restore": user.has_permission("restore_trashed"),
                "can_delete_trashed": user.has_permission("delete_trashed")}

    @app.post("/api/options/{kind}/create", tags=["references"])
    def create_draft(kind: str, request: Request, db: Session = Depends(get_db)):
        ctx, error = context(kind, request, db)
        if error is not None:
            return error
        _, config = ctx
        if not config["draft"]:
            return {"metadata": metadata(config), "item": {"title": "", "short": ""}}
        values = {key: 0 if field_type == "number" else "" for key, _, field_type in config["fields"]}
        row = config["model"](**values)
        db.add(row)
        db.commit()
        return {"metadata": metadata(config), "item": serialize(row, config)}

    @app.post("/api/options/{kind}", tags=["references"])
    def store(kind: str, request: Request, payload: dict, db: Session = Depends(get_db)):
        ctx, error = context(kind, request, db)
        if error is not None:
            return error
        _, config = ctx
        values, errors = validate(payload, config)
        if errors:
            return JSONResponse({"error": "validation", "errors": errors}, status_code=422)
        row = config["model"](**values)
        db.add(row)
        db.commit()
        return {"item": serialize(row, config)}

    @app.get("/api/options/{kind}/{identity}", tags=["references"])
    def detail(kind: str, identity: int, request: Request, db: Session = Depends(get_db)):
        ctx, error = context(kind, request, db)
        if error is not None:
            return error
        user, config = ctx
        row = db.get(config["model"], identity)
        if row is None or (row.deleted_at and not user.has_permission("view_trashed")):
            return JSONResponse({"error": "not_found"}, status_code=404)
        return {"metadata": metadata(config), "item": serialize(row, config)}

    @app.patch("/api/options/{kind}/{identity}", tags=["references"])
    def update(kind: str, identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        ctx, error = context(kind, request, db)
        if error is not None:
            return error
        _, config = ctx
        row = db.get(config["model"], identity)
        if row is None or row.deleted_at:
            return JSONResponse({"error": "not_found"}, status_code=404)
        values, errors = validate(payload, config)
        if errors:
            return JSONResponse({"error": "validation", "errors": errors}, status_code=422)
        for key, value in values.items():
            setattr(row, key, value)
        db.commit()
        return {"item": serialize(row, config)}

    @app.delete("/api/options/{kind}/{identity}", tags=["references"])
    def delete(kind: str, identity: int, request: Request, db: Session = Depends(get_db)):
        ctx, error = context(kind, request, db)
        if error is not None:
            return error
        user, config = ctx
        row = db.get(config["model"], identity)
        if row is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if row.deleted_at:
            if not user.has_permission("delete_trashed"):
                return JSONResponse({"error": "forbidden"}, status_code=403)
            db.delete(row)
        else:
            row.deleted_at = datetime.now()
        db.commit()
        return {"status": "ok"}

    @app.post("/api/options/{kind}/{identity}/restore", tags=["references"])
    def restore(kind: str, identity: int, request: Request, db: Session = Depends(get_db)):
        ctx, error = context(kind, request, db)
        if error is not None:
            return error
        user, config = ctx
        if not user.has_permission("restore_trashed"):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        row = db.get(config["model"], identity)
        if row is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        row.deleted_at = None
        db.commit()
        return {"status": "ok"}