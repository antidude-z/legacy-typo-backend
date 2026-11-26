from datetime import datetime
from decimal import InvalidOperation
import bcrypt

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Action, Role, User
from .reference_inventory import integer
from .admin_safety import require_surviving_admin, security_writer

ADMIN_PERMISSION = "view_menu_options_permissions"
ROLE_PERMISSION = "user_assign_role"
CREDENTIAL_PERMISSION = "user_reset_credentials"


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
        return {"can_create": user.has_permission("user_create") and user.has_permission(ROLE_PERMISSION), "can_edit": user.has_permission("user_edit"),
                "can_delete": user.has_permission("user_delete"),
                "can_restore": user.has_permission("user_delete") and user.has_permission("restore_trashed"),
                "can_delete_trashed": user.has_permission("user_delete") and user.has_permission("delete_trashed"),
                "can_assign_role": user.has_permission(ROLE_PERMISSION),
                "can_reset_credentials": user.has_permission(CREDENTIAL_PERMISSION)}

    def role_is_assignable(user, role):
        if user.has_permission(ADMIN_PERMISSION):
            return True
        actor_permissions = {permission.id for permission in (user.role.permissions if user.role else [])}
        return {permission.id for permission in (role.permissions if role else [])}.issubset(actor_permissions)

    def can_manage_target(user, row):
        return user.has_permission(ADMIN_PERMISSION) or role_is_assignable(user, row.role)

    def role_choices(user, db):
        if not user.has_permission(ROLE_PERMISSION):
            return []
        return [{"id": role.id, "title": role.title}
                for role in db.scalars(select(Role).order_by(Role.id)).all()
                if role_is_assignable(user, role)]

    def enforce_sensitive_changes(user, row, changes, *, creating=False):
        role_change = creating or changes.get("role_id") != row.role_id
        if role_change:
            # Compare effective grants, never numeric role IDs or titles.
            role = changes.get("_role")
            if not user.has_permission(ROLE_PERMISSION) or not role_is_assignable(user, role):
                raise HTTPException(403, "Недостаточно прав для назначения этой роли.")
            if not creating and user.id == row.id and changes["role_id"] != row.role_id:
                raise HTTPException(403, "Нельзя изменить собственную роль.")
        if not creating and ("password" in changes or changes.get("email") != row.email):
            if not user.has_permission(CREDENTIAL_PERMISSION):
                raise HTTPException(403, "Недостаточно прав для изменения учетных данных.")
        if not creating and "fired" in changes and changes["fired"] != bool(row.fired):
            if not user.has_permission("user_delete"):
                raise HTTPException(403, "Недостаточно прав для изменения статуса сотрудника.")
        if row is not None and not can_manage_target(user, row):
            raise HTTPException(403, "Недостаточно прав для изменения более привилегированной учетной записи.")

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

    def audit_change(db, user, row, changes, *, creating=False):
        # Record IDs and changed field names only: never passwords, hashes,
        # email addresses, reset tokens or other recovery material.
        fields = sorted(key for key in changes if creating or getattr(row, key) != changes[key])
        db.add(Action(user_id=user.id, module='users', item_id=row.id,
                      comment=('Created employee: ' if creating else 'Updated employee: ') + ', '.join(fields),
                      url=f'/references/users/{row.id}/edit'))

    @app.get("/api/employee-references", tags=["references"])
    def index(request: Request, page: int = Query(1,ge=1), per_page: int = Query(30,ge=1), sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        user = actor(request, db, "view_menu_references_users")
        query = select(User)
        if not user.has_permission("view_trashed"): query = query.where(User.deleted_at.is_(None))
        column = getattr(User, sort if sort in {"id","surname","post","phone","email","fired"} else "id")
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page-1)*per_page).limit(per_page)).all()
        return {"items":[serialize(row) for row in rows], "page":page,"last_page":max(1,(total+per_page-1)//per_page), **flags(user)}

    @app.get("/api/employee-references/form", tags=["references"])
    def form(request: Request, db: Session = Depends(get_db)):
        user = actor(request,db,"user_create")
        return {"roles": role_choices(user, db), **flags(user)}

    @app.get("/api/employee-references/{identity}", tags=["references"])
    def detail(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request,db,"view_menu_references_users"); row = account(identity,db)
        if row.deleted_at and not user.has_permission("view_trashed"): raise HTTPException(404)
        capabilities = flags(user)
        allowed = can_manage_target(user, row)
        for key in capabilities:
            if key != 'can_create':
                capabilities[key] = capabilities[key] and bool(allowed)
        capabilities['can_assign_role'] = capabilities['can_assign_role'] and user.id != row.id
        if user.id == row.id:
            capabilities['can_delete'] = False
            capabilities['can_delete_trashed'] = False
            capabilities['can_restore'] = False
        return {"item":serialize(row), "roles": role_choices(user, db) if capabilities['can_edit'] else [], **capabilities}

    @app.post("/api/employee-references", tags=["references"])
    @security_writer
    def create(request: Request, payload: dict, db: Session = Depends(get_db)):
        user = actor(request,db,"user_create")
        changes = values(payload, db)
        changes["_role"] = db.get(Role, changes["role_id"])
        enforce_sensitive_changes(user, None, changes, creating=True)
        changes.pop("_role", None)
        row = User(**changes); db.add(row); db.flush()
        audit_change(db, user, row, changes, creating=True)
        db.commit(); return {"id":row.id}

    @app.patch("/api/employee-references/{identity}", tags=["references"])
    @security_writer
    def update(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        user = actor(request,db,"user_edit"); row = account(identity,db)
        if row.deleted_at: raise HTTPException(404)
        changes = values(payload,db,identity)
        if user.id == row.id and changes["fired"]:
            raise HTTPException(403, "Нельзя уволить собственную учетную запись.")
        changes["_role"] = db.get(Role, changes["role_id"])
        enforce_sensitive_changes(user, row, changes)
        changes.pop("_role", None)
        require_surviving_admin(db, identity=row.id, changes=changes)
        audit_change(db, user, row, changes)
        for key,value in changes.items(): setattr(row,key,value)
        db.commit(); return {"status":"ok"}

    @app.delete("/api/employee-references/{identity}", tags=["references"])
    @security_writer
    def delete(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request,db,"user_delete"); row = account(identity,db)
        if user.id == row.id:
            raise HTTPException(403, "Нельзя удалить собственную учетную запись.")
        if not can_manage_target(user, row):
            raise HTTPException(403, "Недостаточно прав для удаления администратора.")
        require_surviving_admin(db, identity=row.id, removed=True)
        if row.deleted_at:
            if not user.has_permission("delete_trashed"): raise HTTPException(403)
            db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status":"ok"}

    @app.post("/api/employee-references/{identity}/restore", tags=["references"])
    @security_writer
    def restore(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request,db,"user_delete")
        if not user.has_permission("restore_trashed"): raise HTTPException(403)
        row = account(identity,db)
        if not can_manage_target(user, row):
            raise HTTPException(403, "Недостаточно прав для восстановления администратора.")
        row.deleted_at = None; db.commit(); return {"status":"ok"}