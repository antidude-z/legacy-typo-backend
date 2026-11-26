"""Cookie-CSRF boundary; isolated ASGI app never opens a business database."""
import re
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.config import SESSION_COOKIE
from app.csrf import CSRF_COOKIE, CSRFMiddleware, token_for_session
from tests import test_review_employee_authorization as employee


class CookieCSRFTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.writes = []
        self.app.add_middleware(CSRFMiddleware)
        self.app.add_middleware(SessionMiddleware, secret_key='isolated-s11-secret', session_cookie=SESSION_COOKIE)

        @self.app.get('/token')
        def token(request: Request):
            from starlette.responses import JSONResponse
            value = token_for_session(request)
            response = JSONResponse({'token': value})
            response.set_cookie(CSRF_COOKIE, value)
            return response

        @self.app.api_route('/mutation', methods=['POST', 'PUT', 'PATCH', 'DELETE'])
        def mutate():
            self.writes.append('write')
            return {'ok': True}

        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_session_cookie_cannot_opt_out_by_deleting_csrf_cookie(self):
        token = self.client.get('/token').json()['token']
        self.client.cookies.delete(CSRF_COOKIE)
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            with self.subTest(method=method):
                self.assertEqual(self.client.request(method, '/mutation', headers={'X-CSRF-Token': token}).status_code, 419)
        self.assertEqual(self.writes, [])

    def test_remember_only_and_empty_cookie_values_fail_closed(self):
        for name in (SESSION_COOKIE, 'typography_remember', CSRF_COOKIE):
            for value in ('present', ''):
                with self.subTest(name=name, value=value):
                    self.client.cookies.clear()
                    self.client.cookies.set(name, value)
                    self.assertEqual(self.client.post('/mutation').status_code, 419)
        self.assertEqual(self.writes, [])

    def test_double_submit_without_matching_signed_session_is_rejected(self):
        self.client.cookies.set(CSRF_COOKIE, 'forged')
        self.assertEqual(self.client.post('/mutation', headers={'X-CSRF-Token': 'forged'}).status_code, 419)
        token = self.client.get('/token').json()['token']
        self.client.cookies.set(CSRF_COOKIE, 'forged', domain='testserver.local', path='/')
        self.assertEqual(self.client.post('/mutation', headers={'X-CSRF-Token': 'forged'}).status_code, 419)
        self.assertEqual(self.writes, [])

    def test_valid_session_bound_token_is_accepted_in_both_modes(self):
        for production in (False, True):
            with self.subTest(production=production), patch('app.csrf.PRODUCTION', production):
                self.client.cookies.clear()
                token = self.client.get('/token').json()['token']
                self.assertEqual(self.client.post('/mutation', headers={'X-CSRF-Token': token}).status_code, 200)

    def test_production_requires_csrf_even_without_cookies(self):
        with patch('app.csrf.PRODUCTION', True):
            self.assertEqual(self.client.post('/mutation').status_code, 419)
        self.assertEqual(self.writes, [])

    def test_only_cookie_free_local_compatibility_is_exempt(self):
        with patch('app.csrf.PRODUCTION', False):
            self.assertEqual(self.client.post('/mutation').status_code, 200)


class S11RealSessionTests(unittest.TestCase):
    mysql = False
    setUp = employee.EmployeeAuthorizationReviewTests.setUp
    tearDown = employee.EmployeeAuthorizationReviewTests.tearDown
    grant = employee.EmployeeAuthorizationReviewTests.grant
    snapshot = employee.EmployeeAuthorizationReviewTests.snapshot

    def test_all_registered_unsafe_aliases_reject_missing_csrf_without_writes(self):
        from app.main import app
        before = self.snapshot()
        self.client.cookies.delete(CSRF_COOKIE)
        for route in app.routes:
            for method in getattr(route, 'methods', set()) - {'GET', 'HEAD', 'OPTIONS', 'TRACE'}:
                path = re.sub(r'\{[^}]+\}', '1', route.path)
                with self.subTest(method=method, path=path):
                    response = self.client.request(method, path, json={})
                    self.assertEqual(response.status_code, 419, response.text)
        self.assertEqual(before, self.snapshot())

    def test_valid_csrf_does_not_grant_employee_delete_authority(self):
        self.grant('view_menu_references_users')
        before = self.snapshot()
        response = self.client.delete(f'/api/employee-references/{self.target.id}', headers=self.headers)
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(before, self.snapshot())