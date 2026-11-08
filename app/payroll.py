"""Manager payroll statements migrated from the legacy reports/payrolls flow."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Bill, Order, Payroll, PayrollOrder, User
from .php_serialization import loads


def _details(raw):
    if not raw or len(raw) > 5_000_000:
        return {}
    try:
        value = loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, UnicodeError, ArithmeticError, RecursionError):
        return {}


def _number(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _costs(order):
    details = _details(order.calc_details)
    materials = Decimal("0")
    works = Decimal("0")
    contractors = Decimal("0")
    for key in ("design", "redaction"):
        values = details.get(key, [])
        if isinstance(values, dict): values = values.values()
        if isinstance(values, (list, tuple)) or hasattr(values, "__iter__"):
            for item in values:
                if isinstance(item, dict): works += _number(item.get("cost"))
    blanks = details.get("blanks", {})
    if isinstance(blanks, dict):
        for blank in blanks.values():
            if not isinstance(blank, dict): continue
            nested = blank.get("details", {}) if isinstance(blank.get("details"), dict) else {}
            paper = nested.get("paper", {}) if isinstance(nested.get("paper"), dict) else {}
            imagesetter = nested.get("imagesetter", {}) if isinstance(nested.get("imagesetter"), dict) else {}
            materials += _number(paper.get("cost"))
            contractors += _number(imagesetter.get("cost"))
            for afterprint in nested.get("afterprint", []) if isinstance(nested.get("afterprint", []), (list, tuple)) else []:
                blocks = afterprint.values() if isinstance(afterprint, dict) else [afterprint]
                for block in blocks:
                    if not isinstance(block, dict): continue
                    for stage in block.get("stages", []) if isinstance(block.get("stages", []), (list, tuple)) else []:
                        for material in stage.get("materials", {}).values() if isinstance(stage, dict) and isinstance(stage.get("materials"), dict) else []:
                            if isinstance(material, dict): materials += _number(material.get("cost"))
            for compile_row in nested.get("compile", []) if isinstance(nested.get("compile", []), (list, tuple)) else []:
                for stage in compile_row.get("stages", []) if isinstance(compile_row, dict) and isinstance(compile_row.get("stages", []), (list, tuple)) else []:
                    for material in stage.get("materials", {}).values() if isinstance(stage, dict) and isinstance(stage.get("materials"), dict) else []:
                        if isinstance(material, dict): materials += _number(material.get("cost"))
    return materials, works, contractors


def _serialize(row):
    return {"id": row.id, "order_id": row.order_id, "title": row.title, "customer": row.customer,
            "printing": row.printing, "bill_number": row.bill_number,
            "bill_date": row.bill_date.isoformat() if row.bill_date else "",
            "order_date": row.order_date.isoformat() if row.order_date else "",
            "materials": str(row.materials), "works": str(row.works), "contractors": str(row.contractors),
            "total": str(row.total), "percent": str(row.percent), "salary": str(row.salary)}


def register_payroll_routes(app, current_user):
    def actor(request, db, edit=False):
        user = current_user(request, db)
        if user is None: raise HTTPException(401)
        permission = "edit_reports_payrolls" if edit else "view_menu_reports_payrolls"
        if not user.has_permission(permission): raise HTTPException(403)
        return user

    def refresh(row, db):
        existing = {item.order_id: item for item in db.scalars(select(PayrollOrder).where(PayrollOrder.payroll_id == row.id)).all()}
        eligible = db.scalars(select(Order).join(Bill, Bill.id == Order.bill_id).where(Order.user_id == row.user_id, Order.deleted_at.is_(None), Bill.paid.is_(True), Bill.closed.is_(True), Bill.filed.is_(True))).all()
        eligible_ids = set()
        for order in eligible:
            if not order.bill: continue
            eligible_ids.add(order.id)
            materials, works, contractors = _costs(order)
            item = existing.get(order.id)
            if item is None:
                item = PayrollOrder(payroll_id=row.id, order_id=order.id, percent=3)
                db.add(item)
            item.title = order.title; item.customer = order.customer.title if order.customer else ""; item.printing = order.printing
            item.bill_number = order.bill.number; item.bill_date = order.bill.bill_date; item.order_date = order.order_date
            item.materials = materials; item.works = works; item.contractors = contractors; item.total = order.total
            item.salary = (Decimal(order.total or 0) - materials - works) * Decimal(item.percent or 0) / 100
        for order_id, item in existing.items():
            if order_id not in eligible_ids: db.delete(item)
        db.flush()

    def serialize(row, db):
        items = db.scalars(select(PayrollOrder).where(PayrollOrder.payroll_id == row.id).order_by(PayrollOrder.order_id)).all()
        return {"id": row.id, "user_id": row.user_id, "manager": f"{row.manager.surname or ''} {row.manager.name}".strip() if row.manager else "",
                "salary": str(row.salary), "period": row.period.isoformat(), "status": row.status,
                "orders": [_serialize(item) for item in items],
                "total": str(sum((_number(item.total) for item in items), Decimal("0"))),
                "orders_salary": str(sum((_number(item.salary) for item in items), Decimal("0"))),
                "month_salary": str(_number(row.salary) + sum((_number(item.salary) for item in items), Decimal("0")))}

    @app.get("/api/reports/payrolls/form", tags=["reports"])
    def form(request: Request, db: Session = Depends(get_db)):
        actor(request, db)
        return {"managers": [{"id": user.id, "title": f"{user.surname or ''} {user.name}".strip()} for user in db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.surname)).all()]}

    @app.post("/api/reports/payrolls", tags=["reports"])
    def create(request: Request, payload: dict, db: Session = Depends(get_db)):
        actor(request, db, True)
        try:
            manager_id = int(payload.get("manager_id")); year = int(payload.get("year")); month = int(payload.get("month"))
            period = date(year, month, 1)
        except (TypeError, ValueError): raise HTTPException(422, "Проверьте менеджера, месяц и год.")
        manager = db.get(User, manager_id)
        if not manager or manager.deleted_at: raise HTTPException(422, "Менеджер недоступен.")
        row = db.scalar(select(Payroll).where(Payroll.user_id == manager_id, Payroll.period == period, Payroll.status == "calc"))
        if row is None: row = Payroll(user_id=manager_id, period=period, salary=0, status="calc"); db.add(row); db.flush()
        refresh(row, db); db.commit()
        return {"id": row.id}

    @app.get("/api/reports/payrolls/{identity}", tags=["reports"])
    def detail(identity: int, request: Request, db: Session = Depends(get_db)):
        actor(request, db); row = db.get(Payroll, identity)
        if not row: raise HTTPException(404)
        refresh(row, db) if row.status == "calc" else None
        db.commit()
        return {"item": serialize(row, db), "markups": list(range(16))}

    @app.patch("/api/reports/payrolls/{identity}", tags=["reports"])
    def update(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        actor(request, db, True); row = db.get(Payroll, identity)
        if not row: raise HTTPException(404)
        if row.status == "calc":
            try: row.salary = _number(payload.get("salary", 0))
            except (ValueError, TypeError): raise HTTPException(422, "Некорректный оклад.")
            for item_id, percent in (payload.get("markups", {}) or {}).items():
                item = db.get(PayrollOrder, int(item_id))
                if item and item.payroll_id == row.id:
                    value = _number(percent)
                    if value < 0 or value > 15: raise HTTPException(422, "Процент должен быть от 0 до 15.")
                    item.percent = value; item.salary = (_number(item.total) - _number(item.materials) - _number(item.works)) * value / 100
        status = payload.get("status", row.status)
        if status not in {"calc", "paid"}: raise HTTPException(422, "Некорректный статус ведомости.")
        row.status = status; db.commit(); return {"status": "ok"}