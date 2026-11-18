import unittest

from app.report_contract import audit_report_catalog
from app.models import Report, ReportParam
from tests import test_reference_dictionaries as fixtures


class ReportContractTests(unittest.TestCase):
    setUp = fixtures.ReferenceDictionaryTests.setUp
    tearDown = fixtures.ReferenceDictionaryTests.tearDown

    def test_active_catalog_matches_supported_contracts(self):
        self.db.add_all([
            Report(id='order_transcript', program='ipc', kind='html', title='Transcript', model='App\\Order', model_title='Заказ'),
            Report(id='order_payment', program='ipc', kind='xls', form=True, title='Payment', model='App\\Bill', model_title='Счет'),
            Report(id='order_shipping', program='ipc', kind='pdf', title='Shipping', model='App\\Bill', model_title='Счет'),
            ReportParam(alias='prorector', report_id='order_payment', title='Prorector', value='A'),
            ReportParam(alias='zam_prorectora', report_id='order_payment', title='Deputy', value='B'),
            ReportParam(alias='boss', report_id='order_payment', title='Boss', value='C'),
            ReportParam(alias='buh', report_id='order_payment', title='Accountant', value='D'),
            ReportParam(alias='pfu', report_id='order_payment', title='PFU', value='E'),
            ReportParam(alias='boss', report_id='order_shipping', title='Boss', value='C'),
            ReportParam(alias='pto', report_id='order_shipping', title='PTO', value='P'),
            ReportParam(alias='buh', report_id='order_shipping', title='Accountant', value='D'),
        ])
        self.db.commit()
        result = audit_report_catalog(self.db)
        self.assertTrue(result['valid'], result['issues'])

    def test_missing_parameter_is_reported(self):
        self.db.add(Report(id='order_payment', program='ipc', kind='xls', form=True, title='Payment', model='App\\Bill', model_title='Счет'))
        self.db.commit()
        result = audit_report_catalog(self.db)
        self.assertFalse(result['valid'])
        self.assertTrue(any(issue['issue'] == 'missing_parameter' and issue['alias'] == 'pfu' for issue in result['issues']))