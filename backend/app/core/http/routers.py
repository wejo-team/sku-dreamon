"""서비스 조회 결과를 공통 응답 계약과 명시적인 HTTP 경로에 연결한다."""

from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, params

from app.core.http.handlers import error_responses
from app.core.http.schemas import Page, ResponseDTO, Success


class BaseCrudRouter:
    """필요한 조회 경로와 의존성만 등록하는 HTTP 어댑터를 제공한다.

    핸들러는 요청 입력을 받아 도메인 서비스를 호출한다. 권한·조회 조건과
    페이지 계산은 서비스가 책임지며, 쓰기와 업무 명령은 router에 직접 등록한다.
    """

    def __init__(
        self,
        *,
        prefix: str,
        tags: list[str] | None = None,
        dependencies: Sequence[params.Depends] = (),
    ) -> None:
        self.router = APIRouter(
            prefix=prefix,
            tags=list(tags) if tags is not None else None,
            dependencies=dependencies,
        )

    def add_list[ItemType: ResponseDTO](
        self,
        path: str = "",
        *,
        handler: Callable[..., Page[ItemType] | Awaitable[Page[ItemType]]],
        response_model: type[Page[ItemType]],
        dependencies: Sequence[params.Depends] = (),
        error_statuses: Sequence[int] = (),
        name: str | None = None,
        summary: str | None = None,
    ) -> None:
        """서비스가 계산한 목록과 페이지 정보를 그대로 반환하는 GET을 등록한다.

        response_model에 확장 페이지 모델을 전달하면 해당 모델의 추가 필드도
        응답과 OpenAPI에 포함된다. 인증과 업무 오류는 의존성·핸들러에서 처리한다.
        """

        async def endpoint(result: Annotated[object, Depends(handler)]) -> object:
            return result

        self.router.add_api_route(
            path,
            endpoint,
            methods=["GET"],
            response_model=response_model,
            dependencies=dependencies,
            responses=error_responses(422, 500, 503, *error_statuses),
            name=name,
            summary=summary,
        )

    def add_detail[ItemType: ResponseDTO](
        self,
        path: str,
        *,
        handler: Callable[..., ItemType | Awaitable[ItemType]],
        response_model: type[Success[ItemType]],
        dependencies: Sequence[params.Depends] = (),
        error_statuses: Sequence[int] = (),
        name: str | None = None,
        summary: str | None = None,
    ) -> None:
        """상세 DTO를 공통 성공 응답으로 감싸는 GET을 등록한다.

        대상의 존재·열람 권한은 서비스가 판단하고 적절한 오류를 발생시킨다.
        핸들러의 경로·query 검증과 의존성 실행은 FastAPI가 담당한다.
        """

        async def endpoint(
            result: Annotated[object, Depends(handler)],
        ) -> dict[str, object]:
            return {"data": result}

        self.router.add_api_route(
            path,
            endpoint,
            methods=["GET"],
            response_model=response_model,
            dependencies=dependencies,
            responses=error_responses(404, 422, 500, 503, *error_statuses),
            name=name,
            summary=summary,
        )
