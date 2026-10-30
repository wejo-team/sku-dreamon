"""모델·도구 원문을 받는 콜백에서 허용된 관측 값만 새 실행으로 내보낸다."""

import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from queue import Empty, Full, Queue
from typing import Any, Literal
from uuid import UUID, uuid4

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from langsmith import Client
from urllib3.util.retry import Retry

from app.core.config import Settings
from app.schemas.ai import AiPurpose

logger = logging.getLogger(__name__)

INPUT_GUARD_TAG = "ai_input_guard"
FINAL_ANSWER_TAG = "ai_final_answer"
TOOL_NAMES = frozenset(
    {
        "search_people",
        "search_contests",
        "search_teams",
        "get_resource_detail",
        "read_applicant",
        "list_applicants",
        "prepare_recommendations",
    }
)
TraceStatus = Literal["completed", "blocked", "failed", "canceled"]
TraceOperation = tuple[Literal["create", "update"], dict[str, Any]]
TRACE_QUEUE_SIZE = 256


@dataclass(frozen=True)
class AiTraceContext:
    """요청 ID는 로컬 상관 로그에만 쓰고 외부 추적에는 복사하지 않는다."""

    request_id: UUID
    attempt: int


@dataclass(frozen=True)
class Span:
    id: UUID
    order: str
    is_model: bool = False


def _segment(start: datetime, run_id: UUID) -> str:
    return start.strftime("%Y%m%dT%H%M%S%fZ") + str(run_id)


