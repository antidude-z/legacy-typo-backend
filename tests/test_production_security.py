import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import validate_production_settings
from app.login_limits import reserve_attempt, clear_attempts
from app.main import app
from app.main import deliver_reset_mail


class ProductionSecurityTests(unittest.TestCase):
    def test_production_configuration_rejects_unsafe_settings(self):
        good = {'APP_ENV': 'production', 'APP_URL': 'https://print.example.test',
                'SESSION_SECRET': 'a' * 48, 'SESSION_SECURE': 'true'}
        validate_production_settings(good)
        for key, value in [('SESSION_SECRET', 'short'), ('APP_URL', 'http://example.test'),
                           ('SESSION_SECURE', 'false'), ('FORWARDED_ALLOW_IPS', '*'),
                           ('RESET_MAIL_MODE', 'file'), ('SESSION_MINUTES', '0')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_production_settings({**good, key: value})
        with self.assertRaises(ValueError):
            validate_production_settings({**good, 'RESET_MAIL_MODE': 'smtp'})
        for value in ('https://example.test/subpath', 'https://user:pass@example.test',
                      'https://example.test?query=1', 'https://example.test#fragment'):
            with self.subTest(url=value), self.assertRaises(ValueError):
                validate_production_settings({**good, 'APP_URL': value})
        with self.assertRaises(ValueError):
            validate_production_settings({**good, 'APP_ENV': 'prodution'})

    def test_shared_attempts_are_atomic_and_expire(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'attempts.db'
            # Create schema before concurrent calls; each call uses its own connection.
            reserve_attempt(path, 'setup', 5, 60, 100)
            with ThreadPoolExecutor(max_workers=8) as pool:
                accepted = list(pool.map(lambda _: reserve_attempt(path, 'ip:email', 5, 60, 100), range(20)))
            self.assertEqual(sum(accepted), 5)
            self.assertTrue(reserve_attempt(path, 'ip:email', 5, 60, 161))
            clear_attempts(path, 'ip:email')
            self.assertTrue(reserve_attempt(path, 'ip:email', 5, 60, 161))
            self.assertNotIn(b'ip:email', path.read_bytes())

    def test_production_csrf_requires_session_cookie_and_header(self):
        with patch('app.csrf.PRODUCTION', True):
            client = TestClient(app, follow_redirects=False)
            self.assertEqual(client.post('/api/auth/logout').status_code, 419)
            client.cookies.set('typography_csrf', 'forged')
            self.assertEqual(client.post('/api/auth/logout', headers={'X-CSRF-Token': 'forged'}).status_code, 419)
            client.cookies.clear()
            token = client.get('/api/csrf-token').json()['token']
            # Unknown route proves middleware accepts real session-bound token without writing data.
            self.assertEqual(client.post('/not-a-route', headers={'X-CSRF-Token': token}).status_code, 404)
            client.cookies.delete('laravel_session')
            self.assertEqual(client.post('/not-a-route', headers={'X-CSRF-Token': token}).status_code, 419)

    def test_production_diagnostics_require_admin(self):
        with patch('app.main.PRODUCTION', True), patch('app.main.current_user', return_value=None):
            client = TestClient(app)
            for url in ('/api/system/database', '/api/system/diagnostics'):
                self.assertEqual(client.get(url).status_code, 401)

    def test_smtp_requires_verified_starttls_before_authentication(self):
        with patch('app.main.RESET_MAIL_MODE', 'smtp'), patch.dict('os.environ', {
                'MAIL_HOST': 'smtp.example.test', 'MAIL_USERNAME': 'sender',
                'MAIL_PASSWORD': 'secret', 'MAIL_FROM': 'sender@example.test'}), \
                patch('app.main.smtplib.SMTP') as smtp:
            deliver_reset_mail('recipient@example.test', 'one-time-token')
            client = smtp.return_value.__enter__.return_value
            context = client.starttls.call_args.kwargs['context']
            self.assertTrue(context.check_hostname)
            import ssl
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            client.login.assert_called_once_with('sender', 'secret')
            client.send_message.assert_called_once()
            self.assertEqual([call[0] for call in client.method_calls], ['starttls', 'login', 'send_message'])