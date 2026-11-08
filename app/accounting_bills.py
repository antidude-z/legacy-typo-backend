from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Bill, Order, Payer, Payment, User
from .reference_inventory import integer


def bill_date(value):
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try: return datetime.strptime(value, pattern).date()
        except (ValueError, TypeError): pass
    raise HTTPException(422, "Введите корректную дату счета.")


def bill_values(payload, db):
    def get(key, default=None):
        alias = {"user_id":"bill_manager", "payer_id":"bill_payer", "bill_date":"bill_date"}.get(key, f"bill_{key}")
        return payload.get(alias, payload.get(key, default))
    number = get("number")
    if not isinstance(number, str) or not number.strip() or len(number) > 20:
        raise HTTPException(422, "Введите номер счета (до 20 символов).")
    try:
        amount = Decimal(str(get("amount", 0)))
        if not amount.is_finite() or abs(amount) >= Decimal("100000000") or amount != amount.quantize(Decimal("0.01")):
            raise ValueError()
        manager = integer(get("user_id", 0) or 0)
        payer = integer(get("payer_id", 0) or 0)
    except (ValueError, TypeError, InvalidOperation):
        raise HTTPException(422, "Проверьте сумму, менеджера и плательщика.")
    for model, identity in ((User, manager), (Payer, payer)):
        row = db.get(model, identity) if identity else None
        if identity and (not row or row.deleted_at): raise HTTPException(422, "Связанный объект недоступен.")
    currency = get("currency", "RUB")
    if currency not in {"RUB", "USD", "EUR"}: raise HTTPException(422, "Некорректная валюта.")
    values = {"number":number, "bill_date":bill_date(get("bill_date")), "amount":amount,
              "currency":currency, "user_id":manager or None, "payer_id":payer or None}
    for key in ("paid", "closed", "filed"):
        value = get(key, False)
        if value not in (True, False, 0, 1, "0", "1"): raise HTTPException(422, "Некорректный статус счета.")
        values[key] = value in (True, 1, "1")
    return values


