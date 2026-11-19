"""Legacy role/permission matrix administration."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Permission, Role, role_permissions
from .permission_audit import audit_payload
from .admin_safety import require_surviving_admin, security_writer


MODULES = {
    "orders": "Заказы",
    "accounting": "Бухгалтерия",
    "system": "Система",
    "users": "Пользователи",
    "prices": "Цены",
    "options": "Настройки",
    "references": "Справочники",
    "reports": "Отчеты",
}


def register_permission_routes(app, current_user):
    def require_admin(request: Request, db: Session):
        user = current_user(request, db)
        if user is None:
            raise HTTPException(401, "Требуется авторизация.")
        if not user.has_permission("view_menu_options_permissions"):
            raise HTTPException(403, "Недостаточно прав для управления разрешениями.")
        return user

    @app.get("/api/options/permissions", tags=["permissions"])
    def matrix(request: Request, db: Session = Depends(get_db)):
        require_admin(request, db)
        roles = db.scalars(select(Role).order_by(Role.id)).all()
        permissions = db.scalars(select(Permission).order_by(Permission.title, Permission.id)).all()
        assigned = {(role_id, permission_id) for role_id, permission_id in db.execute(
            select(role_permissions.c.role_id, role_permissions.c.permission_id)
        ).all()}
        modules = []
        for module_id, module_title in MODULES.items():
            rows = [{
                "id": permission.id,
                "title": permission.title,
                "roles": {str(role.id): (role.id, permission.id) in assigned for role in roles},
            } for permission in permissions if permission.module == module_id]
            if rows:
                modules.append({"id": module_id, "title": module_title, "permissions": rows})
        return {"roles": [{"id": role.id, "title": role.title} for role in roles], "modules": modules}

    @app.get("/api/options/permissions/audit", tags=["permissions"])
    def permission_audit(request: Request, db: Session = Depends(get_db)):
        require_admin(request, db)
        permission_ids = db.scalars(select(Permission.id)).all()
        return audit_payload(permission_ids)

    @app.post("/api/options/permissions", tags=["permissions"])
    @security_writer
    def update_matrix(request: Request, payload: dict, db: Session = Depends(get_db)):
        require_admin(request, db)
        raw = payload.get("permissions")
        if not isinstance(raw, dict):
            raise HTTPException(422, "Матрица разрешений имеет неверный формат.")
        role_ids = set(db.scalars(select(Role.id)).all())
        permission_ids = set(db.scalars(select(Permission.id)).all())
        selected = set()
        for permission_id, roles in raw.items():
            if permission_id not in permission_ids or not isinstance(roles, list):
                raise HTTPException(422, "Неизвестное разрешение или неверный список ролей.")
            for role_id in roles:
                if isinstance(role_id, bool) or not isinstance(role_id, (str, int)):
                    raise HTTPException(422, "Идентификатор роли имеет неверный формат.")
                try:
                    role_id = int(role_id)
                except (TypeError, ValueError):
                    raise HTTPException(422, "Идентификатор роли имеет неверный формат.")
                if role_id not in role_ids:
                    raise HTTPException(422, "Неизвестная роль.")
                selected.add((role_id, permission_id))
        security_permission = "view_menu_options_permissions"
        if security_permission in raw:
            retained = {role_id for role_id, permission_id in selected if permission_id == security_permission}
            require_surviving_admin(db, admin_roles=retained)
        existing_pairs = set(db.execute(select(role_permissions.c.role_id,
                                               role_permissions.c.permission_id)).all())
        additions = selected - existing_pairs
        removals = {pair for pair in existing_pairs if pair[1] in raw} - selected
        # Insert replacement grants before removing old grants. Imported
        # MyISAM cannot roll back a failed DELETE/INSERT replacement sequence.
        if additions:
            db.execute(role_permissions.insert(), [
                {"role_id": role_id, "permission_id": permission_id}
                for role_id, permission_id in additions
            ])
        if removals:
            db.execute(delete(role_permissions).where(or_(*[
                and_(role_permissions.c.role_id == role_id,
                     role_permissions.c.permission_id == permission_id)
                for role_id, permission_id in removals
            ])))
        db.commit()
        return {"status": "ok"}