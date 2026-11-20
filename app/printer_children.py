"""Scoped printer child editors; no pricing formulas are changed here."""
from datetime import datetime
from decimal import InvalidOperation

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import PaperFormat, Printer, PrinterField, PrinterProcess, PrinterProcessStage
from .reference_inventory import integer
from .printer_authorization import require_printer_action, printer_permissions


FIELDS = {
    "fields": [("paper_format_id", "Формат бумаги", "select"), ("pieces", "Раскрой", "number"),
               ("width", "Ширина печатного поля", "number"), ("height", "Высота печатного поля", "number"),
               ("paper_width", "Ширина после раскроя", "number"), ("paper_height", "Высота после раскроя", "number")],
    "processes": [("title", "Название", "text"), ("rejection", "Отбраковка", "number"),
                  ("colors_front", "Цветность лицо", "number"), ("colors_back", "Цветность оборот", "number"),
                  ("resolution", "Разрешение печати, dpi", "number")],
    "stages": [("title", "Название", "text"), ("together", "В обработке", "number"),
               ("colors", "Цветов за прогон", "number"), ("waste", "Отходы за прогон", "number")],
}
MODELS = {"fields": PrinterField, "processes": PrinterProcess, "stages": PrinterProcessStage}


def child_values(kind, payload, db):
    values = {}
    for key, _, field_type in FIELDS[kind]:
        value = payload.get(key, 0 if key in {"paper_width", "paper_height"} else None)
        if field_type == "text":
            if not isinstance(value, str) or not value.strip() or len(value) > 50:
                raise ValueError("Название обязательно, не более 50 символов")
            values[key] = value
        else:
            values[key] = integer(value)
            if values[key] < 0:
                raise ValueError("Значения не могут быть отрицательными")
    if kind == "fields":
        paper_format = db.get(PaperFormat, values["paper_format_id"])
        if not paper_format or paper_format.deleted_at or values["pieces"] < 1:
            raise ValueError("Выберите формат и положительный раскрой")
    return values


