"""通道错误。OpenApiError 为其别名，避免 v1 / Cookie 路由再分一套。"""


class ChannelError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status
