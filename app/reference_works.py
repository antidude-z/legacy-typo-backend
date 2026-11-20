"""Name-only prepress and redaction reference directories."""
from datetime import datetime

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Prepress, Redaction


WORKS = {
    "prepresses": (Prepress, "Работы по дизайну/препресс", "Новая работа по дизайну/препресс", "prepress_title"),
    "redactions": (Redaction, "Работы по редактуре", "Новая работа по редактуре", "redaction_title"),
}
WORK_CAPABILITIES = tuple(
    (f'{action}_reference_{kind}', f'{label} {kind} catalog')
    for kind in WORKS
    for action, label in (('edit', 'Create and edit'), ('delete', 'Delete and restore'))
)


def register_work_routes(app, current_user):
    def context(kind, request, db):
        user = current_user(request, db)
        if user is None: raise HTTPException(401, "Unauthorized")
        if kind not in WORKS: raise HTTPException(404, "Not found")
        required = [f'view_menu_references_{kind}']
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} or request.url.path.endswith('/form-options'):
            lifecycle = request.method == 'DELETE' or request.url.path.endswith('/restore')
            required.append(f'{"delete" if lifecycle else "edit"}_reference_{kind}')
        if not all(user.has_permission(permission) for permission in required):
            raise HTTPException(403, 'Недостаточно прав.')
        return user, WORKS[kind]

    def item(model, identity, db):
        row = db.get(model, identity)
        if row is None: raise HTTPException(404, "Работа не существует")
        return row

    def title_value(payload, field):
        title = payload.get(field, payload.get("title"))
        if not isinstance(title, str) or not title.strip() or len(title) > 50:
            raise HTTPException(422, "Введите название работы (не более 50 символов).")
        return title

    def permissions(user, kind):
        can_delete = user.has_permission(f'delete_reference_{kind}')
        return {"can_edit": user.has_permission(f'edit_reference_{kind}'),
                "can_delete": can_delete,
                "can_restore": can_delete and user.has_permission("restore_trashed"),
                "can_delete_trashed": can_delete and user.has_permission("delete_trashed")}

    @app.get("/api/reference-works/{kind}/form-options", tags=["references"])
    def form_options(kind: str, request: Request, db: Session = Depends(get_db)):
        user, _ = context(kind, request, db)
        return permissions(user, kind)

    @app.get("/api/reference-works/{kind}", tags=["references"])
    def listing(kind: str, request: Request, page: int = Query(1, ge=1), per_page: int = Query(30, ge=1),
                sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        user, (model, heading, new_heading, field) = context(kind, request, db)
        query = select(model)
        if not user.has_permission("view_trashed"): query = query.where(model.deleted_at.is_(None))
        sort = sort if sort in {"id", "title"} else "id"
        order = order if order in {"asc", "desc"} else "desc"
        column = getattr(model, sort)
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc())
                          .offset((page - 1) * per_page).limit(per_page)).all()
        return {"items": [{"id": row.id, "title": row.title, "deleted": row.deleted_at is not None} for row in rows],
                "heading": heading, "new_heading": new_heading, "field": field,
                "page": page, "per_page": per_page, "last_page": max(1, (total + per_page - 1) // per_page),
                "sort": sort, "order": order, **permissions(user, kind)}

    @app.get("/api/reference-works/{kind}/{identity}", tags=["references"])
    def detail(kind: str, identity: int, request: Request, db: Session = Depends(get_db)):
        user, (model, heading, new_heading, field) = context(kind, request, db)
        row = item(model, identity, db)
        if row.deleted_at and not user.has_permission("view_trashed"): raise HTTPException(404)
        return {"item": {"id": row.id, "title": row.title, "deleted": row.deleted_at is not None},
                "heading": heading, "new_heading": new_heading, "field": field, **permissions(user, kind)}

    @app.post("/api/reference-works/{kind}", tags=["references"])
    def create(kind: str, request: Request, payload: dict, db: Session = Depends(get_db)):
        _, (model, _, _, field) = context(kind, request, db)
        row = model(title=title_value(payload, field))
        db.add(row); db.commit()
        return {"id": row.id}

    @app.patch("/api/reference-works/{kind}/{identity}", tags=["references"])
    def update(kind: str, identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        _, (model, _, _, field) = context(kind, request, db)
        row = item(model, identity, db)
        if row.deleted_at: raise HTTPException(404)
        row.title = title_value(payload, field)
        db.commit(); return {"status": "ok"}

    @app.delete("/api/reference-works/{kind}/{identity}", tags=["references"])
    def delete(kind: str, identity: int, request: Request, db: Session = Depends(get_db)):
        user, (model, _, _, _) = context(kind, request, db)
        row = item(model, identity, db)
        if row.deleted_at:
            if not user.has_permission("delete_trashed"): raise HTTPException(403)
            db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status": "ok"}

    @app.post("/api/reference-works/{kind}/{identity}/restore", tags=["references"])
    def restore(kind: str, identity: int, request: Request, db: Session = Depends(get_db)):
        user, (model, _, _, _) = context(kind, request, db)
        if not user.has_permission("restore_trashed"): raise HTTPException(403)
        row = item(model, identity, db)
        row.deleted_at = None; db.commit(); return {"status": "ok"}