"""Repeatable local database initialization and legacy catalog seeding."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, engine
from .models import Permission, Role, Report, ReportParam, SchemaVersion, OrderStatus, Service, Rate, role_permissions


SCHEMA_VERSION = "2026-11-13-01"

ROLES = ("Администратор", "Руководство", "Менеджер", "Дизайнер", "Производство", "Редакция", "Бухгалтерия")
PERMISSIONS = (
    ("view_menu_orders", "Просмотр пункта меню \"заказы\"", "orders"),
    ("view_menu_accounting", "Просмотр пункта меню \"бухгалтерия\"", "accounting"),
    ("view_accounting_bills", "Просмотр счетов", "accounting"),
    ("edit_accounting_bills", "Редактирование счетов", "accounting"),
    ("delete_accounting_bills", "Удаление счетов", "accounting"),
    ("view_menu_accounting_payers", "Просмотр пункта меню \"бухгалтерия-плательщики\"", "accounting"),
    ("view_menu_accounting_payments", "Просмотр пункта меню \"бухгалтерия-платежи\"", "accounting"),
    ("view_menu_references", "Просмотр пункта меню \"справочники\"", "references"),
    ("view_menu_references_customers", "Просмотр пункта меню \"справочники-заказчики\"", "references"),
    ("view_menu_references_printers", "Просмотр пункта меню \"справочники-печатные машины\"", "references"),
    ("view_menu_references_paper_type", "Просмотр пункта меню \"справочники-виды бумаги\"", "references"),
    ("view_menu_references_paper", "Просмотр пункта меню \"справочники-бумага\"", "references"),
    ("view_menu_references_materials", "Просмотр пункта меню \"справочники-материалы\"", "references"),
    ("view_menu_references_works", "Просмотр пункта меню \"справочники-работы\"", "references"),
    ("view_menu_references_redactions", "Просмотр пункта меню \"справочники-работы по редактуре\"", "references"),
    ("view_menu_references_prepresses", "Просмотр пункта меню \"справочники-работы по дизайну/препресс\"", "references"),
    ("view_menu_references_afterprints", "Просмотр пункта меню \"справочники-постпечатъ\"", "references"),
    ("view_menu_references_compiles", "Просмотр пункта меню \"справочники-работы по сборке\"", "references"),
    ("view_menu_references_users", "Просмотр пункта меню \"справочники-сотрудники\"", "references"),
    ("view_menu_prices", "Просмотр пункта меню \"цены\"", "prices"),
    ("view_menu_prices_paper", "Просмотр пункта меню \"цены-бумага\"", "prices"),
    ("view_menu_prices_print", "Просмотр пункта меню \"цены-печать\"", "prices"),
    ("view_menu_prices_materials", "Просмотр пункта меню \"цены-материалы\"", "prices"),
    ("view_menu_prices_imagesetter", "Просмотр пункта меню \"цены-фотовывод\"", "prices"),
    ("view_menu_prices_prepress", "Просмотр пункта меню \"цены-дизайн/препресс\"", "prices"),
    ("view_menu_prices_redaction", "Просмотр пункта меню \"цены-редактура\"", "prices"),
    ("view_menu_prices_afterprint", "Просмотр пункта меню \"цены-постпечать\"", "prices"),
    ("view_menu_prices_compile", "Просмотр пункта меню \"цены-сборка\"", "prices"),
    ("view_menu_reports", "Просмотр пункта меню \"отчеты\"", "reports"),
    ("view_menu_reports_actions", "Просмотр пункта меню \"отчеты-журнал событий\"", "reports"),
    ("view_menu_reports_payrolls", "Просмотр пункта меню \"отчеты-зарплата менеджеров\"", "reports"),
    ("view_menu_options", "Просмотр пункта меню \"настройки\"", "options"),
    ("view_menu_options_main", "Просмотр пункта меню \"настройки-основные\"", "options"),
    ("view_menu_options_paper_type", "Просмотр пункта меню \"настройки-виды бумаги\"", "options"),
    ("view_menu_options_paper_format", "Просмотр пункта меню \"настройки-форматы бумаги\"", "options"),
    ("view_menu_options_measures", "Просмотр пункта меню \"настройки-единицы измерения\"", "options"),
    ("view_menu_options_customer_group", "Просмотр пункта меню \"настройки-группы заказчиков\"", "options"),
    ("view_menu_options_permissions", "Просмотр пункта меню \"настройки-разрешения ролей\"", "options"),
    ("view_menu_options_reports", "Просмотр пункта меню \"настройки-шаблоны документов\"", "options"),
    ("view_trashed", "Просмотр удаленных элементов", "system"),
    ("restore_trashed", "Восстановление удаленных элементов", "system"),
    ("delete_trashed", "Окончательное удаление элементов", "system"),
    ("edit_price", "Редактирование цен", "prices"),
    ("delete_price", "Удаление цен", "prices"),
    ("user_create", "Создание пользователей", "users"),
    ("user_edit", "Редактирование пользователей", "users"),
    ("user_delete", "Удаление пользователей", "users"),
)

ORDER_STATUSES = (("Расчет", 1), ("Подготовка макетов", 2), ("Согласование", 3), ("Передан в производство", 4), ("Передан на склад", 5), ("Отгружен заказчику", 6))
REPORTS = (
    ("order_passport", "pdf", False, "Паспорт заказа", "App\\Order"),
    ("order_shipping", "pdf", False, "Документ на отгрузку", "App\\Bill"),
    ("order_payment", "xls", True, "Заявка на оплату", "App\\Bill"),
    ("order_transcript", "html", False, "Расшифровка расчета", "App\\Order"),
    ("order_design", "xls", False, "Наряд-заказ дизайна", "App\\Order"),
    ("order_economy", "xls", False, "Экономический паспорт", "App\\Order"),
)
REPORT_PARAMS = (("order_shipping", "boss", "Директор", "В. Ю. Малыгин"), ("order_shipping", "pto", "Начальник производственного отдела", "Веретенников Г.С."), ("order_shipping", "buh", "Бухгалтер", "А. Ю. Дружинина"), ("order_payment", "prorector", "Проректор по ИП", "Р. Л. Иваницкая"), ("order_payment", "zam_prorectora", "Заместитель проректора по ЭиСР", "М. В. Жабреев"), ("order_payment", "boss", "Директор ИПЦ УрФУ", "В. Ю. Малыгин"), ("order_payment", "buh", "Главный бухгалтер", "И. Н. Чернявская"), ("order_payment", "pfu", "Начальник ПФУ", "Э. М. Хафизова"))
SERVICES = (("Фотовывод", "", "imagesetter"),)
RATES = (
    ("57.65", "62.0487", "2015-04-01"),
    ("52.8213", "57.7020", "2015-06-01"),
    ("60.3458", "66.0002", "2015-08-01"),
    ("65.7364", "73.7760", "2015-10-01"),
    ("66.7370", "70.6478", "2015-12-01"),
    ("76.3264", "82.8141", "2016-02-02"),
    ("67.8552", "76.9207", "2016-04-01"),
)


def initialize_database(database_engine=engine) -> None:
    """Create the local schema and add legacy-confirmed catalog data.

    This is deliberately additive: existing business rows and role assignments
    are never removed or overwritten.  ``database_engine`` is injectable so the
    initializer can be exercised against a disposable SQLite database.
    """
    from .schema import upgrade_local_schema

    # The current compatibility upgrades inspect the configured engine.  They
    # run during application startup; create_all is safe for a fresh database.
    if database_engine is engine:
        upgrade_local_schema()
    Base.metadata.create_all(bind=database_engine)
    with Session(database_engine) as db:
        if db.get(SchemaVersion, SCHEMA_VERSION) is None:
            for title in ROLES:
                if db.scalar(select(Role).where(Role.title == title)) is None:
                    db.add(Role(title=title))
            for identity, title, module in PERMISSIONS:
                if db.get(Permission, identity) is None:
                    db.add(Permission(id=identity, title=title, module=module))
            for title, sequence in ORDER_STATUSES:
                if db.scalar(select(OrderStatus).where(OrderStatus.title == title)) is None:
                    db.add(OrderStatus(title=title, sequence=sequence))
            db.flush()
            permissions = {row.id: row for row in db.scalars(select(Permission)).all()}
            roles = {row.title: row for row in db.scalars(select(Role)).all()}
            for role_title in ("Администратор", "Руководство"):
                role = roles.get(role_title)
                if role:
                    role.permissions = list({*role.permissions, *permissions.values()})
            manager = roles.get("Менеджер")
            if manager:
                manager.permissions = list({*manager.permissions, *(permissions[x] for x in ("view_menu_orders", "view_menu_references", "view_menu_references_customers"))})
            db.add(SchemaVersion(version=SCHEMA_VERSION, applied_at=datetime.utcnow()))
            db.commit()

        for identity, kind, form, title, model in REPORTS:
            if db.get(Report, identity) is None:
                db.add(Report(id=identity, kind=kind, form=form, title=title, model=model, model_title="Заказ" if "Order" in model else "Счет"))
        db.flush()
        for report_id, alias, title, value in REPORT_PARAMS:
            if db.scalar(select(ReportParam).where(ReportParam.report_id == report_id, ReportParam.alias == alias, ReportParam.deleted_at.is_(None))) is None:
                db.add(ReportParam(report_id=report_id, alias=alias, title=title, value=value, html=False))
        for title, organization, kind in SERVICES:
            if db.scalar(select(Service).where(Service.title == title, Service.kind == kind, Service.deleted_at.is_(None))) is None:
                db.add(Service(title=title, organization=organization, kind=kind))
        for usd, eur, actual_since in RATES:
            effective = date.fromisoformat(actual_since)
            if db.scalar(select(Rate).where(Rate.actual_since == effective, Rate.usd == usd, Rate.eur == eur, Rate.deleted_at.is_(None))) is None:
                db.add(Rate(usd=usd, eur=eur, actual_since=effective))
        db.commit()


if __name__ == "__main__":
    initialize_database()
    print(f"initialized schema {SCHEMA_VERSION}")