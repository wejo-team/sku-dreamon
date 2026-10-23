"""선택한 조회 라우트의 응답·의존성·검증·오류와 OpenAPI 계약을 검증한다."""

from typing import Annotated, Literal
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response
from httpx import AsyncClient

from app.core.exceptions import AppError
from app.core.http.routers import BaseCrudRouter
from app.core.http.schemas import Page, PageMeta, ResponseDTO, Success

pytestmark = pytest.mark.integration

ITEM_ID = UUID("c41b5860-3371-4766-8505-e7ce57c34e29")


class ListItem(ResponseDTO):
    item_id: UUID
    display_name: str


class ItemPage(Page[ListItem]):
    unread_count: int


class DetailItem(ResponseDTO):
    item_id: UUID
    display_name: str
    contact_note: str


class ProjectDetail(ResponseDTO):
    project_title: str


@pytest.fixture(autouse=True)
def crud_calls(app: FastAPI) -> list[str]:
    calls: list[str] = []
    items = BaseCrudRouter(prefix="/crud/items", tags=["items"])

    async def list_items(
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 3,
    ) -> ItemPage:
        calls.append("list")
        return ItemPage(
            data=[ListItem(item_id=ITEM_ID, display_name="listed")],
            pagination=PageMeta(page=page, page_size=page_size, total=9, total_pages=3),
            unread_count=4,
        )

    def get_label() -> str:
        return "detail"

    def detail_item(
        item_id: UUID,
        response: Response,
        label: Annotated[str, Depends(get_label)],
        outcome: Literal["ok", "missing", "conflict", "http_missing"] = "ok",
    ) -> DetailItem:
        calls.append("detail")
        if outcome == "missing":
            raise AppError(404, "ITEM_NOT_FOUND", "항목을 찾을 수 없습니다.")
        if outcome == "conflict":
            raise AppError(409, "ITEM_CONFLICT", "항목이 변경되었습니다.")
        if outcome == "http_missing":
            raise HTTPException(404, detail="private lookup detail")
        response.headers["X-Record-Source"] = "service"
        response.set_cookie("view-token", "example", httponly=True)
        return DetailItem(
            item_id=item_id, display_name=label, contact_note="detail only"
        )

    items.add_list(
        handler=list_items,
        response_model=ItemPage,
        name="list_items",
        summary="항목 목록",
    )
    items.add_detail(
        "/{item_id}",
        handler=detail_item,
        response_model=Success[DetailItem],
        error_statuses=[409],
        name="detail_item",
        summary="항목 상세",
    )

    @items.router.post("/logout", status_code=204)
    async def logout() -> Response:
        response = Response(status_code=204)
        response.delete_cookie("view-token")
        return response

    projects = BaseCrudRouter(prefix="/crud/projects")

    async def detail_project(
        project_id: Annotated[UUID, Path(alias="projectId")],
    ) -> ProjectDetail:
        calls.append("project")
        return ProjectDetail(project_title=str(project_id))

    projects.add_detail(
        "/{projectId}",
        handler=detail_project,
        response_model=Success[ProjectDetail],
    )

    def check_router_auth(request: Request) -> None:
        calls.append("router_auth")
        if request.headers.get("x-session") != "allowed":
            raise HTTPException(401)

    async def check_operation_auth(request: Request) -> None:
        calls.append("operation_auth")
        if request.headers.get("x-role") != "reader":
            raise HTTPException(403)

    private = BaseCrudRouter(
        prefix="/crud/private", dependencies=[Depends(check_router_auth)]
    )

    async def private_detail(item_id: UUID) -> ListItem:
        calls.append("private_service")
        return ListItem(item_id=item_id, display_name="private")

    private.add_detail(
        "/{item_id}",
        handler=private_detail,
        response_model=Success[ListItem],
        dependencies=[Depends(check_operation_auth)],
        error_statuses=[401, 403],
    )
    for router in (items.router, projects.router, private.router):
        app.include_router(router)
    return calls


async def test_routes_are_explicit_and_writes_are_not_generated(
    client: AsyncClient,
) -> None:
    assert BaseCrudRouter(prefix="/unused").router.routes == []
    for method, path in (
        ("POST", "/crud/items"),
        ("PUT", f"/crud/items/{ITEM_ID}"),
        ("PATCH", f"/crud/items/{ITEM_ID}"),
        ("DELETE", f"/crud/items/{ITEM_ID}"),
    ):
        response = await client.request(method, path)
        assert response.status_code == 405


