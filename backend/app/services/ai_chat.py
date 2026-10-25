"""상위 실행 트랜잭션 안에서 일반 대화의 소유권·중복과 원문 저장을 관리한다."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import Reference
from app.core.exceptions import AppError
from app.models.ai_chat import AiMessage
from app.repositories import ai_chat as repository
from app.schemas.ai import ChatStart


async def save_user(
    session: AsyncSession,
    account_id: UUID,
    payload: ChatStart,
    now: datetime,
    *,
    retry: bool,
) -> None:
    conversation = await repository.ensure_conversation(
        session, payload.conversation_id, account_id, now
    )
    if conversation.account_id != account_id:
        raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")
    original = await repository.user_message(session, payload.request_id)
    if original is not None:
        if not retry or (
            original.ai_conversation_id != payload.conversation_id
            or original.client_message_id != payload.client_message_id
            or original.content != payload.content
        ):
            raise AppError(
                409,
                "MESSAGE_ID_CONFLICT",
                "이미 저장한 메시지입니다. 새 메시지 ID를 사용해 주세요.",
            )
        return
    inserted = await repository.insert_user(
        session,
        AiMessage(
            ai_conversation_id=payload.conversation_id,
            client_message_id=payload.client_message_id,
            request_id=payload.request_id,
            role="user",
            content=payload.content,
            attempt=1,
            model=None,
            source_references=[],
            created_at=now,
        ),
    )
    if not inserted:
        raise AppError(
            409,
            "MESSAGE_ID_CONFLICT",
            "이미 저장한 메시지입니다. 새 메시지 ID를 사용해 주세요.",
        )
    conversation.updated_at = now


async def save_answer(
    session: AsyncSession,
    payload: ChatStart,
    answer: str,
    attempt: int,
    model: str,
    sources: list[Reference],
    now: datetime,
) -> None:
    original = await repository.user_message(session, payload.request_id)
    if (
        original is None
        or original.ai_conversation_id != payload.conversation_id
        or original.client_message_id != payload.client_message_id
    ):
        raise ValueError("Missing accepted chat message")
    await repository.add_answer(
        session,
        AiMessage(
            ai_conversation_id=payload.conversation_id,
            client_message_id=payload.client_message_id,
            request_id=payload.request_id,
            role="assistant",
            content=answer,
            attempt=attempt,
            model=model,
            source_references=[ref.model_dump(mode="json") for ref in sources],
            created_at=now,
        ),
    )
    await repository.touch_conversation(session, payload.conversation_id, now)
