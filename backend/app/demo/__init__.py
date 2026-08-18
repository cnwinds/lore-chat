"""公开演示站运行时：访客身份、只读门禁、限流。"""

from app.demo.identity import IDENTITY_ADMIN, IDENTITY_GUEST, resolve_identity

__all__ = ["IDENTITY_ADMIN", "IDENTITY_GUEST", "resolve_identity"]
