"""모델이 직접 정한 컬럼명에 적용할 UUID PK 타입과 기본값을 제공한다."""

from typing import Annotated
from uuid import UUID, uuid4

from sqlalchemy import Uuid
from sqlalchemy.orm import mapped_column

# INSERT 시 UUID를 발급한다. flush 전에 필요하면 서비스에서 값을 직접 전달한다.
UUIDPrimaryKey = Annotated[UUID, mapped_column(Uuid, primary_key=True, default=uuid4)]
