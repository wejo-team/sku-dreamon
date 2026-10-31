# 교과목 카탈로그와 수강 과목 등록

## 기준과 범위

2026-10-31 사용자 요청·인터뷰와 [명세 PR #244](https://github.com/wejo-team/sku-dreamon/pull/244)를 기준으로 [수강 과목 명세](../specs/profile.md#courses)를 구현합니다. 선택 입력, 카탈로그 내 선택, 수강 중 포함·상태 구분 없음이 확정되었습니다. 설명·성적·이수 증빙·연도별 교과목 버전은 제외합니다. 로컬 구현과 개발 DB 적재 범위이며 운영 배포나 GitHub 사람 리뷰 완료를 뜻하지 않습니다.

## 작업 분할과 계약

| 담당 | 수정 범위 | 사용하는 입력 / 제공하는 결과 | 검증 |
| --- | --- | --- | --- |
| 수집·빌더 | `backend/scripts/build_course_catalog.py`, 해당 단위 테스트, gitignored 수집 원본·장부·산출물 | 포털 UI의 학기별 Excel → `{schema_version,courses:[{code,name,aliases,departments}]}` | 파일 해시, 필수 열, 코드 보존, 동일코드 통합·별칭·결정성, 수집 학기 장부 |
| 백엔드 | 과목 ORM·마이그레이션·적재 CLI·카탈로그 API·프로필 저장/조회·관련 테스트 | JSON → DB, `GET /api/v1/catalogs/courses`, `ProfileWrite.courseCodes`, `ProfileResponse.courses` | PostgreSQL 적재·재적재, 검색·페이지, FK·중복·미등록 거부, 원자적 저장·버전·기존값 유지 |
| 프론트 | `frontend/src/features/account`, `catalogs`, `profiles`, 관련 표시 컴포넌트·스타일·테스트·목업 | DB 검색 API → 공용 검색·다중선택 UI → 프로필 저장 | 가입 건너뛰기, 검색 전환·페이지 이동 후 선택 유지, 추가·삭제·취소·빈 결과·실패·재시도 |
| 통합 | 관련 명세/API/DB 문서, `ai_sources.py`, 프롬프트, AI 컨텍스트 테스트, 개발 DB 적용 | 권한 검증된 프로필 과목의 코드·이름만 LLM에 전달 | 개인정보 필드 제한 유지, 현재 과목 반영, 전체 정적 검사·빌드와 DB/API 확인 |

적용 지침은 [에이전트 안내](../agent-guide.md), [작업 분할·인계](../development/workflow.md)의 해당 절, [프론트](../development/frontend.md), [백엔드](../development/backend.md), [테스트](../development/testing.md)를 따릅니다. 기존 공고 기능의 사용자 변경은 보존합니다.

## API·DB 영향과 순서

1. 원본 Excel은 개인명 등 수업 목록의 원문 필드를 포함하므로 gitignored 경로에 보존합니다. 제품 카탈로그에는 학수번호·대표명·별칭·개설학과명만 추출합니다.
2. `courses`는 학수번호를 유일키로 하고 `profile_courses`는 프로필과 과목을 연결합니다. 연도·학기는 원본 수집의 출처 정보에만 남깁니다. 추가 적재는 같은 코드의 표시 정보를 갱신하고 기존 프로필 연결과 누락 과목은 보존합니다.
3. 공개 검색 API는 `q`, `page`, `pageSize`를 받아 기존 `Page` 형식으로 응답합니다. 코드·대표명·별칭을 검색하고 코드 오름차순으로 정렬합니다. 브라우저에서 Excel을 검색하지 않습니다.
4. 프로필 쓰기는 `courseCodes: string[]`를 추가합니다. 명시한 목록으로 교체하고 `[]`는 전체 삭제입니다. 기존 소비자가 필드를 생략하면 저장값을 유지합니다. 읽기는 항상 `courses: {code,name}[]`를 반환합니다.
5. 프론트는 가입·편집 초안에서 검색과 다중선택을 제공하고 저장 시 항상 `courseCodes`를 보냅니다. LLM에는 조회 권한을 통과한 현재 프로필의 `courses`를 함께 전달합니다.
6. 테스트 DB에서 마이그레이션과 동작 검증 후 기존 로컬 개발 DB에 마이그레이션·카탈로그 적재를 적용합니다. 학교 추가 학기 자료는 같은 경로로 재적재합니다.

## 진행·검증 기록

- 2026-10-31 현재 조회 가능한 27개 학기의 Excel을 확보했습니다. 2020~2025년은 매년 1·여름·2·겨울학기, 2026년은 1·여름·2학기입니다. 2026 겨울계절은 포털 옵션에 없어 미수집이며 추후 보완 대상입니다.
- 27개 파일의 UI 행수·XLSX 행수·SHA256을 대조했습니다. 총 25,889강좌, 학수번호 기준 3,864과목이며 동일 코드의 이명은 없었습니다. 폐강·강의계획서 미입력 표시는 카탈로그에서 과목을 제외하는 기준으로 사용하지 않았습니다.
- 로컬 `wejo_dev`에 마이그레이션·3,864과목 적재를 적용했습니다. 재적재에서 신규·갱신 0개를 확인했으며 개발 DB에 대한 HTTP 검색·빈 결과·페이지 보정 확인을 수행했습니다.
- 별도 PostgreSQL QA DB와 실제 HTTPS 프론트·백엔드로 검색·다중선택·페이지 간 선택 유지·가입 시 저장·전체 선택 해제 후 재조회를 확인했습니다. 320·390·1280px의 가로 넘침이 없고 선택 목록·프로필 화면을 시각 확인했습니다.
- 최신 `develop` 통합 전 작업 트리에서 프론트 전체 353개·백엔드 전체 729개 테스트를 통과했습니다. 프론트 lint·format·typecheck·build, 백엔드 Ruff·format·mypy·Alembic check, 문서 원본·빌드·게시 링크 검사를 통과했습니다. 빌드에는 기존 번들 크기 권고가 남아 있습니다.
- 독립 검토에서 발견한 과목명 변경 후 완료 AI 결과의 갱신 필요 표시, 가입 후 재시도의 최신 계정 확인, 저장 응답 유실 후 버전 충돌 안내를 회귀 테스트로 검증했습니다. 검색 오류·재시도와 과목 선택 없이 가입한 뒤 프로필에서 추가하는 흐름도 실제 브라우저에서 확인했습니다. 운영 배포와 실제 LLM 호출은 수행하지 않았습니다.

- 최신 `develop`의 가입 화면·비밀번호 정책·단일 AI 에이전트 구조에 통합했습니다. 프론트 전체 524개 테스트와 lint·format·typecheck·build를 통과했습니다. 새 schema를 정상 준비 상태로 인정하도록 readiness 호환 revision도 `20261031_10`으로 갱신했습니다.
- 최신 코드의 표준 HTTPS 통합 E2E 20개와 고정 모델을 사용한 실제 API·DB의 AI E2E 6개가 통과했습니다. 별도 QA DB에 실제 3,864과목을 적재하여 가입 시 두 과목 저장·수정 취소·전체 해제 후 재조회·과목 없이 가입을 확인했습니다. 최근 비밀번호 안내·아이디 중복 확인도 유지됐고 320·390px에서 가로 넘침·브라우저 오류는 없었습니다. 결과와 스크린샷은 `.bugbash/course-ui/`에 보존했습니다.

- 추가 독립 검토에서 AI 응답 전송 중 과목명 재적재가 끼어들 수 있음을 실제 PostgreSQL로 재현했습니다. 프로필 다음에 연결된 과목을 ID 순서로 SHARE 잠금하도록 보완하고, 전송 중 재적재 대기·이후 근거 변경 감지 회귀를 통과했습니다.

## 데이터 인계와 배포 조건

카탈로그 원본과 생성 JSON은 Git에 포함되지 않습니다. 새 checkout에서 마이그레이션만 실행하면 과목 테이블은 비어 있으며, 아래 적재를 별도로 실행해야 합니다. 현재 수집 산출물은 원래 작업 저장소의 `data/research/academic-catalog-2026-10-31/catalog/courses.json`입니다.

- 카탈로그: 3,864과목, schema version `0.1.0`.
- SHA256: `a56b66d58d7045e9fecfc228702c02729f932c2042ecb23f8685e8182174c939`.
- 인계 시 이 JSON과 `collection/manifest.json`, `catalog/build-report.json`을 함께 보존합니다. Excel 원문에는 개인명이 있으므로 공개 PR에 첨부하지 않습니다.
- 대상 환경의 DB 설정을 확인하고 migration → JSON 검증 → `--apply` 순서로 실행합니다. 적용 후 `courses` 행수 3,864와 재적재 결과의 신규·갱신 0을 확인합니다. 이후 추가 수집·갱신 시 이 숫자와 해시도 함께 갱신합니다.
- 현재 적재는 로컬 개발 DB에만 완료했습니다. `develop` 병합은 운영 데이터 적재나 운영 배포를 수행하지 않습니다.
- 이 앱은 schema `20261031_10`이 필요합니다. 이전 앱은 새 revision을 readiness에서 거부하므로 운영 릴리스 시 [호환 릴리스·schema 전환 절차](deployment-foundation.md)를 먼저 충족해야 합니다. 데이터가 있는 환경에서 downgrade는 과목·프로필 과목 연결을 삭제하므로 자동 복구 수단으로 사용하지 않습니다.

## 재생성·추가 적재

저장소 루트의 `data/research/academic-catalog-2026-10-31/`는 gitignored 원본·출처·검증 결과 경로입니다. `collection/manifest.json`과 `collection/ui-excel-coverage.json`은 원본과 실제 확보 학기를, `catalog/build-report.json`은 통합 규칙과 행수를 보존합니다. 원본을 추가한 뒤 다음 명령을 실행합니다.

```bash
cd backend
uv run python scripts/build_course_catalog.py \
  --manifest ../data/research/academic-catalog-2026-10-31/collection/manifest.json \
  --output-dir ../data/research/academic-catalog-2026-10-31/catalog
uv run alembic upgrade head
# 먼저 무쓰기 검증, 그다음 설정된 개발 DB에 적재
uv run python -m app.cli.courses ../data/research/academic-catalog-2026-10-31/catalog/courses.json
uv run python -m app.cli.courses ../data/research/academic-catalog-2026-10-31/catalog/courses.json --apply
```

빌더는 로컬 원본을 읽는 오프라인 도구이며 포털 로그인·다운로드를 수행하지 않습니다. 원본 장부에 등록되지 않은 임의 파일을 자동 포함하지 않습니다.
