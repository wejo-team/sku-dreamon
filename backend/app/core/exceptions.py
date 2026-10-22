"""안전한 안내 문구와 HTTP 상태를 전달하는 애플리케이션 예외를 정의한다."""


class AppError(Exception):
    """클라이언트에 공개할 수 있는 안내 문구로 예상 가능한 실패를 전달한다."""

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
