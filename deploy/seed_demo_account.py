#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seed the demo account on a fresh clone.

The repo tracks the demo account's showcase data (chats / workspaces / notes)
under the fixed student id ``usr_12e410b4e2``, but ``users/accounts.json`` is
runtime state and stays gitignored (it holds other accounts' password hashes).
Run this script once after cloning so the demo account exists with the SAME
id and the tracked data lights up in the UI:

    python deploy/seed_demo_account.py

账号：example@example.com / example（角色 student，档案 grade=本科）
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
for p in (str(BACKEND), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.identity.models import UserProfile                      # noqa: E402
from app.identity.security import hash_password, verify_password  # noqa: E402
from app.identity import store                                   # noqa: E402

DEMO_EMAIL = "example@example.com"
DEMO_PASSWORD = "example"
DEMO_ID = "usr_12e410b4e2"


def main() -> int:
    user = store.get_by_email(DEMO_EMAIL)
    if user is None:
        user = store.create_user(
            email=DEMO_EMAIL,
            username="example",
            password_hash=hash_password(DEMO_PASSWORD),
            role="student",
            profile=UserProfile(name="example", grade="本科",
                                subjects=["数学", "物理"]),
            user_id=DEMO_ID,
        )
        print(f"created demo account {user.email} id={user.id}")
        return 0
    if user.id != DEMO_ID:
        print(f"WARNING: existing account id is {user.id}, expected {DEMO_ID}; "
              "tracked demo data will not match this account.")
        return 1
    if not verify_password(DEMO_PASSWORD, user.password_hash):
        user.password_hash = hash_password(DEMO_PASSWORD)
        store.update_user(user)
        print("password reset to the documented demo password")
    else:
        print("demo account already present with the expected id/password")
    if (user.profile.grade or "") != "本科":
        user.profile.grade = "本科"
        store.update_user(user)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
