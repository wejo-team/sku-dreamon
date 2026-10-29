# 구현 현황과 다음 작업

## 2026-10-29 컨테이너 실행·앱 교체 기반

[DEP-03 #212](https://github.com/wejo-team/sku-dreamon/issues/212)의 production 이미지·별도 Nginx/PostgreSQL·선택 앱 슬롯·비공개 JSON·배포 lock/journal·후보 readiness·설정 검사·worker 드레인·복구·롤백·인증서 실행 경로를 구현했습니다. [운영 가이드](container-deployment.md)가 이미지·설정·권한·명령과 실패 시 동작의 원본입니다. DB는 앱 교체에서 재생성하거나 downgrade하지 않으며 UUID·실제 장치를 확인한 데이터 mount와 검증 TLS를 사용합니다.

검증은 host unit·정적 계약과 수동 컨테이너 실행을 구분합니다. host unit은 통과했고 단일 SAN 인증서 패턴은 Python 3.13의 엄격한 TLS handshake로 별도 확인했습니다. 일반 단위 검사에서는 인증서를 생성하지 않으며 실제 컨테이너 전체 성공은 미확인입니다. 앞선 실행은 합성 CA의 keyUsage 누락으로 첫 migration의 인증서 검증에 실패했습니다. 현재 수동 스크립트는 기존 DB TLS 테스트와 같은 단일 자체 서명 SAN 인증서를 명시적으로 신뢰하도록 단순화했고, 수정 후 실제 전체 재실행은 수행하지 않았습니다. 이미지·HTTP bootstrap·앱 교체/롤백·DB 보존·짧은 fixture SSE는 [수동 검사](container-deployment.md#검증과-범위) 범위입니다. 기존 앱 CI는 유지하며 CI 변경은 별도 PR로 다룹니다.

실제 도메인의 ACME 발급/갱신·최대 300초 벽시계·DB 지연 종료 종합은 최초 운영 검증 후속입니다. 소스·unit·계산한 timeout만으로 실제 실행을 완료했다고 판단하지 않습니다.

AWS·실제 EBS 부착/보존 설정·공개 인증서 발급·S3/CloudFront·ECR/SSM/OIDC CD·운영 용량과 비용·백업/복원·외부 scheduler/알림 수신자 설치는 후속 DEP-01·04~07 범위입니다. 제품 운영 배포와 실제 모델 호출은 수행하지 않았습니다.

## 2026-10-29 앱 운영 준비 계약 구현

[DEP-02 #211](https://github.com/wejo-team/sku-dreamon/issues/211)의 production 설정 검증·전역 credentialed CORS·Host/단일 trusted proxy 경계·검증 TLS/DB 예산·readiness·SSE 종료/지연 정리를 구현했습니다. 구현·검증 근거는 [PR #217](https://github.com/wejo-team/sku-dreamon/pull/217)입니다. [배포 기반 계획](../development-plans/deployment-foundation.md)과 [health API](../api/health.md)가 계약을 설명합니다. 이 작업에서 실제 키·운영 DB·모델 제공자 호출은 사용하지 않았습니다.

초기 MVP/PoC의 배포 방향은 **단일 EC2의 별도 Nginx·FastAPI·PostgreSQL 컨테이너 + DB용 EBS + Alembic**으로 합의했습니다. 프론트는 S3·CloudFront를 유지합니다. production DB의 자체 CA·서비스 호스트명 검증 TLS와 앱 교체 시 DB/EBS 보존을 계획에 반영했으며 PoC 재구성·실제 데이터 MVP의 dump/복원 수준은 제안 단계입니다. 컨테이너 실행·전환은 위 DEP-03 경로에서 다루며, AWS·실제 EBS 연결·CD·백업/복원 자동화·운영 스케줄은 미배포입니다. DEP-01의 월 3만 원 미만 목표 전체 견적·도메인/리전/용량/복구 기준/담당자 결정과 DEP-04~07은 후속입니다.

## 2026-10-28 AI 제품 화면 연결

[AI 화면 연결 #163](https://github.com/wejo-team/sku-dreamon/issues/163)의 [구현 PR #192](https://github.com/wejo-team/sku-dreamon/pull/192)에서 일반 대화·팀장의 지원자 검토·팀 지원자 추천을 기존 실제 API에 연결했습니다. `VITE_API_MOCK=false`는 POST SSE를 사용하고, 명시적인 모의 모드에서만 예시 답변을 만듭니다. 준비·생성·완료·빈 결과·실패·취소, 원입력 재시도와 실행 상태 확인을 구분합니다.

- 대화·초안은 현재 탭 메모리에서 유지하고, 새 대화·새로고침·로그아웃·동일 계정 재로그인 때 초기화합니다. 서버 기록 조회·복원은 추가하지 않았습니다.
- 최초 결과 DTO를 보존해 표시·복사·화면 복귀·포커스 때 현재 권한과 근거를 재검증합니다. 무효화·세션 변경·늦은 응답은 본문과 카드 전체에 적용합니다.
- 팀장 검토는 최신/사용 프로필 버전과 선발 후보 여부를 보여주며, 추천은 실제 지원자 상세로 연결합니다. 생성·검토·추천만으로 지원 상태나 선발을 변경하지 않습니다.
- 자동 검증은 프론트 API/컴포넌트 검사와 [실제 HTTPS·DB AI 브라우저 검사](bug-bash.md#ai-e2e)를 분리합니다. 브라우저에서는 모델만 대체하며 실제 제공자 호출은 0회입니다. 이전에 실시한 제공자 API 3회 검증을 이번 UI 실행으로 다시 계산하지 않습니다.

병합 기준 [main `94bda18`](https://github.com/wejo-team/sku-dreamon/commit/94bda183dce2dabaf0cf7358334dd140ff5a5f27)의 [앱 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40609049159)는 프론트 468개·백엔드 766개·격리 DB 비AI 브라우저 20개·AI 브라우저 6개를 통과했고, [문서 검사·게시](https://github.com/wejo-team/sku-dreamon/actions/runs/40609048885)도 성공했습니다. AI 브라우저 검사는 실제 HTTPS·인증·DB·SSE에 시험 모델을 연결한 결과입니다. 실제 모델을 사용한 화면 통합 검사는 아직 수행하지 않았습니다.

실제 자료의 추천 품질·비용·보존 정책 [#164](https://github.com/wejo-team/sku-dreamon/issues/164), 공동 HTTPS·운영 배포 [#165](https://github.com/wejo-team/sku-dreamon/issues/165)는 후속 범위입니다. 공식 학사 원장 대조와 전체 AC·실기기·데이터 조합의 남은 검증은 [#77](https://github.com/wejo-team/sku-dreamon/issues/77), 정책 결정은 [#19](https://github.com/wejo-team/sku-dreamon/issues/19), 구현·운영의 전체 지도는 [#97](https://github.com/wejo-team/sku-dreamon/issues/97)에서 추적합니다. 아래는 각 기준 커밋 당시의 기록입니다.

## 2026-10-28 통합 검증과 점검 기록

제품 기준은 [main `329b9b9`](https://github.com/wejo-team/sku-dreamon/commit/329b9b968f4ae0cf997cd9cce821aca08e70d350)입니다. 문서 **64개를 개별 검토**했고, 코드 점검은 인증·프로필·AI·업무 트랜잭션·프론트·기반 설정의 **고유 파일 126개**를 대상으로 했습니다. 코드에는 기능별 일부 구간 검토가 포함되므로 모든 줄·실행 경로를 전수 검증한 수치가 아닙니다.

| 범위 | 병합·반영한 변경 | 검증 범위와 한계 |
| --- | --- | --- |
| 개발 DB 통합 검증 | 실제 서버 실행기·혼합 데이터·CI E2E [#173](https://github.com/wejo-team/sku-dreamon/pull/173), 검토 시작·미선발 UI [#175](https://github.com/wejo-team/sku-dreamon/pull/175), 시연 표시 [#177](https://github.com/wejo-team/sku-dreamon/pull/177) | #177 병합 후 원본 DB 기본 16개 통과. 이후 수정을 포함한 반복 실행은 커밋별 기록으로 구분 |
| 취약 의존성 | 제품·디자인 레퍼런스·문서·Python 의존성 수정 [#183](https://github.com/wejo-team/sku-dreamon/pull/183) | 해당 변경의 npm audit와 pip-audit에서 알려진 취약점 0건. 검사 시점의 의존성 목록과 권고 기준 |
| CI 준비 | Linux 브라우저 의존성 설치 지연 개선 [#185](https://github.com/wejo-team/sku-dreamon/pull/185) | 병합 후 [앱 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40571490806)와 [문서 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40571490711) 통과. 설치 측정·이전 timeout은 [실행 기록](bug-bash.md)에 구분 |
| AI·인증 응답 경계 | AI 발행의 중첩 DB 연결 제거 [#186](https://github.com/wejo-team/sku-dreamon/pull/186), 개인 응답·오류의 HTTP 캐시 방지 [#187](https://github.com/wejo-team/sku-dreamon/pull/187) | 실제 AI 추가 호출 없이 격리 회귀 검증. 운영 부하·실제 배포 캐시 검증과 구분 |
| 화면 경계 | 세션 만료·재지원·목록 페이지·알림 조회 실패 수정 [#188](https://github.com/wejo-team/sku-dreamon/pull/188) | [PR CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40572857540)에서 프론트 26개 파일·413개 테스트, 정적 검사·빌드와 CI E2E 20개 통과. 100건 초과 목록은 컴포넌트 검사 범위 |
| 시드·문서 검색 | 개발 시드 기간 경계·롤백·재실행 보존 [#189](https://github.com/wejo-team/sku-dreamon/pull/189), 문서 개발 서버 검색 색인 갱신 [#190](https://github.com/wejo-team/sku-dreamon/pull/190) | [#189 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40573652554)의 백엔드 759개·CI E2E 20개 통과. [#190 문서 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40574400021)의 검색 회귀 2개·기존 문서 도구 44개·원본 문서 64개 검사 통과 |
| 문서 정합성 | [#176](https://github.com/wejo-team/sku-dreamon/issues/176)의 명세·API·DB·개발 안내를 실제 구현과 대조 | 초기 정합성 변경 26개 문서의 독립 리뷰에서 미해결 결함 0건. 구현 현황·실행 안내는 위 병합 기준과 검증 범위를 반영 |

[#190 앱 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40574400031)는 프론트 **413개**, 백엔드 **759개**, 격리 CI DB의 브라우저 E2E **20개**를 통과했습니다. #188·#189 병합 후 main의 앱·문서 CI도 통과했습니다. CI의 새 가상 자료와 원본 개발 DB는 서로 다른 대상입니다. UI 작업 브랜치의 생명주기 집중 검사 8개와 복제 DB의 실제/시연 조합 검사 8개도 각각의 실행 기록으로 구분합니다.

실제 AI 검증은 **사용자 채팅 요청 1건에서 제공자 API 전송 3회**, 재시도 0회로 끝냈습니다. 응답 도착·SSE 순서·DTO·상태·결과 유효성을 확인한 제한적 검사이며, 전체 AI 기능·추천 품질·비용 평가·실제 AI 화면 연결 완료를 뜻하지 않습니다. 후속 AI 회귀는 가짜 모델과 격리 테스트 DB를 사용합니다.

최종 반복 검증의 범위는 **원본 개발 DB 기본 20개와 복제 DB 혼합 8개**입니다. 실행 커밋·대상·개수·성공/실패·생략·재시도·원본 보존 판정과 후속 조치는 [반복 검증 이슈 #169](https://github.com/wejo-team/sku-dreamon/issues/169)를 기준 기록으로 확인합니다. 이 문서의 구성 개수나 다른 커밋의 CI 결과로 해당 실행의 성공을 대신 판단하지 않습니다. [통합테스트와 bug bash](bug-bash.md)는 재현 방법과 완료된 시점별 검증 범위를 설명합니다.

이 통합 점검 당시 남았던 AI 화면 연결 #163은 위 후속 구현에서 다룹니다. 품질·비용·보존 [#164](https://github.com/wejo-team/sku-dreamon/issues/164), 운영 인증 [#98](https://github.com/wejo-team/sku-dreamon/issues/98), 공동 HTTPS·제품 배포 [#165](https://github.com/wejo-team/sku-dreamon/issues/165), 공식 학사 원장 대조 [#101](https://github.com/wejo-team/sku-dreamon/issues/101)와 기존 미정 정책은 후속입니다. 아래 과거 기준의 테스트·테이블·migration 수는 해당 시점의 기록으로 보존하며 현재 수치로 합산하지 않습니다. 로컬 검증·CI 통과·문서 게시를 제품 운영 배포 완료로 해석하지 않습니다.

## 2026-10-26 main 검증 기록

당시 제품 기준은 [main `53c0003`](https://github.com/wejo-team/sku-dreamon/commit/53c00039427efe14c4017372b1ab77a316a3bd9a)입니다. 아래의 2026-10-25 수치·리뷰는 당시 비AI 병합 기록으로 보존합니다.

| 영역 | 현재 구현 | 남은 작업 |
| --- | --- | --- |
| 인증·프로필·탐색·팀·지원·알림 | 비AI 서버와 화면 API 호출 연결 [#160](https://github.com/wejo-team/sku-dreamon/pull/160) | 실서버 E2E·실기기·운영 검증 [#162](https://github.com/wejo-team/sku-dreamon/issues/162) |
| AI | 스트림·실행 제어·권한/결과 재검증·대화 저장 서버 [#157](https://github.com/wejo-team/sku-dreamon/pull/157) | 화면은 모의 응답. 프론트 연결 [#163](https://github.com/wejo-team/sku-dreamon/issues/163), 비용·품질·보존 [#164](https://github.com/wejo-team/sku-dreamon/issues/164) |
| 개발 데이터 | 사용자 300명·학사 94개·조건부 팀/지원 시드 [#161](https://github.com/wejo-team/sku-dreamon/pull/161) | 현행 운영 학사 원장 검증 [#101](https://github.com/wejo-team/sku-dreamon/issues/101) |
| 공고 | 공개 탐색·상세와 확인된 JSON 신규 입력 CLI | 최종 수동 탑재 방식 [#104](https://github.com/wejo-team/sku-dreamon/issues/104)·운영 경로 [#106](https://github.com/wejo-team/sku-dreamon/issues/106), 변경 정책 #50·#51 |
| 운영 | 로컬 실행·CI·문서 게시 | 인증 운영 [#98](https://github.com/wejo-team/sku-dreamon/issues/98), 공동 HTTPS 환경·제품 배포 [#165](https://github.com/wejo-team/sku-dreamon/issues/165) |
| 보류 정책 | 프로필 수정·모집 종료/재개·지원 상태 변경은 구현 | 모집글/지원 메시지 편집 [#166](https://github.com/wejo-team/sku-dreamon/issues/166), 탈퇴·보존 #25, 공고 요약 #38·#52 |

이 커밋의 서버는 **21개 테이블·8개 migration·42개 API 경로·44개 HTTP 작업**입니다. main의 [CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40291616590)는 프론트 345개·백엔드 681개 검사를 통과했습니다. 프론트의 Vitest는 목업 검사이며 제품 E2E와 구분합니다. 실제 로컬 통합 검증의 명령·결과·한계는 [통합테스트와 bug bash](bug-bash.md)에 기록합니다. 배포환경·실제 LLM을 이번 로컬 검증으로 완료 처리하지 않습니다.

## 2026-10-25 비AI 병합 기록

**기준: 2026-10-25, 구현 계획 [#147](https://github.com/wejo-team/sku-dreamon/issues/147)과 PR #148~#154 검증 결과.** 기능 PR #148~#154는 독립 리뷰와 추가 직접 재검토를 거쳐 모두 `main`에 Squash merge했습니다. 서버 구현과 남은 화면 연결·운영 작업을 구분하며, 운영 배포는 수행하지 않았습니다.

## 병합한 서버 기능

AI를 제외하고 설계가 정해진 서버의 진입 기능을 구현했습니다. 실제 DB에서 **가입 → 자동 로그인 → 프로필 저장·공개 → 팀 생성 → 지원 → 선발 → 취소** 흐름을 확인했습니다. 화면 연결과 운영 주소에서의 브라우저 E2E는 별도 작업입니다.

| 영역 | 병합한 변경 | PR |
| --- | --- | --- |
| 선행 정책 | 일반 텍스트 NFC·코드 포인트, 팀 생성의 필수 프로필·공개 불필요 조건, 공고 목록 기본값, 인증 운영 기준 | [#149](https://github.com/wejo-team/sku-dreamon/pull/149) |
| 공고 입력 | 확인된 JSON의 무쓰기 검증, 명시적 신규 저장 CLI, 공고·분류의 원자적 저장 | [#148](https://github.com/wejo-team/sku-dreamon/pull/148) |
| 계정·인증 | 가입·자동 로그인·로그인·아이디 중복 확인, 공유 DB 시도 제한, 운영 차단 목록 설정 | [#150](https://github.com/wejo-team/sku-dreamon/pull/150) |
| 프로필 | 전체 저장·수정·공개 전환, 버전 충돌·학사·선택지 검증 | [#151](https://github.com/wejo-team/sku-dreamon/pull/151) |
| 공고 탐색 | 공개 목록, 제목·주최자·분야 검색, 접수 상태·분야 필터, 안정 정렬·페이지 보정 | [#152](https://github.com/wejo-team/sku-dreamon/pull/152) |
| 팀 생성 | 팀·팀장 소속, 같은 공고의 본인 대기 지원 폐기·사건·알림을 함께 저장 | [#153](https://github.com/wejo-team/sku-dreamon/pull/153) |
| 지원 접수 | 공개·필수 프로필 및 현재 조건 검사, 지원·제출 사건·본인/팀장 알림을 함께 저장 | [#154](https://github.com/wejo-team/sku-dreamon/pull/154) |

기존의 조회·지원 검토·선발·취소·모집 종료/재개·워크스페이스·알림 읽음과 연결됩니다. 정확한 입력·응답은 각 PR의 라우터·DTO와 실행 앱의 `/docs`·`/openapi.json`을 따릅니다.

모든 기능 PR을 반영한 서버는 **18개 테이블, 6개 마이그레이션, 35개 API 경로·37개 HTTP 작업**입니다. 이 수치는 기능 PR을 모두 반영한 기본 브랜치 기준입니다.

## PR 분리와 병합 순서

기능별 독립 리뷰에는 선행 기능 브랜치를 비교 기준으로 사용했습니다. 병합할 때는 각 PR의 기준을 `main`으로 바꾸고 최신 `main`을 반영하여 해당 기능의 diff와 CI를 다시 확인했습니다.

실제 병합 순서는 **#149 → #148 → #150 → #151 → #152 → #153 → #154**입니다. 각 PR에 독립 리뷰와 최종 직접 재검토 코멘트를 남겼으며, 필수 CI 3개 성공·최신 `main` 포함·미해결 리뷰 대화 없음을 확인한 뒤 병합했습니다.

각 기능은 원자적 구현 커밋으로 작성했고, 리뷰에서 발견한 수정은 별도 목적의 커밋으로 남겼습니다. 의존 브랜치를 반영한 merge commit은 작업 브랜치의 연결 기록입니다. `main`에는 저장소의 [Squash merge 절차](workflow.md)에 따라 PR 하나당 커밋 하나를 남겼습니다. 사용자 요청에 따라 `jhpark324`의 명시된 리뷰 요건 예외를 사용했으며, 에이전트 코멘트를 사람의 승인으로 표시하지 않았습니다.

## 독립 리뷰와 직접 재검토

구현을 마친 뒤 PR마다 별도의 리뷰어가 정상·실패·권한·동시성·문서 계약을 검토했습니다. 에이전트의 기술 리뷰이며 사람의 승인 기록을 대신하지 않습니다.

| PR | 발견한 문제와 조치 | 최종 검토 범위 |
| --- | --- | --- |
| #148 | DB 연결 거절을 입력 오류로 분류하고 일부 드라이버 오류가 traceback을 출력했음. 파일 오류와 DB 단계 오류를 분리하고 실제 CLI 회귀 검사 추가 | 정상 등록·실제 commit 실패 롤백·안전한 오류 출력 |
| #149 | 확정한 정책과 기존 문서의 미정 표현이 충돌했음. 기능·API·DB·개발 가이드의 관련 설명 동기화 | 사용자 결정·구현 선택·남은 운영 작업 구분 |
| #150 | 고정 쿠키 Max-Age가 응답 지연만큼 서버 절대 만료를 넘겼음. 응답 시점의 남은 수명만 설정 | 동일 지연 재현, 가입 경쟁·롤백·시도 제한·세션 독립성 |
| #151 | 재현 가능한 P1/P2 결함 없음 | 전체 저장·null·경험·학사·선택지·공개 범위·버전·CSRF |
| #152 | 재현 가능한 P1/P2 결함 없음 | 검색·정렬·상태 경계·페이지·동시 변경의 읽기 일관성 |
| #153 | 독립 리뷰 후 직접 재검토에서 Unicode 역할 코드의 500 오류를 추가 발견·수정 | 정규화 재시도·필수 프로필·마감 대기·소속 경쟁·폐기 원인·알림 |
| #154 | 직접 재검토에서 같은 Unicode 역할 코드 오류를 재현·수정 | 경로에 결합된 재시도·재지원 이력·마감·소속·공개 전환 경합·두 알림 롤백 |

발견한 문제는 수정 후 같은 리뷰어가 재확인했습니다. PR의 리뷰 코멘트에서 발견 이유·수정 결과·검증과 한계를 읽을 수 있습니다. 의존 관계 정리 후에는 해당 기능의 변경만 남는지도 확인했습니다.

**추가 직접 재검토:** #153·#154의 역할 코드에 고립된 Unicode surrogate가 포함되면 재전송 식별값 계산에서 500이 발생함을 재현했습니다. 각 요청 DTO에서 이를 422로 거부하도록 수정했고, 두 종류의 잘못된 코드에 대한 HTTP 회귀 테스트 4개와 팀·지원이 생성되지 않는 결과를 확인했습니다. 정상 입력의 재전송 식별값은 유지합니다. 수정 뒤 팀 생성 관련 10개, 지원 접수 관련 13개 테스트와 전체 통합 검사가 통과했습니다.

## 검증 결과

- 모든 기능을 조합한 로컬 PostgreSQL 18.6에서 **635개 테스트 통과**. Ruff·format·mypy와 Alembic 모델 차이 검사도 통과했습니다.
- 별도 격리 DB·HTTPS ASGI 요청으로 전체 흐름 1건 통과: 가입·자동 로그인, 두 사람의 프로필 저장, 비공개 상태 팀 생성, 비공개 지원 거부, 공개 후 지원, 재전송, 팀장 지원자 조회·선발, 알림, 선발자 취소·자리 반환·팀 공간 권한 종료, 로그아웃.
- 원본 Markdown 문서 58개의 링크·앵커, VitePress 빌드, 생성 사이트 링크·앵커·자산 검사 통과. 초기 공고/인증 문서의 게시 앵커 오류도 수정했습니다.
- PR CI는 저장소 기준 PostgreSQL 17.11에서 백엔드 검사와 마이그레이션을 실행합니다. 최신 실행은 각 PR의 Checks에서 확인합니다. 프론트 영향이 없는 경우 기존 규칙에 따라 프론트 실행 검사는 생략됩니다.
- 독립 리뷰어의 추가 경계·경합 검사도 실제 격리 schema에서 실행했습니다. 운영 DB나 실제 사용자 데이터는 사용하지 않았습니다.

설치·명령은 [로컬 실행](local-development.md), 범위는 [테스트·CI](testing.md)를 따릅니다. 이 결과는 실제 프론트의 브라우저 통합 검증이나 운영 배포 결과가 아닙니다.

## 현재 후속 작업의 원본

현재 상태는 문서 상단의 AI 제품 화면 연결 절·2026-10-28 점검 표와 연결된 이슈를 따릅니다. 최종 반복 실행의 커밋·결과는 [#169](https://github.com/wejo-team/sku-dreamon/issues/169)에서 확인합니다. AI 구조는 [SDD](../development-plans/ai-agent.md)·[아키텍처](ai-architecture.md), 실행 결과는 [bug bash 기록](bug-bash.md)에서 구분합니다. 미정 정책을 구현 완료나 운영 배포로 표시하지 않습니다.

이전 PR #123~#146의 모델·조회·지원 상태 변경 기반은 유지합니다. 기존 기록은 [이전 구현 현황 문서](https://github.com/wejo-team/sku-dreamon/blob/ad423ca8d56118d5d95c75bbe4e8081a5f950707/docs/development/implementation-status.md)와 각 PR에서 확인할 수 있습니다.