async def test_sync_and_async_handlers_preserve_models_metadata_and_headers(
    client: AsyncClient, crud_calls: list[str]
) -> None:
    listing = await client.get("/crud/items", params={"page": 2, "pageSize": 3})
    detail = await client.get(f"/crud/items/{ITEM_ID}")
    project = await client.get(f"/crud/projects/{ITEM_ID}")

    assert listing.status_code == detail.status_code == project.status_code == 200
    assert listing.json() == {
        "data": [{"itemId": str(ITEM_ID), "displayName": "listed"}],
        "pagination": {"page": 2, "pageSize": 3, "total": 9, "totalPages": 3},
        "unreadCount": 4,
    }
    assert detail.json() == {
        "data": {
            "itemId": str(ITEM_ID),
            "displayName": "detail",
            "contactNote": "detail only",
        }
    }
    assert detail.headers["x-record-source"] == "service"
    assert "view-token=example" in detail.headers["set-cookie"]
    assert project.json() == {"data": {"projectTitle": str(ITEM_ID)}}
    assert crud_calls == ["list", "detail", "project"]


@pytest.mark.parametrize(
    ("path", "location"),
    [
        ("/crud/items/not-a-uuid", ["path", "item_id"]),
        ("/crud/items?page=0", ["query", "page"]),
    ],
)
async def test_validation_rejects_invalid_inputs_before_calling_handler(
    client: AsyncClient, crud_calls: list[str], path: str, location: list[str]
) -> None:
    response = await client.get(path)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == location
    assert crud_calls == []


async def test_router_and_operation_dependencies_block_service_calls(
    client: AsyncClient, crud_calls: list[str]
) -> None:
    path = f"/crud/private/{ITEM_ID}"
    denied_session = await client.get(path)
    assert denied_session.status_code == 401
    assert crud_calls == ["router_auth"]

    crud_calls.clear()
    denied_role = await client.get(path, headers={"x-session": "allowed"})
    assert denied_role.status_code == 403
    assert crud_calls == ["router_auth", "operation_auth"]

    crud_calls.clear()
    allowed = await client.get(
        path, headers={"x-session": "allowed", "x-role": "reader"}
    )
    assert allowed.status_code == 200
    assert crud_calls == ["router_auth", "operation_auth", "private_service"]


@pytest.mark.parametrize(
    ("outcome", "status_code", "error_code"),
    [
        ("missing", 404, "ITEM_NOT_FOUND"),
        ("conflict", 409, "ITEM_CONFLICT"),
        ("http_missing", 404, "RESOURCE_NOT_FOUND"),
    ],
)
async def test_service_errors_keep_status_and_common_error_shape(
    client: AsyncClient, outcome: str, status_code: int, error_code: str
) -> None:
    response = await client.get(f"/crud/items/{ITEM_ID}", params={"outcome": outcome})

    assert response.status_code == status_code
    assert set(response.json()) == {"error", "requestId"}
    assert response.json()["error"]["code"] == error_code
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert "private lookup detail" not in response.text


async def test_custom_routes_keep_empty_responses_and_cookies(
    client: AsyncClient,
) -> None:
    response = await client.post("/crud/items/logout")

    assert response.status_code == 204
    assert response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]


async def test_openapi_describes_actual_models_parameters_and_errors(
    client: AsyncClient,
) -> None:
    schema = (await client.get("/openapi.json")).json()
    models = schema["components"]["schemas"]
    listing = schema["paths"]["/crud/items"]["get"]
    detail = schema["paths"]["/crud/items/{item_id}"]["get"]
    private = schema["paths"]["/crud/private/{item_id}"]["get"]
    project = schema["paths"]["/crud/projects/{projectId}"]["get"]

    assert listing["tags"] == ["items"]
    assert listing["summary"] == "항목 목록"
    assert detail["summary"] == "항목 상세"
    assert listing["operationId"].startswith("list_items_")
    assert detail["operationId"].startswith("detail_item_")
    assert {(item["name"], item["in"]) for item in listing["parameters"]} == {
        ("page", "query"),
        ("pageSize", "query"),
    }
    detail_parameters = {item["name"]: item for item in detail["parameters"]}
    assert set(detail_parameters) == {"item_id", "outcome"}
    assert detail_parameters["item_id"]["in"] == "path"
    assert detail_parameters["item_id"]["schema"]["format"] == "uuid"
    assert len(project["parameters"]) == 1
    assert project["parameters"][0]["name"] == "projectId"
    assert project["parameters"][0]["in"] == "path"
    assert project["parameters"][0]["schema"]["format"] == "uuid"

    page_ref = listing["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    page_properties = models[page_ref.rsplit("/", 1)[1]]["properties"]
    assert set(page_properties) == {"data", "pagination", "unreadCount"}
    assert page_properties["data"]["items"] == {"$ref": "#/components/schemas/ListItem"}
    detail_ref = detail["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert models[detail_ref.rsplit("/", 1)[1]]["properties"] == {
        "data": {"$ref": "#/components/schemas/DetailItem"}
    }
    assert set(listing["responses"]) == {"200", "422", "500", "503"}
    assert set(detail["responses"]) == {"200", "404", "409", "422", "500", "503"}
    assert {"401", "403"} <= set(private["responses"])
    assert detail["responses"]["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ValidationErrorResponse"
    }
    assert detail["responses"]["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert (
        "content"
        not in schema["paths"]["/crud/items/logout"]["post"]["responses"]["204"]
    )
