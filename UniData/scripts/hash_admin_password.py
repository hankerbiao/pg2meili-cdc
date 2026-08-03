"""生成 OPEN_PLATFORM_ADMIN_PASSWORD_HASH 配置值。"""
from getpass import getpass

from argon2 import PasswordHasher


if __name__ == "__main__":
    password = getpass("Admin password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("两次密码不一致")
    if len(password) < 12:
        raise SystemExit("密码至少需要 12 个字符")
    print(PasswordHasher().hash(password))
