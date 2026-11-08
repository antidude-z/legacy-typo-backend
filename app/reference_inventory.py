from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Measure, Material, Paper, PaperFormat, PaperType


WORK_TYPES = {"print": "Печать", "afterprint": "Постпечать", "compile": "Сборка"}


def integer(value):
    number = Decimal(str(value))
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("Integer required")
    return int(number)


def material_values(payload, db):
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 50:
        raise ValueError("Title required")
    measure_id = integer(payload.get("measure_id"))
    measure = db.get(Measure, measure_id)
    if not measure or measure.deleted_at or payload.get("work_type") not in WORK_TYPES:
        raise ValueError("Invalid measure or work type")
    values = {"title": title, "measure_id": measure_id, "work_type": payload["work_type"], "description": payload.get("description", "")}
    for key in ("production_book", "production_poly", "production_souvenir", "production_wide"):
        if payload.get(key, False) not in (True, False, 0, 1, "0", "1"):
            raise ValueError("Invalid flag")
        values[key] = payload.get(key, False) in (True, 1, "1")
    return values


def auth_user(request, current_user, db):
    user = current_user(request, db)
    return user, None if user else JSONResponse({"error": "unauthorized"}, status_code=401)


def form_options(kind, db):
    if kind == "paper":
        return {
            "types": [{"id": x.id, "title": x.title} for x in db.scalars(select(PaperType).where(PaperType.deleted_at.is_(None)).order_by(PaperType.id)).all()],
            "formats": [{"id": x.id, "title": x.title} for x in db.scalars(select(PaperFormat).where(PaperFormat.deleted_at.is_(None)).order_by(PaperFormat.id)).all()],
        }
    return {"measures": [{"id": x.id, "title": x.title} for x in db.scalars(select(Measure).where(Measure.deleted_at.is_(None)).order_by(Measure.id)).all()], "work_types": WORK_TYPES}


