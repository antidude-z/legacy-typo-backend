"""Explicit operator-only role assignment; never creates roles or permissions."""
import argparse
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Role, User
from .admin_safety import require_surviving_admin, security_writer


@security_writer
def assign_role(db, user_selector, role_selector, apply=False):
    user_query = select(User).where(User.deleted_at.is_(None))
    user_query = user_query.where(User.id == int(user_selector[3:])) if user_selector.startswith('id:') else user_query.where(User.email == user_selector)
    users = db.scalars(user_query).all()
    role_query = select(Role)
    role_query = role_query.where(Role.id == int(role_selector[3:])) if role_selector.startswith('id:') else role_query.where(Role.title == role_selector)
    roles = db.scalars(role_query).all()
    if len(users) != 1 or len(roles) != 1:
        raise ValueError('Expected exactly one active user and one existing role; use id:N to disambiguate')
    user, role = users[0], roles[0]
    if user.fired:
        raise ValueError('Refusing assignment to a fired account')
    if apply:
        from fastapi import HTTPException
        try:
            require_surviving_admin(db, identity=user.id, changes={'role_id': role.id})
        except HTTPException as exc:
            raise ValueError(exc.detail) from exc
    result = {'user_id': user.id, 'email': user.email, 'previous_role_id': user.role_id,
              'role_id': role.id, 'role': role.title, 'applied': apply}
    if apply:
        user.role_id = role.id
        db.commit()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('user', help='Exact email or id:N')
    parser.add_argument('role', help='Exact role title or id:N')
    parser.add_argument('--apply', action='store_true', help='Commit; default is read-only preview')
    args = parser.parse_args()
    from .db import engine
    try:
        with Session(engine) as db:
            try:
                print(json.dumps(assign_role(db, args.user, args.role, args.apply), ensure_ascii=False))
            except ValueError as exc:
                parser.exit(1, f'{exc}\n')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()