"""S12 public roster compatibility endpoints never disclose account data."""
import unittest
from tests import test_authentication as auth


class DiscoveryTests(unittest.TestCase):
    setUp = auth.AuthenticationTests.setUp
    tearDown = auth.AuthenticationTests.tearDown

    def test_both_public_aliases_return_empty_uncacheable_payload(self):
        for path in ('/auth/users', '/api/auth/users'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {})
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertNotIn(self.user.email, response.text)
                self.assertNotIn(self.user.name, response.text)

    def test_typed_email_login_does_not_require_directory_lookup(self):
        response = self.client.post('/api/auth/login', data={
            'email': self.user.email, 'password': self.password}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertTrue(self.client.get('/api/session').json()['authenticated'])