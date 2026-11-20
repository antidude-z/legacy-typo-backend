"""S02 admission contract on an empty, guarded, disposable MySQL database."""
import os
import unittest

import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base, get_db
from app.main import app
from app.models import User
from app.mysql_test_guard import verify_test_database
from tests import test_review_registration


@unittest.skipUnless(os.getenv('S02_MYSQL_URL'), 'Requires isolated S02 MySQL')
class MySQLRegistrationReviewTests(test_review_registration.RegistrationReviewTests):
    def setUp(self):
        url = os.environ['S02_MYSQL_URL']
        verify_test_database(url, os.getenv('DATABASE_URL'))
        self.engine = create_engine(url)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        if self.db.scalar(select(User.id).limit(1)) is not None:
            self.db.close()
            self.engine.dispose()
            raise RuntimeError('S02 requires an empty disposable fixture database')
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.password = 'secret123'
        self.user = User(id=10, name='Existing', email='existing@example.test',
                         password=bcrypt.hashpw(self.password.encode(), bcrypt.gensalt()).decode())
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.db.close()
        # Only the dedicated empty fixture server supplied for this test is used.
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()