"""Create a fresh browser-only SQLite fixture; never uses the configured DB."""
from pathlib import Path
import bcrypt
from sqlalchemy import create_engine, select
from app.bootstrap import initialize_database
from app.models import User, Role, Permission, Prepress
from sqlalchemy.orm import Session


def main():
    target = Path('data/browser-e2e.db').resolve()
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        target.unlink()
    engine = create_engine('sqlite:///' + target.as_posix())
    initialize_database(engine)
    with Session(engine) as db:
        role = Role(title='Browser QA', permissions=db.scalars(select(Permission)).all())
        db.add(User(name='Browser', surname='QA', email='browser@example.test', role=role,
                    password=bcrypt.hashpw(b'Browser-test-123', bcrypt.gensalt()).decode()))
        db.add(Prepress(title='Browser prepress'))
        db.commit()
    engine.dispose()


if __name__ == '__main__':
    main()