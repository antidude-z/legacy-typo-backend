"""Read-only inventory: IDs and account state only, never credentials."""
import json
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from .db import engine
from .models import User


def inventory(db):
    return [
        {"id": user.id, "role_id": user.role_id, "fired": bool(user.fired),
         "deleted": user.deleted_at is not None,
         "reason": "missing_role" if user.role is None else "empty_permissions"}
        for user in db.scalars(select(User).options(joinedload(User.role)).order_by(User.id))
        if user.role is None or not user.role.permissions
    ]


if __name__ == "__main__":
    with Session(engine) as db:
        print(json.dumps({"pending_accounts": inventory(db)}, indent=2))