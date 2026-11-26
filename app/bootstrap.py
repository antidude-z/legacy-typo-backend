from .clock import utc_now
"""Repeatable local database initialization and legacy catalog seeding."""

from datetime import date, datetime

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from .db import Base, engine
from .models import Option, Permission, Role, Report, ReportParam, SchemaVersion, OrderStatus, Service, Rate, User, role_permissions


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
    ("edit_reports_payrolls", "Редактирование расчета зарплаты менеджеров", "reports"),
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
OPTIONS = (
    ("markups", "min_markup", "Максимальная скидка", "-5", "1970-01-01"),
    ("markups", "max_markup", "Максимальная наценка", "20", "1970-01-01"),
    ("markups", "step_markup", "Шаг наценки", "1", "1970-01-01"),
)


def initialize_database(database_engine=engine) -> None:
    from .admin_safety import security_lock
    # Include startup seed writers in the same serialization boundary as HTTP
    # and operator changes, including on imported nontransactional tables.
    with Session(database_engine) as lock_session:
        with security_lock(lock_session):
            _initialize_database(database_engine)


def preview_initialization(database_engine=engine):
    """Read-only access diff; never create tables, migrate, or assign grants."""
    with database_engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        populated = any(
            table.name in tables and connection.execute(select(table).limit(1)).first() is not None
            for table in (Role.__table__, User.__table__, Permission.__table__, role_permissions)
        )
        marked = (SchemaVersion.__tablename__ in tables and
                  connection.execute(select(SchemaVersion.version).where(
                      SchemaVersion.version == SCHEMA_VERSION)).first() is not None)
        fresh = not populated and not marked
        grants = []
        if role_permissions.name in tables:
            grants = [dict(row) for row in connection.execute(select(role_permissions).order_by(
                role_permissions.c.role_id, role_permissions.c.permission_id)).mappings()]
        additions = []
        if fresh:
            for title in ('Администратор', 'Руководство'):
                additions.extend({'role_title': title, 'permission_id': identity}
                                 for identity, _, _ in PERMISSIONS)
            additions.extend({'role_title': 'Менеджер', 'permission_id': identity}
                             for identity in ('view_menu_orders', 'view_menu_references',
                                              'view_menu_references_customers'))
        return {'mode': 'fresh' if fresh else 'upgrade', 'existing_grants': grants,
                'grant_additions': additions, 'grant_removals': [], 'applied': False}


def _initialize_database(database_engine) -> None:
    """Create the local schema and add legacy-confirmed catalog data.

    This is deliberately additive: existing business rows and role assignments
    are never removed or overwritten.  ``database_engine`` is injectable so the
    initializer can be exercised against a disposable SQLite database.
    """
    from .schema import apply_migrations

    apply_migrations(database_engine)
    with Session(database_engine) as db:
        if db.get(SchemaVersion, SCHEMA_VERSION) is None:
            # A missing marker is ambiguous: old imports predate this table, but
            # a fresh database also has no marker. Only an actually empty account
            # catalog may receive the documented baseline role grants. Existing
            # roles/users are evidence of a legacy installation, so preserve its
            # exact assignments and add definitions without inferring authority
            # from role titles.
            fresh_install = (
                db.scalar(select(Role.id).limit(1)) is None
                and db.scalar(select(User.id).limit(1)) is None
                and db.scalar(select(Permission.id).limit(1)) is None
                and db.execute(select(role_permissions).limit(1)).first() is None
            )
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
            if fresh_install:
                permissions = {identity: db.get(Permission, identity) for identity, _, _ in PERMISSIONS}
                roles = {row.title: row for row in db.scalars(select(Role)).all()}
                for role_title in ("Администратор", "Руководство"):
                    role = roles.get(role_title)
                    if role:
                        role.permissions = list({*role.permissions, *permissions.values()})
                manager = roles.get("Менеджер")
                if manager:
                    manager.permissions = list({*manager.permissions, *(permissions[x] for x in ("view_menu_orders", "view_menu_references", "view_menu_references_customers"))})
            db.add(SchemaVersion(version=SCHEMA_VERSION, applied_at=utc_now()))
            db.commit()

        # Existing installations must expose the write gate in the matrix too;
        # do not silently grant it to existing roles during an upgrade.
        if db.get(Permission, "edit_reports_payrolls") is None:
            db.add(Permission(id="edit_reports_payrolls", title="Редактирование расчета зарплаты менеджеров", module="reports"))
        # Security delegation is explicit even for fresh installations. Never
        # broaden historical grants or infer authority from a role title.
        for identity, title in (("user_assign_role", "Назначение ролей пользователей"),
                                ("user_reset_credentials", "Сброс учетных данных пользователей")):
            if db.get(Permission, identity) is None:
                db.add(Permission(id=identity, title=title, module="users"))
        from .order_authorization import ORDER_CAPABILITIES
        from .accounting_payers import PAYER_CAPABILITIES
        for identity, title in ORDER_CAPABILITIES + PAYER_CAPABILITIES:
            if db.get(Permission, identity) is None:
                db.add(Permission(id=identity, title=title, module='orders' if identity.endswith('_orders') else 'accounting'))
        from .reference_dictionaries import DICTIONARY_CAPABILITIES
        for identity, title in DICTIONARY_CAPABILITIES:
            if db.get(Permission, identity) is None:
                db.add(Permission(id=identity, title=title, module='options'))
        from .reference_customers import CUSTOMER_CAPABILITIES
        from .reference_inventory import INVENTORY_CAPABILITIES
        from .printer_authorization import PRINTER_CAPABILITIES
        from .reference_afterprints import AFTERPRINT_CAPABILITIES
        from .reference_compiles import COMPILE_CAPABILITIES
        from .reference_works import WORK_CAPABILITIES
        for identity, title in CUSTOMER_CAPABILITIES + INVENTORY_CAPABILITIES + PRINTER_CAPABILITIES + AFTERPRINT_CAPABILITIES + COMPILE_CAPABILITIES + WORK_CAPABILITIES:
            if db.get(Permission, identity) is None:
                db.add(Permission(id=identity, title=title, module='references'))
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
        for depart, alias, title, value, actual_since in OPTIONS:
            if db.scalar(select(Option).where(Option.alias == alias, Option.deleted_at.is_(None))) is None:
                db.add(Option(depart=depart, alias=alias, title=title, value=value, actual_since=date.fromisoformat(actual_since)))
        db.commit()


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description='Initialize catalogs without broadening imported grants.')
    parser.add_argument('--preview', action='store_true', help='Read-only access diff; no migrations or writes')
    args = parser.parse_args()
    try:
        if args.preview:
            print(json.dumps(preview_initialization(), ensure_ascii=False, indent=2))
        else:
            initialize_database()
            print(f"initialized schema {SCHEMA_VERSION}")
    finally:
        engine.dispose()