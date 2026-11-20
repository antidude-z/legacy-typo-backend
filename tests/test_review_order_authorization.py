"""S03 real-session, valid-resource denial tests on disposable SQLite."""
from datetime import date
from app.models import Order
from tests import test_review_employee_authorization


class OrderAuthorizationReviewTests(test_review_employee_authorization.EmployeeAuthorizationReviewTests):
    def test_order_reader_cannot_write_or_delete_existing_resources(self):
        self.grant('view_menu_orders')
        item = Order(title='Protected', order_type='poly', status_id=1, printing=10, order_date=date.today())
        self.db.add(item); self.db.commit()
        self.assertEqual(self.client.get(f'/api/orders/{item.id}').status_code, 200)
        before = self.snapshot()
        for method, path, payload in (
            ('PUT', f'/api/orders/{item.id}', {'title': 'Changed'}),
            ('POST', f'/api/orders/{item.id}', {'title': 'Changed'}),
            ('DELETE', f'/api/orders/{item.id}', {}),
            ('POST', f'/api/orders/{item.id}/copy', {}),
            ('POST', f'/api/orders/{item.id}/blanks', {}),
            ('POST', f'/api/orders/{item.id}/recalculate', {}),
            ('POST', '/api/orders/add/poly', {'title': 'New'}),
        ):
            response = self.client.request(method, path, json=payload, headers=self.headers)
            self.assertEqual(response.status_code, 403, (method, path, response.text))
        self.assertEqual(before, self.snapshot())
        self.grant('edit_orders')
        response = self.client.put(f'/api/orders/{item.id}', json={'title': 'Allowed'}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.db.get(Order, item.id).title, 'Allowed')
        self.assertEqual(self.client.delete(f'/api/orders/{item.id}', headers=self.headers).status_code, 403)

    def test_unrelated_staff_cannot_read_orders_or_use_alias(self):
        self.grant('view_menu_references_users')
        before = self.snapshot()
        for path in ('/api/orders', '/orders', '/api/orders/add/poly', '/orders/formats/book'):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        self.assertEqual(before, self.snapshot())