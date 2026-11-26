from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .accounting_bills import bill_date
from .db import get_db
from .models import Bill, Payment
from .accounting_authorization import accounting_capabilities, require_accounting_delete


def payment_values(payload):
    try:
        amount = Decimal(str(payload.get("payment_amount", payload.get("amount", 0))))
        if not amount.is_finite() or abs(amount) >= Decimal("100000000") or amount != amount.quantize(Decimal("0.01")):
            raise ValueError()
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(422, "Введите сумму платежа с точностью до копеек.")
    return {"amount": amount, "payment_date": bill_date(payload.get("payment_date"))}


def register_payment_routes(app, current_user):
    def context(bill_id, request, db, edit=False, allow_deleted=False):
        user = current_user(request, db)
        if user is None: raise HTTPException(401)
        if not user.has_permission("edit_accounting_bills" if edit else "view_accounting_bills"):
            raise HTTPException(403)
        bill = db.get(Bill, bill_id)
        if not bill or (bill.deleted_at and (not allow_deleted or not user.has_permission("view_trashed"))):
            raise HTTPException(404)
        return user, bill

    def row_for(bill_id, identity, db):
        row = db.get(Payment, identity)
        if not row or row.bill_id != bill_id: raise HTTPException(404)
        return row

    def flags(user):
        return accounting_capabilities(user)

    @app.get("/api/accounting/bills/{bill_id}/payments/form", tags=["accounting"])
    def form(bill_id: int, request: Request, db: Session = Depends(get_db)):
        user, bill = context(bill_id, request, db, True)
        return {"bill": {"id": bill.id, "number": bill.number},
                "item": {"amount": "", "payment_date": date.today().isoformat()}, **flags(user)}

    @app.get("/api/accounting/bills/{bill_id}/payments/{identity}", tags=["accounting"])
    def detail(bill_id: int, identity: int, request: Request, db: Session = Depends(get_db)):
        user, bill = context(bill_id, request, db, allow_deleted=True)
        row = row_for(bill_id, identity, db)
        if row.deleted_at and not user.has_permission("view_trashed"): raise HTTPException(404)
        return {"bill": {"id": bill.id, "number": bill.number, "deleted": bill.deleted_at is not None},
                "item": {"id": row.id, "amount": str(row.amount), "payment_date": row.payment_date.isoformat(), "deleted": row.deleted_at is not None}, **flags(user)}

    @app.post("/api/accounting/bills/{bill_id}/payments", tags=["accounting"])
    def create(bill_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        context(bill_id, request, db, True)
        row = Payment(bill_id=bill_id, customer_id=0, **payment_values(payload))
        db.add(row); db.commit()
        return {"id": row.id, "location": f"/accounting/bills/{bill_id}/edit"}

    @app.patch("/api/accounting/bills/{bill_id}/payments/{identity}", tags=["accounting"])
    def update(bill_id: int, identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        context(bill_id, request, db, True)
        row = row_for(bill_id, identity, db)
        if row.deleted_at: raise HTTPException(404)
        for key, value in payment_values(payload).items(): setattr(row, key, value)
        db.commit()
        return {"status": "ok", "location": f"/accounting/bills/{bill_id}/edit"}

    @app.delete("/api/accounting/bills/{bill_id}/payments/{identity}", tags=["accounting"])
    def delete(bill_id: int, identity: int, request: Request, db: Session = Depends(get_db)):
        user, _ = context(bill_id, request, db)
        require_accounting_delete(user)
        row = row_for(bill_id, identity, db)
        if row.deleted_at:
            require_accounting_delete(user, 'delete_trashed')
            db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status": "ok"}

    @app.post("/api/accounting/bills/{bill_id}/payments/{identity}/restore", tags=["accounting"])
    def restore(bill_id: int, identity: int, request: Request, db: Session = Depends(get_db)):
        user, _ = context(bill_id, request, db)
        require_accounting_delete(user, 'restore_trashed')
        row = row_for(bill_id, identity, db); row.deleted_at = None
        db.commit(); return {"status": "ok"}