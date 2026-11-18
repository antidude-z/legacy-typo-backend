import tempfile
import unittest
from pathlib import Path

import xlwt
from reportlab.pdfgen import canvas

from app.compare_reports import compare


class ReportComparisonTests(unittest.TestCase):
    def test_pdf_text_matches_and_detects_changed_content(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'{name}.pdf' for name in ('legacy', 'rework')]
            for path in paths:
                pdf = canvas.Canvas(str(path)); pdf.drawString(40, 700, 'Order 123'); pdf.save()
            self.assertTrue(compare(*paths)['content_equal'])
            pdf = canvas.Canvas(str(paths[1])); pdf.drawString(40, 700, 'Order 124'); pdf.save()
            self.assertFalse(compare(*paths)['content_equal'])

    def test_xls_compares_cells_types_and_merges(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'{name}.xls' for name in ('legacy', 'rework')]
            for path in paths:
                book = xlwt.Workbook(); sheet = book.add_sheet('Report')
                sheet.write_merge(0, 0, 0, 1, 'Total'); sheet.write(1, 0, 123.45)
                book.save(str(path))
            result = compare(*paths)
            self.assertTrue(result['content_equal'])
            self.assertEqual(result['visual_acceptance'], 'not_checked')
            book = xlwt.Workbook(); sheet = book.add_sheet('Report'); sheet.write(0, 0, 'Total')
            book.save(str(paths[1]))
            self.assertFalse(compare(*paths)['content_equal'])

    def test_missing_and_unsupported_artifacts_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / 'missing.pdf'
            with self.assertRaisesRegex(ValueError, 'does not exist'):
                compare(missing, missing)
            unsupported = Path(directory) / 'report.txt'; unsupported.write_text('text')
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                compare(unsupported, unsupported)