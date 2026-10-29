"""앱이 유일한 전달 헤더 검증자가 되도록 운영 HTTP 서버를 실행한다."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        proxy_headers=False,
        forwarded_allow_ips="",
    )


if __name__ == "__main__":
    main()
