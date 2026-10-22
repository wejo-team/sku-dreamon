class AppError(Exception):
    """An expected failure with a safe, client-facing message."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        if status_code == 422:
            raise ValueError("422 is reserved for request validation errors")
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
