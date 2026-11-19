"""Read-only model/live-schema drift inventory. Never repairs data or DDL."""
import argparse
import json
from pathlib import Path

from sqlalchemy import Boolean, Numeric, String, inspect
from sqlalchemy.dialects.mysql import ENUM, TINYINT
from .db import Base, engine


def audit_schema(database_engine):
    from . import models  # Register metadata.
    inspector = inspect(database_engine)
    actual_tables = set(inspector.get_table_names())
    tables = {}
    for table in Base.metadata.sorted_tables:
        if table.name not in actual_tables:
            tables[table.name] = {'missing_table': True}
            continue
        actual = {column['name']: column for column in inspector.get_columns(table.name)}
        differences = []
        for column in table.columns:
            if column.name not in actual:
                differences.append({'column': column.name, 'issue': 'missing_column'})
                continue
            live = actual[column.name]
            if not column.primary_key and column.nullable != live['nullable']:
                differences.append({'column': column.name, 'issue': 'nullability',
                                    'model': column.nullable, 'database': live['nullable']})
            wanted, found = column.type, live['type']
            if isinstance(wanted, Boolean) and isinstance(found, TINYINT):
                continue
            if isinstance(found, ENUM):
                # Enumerated values remain constrained; VARCHAR length is not
                # a useful measure of enum storage compatibility.
                continue
            if isinstance(wanted, Numeric) and isinstance(found, Numeric):
                if (wanted.precision, wanted.scale) != (found.precision, found.scale):
                    differences.append({'column': column.name, 'issue': 'decimal_precision',
                                        'model': str(wanted), 'database': str(found)})
            elif isinstance(wanted, String) and isinstance(found, String):
                if wanted.length and found.length and wanted.length > found.length:
                    differences.append({'column': column.name, 'issue': 'shorter_database_string',
                                        'model': wanted.length, 'database': found.length})
            elif wanted._type_affinity is not found._type_affinity:
                differences.append({'column': column.name, 'issue': 'type_affinity',
                                    'model': str(wanted), 'database': str(found)})
        tables[table.name] = {
            'differences': differences,
            'extra_columns': sorted(set(actual) - set(table.c.keys())),
            'columns': [{
                'name': column.name, 'type': str(column.type),
                'database_type': str(actual[column.name]['type']),
                'database_default': str(actual[column.name]['default']) if actual[column.name]['default'] is not None else None,
                'model_client_default': str(column.default.arg) if column.default is not None and not callable(column.default.arg) else ('callable' if column.default else None),
                'model_server_default': str(column.server_default.arg) if column.server_default else None,
            } for column in table.columns if column.name in actual],
            'indexes': inspector.get_indexes(table.name),
            'unique_constraints': inspector.get_unique_constraints(table.name),
            'foreign_keys': inspector.get_foreign_keys(table.name),
        }
    return {'dialect': database_engine.dialect.name, 'tables': tables,
            'extra_tables': sorted(actual_tables - set(Base.metadata.tables)),
            'note': 'Client defaults are not server defaults. Historical extra columns and absent foreign keys are not automatically repaired.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(audit_schema(engine), indent=2, default=str) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()