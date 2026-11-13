"""Command-line entry point for tracked schema migrations."""

import argparse

from .db import engine
from .schema import apply_migrations, migration_status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "upgrade"), default="status", nargs="?")
    args = parser.parse_args()
    if args.command == "status":
        print(migration_status(engine))
        return
    print("before:", migration_status(engine))
    applied = apply_migrations(engine)
    print("applied:", applied or "none")
    print("after:", migration_status(engine))


if __name__ == "__main__":
    main()