def register_inventory_routes(app, current_user):
    @app.get("/api/references/{kind}/form/options", tags=["references"])
    def inventory_options(kind: str, request: Request, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        if kind not in {"paper", "materials"}: return JSONResponse({"error": "not_found"}, status_code=404)
        return {"metadata": form_options(kind, db)}

    @app.get("/api/references/{kind}/{identity}", tags=["references"])
    def inventory_detail(kind: str, identity: int, request: Request, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        model = {"paper": Paper, "materials": Material}.get(kind)
        row = db.get(model, identity) if model else None
        if row is None or (row.deleted_at and not user.has_permission("view_trashed")):
            return JSONResponse({"error": "not_found"}, status_code=404)
        fields = ("title", "type_id", "format_id", "weight", "markup") if kind == "paper" else ("title", "description", "measure_id", "work_type", "production_book", "production_poly", "production_souvenir", "production_wide")
        return {"item": {"id": row.id, "deleted": row.deleted_at is not None, **{field: getattr(row, field) for field in fields}}, "metadata": form_options(kind, db), "can_restore": user.has_permission("restore_trashed"), "can_delete_trashed": user.has_permission("delete_trashed")}

    @app.get("/api/references/paper", tags=["references"])
    def paper_list(request: Request, page: int = Query(1, ge=1), per_page: int = Query(30, ge=1), sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        query = select(Paper)
        if not user.has_permission("view_trashed"):
            query = query.where(Paper.deleted_at.is_(None))
        column = getattr(Paper, sort if sort in {"id", "title", "type_id", "weight", "format_id"} else "id")
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page - 1) * per_page).limit(per_page)).all()
        return {"items": [{"id": row.id, "title": row.title, "type_id": row.type_id, "type": row.paper_type.title if row.paper_type else "", "format_id": row.format_id, "format": row.paper_format.title if row.paper_format else "", "weight": row.weight, "markup": row.markup, "deleted": row.deleted_at is not None} for row in rows], "metadata": {"types": [{"id": x.id, "title": x.title} for x in db.scalars(select(PaperType).where(PaperType.deleted_at.is_(None)).order_by(PaperType.title)).all()], "formats": [{"id": x.id, "title": x.title} for x in db.scalars(select(PaperFormat).where(PaperFormat.deleted_at.is_(None)).order_by(PaperFormat.title)).all()]}, "page": page, "last_page": max(1, (total + per_page - 1) // per_page), "can_restore": user.has_permission("restore_trashed"), "can_delete_trashed": user.has_permission("delete_trashed")}

    @app.post("/api/references/paper/create", tags=["references"])
    def paper_create(request: Request, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        first_type = db.scalar(select(PaperType).where(PaperType.deleted_at.is_(None)).order_by(PaperType.id))
        first_format = db.scalar(select(PaperFormat).where(PaperFormat.deleted_at.is_(None)).order_by(PaperFormat.id))
        if not first_type or not first_format:
            return JSONResponse({"error": "paper_type_or_format_required"}, status_code=422)
        row = Paper(title=f"{first_type.title} 80 {first_format.title}", type_id=first_type.id, weight=80, format_id=first_format.id, markup=10)
        db.add(row); db.commit(); return {"id": row.id}

    @app.patch("/api/references/paper/{identity}", tags=["references"])
    def paper_update(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        row = db.get(Paper, identity)
        if not row or row.deleted_at: return JSONResponse({"error": "not_found"}, status_code=404)
        try:
            type_id, format_id = integer(payload["type_id"]), integer(payload["format_id"])
            weight, markup = integer(payload["weight"]), integer(payload.get("markup", 10))
        except (KeyError, ValueError, TypeError, InvalidOperation):
            return JSONResponse({"error": "invalid_paper"}, status_code=422)
        paper_type, paper_format = db.get(PaperType, type_id), db.get(PaperFormat, format_id)
        if not paper_type or not paper_format or paper_type.deleted_at or paper_format.deleted_at or weight < 0 or markup < 0:
            return JSONResponse({"error": "invalid_paper"}, status_code=422)
        row.type_id, row.format_id, row.weight, row.markup = type_id, format_id, weight, markup
        row.title = f"{paper_type.title} {weight} {paper_format.title}"
        db.commit(); return {"status": "ok", "title": row.title}

    @app.delete("/api/references/paper/{identity}", tags=["references"])
    def paper_delete(identity: int, request: Request, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        row = db.get(Paper, identity)
        if not row: return JSONResponse({"error": "not_found"}, status_code=404)
        if row.deleted_at and not user.has_permission("delete_trashed"): return JSONResponse({"error": "forbidden"}, status_code=403)
        if row.deleted_at: db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status": "ok"}

    @app.post("/api/references/paper/{identity}/restore", tags=["references"])
    def paper_restore(identity: int, request: Request, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        if not user.has_permission("restore_trashed"): return JSONResponse({"error": "forbidden"}, status_code=403)
        row = db.get(Paper, identity)
        if not row: return JSONResponse({"error": "not_found"}, status_code=404)
        row.deleted_at = None; db.commit(); return {"status": "ok"}

    @app.get("/api/references/materials", tags=["references"])
    def material_list(request: Request, page: int = Query(1, ge=1), per_page: int = Query(30, ge=1), filter_text: str | None = None, filter_type: str | None = None, sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        query = select(Material)
        stored = request.session.get("materials_filter", {})
        filter_text = stored.get("filter_text", "") if filter_text is None else filter_text
        filter_type = stored.get("filter_type", "") if filter_type is None else filter_type
        if not user.has_permission("view_trashed"): query = query.where(Material.deleted_at.is_(None))
        if filter_text: query = query.where(Material.title.ilike(f"%{filter_text}%"))
        if filter_type: query = query.where(Material.work_type == filter_type)
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        column = getattr(Material, sort if sort in {"id", "title", "measure_id", "work_type"} else "id")
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page - 1) * per_page).limit(per_page)).all()
        return {"items": [{"id": x.id, "title": x.title, "description": x.description or "", "measure_id": x.measure_id, "measure": x.measure.short if x.measure else "", "work_type": x.work_type, "work_type_title": WORK_TYPES.get(x.work_type, x.work_type or ""), "production": {"book": x.production_book, "poly": x.production_poly, "souvenir": x.production_souvenir, "wide": x.production_wide}, "deleted": x.deleted_at is not None} for x in rows], "metadata": {"measures": [{"id": x.id, "title": x.title} for x in db.scalars(select(Measure).where(Measure.deleted_at.is_(None)).order_by(Measure.title)).all()], "work_types": WORK_TYPES}, "filter": {"filter_text": filter_text, "filter_type": filter_type}, "page": page, "last_page": max(1, (total + per_page - 1) // per_page), "can_restore": user.has_permission("restore_trashed"), "can_delete_trashed": user.has_permission("delete_trashed")}

    @app.post("/api/references/materials/filter", tags=["references"])
    def material_filter(request: Request, payload: dict, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        if payload.get("flush"):
            request.session.pop("materials_filter", None)
        else:
            request.session["materials_filter"] = {"filter_text": str(payload.get("filter_text", "")), "filter_type": str(payload.get("filter_type", ""))}
        return {"status": "ok"}

    @app.post("/api/references/materials", tags=["references"])
    def material_store(request: Request, payload: dict, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        try:
            values = material_values(payload, db)
        except (ValueError, TypeError, InvalidOperation):
            return JSONResponse({"error": "invalid_material"}, status_code=422)
        row = Material(**values)
        db.add(row); db.commit(); return {"id": row.id}

    @app.patch("/api/references/materials/{identity}", tags=["references"])
    def material_update(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        row = db.get(Material, identity)
        if not row or row.deleted_at: return JSONResponse({"error": "not_found"}, status_code=404)
        try:
            values = material_values(payload, db)
        except (ValueError, TypeError, InvalidOperation):
            return JSONResponse({"error": "invalid_material"}, status_code=422)
        for field, value in values.items():
            setattr(row, field, value)
        db.commit(); return {"status": "ok"}

    @app.delete("/api/references/materials/{identity}", tags=["references"])
    def material_delete(identity: int, request: Request, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        row = db.get(Material, identity)
        if not row: return JSONResponse({"error": "not_found"}, status_code=404)
        if row.deleted_at and not user.has_permission("delete_trashed"): return JSONResponse({"error": "forbidden"}, status_code=403)
        if row.deleted_at: db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status": "ok"}

    @app.post("/api/references/materials/{identity}/restore", tags=["references"])
    def material_restore(identity: int, request: Request, db: Session = Depends(get_db)):
        user, error = auth_user(request, current_user, db)
        if error: return error
        if not user.has_permission("restore_trashed"): return JSONResponse({"error": "forbidden"}, status_code=403)
        row = db.get(Material, identity)
        if not row: return JSONResponse({"error": "not_found"}, status_code=404)
        row.deleted_at = None; db.commit(); return {"status": "ok"}