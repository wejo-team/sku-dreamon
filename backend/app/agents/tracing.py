"""명시적 LangSmith Client로 LangChain의 기본 실행 추적을 연결한다."""

import asyncio
import logging
import os
import re
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID, uuid4

from langchain_core.runnables import RunnableConfig
from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client, tracing_context
from langsmith import utils as langsmith_utils
from langsmith.anonymizer import create_secret_anonymizer
from urllib3.util.retry import Retry

from app.core.config import Settings
from app.schemas.ai import AiPurpose

logger = logging.getLogger(__name__)
INPUT_GUARD_TAG = "ai_input_guard"
FINAL_ANSWER_TAG = "ai_final_answer"


@dataclass(frozen=True)
class AiTraceContext:
    """실행 ID는 로컬 상관 로그에만 사용한다."""

    request_id: UUID
    attempt: int


class AiTracing:
    """네이티브 SDK의 배치 전송과 유한한 앱 종료 대기만 관리한다."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client: Client | None = None
        if settings.langsmith_api_key is None:
            if settings.app_env == "production" and settings.ai_enabled:
                logger.warning("AI tracing unavailable: LangSmith API key is missing")
            return
        # 공식 SDK의 daemon 배치를 사용하고 압축 전송의 별도 executor는 끈다.
        os.environ["LANGSMITH_USE_DAEMON"] = "true"
        os.environ["LANGSMITH_DISABLE_RUN_COMPRESSION"] = "true"
        # SDK의 overload 타입이 functools의 cache_clear API를 노출하지 않는다.
        cast(Any, langsmith_utils.get_env_var).cache_clear()
        secrets = [
            value.get_secret_value()
            for value in (
                settings.openai_api_key,
                settings.langsmith_api_key,
                settings.csrf_signing_key,
            )
            if value is not None and value.get_secret_value()
        ]
        try:
            endpoint = str(settings.langsmith_endpoint).rstrip("/")
            self.client = Client(
                api_urls={endpoint: settings.langsmith_api_key.get_secret_value()},
                workspace_id=str(settings.langsmith_workspace_id or ""),
                auto_batch_tracing=True,
                hide_inputs=settings.langsmith_hide_inputs,
                hide_outputs=settings.langsmith_hide_outputs,
                hide_metadata=False,
                anonymizer=create_secret_anonymizer(
                    extra_rules=[
                        {
                            "pattern": re.compile(re.escape(value)),
                            "replace": "[REDACTED]",
                        }
                        for value in secrets
                    ]
                ),
                omit_traced_runtime_info=True,
                tracing_mode="langsmith",
                tracing_sampling_rate=1.0,
                timeout_ms=(1000, 1000),
                retry_config=Retry(total=0),
            )
        except Exception:
            logger.warning("AI tracing initialization failed")

    def context(self) -> AbstractContextManager[None]:
        # await마다 설정하고 yield 전에 복구해 다른 task·요청으로 새지 않게 한다.
        return tracing_context(
            enabled=self.client is not None,
            client=self.client,
            project_name=self.settings.langsmith_project,
            parent=False,
            replicas=[],
        )

    def config(
        self, purpose: AiPurpose, context: AiTraceContext | None
    ) -> RunnableConfig:
        if self.client is None:
            return {"callbacks": []}
        trace_id = uuid4()
        metadata: dict[str, object] = {"purpose": purpose}
        if context is not None:
            metadata["request_attempt"] = context.attempt
            logger.info(
                "AI trace request_id=%s attempt=%s trace_id=%s",
                context.request_id,
                context.attempt,
                trace_id,
            )
        return {
            "callbacks": [
                LangChainTracer(
                    client=self.client, project_name=self.settings.langsmith_project
                )
            ],
            "run_name": "ai_turn",
            "run_id": trace_id,
            "metadata": metadata,
        }

    async def aclose(self) -> None:
        if self.client is None:
            return
        client, self.client = self.client, None
        timeout = min(2.0, self.settings.shutdown_timeout_seconds)
        try:
            async with asyncio.timeout(timeout):
                await asyncio.to_thread(client.close, timeout=timeout)
        except Exception:
            logger.warning("AI tracing shutdown incomplete")
