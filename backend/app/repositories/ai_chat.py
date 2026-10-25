"""대화 소유 행과 입력·답변의 중복 없는 저장을 담당한다."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_chat import AiConversation, AiMessage


async def ensure_conversation(
    session: AsyncSession, conversation_id: UUID, account_id: UUID, now: datetime
) -> AiConversation:
    await session.execute(
        insert(AiConversation)
        .values(
            ai_conversation_id=conversation_id,
            account_id=account_id,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=[AiConversation.ai_conversation_id])
    )
    return (
        await session.scalars(
            select(AiConversation)
            .where(AiConversation.ai_conversation_id == conversation_id)
            .with_for_update()
        )
    ).one()


async def user_message(session: AsyncSession, request_id: UUID) -> AiMessage | None:
    return (
        await session.scalars(
            select(AiMessage).where(
                AiMessage.request_id == request_id, AiMessage.role == "user"
            )
        )
    ).one_or_none()


async def insert_user(session: AsyncSession, message: AiMessage) -> bool:
    identifier = await session.scalar(
        insert(AiMessage)
        .values(
            ai_conversation_id=message.ai_conversation_id,
            client_message_id=message.client_message_id,
            request_id=message.request_id,
            role="user",
            content=message.content,
            attempt=1,
            model=None,
            source_references=[],
            created_at=message.created_at,
        )
        .on_conflict_do_nothing()
        .returning(AiMessage.ai_message_id)
    )
    return identifier is not None


async def add_answer(session: AsyncSession, message: AiMessage) -> None:
    session.add(message)
    await session.flush()


async def touch_conversation(
    session: AsyncSession, conversation_id: UUID, now: datetime
) -> None:
    await session.execute(
        update(AiConversation)
        .where(AiConversation.ai_conversation_id == conversation_id)
        .values(updated_at=now)
    )
