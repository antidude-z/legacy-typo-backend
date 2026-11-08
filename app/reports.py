"""Report catalog/settings and first migrated renderer (HTML transcript)."""
from html import escape
import json

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from io import BytesIO
from pathlib import Path
from reportlab.lib.pagesizes import A3, A4, A5, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Bill, Blank, Order, OrderStatus, Report, ReportParam
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


def _date(value):
    return value.strftime("%d.%m.%Y") if value else ""


def _safe_pdf_value(value):
    return "" if value is None else str(value)


def build_passport_pdf(order, report, blanks, calc_details):
    """Build the portable core of the legacy IPC order passport.

    The legacy document contains many production-specific columns. This renderer
    emits only fields represented by the migrated models and stored calculation
    details, leaving unsupported values blank instead of fabricating them.
    """
    assets = Path(__file__).parent / "assets"
    if "Passport" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Passport", str(assets / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("PassportBold", str(assets / "DejaVuSans-Bold.ttf")))
    page = {"A3": A3, "A4": A4, "A5": A5}.get(report.format)
    if page is None:
        raise HTTPException(501, "Формат бумаги этого шаблона ещё не поддерживается.")
    if report.orientation == "L": page = landscape(page)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page, title=report.title, rightMargin=10*mm,
                            leftMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = getSampleStyleSheet()
    styles["Title"].fontName = "PassportBold"
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontName="Passport", fontSize=7, leading=9))
    styles.add(ParagraphStyle(name="Heading", parent=styles["Heading2"], fontName="PassportBold", fontSize=10, leading=12, spaceBefore=5, spaceAfter=3))
    def cells(rows):
        return [[Paragraph(escape(_safe_pdf_value(value)).replace("\n", "<br/>"), styles["Small"]) for value in row] for row in rows]
    def widths(weights):
        return [doc.width * weight / sum(weights) for weight in weights]
    story = [Paragraph(escape(report.title), styles["Title"]), Spacer(1, 3*mm)]
    meta = [
        ["Паспорт заказа №", _safe_pdf_value(order.id), "Дата приема", _date(order.prod_date), "Дата готовности", _date(order.deadline)],
        ["Заказчик", _safe_pdf_value(order.customer.title if order.customer else ""), "Менеджер", _safe_pdf_value((order.manager.surname + " " if order.manager and order.manager.surname else "") + (order.manager.name if order.manager else "")), "Счет №", _safe_pdf_value(order.bill.number if order.bill else "")],
        ["Тип продукции", _safe_pdf_value(order.order_type), "Название", _safe_pdf_value(order.title), "Файлы", _safe_pdf_value(order.files)],
        ["Тираж", _safe_pdf_value(order.printing), "Объем", _safe_pdf_value(order.volume), "Формат", _safe_pdf_value(order.format)],
    ]
    meta_table = Table(cells(meta), colWidths=widths([30,45,25,45,30,55]))
    meta_table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), .4, colors.black), ("FONTNAME", (0,0), (-1,-1), "Helvetica"), ("FONTSIZE", (0,0), (-1,-1), 7), ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#eeeeee")), ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#eeeeee")), ("BACKGROUND", (4,0), (4,-1), colors.HexColor("#eeeeee")), ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story.extend([meta_table, Spacer(1, 4*mm), Paragraph("Бумага и печать", styles["Heading"])])
    rows = [["Заготовка", "Бумага", "Формат бумаги", "Плотность", "Машина", "Цветность", "Кол-во ПЛ", "Стоимость"]]
    details_blanks = calc_details.get("blanks", {}) if isinstance(calc_details, dict) else {}
    for blank in blanks:
        paper = blank.paper
        paper_title = paper.title if paper else ""
        format_title = paper.paper_format.title if paper and paper.paper_format else ""
        type_title = paper.paper_type.title if paper and paper.paper_type else ""
        detail = details_blanks.get(str(blank.id), details_blanks.get(blank.id, {}))
        detail = detail if isinstance(detail, dict) else {}
        paper_detail = detail.get("details", {}).get("paper", {}) if isinstance(detail.get("details", {}), dict) else {}
        print_detail = detail.get("details", {}).get("print", {}) if isinstance(detail.get("details", {}), dict) else {}
        rows.append([blank.title, " ".join(x for x in [type_title, paper_title] if x), format_title,
                     _safe_pdf_value(paper.weight if paper else ""),
                     _safe_pdf_value(blank.printer.title if blank.printer else ""),
                     f"{blank.colors_front}/{blank.colors_back}",
                     _safe_pdf_value(paper_detail.get("print_list_count", print_detail.get("steps_count", ""))),
                     _safe_pdf_value(detail.get("cost", blank.cost))])
    if len(rows) == 1:
        rows.append(["Нет заготовок", "", "", "", "", "", "", ""])
    blank_table = Table(cells(rows), colWidths=widths([32,50,30,20,38,22,25,25]), repeatRows=1)
    blank_table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), .4, colors.black), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#dddddd")), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7), ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story.append(blank_table)
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("Материалы", styles["Heading"]))
    material_rows = [["Материал", "Ед. измерения", "Количество", "Примечание"]]
    for blank in blanks:
        detail = details_blanks.get(str(blank.id), details_blanks.get(blank.id, {}))
        detail = detail if isinstance(detail, dict) else {}
        for section in (detail.get("details", {}).get("afterprint", []), detail.get("details", {}).get("compile", [])):
            if not isinstance(section, (list, dict)): continue
            values = section.values() if isinstance(section, dict) else section
            for item in values:
                if not isinstance(item, dict): continue
                stages = item.get("stages", []) if isinstance(item.get("stages", []), (list, dict)) else []
                for stage in (stages.values() if isinstance(stages, dict) else stages):
                    for material in (stage.get("materials", {}).values() if isinstance(stage, dict) and isinstance(stage.get("materials"), dict) else []):
                        if isinstance(material, dict): material_rows.append([_safe_pdf_value(material.get("title")), _safe_pdf_value(material.get("measure")), _safe_pdf_value(material.get("quantity")), ""])
    if len(material_rows) == 1: material_rows.append(["Нет данных", "", "", ""])
    material_table = Table(cells(material_rows), colWidths=widths([75,35,35,70]), repeatRows=1)
    material_table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), .4, colors.black), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#dddddd")), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7)]))
    story.append(material_table)
    doc.build(story)
    return buffer.getvalue()


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
            "available":((row.id == "order_transcript" and row.program == "ipc" and row.kind == "html") or (row.id == "order_passport" and row.program == "ipc" and row.kind == "pdf")) and not row.form,
            "blocked":str(getattr(item,"status_id","")) in row.prohibitions.split(","),
            "url":f"/reports/{row.id}/item/{identity}",
        } for row in rows]}

    @app.get("/reports/{report_id}/item/{identity}", tags=["reports"])
    def generate(report_id: str, identity: int, request: Request, db: Session = Depends(get_db)):
        actor(request,db); report = report_for(report_id,db)
        if report.model != "App\\Order" or report.program != "ipc" or report.form:
            raise HTTPException(501,"Этот шаблон/формат ещё не перенесён.")
        item = db.get(Order,identity)
        if not item or item.deleted_at: raise HTTPException(404)
        if str(item.status_id) in report.prohibitions.split(","): raise HTTPException(403,"Документ недоступен при текущем статусе.")
        if report.id == "order_passport" and report.kind == "pdf":
            raw = item.calc_details or ""
            if not raw:
                raise HTTPException(422,"Сохранённый расчёт отсутствует или повреждён. Пересчитайте заказ.")
            try:
                if len(raw) > 5_000_000: raise ValueError("Calculation too large")
                decoded = json.loads(raw) if raw.lstrip().startswith("{") else loads(raw)
                if not isinstance(decoded, dict): raise ValueError("Expected array")
            except (ValueError, UnicodeError, ArithmeticError, RecursionError):
                raise HTTPException(422,"Сохранённый расчёт отсутствует или повреждён. Пересчитайте заказ.")
            blanks = db.scalars(select(Blank).where(Blank.order_id == item.id, Blank.deleted_at.is_(None)).order_by(Blank.id)).all()
            pdf = build_passport_pdf(item, report, blanks, decoded)
            headers = {"Cache-Control":"no-store", "X-Content-Type-Options":"nosniff"}
            if report.download:
                headers["Content-Disposition"] = f'attachment; filename="order-passport-{identity}.pdf"'
            return Response(pdf, media_type="application/pdf", headers=headers)
        if report.id != "order_transcript" or report.program != "ipc" or report.kind != "html":
            raise HTTPException(501,"Этот шаблон/формат ещё не перенесён.")
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