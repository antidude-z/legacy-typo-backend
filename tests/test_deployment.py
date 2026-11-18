import unittest
from pathlib import Path

from app.deployment import validate_compose, validate_mysql_url, validate_nginx_proxy


ROOT = Path(__file__).resolve().parents[2]


class DeploymentTests(unittest.TestCase):
    def test_mysql_url_is_parsed_without_connecting(self):
        result = validate_mysql_url("mysql+pymysql://typography:secret@mysql:3306/typography")
        self.assertEqual(result["host"], "mysql")
        self.assertEqual(result["database"], "typography")
        self.assertTrue(result["has_password"])

    def test_mysql_url_rejects_non_mysql(self):
        with self.assertRaises(ValueError):
            validate_mysql_url("sqlite:///./data/typography.db")

    def test_compose_and_nginx_contracts(self):
        compose = validate_compose(ROOT / "docker-compose.yaml")
        self.assertTrue(compose["valid"])
        self.assertEqual(compose["mysql_profile"], "mysql")
        proxy = validate_nginx_proxy(ROOT / "frontend" / "nginx.conf")
        self.assertEqual(proxy["target"], "backend:8000")


if __name__ == "__main__":
    unittest.main()