def register_printer_child_routes(app, current_user):
    def context(printer_id, kind, request, db, process_id=None):
        user = require_printer_action(request, current_user(request, db))
        if kind not in MODELS or (kind == "stages") != (process_id is not None):
            raise HTTPException(404, "Not found")
        printer = db.get(Printer, printer_id)
        if not printer or printer.deleted_at:
            raise HTTPException(404, "Printer not found")
        if process_id is not None:
            process = db.get(PrinterProcess, process_id)
            if not process or process.printer_id != printer_id or process.deleted_at:
                raise HTTPException(404, "Process not found")
        return user, MODELS[kind]

    def scoped_row(model, identity, printer_id, process_id, user, db):
        row = db.get(model, identity)
        owner = row.printer_process_id if model is PrinterProcessStage and row else row.printer_id if row else None
        if not row or owner != (process_id if model is PrinterProcessStage else printer_id):
            raise HTTPException(404, "Not found")
        return row

    def serialize(row, kind):
        return {"id": row.id, "deleted": row.deleted_at is not None,
                **{key: getattr(row, key) for key, _, _ in FIELDS[kind]},
                **({"weight": row.weight} if kind == "stages" else {}),
                **({"format_title": row.paper_format.title if row.paper_format else ""} if kind == "fields" else {})}

    @app.get("/api/references/printers/{printer_id}/{kind}/form")
    @app.get("/api/references/printers/{printer_id}/processes/{process_id}/{kind}/form")
    def new_form(printer_id: int, kind: str, request: Request, process_id: int | None = None, db: Session = Depends(get_db)):
        user, _ = context(printer_id, kind, request, db, process_id)
        return {"fields": FIELDS[kind], **printer_permissions(user), "formats": [{"id": x.id, "title": x.title} for x in db.scalars(select(PaperFormat).where(PaperFormat.deleted_at.is_(None)).order_by(PaperFormat.id)).all()]}

    @app.get("/api/references/printers/{printer_id}/{kind}/items")
    @app.get("/api/references/printers/{printer_id}/processes/{process_id}/{kind}/items")
    def listing(printer_id: int, kind: str, request: Request, process_id: int | None = None, db: Session = Depends(get_db)):
        user, model = context(printer_id, kind, request, db, process_id)
        query = select(model).where(model.printer_process_id == process_id) if kind == "stages" else select(model).where(model.printer_id == printer_id)
        if not user.has_permission("view_trashed"):
            query = query.where(model.deleted_at.is_(None))
        rows = db.scalars(query.order_by(model.weight if kind == "stages" else model.id)).all()
        return {"items": [serialize(row, kind) for row in rows], "fields": FIELDS[kind],
                **printer_permissions(user),
                "can_view_prices": user.has_permission("view_menu_prices")}

    @app.post("/api/references/printers/{printer_id}/{kind}/create")
    @app.post("/api/references/printers/{printer_id}/processes/{process_id}/{kind}/create")
    def draft(printer_id: int, kind: str, request: Request, process_id: int | None = None, db: Session = Depends(get_db)):
        user, model = context(printer_id, kind, request, db, process_id)
        if kind == "fields":
            return {"item": {key: 0 for key, _, _ in FIELDS[kind]}, **printer_permissions(user)}
        if kind == "processes":
            row = model(printer_id=printer_id, title="", colors_front=1, colors_back=0, rejection=0, resolution=0)
        else:
            weight = db.scalar(select(func.max(model.weight)).where(model.printer_process_id == process_id, model.deleted_at.is_(None)))
            row = model(printer_process_id=process_id, title="", together=1, colors=1, waste=0, weight=0 if weight is None else weight + 1)
        db.add(row); db.commit()
        return {"item": serialize(row, kind), **printer_permissions(user)}

    @app.post("/api/references/printers/{printer_id}/fields")
    def store_field(printer_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        context(printer_id, "fields", request, db)
        try:
            values = child_values("fields", payload, db)
        except (ValueError, TypeError, InvalidOperation) as error:
            raise HTTPException(422, str(error))
        row = PrinterField(printer_id=printer_id, **values)
        db.add(row); db.commit()
        return {"id": row.id}

    @app.get("/api/references/printers/{printer_id}/{kind}/{identity}")
    @app.get("/api/references/printers/{printer_id}/processes/{process_id}/{kind}/{identity}")
    def detail(printer_id: int, kind: str, identity: int, request: Request, process_id: int | None = None, db: Session = Depends(get_db)):
        user, model = context(printer_id, kind, request, db, process_id)
        row = scoped_row(model, identity, printer_id, process_id, user, db)
        if row.deleted_at and not user.has_permission("view_trashed"):
            raise HTTPException(404, "Not found")
        return {"item": serialize(row, kind), "fields": FIELDS[kind],
                **printer_permissions(user)}

    @app.patch("/api/references/printers/{printer_id}/{kind}/{identity}")
    @app.patch("/api/references/printers/{printer_id}/processes/{process_id}/{kind}/{identity}")
    def update(printer_id: int, kind: str, identity: int, request: Request, payload: dict, process_id: int | None = None, db: Session = Depends(get_db)):
        user, model = context(printer_id, kind, request, db, process_id)
        row = scoped_row(model, identity, printer_id, process_id, user, db)
        if row.deleted_at: raise HTTPException(404, "Not found")
        try:
            values = child_values(kind, payload, db)
        except (ValueError, TypeError, InvalidOperation) as error:
            raise HTTPException(422, str(error))
        for key, value in values.items(): setattr(row, key, value)
        db.commit(); return {"status": "ok"}

    @app.delete("/api/references/printers/{printer_id}/{kind}/{identity}")
    @app.delete("/api/references/printers/{printer_id}/processes/{process_id}/{kind}/{identity}")
    def delete(printer_id: int, kind: str, identity: int, request: Request, process_id: int | None = None, db: Session = Depends(get_db)):
        user, model = context(printer_id, kind, request, db, process_id)
        row = scoped_row(model, identity, printer_id, process_id, user, db)
        if row.deleted_at:
            if not user.has_permission("delete_trashed"): raise HTTPException(403, "Forbidden")
            db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status": "ok"}

    @app.post("/api/references/printers/{printer_id}/{kind}/{identity}/restore")
    @app.post("/api/references/printers/{printer_id}/processes/{process_id}/{kind}/{identity}/restore")
    def restore(printer_id: int, kind: str, identity: int, request: Request, process_id: int | None = None, db: Session = Depends(get_db)):
        user, model = context(printer_id, kind, request, db, process_id)
        if not user.has_permission("restore_trashed"): raise HTTPException(403, "Forbidden")
        row = scoped_row(model, identity, printer_id, process_id, user, db)
        row.deleted_at = None; db.commit(); return {"status": "ok"}