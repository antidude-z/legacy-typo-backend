"""Compilation reference definitions and scoped stage/material editors."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Compile, CompileStage, CompileStageMaterial, Material
from .orders import resolve_price
from .reference_inventory import integer


STAGE_FIELDS = [("title", "Название", "text"), ("together", "В обработке", "number"),
                ("waste", "Отходы за прогон", "number"), ("fitting", "Этап является приладкой", "checkbox")]
MATERIAL_FIELDS = [("material_id", "Материал", "select"), ("quantity", "Количество", "decimal")]
PRODUCTIONS = ("book", "poly", "souvenir", "wide")


def definition_values(payload):
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 50:
        raise HTTPException(422, "Введите название (не более 50 символов).")
    try:
        fitting = integer(payload.get("fitting", 0))
        if fitting < 0: raise ValueError()
    except (ValueError, TypeError, InvalidOperation):
        raise HTTPException(422, "Количество листов на приладку должно быть неотрицательным целым числом.")
    values = {"title": title, "fitting": fitting}
    for key in PRODUCTIONS:
        field = f"production_{key}"
        if payload.get(field, False) not in (True, False, 0, 1, "0", "1"):
            raise HTTPException(422, "Некорректный тип продукции.")
        values[field] = payload.get(field, False) in (True, 1, "1")
    return values


def stage_values(payload):
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("Введите название (не более 200 символов).")
    values = {"title": title}
    for field in ("together", "waste"):
        values[field] = integer(payload.get(field, 0))
        if values[field] < 0:
            raise ValueError("Значения не могут быть отрицательными.")
    if payload.get("fitting", False) not in (True, False, 0, 1, "0", "1"):
        raise ValueError("Некорректное значение приладки.")
    values["fitting"] = payload.get("fitting", False) in (True, 1, "1")
    return values


def register_compile_routes(app, current_user):
    def user_for(request, db):
        user = current_user(request, db)
        if user is None: raise HTTPException(401, "Unauthorized")
        return user

    def parent(identity, db, user):
        row = db.get(Compile, identity)
        if not row or (row.deleted_at and not user.has_permission("view_trashed")):
            raise HTTPException(404, "Compile not found")
        return row

    def stage_for(identity, stage_id, db, user, include_deleted=False):
        parent(identity, db, user)
        stage = db.get(CompileStage, stage_id)
        if not stage or stage.compile_id != identity or (stage.deleted_at and not include_deleted and not user.has_permission("view_trashed")):
            raise HTTPException(404, "Stage not found")
        return stage

    def permissions(user):
        return {"can_restore": user.has_permission("restore_trashed"), "can_delete_trashed": user.has_permission("delete_trashed"), "can_view_prices": user.has_permission("view_menu_prices")}

    def stage_data(row):
        return {"id": row.id, "deleted": row.deleted_at is not None, "weight": row.weight,
                **{field: getattr(row, field) for field, _, _ in STAGE_FIELDS}}

    def materials_for(reference, db):
        flags = [getattr(Material, f"production_{key}").is_(True) for key in PRODUCTIONS if getattr(reference, f"production_{key}")]
        if not flags: return []
        return db.scalars(select(Material).where(Material.deleted_at.is_(None), or_(*flags)).order_by(Material.title)).all()

    def material_values(payload, reference, db):
        identity = integer(payload.get("material_id"))
        if identity not in {row.id for row in materials_for(reference, db)}:
            raise ValueError("Выберите материал для данного типа продукции.")
        quantity = Decimal(str(payload.get("quantity")))
        if not quantity.is_finite() or quantity < 0 or quantity >= Decimal("1000000") or quantity != quantity.quantize(Decimal("0.0001")):
            raise ValueError("Количество должно быть неотрицательным числом с точностью до четырёх знаков.")
        return {"material_id": identity, "quantity": quantity}

    def assignment_data(row):
        return {"id": row.id, "material_id": row.material_id, "title": row.material.title if row.material else "",
                "quantity": str(row.quantity), "deleted": row.deleted_at is not None}

    @app.get("/api/references/compiles", tags=["references"])
    def index(request: Request, page: int = Query(1, ge=1), per_page: int = Query(30, ge=1), sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        user = user_for(request, db)
        query = select(Compile)
        if not user.has_permission("view_trashed"): query = query.where(Compile.deleted_at.is_(None))
        column = getattr(Compile, sort if sort in {"id", "title"} else "id")
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page - 1) * per_page).limit(per_page)).all()
        return {"items": [{"id": row.id, "title": row.title, "fitting": row.fitting, "deleted": row.deleted_at is not None, "production": {key: getattr(row, f"production_{key}") for key in PRODUCTIONS}} for row in rows],
                "page": page, "last_page": max(1, (total + per_page - 1) // per_page), **permissions(user)}

    @app.post("/api/references/compiles", tags=["references"])
    def create(request: Request, payload: dict, db: Session = Depends(get_db)):
        user_for(request, db)
        row = Compile(**definition_values(payload))
        db.add(row); db.commit(); return {"id": row.id}

    @app.delete("/api/references/compiles/{identity}", tags=["references"])
    def definition_delete(identity: int, request: Request, db: Session = Depends(get_db)):
        user = user_for(request, db)
        row = db.get(Compile, identity)
        if row is None: raise HTTPException(404)
        if row.deleted_at:
            if not user.has_permission("delete_trashed"): raise HTTPException(403)
            db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status": "ok"}

    @app.post("/api/references/compiles/{identity}/restore", tags=["references"])
    def definition_restore(identity: int, request: Request, db: Session = Depends(get_db)):
        user = user_for(request, db)
        if not user.has_permission("restore_trashed"): raise HTTPException(403)
        row = db.get(Compile, identity)
        if row is None: raise HTTPException(404)
        row.deleted_at = None; db.commit(); return {"status": "ok"}

    @app.get("/api/references/compiles/{identity}", tags=["references"])
    def detail(identity: int, request: Request, db: Session = Depends(get_db)):
        user = user_for(request, db)
        row = parent(identity, db, user)
        query = select(CompileStage).where(CompileStage.compile_id == identity)
        if not user.has_permission("view_trashed"): query = query.where(CompileStage.deleted_at.is_(None))
        stages = db.scalars(query.order_by(CompileStage.weight, CompileStage.id)).all()
        return {"item": {"id": row.id, "title": row.title, "fitting": row.fitting, **{f"production_{key}": getattr(row, f"production_{key}") for key in PRODUCTIONS}, "deleted": row.deleted_at is not None},
                "stages": [stage_data(stage) | {"price": str(resolve_price(db, "App\\CompileStage", stage.id)["amount"])} for stage in stages],
                **permissions(user)}

    @app.patch("/api/references/compiles/{identity}", tags=["references"])
    def update(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        row = parent(identity, db, user_for(request, db))
        if row.deleted_at: raise HTTPException(404)
        values = definition_values(payload)
        for key, value in values.items(): setattr(row, key, value)
        db.commit(); return {"status": "ok"}

    @app.get("/api/references/compiles/{identity}/stages/form", tags=["references"])
    def stage_form(identity: int, request: Request, db: Session = Depends(get_db)):
        parent(identity, db, user_for(request, db))
        return {"fields": STAGE_FIELDS, "item": {"title": "", "together": 1, "waste": 0, "fitting": False}}

    @app.post("/api/references/compiles/{identity}/stages", tags=["references"])
    def stage_create(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        parent(identity, db, user_for(request, db))
        try: values = stage_values(payload)
        except (ValueError, TypeError, InvalidOperation) as error: raise HTTPException(422, str(error))
        weight = db.scalar(select(func.max(CompileStage.weight)).where(CompileStage.compile_id == identity, CompileStage.deleted_at.is_(None)))
        row = CompileStage(compile_id=identity, weight=0 if weight is None else weight + 1, **values)
        db.add(row); db.commit(); return {"id": row.id}

    @app.get("/api/references/compiles/{identity}/stages/{stage_id}", tags=["references"])
    def stage_detail(identity: int, stage_id: int, request: Request, db: Session = Depends(get_db)):
        user = user_for(request, db); stage = stage_for(identity, stage_id, db, user)
        query = select(CompileStageMaterial).where(CompileStageMaterial.compile_stage_id == stage_id)
        if not user.has_permission("view_trashed"): query = query.where(CompileStageMaterial.deleted_at.is_(None))
        return {"item": stage_data(stage), "fields": STAGE_FIELDS,
                "materials": [assignment_data(row) for row in db.scalars(query.order_by(CompileStageMaterial.id)).all()], **permissions(user)}

    @app.patch("/api/references/compiles/{identity}/stages/{stage_id}", tags=["references"])
    def stage_update(identity: int, stage_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        stage = stage_for(identity, stage_id, db, user_for(request, db))
        if stage.deleted_at: raise HTTPException(404)
        try: values = stage_values(payload)
        except (ValueError, TypeError, InvalidOperation) as error: raise HTTPException(422, str(error))
        for key, value in values.items(): setattr(stage, key, value)
        db.commit(); return {"status": "ok"}

    @app.get("/api/references/compiles/{identity}/stages/{stage_id}/materials/form", tags=["references"])
    def material_form(identity: int, stage_id: int, request: Request, db: Session = Depends(get_db)):
        user = user_for(request, db); stage_for(identity, stage_id, db, user)
        reference = parent(identity, db, user)
        return {"fields": MATERIAL_FIELDS, "choices": [{"id": row.id, "title": row.title} for row in materials_for(reference, db)], "item": {"material_id": "", "quantity": "0"}}

    @app.post("/api/references/compiles/{identity}/stages/{stage_id}/materials", tags=["references"])
    def material_create(identity: int, stage_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        user = user_for(request, db); stage = stage_for(identity, stage_id, db, user)
        if stage.deleted_at: raise HTTPException(404)
        try: values = material_values(payload, parent(identity, db, user), db)
        except (ValueError, TypeError, InvalidOperation) as error: raise HTTPException(422, str(error))
        row = CompileStageMaterial(compile_stage_id=stage_id, **values)
        db.add(row); db.commit(); return {"id": row.id}

    def assignment(identity, stage_id, item_id, db, user):
        stage_for(identity, stage_id, db, user)
        row = db.get(CompileStageMaterial, item_id)
        if not row or row.compile_stage_id != stage_id: raise HTTPException(404)
        return row

    @app.get("/api/references/compiles/{identity}/stages/{stage_id}/materials/{item_id}", tags=["references"])
    def material_detail(identity: int, stage_id: int, item_id: int, request: Request, db: Session = Depends(get_db)):
        user = user_for(request, db); row = assignment(identity, stage_id, item_id, db, user)
        if row.deleted_at and not user.has_permission("view_trashed"): raise HTTPException(404)
        return {"item": assignment_data(row), "fields": MATERIAL_FIELDS, **permissions(user)}

    @app.patch("/api/references/compiles/{identity}/stages/{stage_id}/materials/{item_id}", tags=["references"])
    def material_update(identity: int, stage_id: int, item_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        user = user_for(request, db); row = assignment(identity, stage_id, item_id, db, user)
        if row.deleted_at: raise HTTPException(404)
        try: values = material_values(payload, parent(identity, db, user), db)
        except (ValueError, TypeError, InvalidOperation) as error: raise HTTPException(422, str(error))
        for key, value in values.items(): setattr(row, key, value)
        db.commit(); return {"status": "ok"}

    @app.delete("/api/references/compiles/{identity}/stages/{stage_id}", tags=["references"])
    @app.delete("/api/references/compiles/{identity}/stages/{stage_id}/materials/{item_id}", tags=["references"])
    def delete(identity: int, stage_id: int, request: Request, item_id: int | None = None, db: Session = Depends(get_db)):
        user = user_for(request, db)
        row = stage_for(identity, stage_id, db, user, True) if item_id is None else assignment(identity, stage_id, item_id, db, user)
        if row.deleted_at:
            if not user.has_permission("delete_trashed"): raise HTTPException(403)
            db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status": "ok"}

    @app.post("/api/references/compiles/{identity}/stages/{stage_id}/restore", tags=["references"])
    @app.post("/api/references/compiles/{identity}/stages/{stage_id}/materials/{item_id}/restore", tags=["references"])
    def restore(identity: int, stage_id: int, request: Request, item_id: int | None = None, db: Session = Depends(get_db)):
        user = user_for(request, db)
        if not user.has_permission("restore_trashed"): raise HTTPException(403)
        row = stage_for(identity, stage_id, db, user, True) if item_id is None else assignment(identity, stage_id, item_id, db, user)
        row.deleted_at = None; db.commit(); return {"status": "ok"}