"""Central credential revocation; callers commit the user-row update together."""
import secrets
from sqlalchemy import delete
from .models import PasswordReset


def discard_password_resets(db, email):
    """Consume recovery material before changing credentials (fail closed on MyISAM)."""
    db.execute(delete(PasswordReset).where(PasswordReset.email == email))


def revoke_credentials(user):
    user.security_stamp = secrets.token_hex(32)
    user.remember_token = None


def replace_password(user, password_hash):
    user.password = password_hash
    revoke_credentials(user)