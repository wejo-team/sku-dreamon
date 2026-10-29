# 개발 계획

기능 명세를 구현 구조·작업 순서·검증 방법으로 연결하는 긴 계획을 보관합니다. 문서 작성과 설계 검토, 실제 구현 완료를 구분하며 [팀 작업 흐름](../development/workflow.md)을 따릅니다.

| 문서 | 상태 | 기준 명세 |
| --- | --- | --- |
| [AI 에이전트 SDD](ai-agent.md) | 백엔드 [#157](https://github.com/wejo-team/sku-dreamon/pull/157)·제품 화면의 실제 API 연결 [#192](https://github.com/wejo-team/sku-dreamon/pull/192) 병합, 단일 ReAct·입력 가드 [#206](https://github.com/wejo-team/sku-dreamon/pull/206) 구현. 실제 모델 화면 통합 검사·운영 배포 후속 | [LLM 기반 추천](../specs/matching.md) |
| [제품 배포 기반 설계안](deployment-foundation.md) | AWS 방향 합의 · [DEP-02 #211](https://github.com/wejo-team/sku-dreamon/issues/211) 앱 계약 구현, 구현·검증 근거 [PR #217](https://github.com/wejo-team/sku-dreamon/pull/217) · 인프라 미구현·미배포. RDS 기준안과 EC2 PostgreSQL 비용 비교 후보, DEP-01·03~07 후속·배포/복구 순서 | [배포 검증 #165](https://github.com/wejo-team/sku-dreamon/issues/165), [인증 전송](../api/conventions.md#csrf-transport), [AI API](../api/ai.md) |
