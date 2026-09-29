"""发布前运行 python -m app.migrations；--check 仅校验版本。"""

import argparse

from app.db import close_pg_pool, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        init_db(migrate=not args.check)
    finally:
        close_pg_pool()


if __name__ == "__main__":
    main()
