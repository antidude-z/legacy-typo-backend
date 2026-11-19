"""Create a fresh browser-only SQLite fixture; never uses the configured DB."""
from pathlib import Path
import os
import argparse
import bcrypt
from sqlalchemy import create_engine, select
from app.bootstrap import initialize_database
from app.models import User, Role, Permission, Prepress, Bill, Customer
from sqlalchemy.orm import Session
from app.mysql_test_guard import verify_test_database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mysql-clone', action='store_true')
    args = parser.parse_args()
    if args.mysql_clone:
        url = os.environ['MYSQL_TEST_URL']
        verify_test_database(url)
        engine = create_engine(url)
    else:
        target = Path('data/browser-e2e.db').resolve()
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            target.unlink()
        engine = create_engine('sqlite:///' + target.as_posix())
    initialize_database(engine)
    with Session(engine) as db:
        role = Role(title='Browser QA', permissions=db.scalars(select(Permission)).all())
        reader = Role(title='Browser Orders reader', permissions=[db.get(Permission, 'view_menu_orders')])
        for email, name, assigned_role in [('browser@example.test', 'Browser', role), ('limited@example.test', 'Pending', None), ('reader@example.test', 'Reader', reader)]:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email)
                db.add(user)
            user.name = name; user.surname = 'QA'; user.role = assigned_role
            user.fired = 0; user.deleted_at = None
            user.password = bcrypt.hashpw(b'Browser-test-123', bcrypt.gensalt()).decode()
        if db.scalar(select(Prepress).where(Prepress.title == 'Browser prepress')) is None:
            db.add(Prepress(title='Browser prepress'))
        if not args.mysql_clone:
            from datetime import date
            db.add(Bill(id=88001, number='Orphan browser', bill_date=date(2024, 1, 1),
                        amount=10, currency='RUB', payer_id=88002, user_id=88003))
            db.add(Customer(id=88001, title='Orphan browser', customer_group_id=88002))
        db.commit()
    engine.dispose()


if __name__ == '__main__':
    main()