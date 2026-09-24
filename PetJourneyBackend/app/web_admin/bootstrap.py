"""创建第一个平台员工账号。**只能在服务器上跑，网页没有对应入口。**

    python -m app.web_admin.bootstrap --username ops-owner --display-name 运营负责人

规则（这是"没有万能后门"的具体含义）：
- 已经存在任何员工账号时直接拒绝，除非显式 `--allow-additional`（那也要先在服务器上有执行权限）；
- 口令从 `PETSOUL_ADMIN_BOOTSTRAP_PASSWORD` 读；没给就随机生成，写进数据目录下
  `admin-bootstrap.local.txt`（0600 权限尽力而为），**不打印到终端、不写进仓库**；
- 默认角色 platform_owner；创建这件事本身会进审计。
- 公网环境（staging / production）下 `PETSOUL_ADMIN_REQUIRE_MFA` 默认开启，
  这个账号第一次登录后必须先入册 MFA 才能做任何事。这里不提供绕过参数。
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from ..config import load_settings
from ..storage import JourneyStorage
from ..web_platform.migrations import apply_web_migrations
from .audit import AuditLog
from .config import load_admin_settings
from .identity import AdminIdentityService, StaffExists


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="创建第一个 PetSoul 平台员工账号（仅服务器端）")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--roles", default="platform_owner", help="逗号分隔；默认 platform_owner")
    parser.add_argument("--allow-additional", action="store_true", help="已有员工时仍然创建（默认拒绝）")
    args = parser.parse_args(argv)

    settings = load_settings()
    storage = JourneyStorage(settings.database_path)
    apply_web_migrations(storage)
    admin_settings = load_admin_settings(getattr(settings, "web_environment", "dev"), bool(getattr(settings, "web_cookie_secure", True)))
    if not settings.auth_secret:
        print("拒绝：PETJOURNEY_AUTH_SECRET 没有配置，签发不了员工会话。", file=sys.stderr)
        return 2
    identity = AdminIdentityService(storage, auth_secret=settings.auth_secret, settings=admin_settings)
    if identity.any_staff_exists() and not args.allow_additional:
        print("拒绝：已经存在员工账号。要再建一个请在后台用平台负责人身份创建，"
              "或显式加 --allow-additional。", file=sys.stderr)
        return 3

    password = os.getenv("PETSOUL_ADMIN_BOOTSTRAP_PASSWORD") or secrets.token_urlsafe(18)
    generated = not os.getenv("PETSOUL_ADMIN_BOOTSTRAP_PASSWORD")
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    try:
        staff = identity.create_staff(args.username, password, args.display_name or args.username, roles, created_by="bootstrap")
    except StaffExists:
        print("拒绝：这个员工名已经存在。", file=sys.stderr)
        return 4

    AuditLog(storage).record(action="staff.bootstrap", status="succeeded", actor_username="bootstrap",
                             target_kind="staff", target_id=staff.staff_id,
                             reason="服务器端创建初始员工账号", changes={"roles": roles, "username": staff.username})

    out = Path(settings.database_path).parent / "admin-bootstrap.local.txt"
    if generated:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"username={staff.username}\npassword={password}\nstaff_id={staff.staff_id}\n", encoding="utf-8")
        try:
            os.chmod(out, 0o600)
        except OSError:
            pass
    print(f"已创建员工 {staff.staff_id}（{staff.username}），角色：{', '.join(staff.roles)}")
    print(f"口令写在 {out}（请立刻取走并删除该文件）" if generated else "口令取自 PETSOUL_ADMIN_BOOTSTRAP_PASSWORD，未落盘。")
    if admin_settings.require_mfa:
        print("本环境要求二次验证：这个账号第一次登录后必须先入册 MFA，否则任何权限检查都会被拒。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
