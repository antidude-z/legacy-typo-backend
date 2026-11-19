import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Role, User
from app.assign_role import assign_role


class AssignRoleTests(unittest.TestCase):
    def test_preview_apply_and_reject_unknown_or_inactive(self):
        engine = create_engine('sqlite:///:memory:')
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                db.add_all([Role(id=1, title='Менеджер'), Role(id=2, title='Администратор'),
                            User(id=1, name='QA', email='qa@example.test', password='unused', role_id=1)])
                db.commit()
                self.assertFalse(assign_role(db, 'qa@example.test', 'Администратор')['applied'])
                self.assertEqual(db.get(User, 1).role_id, 1)
                assign_role(db, 'id:1', 'id:2', True)
                self.assertEqual(db.get(User, 1).role_id, 2)
                with self.assertRaises(ValueError):
                    assign_role(db, 'missing', 'id:2', True)
                db.get(User, 1).fired = 1
                db.commit()
                with self.assertRaises(ValueError):
                    assign_role(db, 'id:1', 'id:1', True)
        finally:
            engine.dispose()