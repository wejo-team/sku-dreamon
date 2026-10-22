from app.schemas.base import ResponseDTO
from app.schemas.types import NonnegativeInt, PageSize, PositiveInt


class Success[T](ResponseDTO):
    data: T


class PageMeta(ResponseDTO):
    page: PositiveInt
    page_size: PageSize
    total: NonnegativeInt
    total_pages: NonnegativeInt


class Page[T](ResponseDTO):
    data: list[T]
    pagination: PageMeta