def register_bill_routes(app, current_user):
    def actor(request, db, edit=False):
        user = current_user(request, db)
        if user is None: raise HTTPException(401)
        if not user.has_permission("edit_accounting_bills" if edit else "view_accounting_bills"):
            raise HTTPException(403)
        return user

    def flags(user):
        return {"can_edit":user.has_permission("edit_accounting_bills"), "can_restore":user.has_permission("restore_trashed"), "can_delete_trashed":user.has_permission("delete_trashed")}

    def options(db):
        return {"managers":[{"id":x.id,"title":f"{x.surname or ''} {x.name}".strip()} for x in db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.surname)).all()],
                "payers":[{"id":x.id,"title":x.title} for x in db.scalars(select(Payer).where(Payer.deleted_at.is_(None)).order_by(Payer.title)).all()]}

    def paid_sum(identity, db):
        return db.scalar(select(func.sum(Payment.amount)).where(Payment.bill_id == identity, Payment.deleted_at.is_(None))) or Decimal("0")

    def serialize(row, db):
        return {"id":row.id,"number":row.number,"bill_date":row.bill_date.isoformat() if row.bill_date else "",
                "amount":str(row.amount),"currency":row.currency,"user_id":row.user_id or 0,"payer_id":row.payer_id or 0,
                "manager":f"{row.manager.surname or ''} {row.manager.name}".strip() if row.manager else "",
                "payer":row.payer.title if row.payer else "", "paid_sum":str(paid_sum(row.id, db)),
                "paid":row.paid,"closed":row.closed,"filed":row.filed,"deleted":row.deleted_at is not None}

    def row_for(identity, user, db):
        row = db.get(Bill, identity)
        if not row or (row.deleted_at and not user.has_permission("view_trashed")): raise HTTPException(404)
        return row

    @app.get("/api/accounting/bills", tags=["accounting"])
    def index(request: Request, page: int = Query(1,ge=1), per_page: int = Query(30,ge=1), sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        user = actor(request,db)
        query = select(Bill)
        if not user.has_permission("view_trashed"): query = query.where(Bill.deleted_at.is_(None))
        filters = request.session.get("bills_filter", {})
        for key,column in (("filter_manager",Bill.user_id),("filter_payer",Bill.payer_id)):
            if filters.get(key): query = query.where(column == filters[key])
        if filters.get("filter_text"): query = query.where(Bill.number.ilike(f"%{filters['filter_text']}%"))
        if filters.get("filter_date_from"): query = query.where(Bill.bill_date >= bill_date(filters["filter_date_from"]))
        if filters.get("filter_date_to"): query = query.where(Bill.bill_date <= bill_date(filters["filter_date_to"]))
        column = getattr(Bill, sort if sort in {"id","number","bill_date","payer_id","user_id","amount"} else "id")
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page-1)*per_page).limit(per_page)).all()
        return {"items":[serialize(row,db) for row in rows],"metadata":options(db),"filter":filters,"page":page,"last_page":max(1,(total+per_page-1)//per_page),**flags(user)}

    @app.post("/api/accounting/bills/filter", tags=["accounting"])
    def filter_bills(request: Request, payload: dict, db: Session = Depends(get_db)):
        actor(request,db)
        values = {key:payload.get(key, "") for key in ("filter_manager","filter_payer","filter_text","filter_date_from","filter_date_to")}
        if not payload.get("flush"):
            if any(not isinstance(values[key], str) for key in ("filter_text", "filter_date_from", "filter_date_to")):
                raise HTTPException(422, "Некорректные поля фильтра.")
            for key in ("filter_date_from","filter_date_to"):
                if values[key]: values[key] = bill_date(values[key]).isoformat()
            for key in ("filter_manager","filter_payer"):
                try: values[key] = integer(values[key]) if values[key] else ""
                except (ValueError, TypeError, InvalidOperation): raise HTTPException(422)
                if values[key] != "" and values[key] < 0: raise HTTPException(422)
            if values["filter_date_from"] and values["filter_date_to"] and values["filter_date_from"] > values["filter_date_to"]:
                raise HTTPException(422, "Дата начала не может быть позже даты окончания.")
        request.session["bills_filter"] = {} if payload.get("flush") else values
        return {"status":"ok"}

    @app.get("/api/accounting/bills/form", tags=["accounting"])
    def form(request: Request, db: Session = Depends(get_db)):
        actor(request,db,True)
        return {"metadata":options(db)}

    @app.get("/api/accounting/bills/search", tags=["accounting"])
    def search(request: Request, search: str | None = None, db: Session = Depends(get_db)):
        actor(request,db)
        result = [{"id":0,"text":" - Не выбран - "}]
        if search is None: return result
        query = select(Bill).outerjoin(User,User.id == Bill.user_id).outerjoin(Payer,Payer.id == Bill.payer_id).where(Bill.deleted_at.is_(None))
        for token in search.split():
            query = query.where(or_(Bill.number.ilike(f"{token}%"),User.name.ilike(f"{token}%"),User.surname.ilike(f"{token}%"),Payer.title.ilike(f"%{token}%")))
        for row in db.scalars(query.order_by(Bill.number).limit(20)).all():
            manager = f" ({row.manager.surname or ''} {row.manager.name[:1]}.)" if row.manager else ""
            date = row.bill_date.strftime("%d.%m.%Y г.") if row.bill_date else ""
            result.append({"id":row.id,"text":f"{row.number} от {date}{manager}" + (f", {row.payer.title}" if row.payer else "")})
        return result

    @app.get("/api/accounting/bills/{identity}", tags=["accounting"])
    def detail(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request,db); row = row_for(identity,user,db)
        orders = db.scalars(select(Order).where(Order.bill_id == identity,Order.deleted_at.is_(None)).order_by(Order.id)).all()
        query = select(Payment).where(Payment.bill_id == identity)
        if not user.has_permission("view_trashed"): query = query.where(Payment.deleted_at.is_(None))
        return {"item":serialize(row,db),"metadata":options(db),"orders_total":str(sum((x.total for x in orders), Decimal("0.00"))),"orders":[{"id":x.id,"title":x.title,"printing":x.printing,"total":str(x.total),"price":str(x.total/x.printing if x.printing else 0)} for x in orders],
                "payments":[{"id":x.id,"payment_date":x.payment_date.isoformat(),"amount":str(x.amount),"deleted":x.deleted_at is not None} for x in db.scalars(query.order_by(Payment.id)).all()],**flags(user)}

    @app.post("/api/accounting/bills", tags=["accounting"])
    def create(request: Request, payload: dict, db: Session = Depends(get_db)):
        actor(request,db,True); row = Bill(**bill_values(payload,db))
        db.add(row); db.commit(); return {"id":row.id}

    @app.patch("/api/accounting/bills/{identity}", tags=["accounting"])
    def update(identity: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        user = actor(request,db,True); row = row_for(identity,user,db)
        if row.deleted_at: raise HTTPException(404)
        for key,value in bill_values(payload,db).items(): setattr(row,key,value)
        db.commit(); return {"status":"ok"}

    @app.delete("/api/accounting/bills/{identity}", tags=["accounting"])
    def delete(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request,db,True); row = db.get(Bill,identity)
        if not row: raise HTTPException(404)
        if row.deleted_at:
            if not user.has_permission("delete_trashed"): raise HTTPException(403)
            db.delete(row)
        else: row.deleted_at = datetime.now()
        db.commit(); return {"status":"ok"}

    @app.post("/api/accounting/bills/{identity}/restore", tags=["accounting"])
    def restore(identity: int, request: Request, db: Session = Depends(get_db)):
        user = actor(request,db,True)
        if not user.has_permission("restore_trashed"): raise HTTPException(403)
        row = db.get(Bill,identity)
        if not row: raise HTTPException(404)
        row.deleted_at = None; db.commit(); return {"status":"ok"}