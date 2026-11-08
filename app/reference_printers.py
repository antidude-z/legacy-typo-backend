from datetime import datetime

from fastapi import Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Printer, PrinterProcess


def register_printer_routes(app, current_user):
    @app.get("/api/references/printers", tags=["references"])
    def printer_list(request: Request, page: int = Query(1, ge=1), per_page: int = Query(30, ge=1), sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        user = current_user(request, db)
        if user is None: return JSONResponse({"error": "unauthorized"}, status_code=401)
        query = select(Printer)
        if not user.has_permission("view_trashed"): query = query.where(Printer.deleted_at.is_(None))
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        column = getattr(Printer, sort if sort in {"id", "title"} else "id")
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page - 1) * per_page).limit(per_page)).all()
        return {"items": [{"id": x.id, "title": x.title, "need_imagesetter": x.need_imagesetter, "production": {"book": x.production_book, "poly": x.production_poly, "souvenir": x.production_souvenir, "wide": x.production_wide}, "deleted": x.deleted_at is not None} for x in rows], "page": page, "last_page": max(1, (total + per_page - 1) // per_page), "can_restore": user.has_permission("restore_trashed"), "can_delete_trashed": user.has_permission("delete_trashed")}

    @app.post("/api/references/printers/create", tags=["references"])
    def printer_create(request: Request, db: Session = Depends(get_db)):
        user = current_user(request, db)
        if user is None: return JSONResponse({"error": "unauthorized"}, status_code=401)
        row = Printer(title="", need_imagesetter=False)
        db.add(row); db.commit(); return {"id": row.id}

    @app.get("/api/references/printers/{identity}", tags=["references"])
    def printer_detail(identity: int, request: Request, db: Session = Depends(get_db)):
        user = current_user(request, db)
        if user is None: return JSONResponse({"error": "unauthorized"}, status_code=401)
        row = db.get(Printer, identity)
        if row is None or (row.deleted_at and not user.has_permission("view_trashed")): return JSONResponse({"error": "not_found"}, status_code=404)
        process_query = select(PrinterProcess).where(PrinterProcess.printer_id == row.id)
        if not user.has_permission("view_trashed"):
            process_query = process_query.where(PrinterProcess.deleted_at.is_(None))
        processes = db.scalars(process_query.order_by(PrinterProcess.id)).all()
        return {"item": {"id": row.id, "title": row.title, "need_imagesetter": row.need_imagesetter, "production_book": row.production_book, "production_poly": row.production_poly, "production_souvenir": row.production_souvenir, "production_wide": row.production_wide, "deleted": row.deleted_at is not None}, "processes": [{"id": x.id, "title": x.title, "colors_front": x.colors_front, "colors_back": x.colors_back, "resolution": x.resolution, "rejection": x.rejection} for x in processes], "can_restore": user.has_permission("restore_trashed"), "can_delete_trashed": user.has_permission("delete_trashed")}

    @app.patch("/api/references/printers/{identity}", tags=["references"])
    def printer_update(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        user = current_user(request, db)
        row = db.get(Printer, identity)
        if user is None: return JSONResponse({"error": "unauthorized"}, status_code=401)
        if row is None or row.deleted_at: return JSONResponse({"error": "not_found"}, status_code=404)
        if not isinstance(payload.get("title"), str) or not payload["title"].strip() or len(payload["title"]) > 50: return JSONResponse({"error": "invalid_printer"}, status_code=422)
        flags = ("need_imagesetter", "production_book", "production_poly", "production_souvenir", "production_wide")
        if any(payload.get(field, False) not in (True, False, 0, 1, "0", "1") for field in flags):
            return JSONResponse({"error": "invalid_printer"}, status_code=422)
        row.title = payload["title"]
        for field in ("need_imagesetter", "production_book", "production_poly", "production_souvenir", "production_wide"):
            setattr(row, field, payload.get(field, False) in (True, 1, "1"))
        db.commit(); return {"status": "ok"}

    @app.delete("/api/references/printers/{identity}", tags=["references"])
    def printer_delete(identity: int, request: Request, db: Session = Depends(get_db)):
        user = current_user(request, db); row = db.get(Printer, identity)
        if user is None: return JSONResponse({"error": "unauthorized"}, status_code=401)
        if row is None: return JSONResponse({"error": "not_found"}, status_code=404)
        if row.deleted_at and not user.has_permission("delete_trashed"): return JSONResponse({"error": "forbidden"}, status_code=403)
        if row.deleted_at: db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status": "ok"}

    @app.post("/api/references/printers/{identity}/restore", tags=["references"])
    def printer_restore(identity: int, request: Request, db: Session = Depends(get_db)):
        user = current_user(request, db); row = db.get(Printer, identity)
        if user is None: return JSONResponse({"error": "unauthorized"}, status_code=401)
        if not user.has_permission("restore_trashed"): return JSONResponse({"error": "forbidden"}, status_code=403)
        if row is None: return JSONResponse({"error": "not_found"}, status_code=404)
        row.deleted_at = None; db.commit(); return {"status": "ok"}