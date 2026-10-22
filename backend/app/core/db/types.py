from typing import Annotated
from uuid import UUID, uuid4

from sqlalchemy import Uuid
from sqlalchemy.orm import mapped_column

# Generated at INSERT; pass a UUID explicitly when it is needed before flush.
UUIDPrimaryKey = Annotated[UUID, mapped_column(Uuid, primary_key=True, default=uuid4)]
