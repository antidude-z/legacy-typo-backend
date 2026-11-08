"""Report catalog/settings and first migrated renderer (HTML transcript)."""
from html import escape
import json

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Bill, Order, OrderStatus, Report, ReportParam
from .php_serialization import loads


MODELS = {"orders": (Order, "App\\Order"), "bills": (Bill, "App\\Bill")}


def serialize_report(row):
    return {"id": row.id, "title": row.title, "program": row.program, "kind": row.kind,
            "model": row.model, "model_title": row.model_title, "format": row.format,
            "orientation": row.orientation, "form": row.form, "download": row.download,
            "prohibitions": [x for x in row.prohibitions.split(",") if x]}


def php_print_r(value, depth=0):
    """PHP print_r-style scalar-array presentation, not executable markup."""
    if isinstance(value, dict):
        indent = "    " * depth
        lines = ["Array", f"{indent}("]
        for key, item in value.items():
            rendered = php_print_r(item, depth + 1)
            lines.append(f"{indent}    [{key}] => {rendered}")
            if isinstance(item, dict): lines.append("")
        lines.append(f"{indent})")
        return "\n".join(lines)
    if value is None or value is False: return ""
    if value is True: return "1"
    return str(value)


def register_report_routes(app, current_user):
    def actor(request, db, settings=False):
        user = current_user(request, db)
        if user is None: raise HTTPException(401)
        if settings and not user.has_permission("view_menu_options_reports"): raise HTTPException(403)
        return user

    def report_for(identity, db):
        row = db.get(Report, identity)
        if not row or row.deleted_at: raise HTTPException(404, "Шаблон документа не существует.")
        return row

    def params_for(identity, db):
        return db.scalars(select(ReportParam).where(ReportParam.report_id == identity, ReportParam.deleted_at.is_(None)).order_by(ReportParam.id)).all()

    def param_data(row):
        return {"id":row.id,"alias":row.alias,"title":row.title,"value":row.value,"html":row.html}

    @app.get("/api/report-settings", tags=["reports"])
    def index(request: Request, page: int = Query(1,ge=1), per_page: int = Query(30,ge=1), sort: str = "id", order: str = "desc", db: Session = Depends(get_db)):
        actor(request,db,True)
        query = select(Report).where(Report.deleted_at.is_(None))
        column = getattr(Report,sort if sort in {"id","title","model_title","format","orientation"} else "id")
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(column.asc() if order == "asc" else column.desc()).offset((page-1)*per_page).limit(per_page)).all()
        return {"items":[serialize_report(row) for row in rows],"page":page,"last_page":max(1,(total+per_page-1)//per_page)}

    @app.get("/api/report-settings/{identity}", tags=["reports"])
    def detail(identity: str, request: Request, db: Session = Depends(get_db)):
        actor(request,db,True); row = report_for(identity,db)
        statuses = db.scalars(select(OrderStatus).where(OrderStatus.deleted_at.is_(None)).order_by(OrderStatus.sequence)).all() if row.model == "App\\Order" else []
        return {"item":serialize_report(row),"params":[param_data(x) for x in params_for(identity,db)],"statuses":[{"id":x.id,"title":x.title} for x in statuses]}

    @app.patch("/api/report-settings/{identity}", tags=["reports"])
    def update(identity: str, request: Request, payload: dict, db: Session = Depends(get_db)):
        actor(request,db,True); row = report_for(identity,db)
        title = payload.get("title")
        if not isinstance(title,str) or not title.strip() or len(title)>255 or payload.get("format") not in {"A3","A4"} or payload.get("orientation") not in {"P","L"}:
            raise HTTPException(422,"Проверьте название, формат и ориентацию.")
        prohibitions = payload.get("prohibitions",[])
        if not isinstance(prohibitions,list) or any(not str(x).isdigit() for x in prohibitions): raise HTTPException(422)
        download = payload.get("download",False)
        if not isinstance(download,bool): raise HTTPException(422)
        row.title,row.format,row.orientation,row.download = title,payload["format"],payload["orientation"],download
        row.prohibitions = ",".join(str(x) for x in prohibitions)
        db.commit(); return {"status":"ok"}

    @app.get("/api/report-settings/{identity}/params/{param_id}", tags=["reports"])
    def param_detail(identity: str, param_id: int, request: Request, db: Session = Depends(get_db)):
        actor(request,db,True); report_for(identity,db)
        row = db.get(ReportParam,param_id)
        if not row or row.report_id != identity or row.deleted_at: raise HTTPException(404)
        return {"item":param_data(row)}

    @app.patch("/api/report-settings/{identity}/params/{param_id}", tags=["reports"])
    def param_update(identity: str, param_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
        actor(request,db,True); report_for(identity,db)
        row = db.get(ReportParam,param_id)
        if not row or row.report_id != identity or row.deleted_at: raise HTTPException(404)
        title,value = payload.get("title"),payload.get("value")
        if not isinstance(title,str) or not title.strip() or len(title)>255 or not isinstance(value,str) or not value.strip(): raise HTTPException(422)
        row.title,row.value = title,value
        db.commit(); return {"status":"ok"}

    @app.get("/api/reports/for/{kind}/{identity}", tags=["reports"])
    def for_item(kind: str, identity: int, request: Request, db: Session = Depends(get_db)):
        actor(request,db)
        if kind not in MODELS: raise HTTPException(404)
        model,model_name = MODELS[kind]
        item = db.get(model,identity)
        if not item or item.deleted_at: raise HTTPException(404)
        rows = db.scalars(select(Report).where(Report.model == model_name,Report.deleted_at.is_(None)).order_by(Report.id)).all()
        return {"items":[serialize_report(row) | {
            "available":row.id == "order_transcript" and row.program == "ipc" and row.kind == "html" and not row.form,
            "blocked":str(getattr(item,"status_id","")) in row.prohibitions.split(","),
            "url":f"/reports/{row.id}/item/{identity}",
        } for row in rows]}

    @app.get("/reports/{report_id}/item/{identity}", tags=["reports"])
    def generate(report_id: str, identity: int, request: Request, db: Session = Depends(get_db)):
        actor(request,db); report = report_for(report_id,db)
        if report.model != "App\\Order" or report.id != "order_transcript" or report.program != "ipc" or report.kind != "html" or report.form:
            raise HTTPException(501,"Этот шаблон/формат ещё не перенесён.")
        item = db.get(Order,identity)
        if not item or item.deleted_at: raise HTTPException(404)
        if str(item.status_id) in report.prohibitions.split(","): raise HTTPException(403,"Документ недоступен при текущем статусе.")
        try:
            raw = item.calc_details or ""
            if not raw: raise ValueError("No stored calculation")
            if len(raw)>5_000_000: raise ValueError("Calculation too large")
            decoded = json.loads(raw) if raw.lstrip().startswith("{") else loads(raw)
            if not isinstance(decoded,dict): raise ValueError("Expected array")
        except (ValueError, UnicodeError, ArithmeticError, RecursionError):
            raise HTTPException(422,"Сохранённый расчёт отсутствует или повреждён. Пересчитайте заказ.")
        content = php_print_r(decoded)
        html = '<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><title>' + escape(report.title) + '</title><style>*{margin:0;padding:0;font-family:Arial;font-size:8pt;color:#000}pre{font-size:1.5em;white-space:pre}</style></head><body><pre>' + escape(content) + '</pre></body></html>'
        headers = {"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}
        if report.download:
            headers["Content-Disposition"] = f'attachment; filename="{report.id}-{identity}.html"'
        return HTMLResponse(html,headers=headers)