class AiTracing:
    """유한한 앱 큐에 즉시 추가하고 단일 daemon worker만 SDK·HTTP를 실행한다."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client: Client | None = None
        self.queue: Queue[TraceOperation] = Queue(maxsize=TRACE_QUEUE_SIZE)
        self.stopping = threading.Event()
        self.worker: threading.Thread | None = None
        if not settings.langsmith_tracing:
            return
        assert settings.langsmith_api_key is not None
        try:
            self.client = Client(
                # 단일 목적지를 명시해 ambient RUNS_ENDPOINTS로 복제하지 않는다.
                api_urls={
                    str(settings.langsmith_endpoint).rstrip(
                        "/"
                    ): settings.langsmith_api_key.get_secret_value()
                },
                workspace_id=(
                    str(settings.langsmith_workspace_id)
                    if settings.langsmith_workspace_id is not None
                    else ""
                ),
                # SDK 배치는 자체 retry/sleep를 추가하므로 앱이 큐를 소유한다.
                auto_batch_tracing=False,
                hide_inputs=True,
                hide_outputs=True,
                hide_metadata=False,
                omit_traced_runtime_info=True,
                tracing_mode="langsmith",
                tracing_sampling_rate=1.0,
                timeout_ms=(1000, 1000),
                retry_config=Retry(total=0),
            )
            self.worker = threading.Thread(
                target=self._export,
                args=(self.client,),
                name="ai-trace-export",
                daemon=True,
            )
            self.worker.start()
        except Exception:
            client, self.client = self.client, None
            self.worker = None
            if client is not None:
                try:
                    client.close(timeout=0)
                except Exception:
                    pass
            logger.warning("AI tracing initialization failed")

    def start(
        self, purpose: AiPurpose, context: AiTraceContext | None
    ) -> "TurnTrace | None":
        if self.client is None:
            return None
        trace = TurnTrace(self, self.settings, purpose, context)
        trace.start()
        return trace

    def create_run(self, **payload: Any) -> None:
        self._enqueue("create", payload)

    def update_run(self, run_id: UUID, **payload: Any) -> None:
        self._enqueue("update", {"run_id": run_id, **payload})

    def _enqueue(
        self, operation: Literal["create", "update"], payload: dict[str, Any]
    ) -> None:
        if self.stopping.is_set():
            return
        try:
            self.queue.put_nowait((operation, payload))
        except Full:
            logger.warning("AI tracing queue full; telemetry dropped")

    def _export(self, client: Client) -> None:
        try:
            while not self.stopping.is_set() or not self.queue.empty():
                try:
                    operation, payload = self.queue.get(timeout=0.05)
                except Empty:
                    continue
                try:
                    if operation == "create":
                        client.create_run(**payload)
                    else:
                        client.update_run(**payload)
                except Exception:
                    logger.warning("AI tracing export failed")
                finally:
                    self.queue.task_done()
        finally:
            # HTTP와 session close가 다른 task에서 경쟁하지 않게 worker가 소유한다.
            try:
                client.close(timeout=0)
            except Exception:
                logger.warning("AI tracing shutdown incomplete")

    async def aclose(self) -> None:
        if self.worker is None or self.stopping.is_set():
            return
        self.client = None
        self.stopping.set()
        timeout = min(2.0, self.settings.shutdown_timeout_seconds)
        try:
            await asyncio.to_thread(self.worker.join, timeout=timeout)
        finally:
            if self.worker.is_alive():
                # deadline 뒤 아직 전송하지 않은 관측만 폐기한다. 진행 중 HTTP는
                # 유한 timeout으로 끝나며 daemon이 프로세스 종료를 붙잡지 않는다.
                while True:
                    try:
                        self.queue.get_nowait()
                    except Empty:
                        break
                    else:
                        self.queue.task_done()
                logger.warning("AI tracing shutdown incomplete; telemetry dropped")


class TurnTrace(AsyncCallbackHandler):
    """직렬화·입출력·예외 문자열·외부 metadata를 SDK에 전달하지 않는다."""

    run_inline = True

    def __init__(
        self,
        client: AiTracing,
        settings: Settings,
        purpose: AiPurpose,
        context: AiTraceContext | None,
    ) -> None:
        self.client, self.project = client, settings.langsmith_project
        self.model = settings.ai_model
        start = datetime.now(UTC)
        trace_id = uuid4()
        self.root = Span(trace_id, _segment(start, trace_id))
        self.started_at = start
        self.spans: dict[UUID, Span] = {}
        self.blocked = False
        self.metadata: dict[str, object] = {"purpose": purpose}
        if context is not None:
            self.metadata["request_attempt"] = context.attempt
            logger.info(
                "AI trace request_id=%s attempt=%s trace_id=%s",
                context.request_id,
                context.attempt,
                trace_id,
            )

    def start(self) -> None:
        try:
            self.client.create_run(
                name="ai_turn",
                inputs={},
                run_type="chain",
                id=self.root.id,
                trace_id=self.root.id,
                dotted_order=self.root.order,
                start_time=self.started_at,
                project_name=self.project,
                extra={"metadata": dict(self.metadata)},
            )
        except Exception:
            logger.warning("AI tracing enqueue failed")

    def _start(self, run_id: UUID, name: str, run_type: Literal["llm", "tool"]) -> None:
        start = datetime.now(UTC)
        span_id = uuid4()
        span = Span(
            span_id,
            self.root.order + "." + _segment(start, span_id),
            is_model=run_type == "llm",
        )
        self.spans[run_id] = span
        metadata = dict(self.metadata)
        if run_type == "llm":
            metadata.update(ls_provider="openai", ls_model_name=self.model)
        try:
            self.client.create_run(
                name=name,
                inputs={},
                run_type=run_type,
                id=span.id,
                trace_id=self.root.id,
                parent_run_id=self.root.id,
                dotted_order=span.order,
                start_time=start,
                project_name=self.project,
                extra={"metadata": metadata},
            )
        except Exception:
            logger.warning("AI tracing enqueue failed")

    def _finish(
        self, span: Span, status: TraceStatus, usage: dict[str, int] | None = None
    ) -> None:
        metadata = {**self.metadata, "status": status}
        if span.is_model:
            metadata.update(ls_provider="openai", ls_model_name=self.model)
        if usage:
            metadata["usage_metadata"] = usage
        try:
            self.client.update_run(
                span.id,
                trace_id=self.root.id,
                dotted_order=span.order,
                end_time=datetime.now(UTC),
                outputs={},
                error="execution_" + status
                if status in {"failed", "canceled"}
                else None,
                extra={"metadata": metadata},
            )
        except Exception:
            logger.warning("AI tracing enqueue failed")

    def finish(self, status: TraceStatus) -> None:
        for span in self.spans.values():
            self._finish(span, "canceled" if status == "canceled" else "failed")
        self.spans.clear()
        self._finish(self.root, status)

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        name = (
            "input_guard"
            if INPUT_GUARD_TAG in (tags or [])
            else "final_answer"
            if FINAL_ANSWER_TAG in (tags or [])
            else "react_model"
        )
        self._start(run_id, name, "llm")

    async def on_llm_end(
        self, response: LLMResult, *, run_id: UUID, **kwargs: Any
    ) -> None:
        span = self.spans.pop(run_id, None)
        if span is None:
            return
        usage: dict[str, int] = {}
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                values = getattr(message, "usage_metadata", None)
                if not isinstance(values, dict):
                    continue
                for key in ("input_tokens", "output_tokens", "total_tokens"):
                    value = values.get(key)
                    if type(value) is int and 0 <= value <= 10_000_000:
                        usage[key] = usage.get(key, 0) + value
        self._finish(span, "completed", usage)

    async def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        span = self.spans.pop(run_id, None)
        if span is not None:
            self._finish(
                span,
                "canceled"
                if isinstance(error, (asyncio.CancelledError, GeneratorExit))
                else "failed",
            )

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = serialized.get("name")
        if isinstance(name, str) and name in TOOL_NAMES:
            self._start(run_id, name, "tool")

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        span = self.spans.pop(run_id, None)
        if span is not None:
            self._finish(span, "completed")

    async def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        await self.on_llm_error(error, run_id=run_id)
