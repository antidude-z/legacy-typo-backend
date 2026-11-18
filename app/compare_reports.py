"""Compare paired PDF/XLS artifacts without modifying either source file.

Run with uv's development dependencies installed (pypdf and xlrd).
Text/cell equality is not visual, formula, or print-layout acceptance.
"""

import argparse
import hashlib
import json
from pathlib import Path


def snapshot(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Report file does not exist: {path}")
    kind = path.suffix.lower()
    if kind == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        content = {'pages': [" ".join((page.extract_text() or '').split()) for page in reader.pages]}
        if not any(content['pages']):
            raise ValueError(f"PDF has no extractable text: {path}")
    elif kind == '.xls':
        import xlrd
        book = xlrd.open_workbook(str(path), formatting_info=True)
        try:
            content = {'sheets': [{
                'name': sheet.name,
                'cells': [[{'type': cell.ctype, 'value': cell.value} for cell in sheet.row(row)] for row in range(sheet.nrows)],
                'merged_cells': sorted(sheet.merged_cells),
            } for sheet in book.sheets()]}
        finally:
            book.release_resources()
    else:
        raise ValueError(f"Unsupported report extension: {kind}")
    return {'kind': kind, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'content': content}


def compare(legacy, rework):
    left, right = snapshot(legacy), snapshot(rework)
    if left['kind'] != right['kind']:
        raise ValueError('Report formats must match')
    return {
        'legacy': str(legacy), 'rework': str(rework),
        'byte_equal': left['sha256'] == right['sha256'],
        'content_equal': left['content'] == right['content'],
        'legacy_snapshot': left, 'rework_snapshot': right,
        'visual_acceptance': 'not_checked',
        'formulas_and_print_settings': 'not_checked',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('legacy', type=Path)
    parser.add_argument('rework', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {args.legacy.resolve(), args.rework.resolve()}:
        parser.error('Output must not overwrite either source report')
    try:
        result = compare(args.legacy, args.rework)
    except Exception as exc:
        parser.exit(2, f'Comparison failed: {exc}\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    parser.exit(0 if result['content_equal'] else 1)


if __name__ == '__main__':
    main()