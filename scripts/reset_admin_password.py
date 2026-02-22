"""
强制重置管理员密码（独立脚本）。

用法：
  python3 scripts/reset_admin_password.py --username admin --password 'newpass'

依赖：
  - 读取 backend.config.settings.DATABASE_URL
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from backend.auth.jwt_utils import hash_password
from backend.database.db import async_session
from backend.database.models import User


async def _run(username: str, password: str) -> None:
    async with async_session() as db:
        r = await db.execute(select(User).where(User.username == username))
        user = r.scalar_one_or_none()
        if not user:
            raise SystemExit(f"用户不存在: {username}")
        user.password_hash = hash_password(password)
        await db.commit()
        print(f"已重置密码: {username}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", required=True)
    args = ap.parse_args()
    asyncio.run(_run(args.username, args.password))


if __name__ == "__main__":
    main()

