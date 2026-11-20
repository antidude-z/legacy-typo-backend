"""All registered S03 methods/aliases, real sessions, no authorization mocks."""
import json
from pathlib import Path
import re

from fastapi.routing import APIRoute
from app.main import app
from app.s03_policy import KINDS, declared_routes, domain_policy, in_scope
from tests import test_review_employee_authorization as fixtures


class S03RouteMatrixTests(fixtures.EmployeeAuthorizationReviewTests):
    def test_inventory_matches_reviewed_routes(self):
        expected = json.loads((Path(__file__).parent / 'fixtures' / 's03-routes.json').read_text())
        self.assertEqual([list(row) for row in declared_routes(app)], expected,
                         'S03 route changed: review policy and extend real-session coverage')

    def test_every_route_denies_unrelated_reader_and_generic_lifecycle_roles(self):
        routes = [r for r in app.routes if isinstance(r, APIRoute) and in_scope(r)]
        checked = set()
        for route in routes:
            module = route.endpoint.__module__
            kinds = KINDS.get(module, ('prepresses',)) if '{kind}' in route.path else (None,)
            if module == 'app.main' and '{operation}' in route.path:
                kinds = ('blanks', 'prepresses', 'redactions', 'compiles', 'others')
            for kind in kinds:
                path = route.path.replace('{kind}', kind or '').replace('{operation}', kind or '')
                path = path.replace('{order_type}', 'poly').replace('{format_prefix}', 'A')
                path = re.sub(r'\{[^}]+\}', '1', path)
                reads, edit, delete = domain_policy(module, path, kind)
                for method in route.methods:
                    checked.add((method, route.path, kind))
                    cases = [('unrelated', ('view_menu_reports',)),
                             ('generic lifecycle', ('view_menu_reports', 'restore_trashed', 'delete_trashed', 'view_trashed'))]
                    if method not in {'GET', 'HEAD', 'OPTIONS'} and not path.endswith('/filter'):
                        cases += [('reader', (reads[0],)), ('wrong-domain writer', (reads[0], 'edit_price'))]
                        if method == 'DELETE' or path.endswith(('/restore', '/permanent')):
                            cases += [('editor', (reads[0], edit))]
                    for actor, grants in cases:
                        self.role.permissions.clear(); self.db.commit(); self.grant(*dict.fromkeys(grants))
                        before = self.snapshot()
                        response = self.client.request(method, path, headers=self.headers, json={})
                        self.assertEqual(response.status_code, 403, (actor, method, path, response.text))
                        self.assertEqual(before, self.snapshot(), (actor, method, path))
        self.assertGreater(len(checked), 150)