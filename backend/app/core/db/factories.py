"""레포지토리 생성과 DB 세션 소유권의 공통 계약을 제공한다."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import Database


class RepositoryFactory[RepositoryType]:
    """요청과 독립 실행에 동일한 레포지토리 생성 방식을 제공한다.

    외부에서 받은 세션의 수명은 호출자가 관리하고, 자체 세션의 수명은
    레포지토리 사용 범위에 맞춘다. 트랜잭션의 저장 확정은 서비스가 맡는다.
    생성자로 클래스 또는 추가 의존성을 묶은 함수를 사용할 수 있다.
    """

    def __init__(
        self,
        *,
        repository_class: Callable[[AsyncSession], RepositoryType],
        database: Database | None = None,
    ) -> None:
        self._repository_class = repository_class
        self._database = database

    def create_repository(self, db_session: AsyncSession) -> RepositoryType:
        """호출자의 세션을 공유하는 레포지토리를 생성한다.

        세션의 커밋과 종료에 대한 책임은 호출자에게 있다.
        """
        return self._repository_class(db_session)

    @asynccontextmanager
    async def open_repository(self) -> AsyncIterator[RepositoryType]:
        """독립된 세션을 사용하는 레포지토리를 사용 범위 동안 제공한다.

        database가 없으면 ValueError를 발생시킨다. 범위를 벗어나면 세션을
        정리하고 미커밋 변경을 롤백한다. 생성자와 본문의 예외는 전파한다.
        """
        if self._database is None:
            raise ValueError("database is required to open a repository")

        async with self._database.session() as session:
            yield self.create_repository(session)
