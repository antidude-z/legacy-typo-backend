from .models import User


def item(title: str, link: str) -> dict:
    return {"title": title, "link": link, "below": []}


MENU_GROUPS = [
    ("view_menu_orders", item("Заказы", "orders"), []),
    ("view_menu_accounting", item("Бухгалтерия", "accounting"), [
        ("view_accounting_bills", item("Счета", "accounting/bills")),
        ("view_menu_accounting_payers", item("Плательщики", "accounting/payers")),
    ]),
    ("view_menu_references", item("Справочники", "references"), [
        ("view_menu_references_customers", item("Заказчики", "references/customers")),
        ("view_menu_references_printers", item("Печатные машины", "references/printers")),
        ("view_menu_references_paper_type", item("Виды бумаги", "references/paper-type")),
        ("view_menu_references_paper", item("Бумага", "references/paper")),
        ("view_menu_references_materials", item("Материалы", "references/materials")),
        ("view_menu_references_prepresses", item("Работы по дизайну/препресс", "references/prepresses")),
        ("view_menu_references_redactions", item("Работы по редактуре", "references/redactions")),
        ("view_menu_references_afterprints", item("Постпечатные работы", "references/afterprints")),
        ("view_menu_references_compiles", item("Работы по сборке", "references/compiles")),
        ("view_menu_references_users", item("Сотрудники", "references/users")),
    ]),
    ("view_menu_prices", item("Цены", "prices"), [
        ("view_menu_prices_paper", item("Бумага", "prices/paper")),
        ("view_menu_prices_print", item("Печать", "prices/print")),
        ("view_menu_prices_materials", item("Материалы", "prices/materials")),
        ("view_menu_prices_prepress", item("Дизайн/препресс", "prices/prepress")),
        ("view_menu_prices_redaction", item("Редактура", "prices/redaction")),
        ("view_menu_prices_afterprint", item("Постпечать", "prices/afterprint")),
        ("view_menu_prices_compile", item("Сборка", "prices/compile")),
        ("view_menu_prices_compile", item("Этапы сборки", "prices/compiles")),
        ("view_menu_prices_imagesetter", item("Услуги подрядчиков", "prices/services")),
    ]),
    ("view_menu_reports", item("Отчёты", "reports"), [
        ("view_menu_reports_payrolls", item("Зарплата менеджеров", "reports/payrolls")),
    ]),
    ("view_menu_options", item("Настройки", "options"), [
        ("view_menu_options_main", item("Основные настройки", "options/main")),
        ("view_menu_options_paper_type", item("Виды бумаги", "options/paper-type")),
        ("view_menu_options_paper_format", item("Форматы бумаги", "options/paper-format")),
        ("view_menu_options_measures", item("Единицы измерения", "options/measures")),
        ("view_menu_options_customer_group", item("Группы заказчиков", "options/customer-group")),
        ("view_menu_options_permissions", item("Разрешения ролей", "options/permissions")),
        ("view_menu_options_reports", item("Шаблоны документов", "options/reports")),
    ]),
]


def build_navigation(user: User | None) -> list[dict]:
    if user is None:
        return []
    result = []
    for group_permission, group, children in MENU_GROUPS:
        if not user.has_permission(group_permission):
            continue
        group = {**group, "below": [child for permission, child in children if user.has_permission(permission)]}
        result.append(group)
    return result
