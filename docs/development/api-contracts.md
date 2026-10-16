# API 계약과 타입 동기화

API 경로·요청·응답·오류를 바꿀 때 프론트와 백엔드가 함께 읽습니다. 기능의 동작·예외·완료 조건은 해당 [명세](../specs/README.md)에 두고, 이 문서는 코드에서 계약을 선언하고 검증하는 공통 방법을 다룹니다.

## 원본과 생성물

| 파일 | 역할 | 수정 방법 |
| --- | --- | --- |
| `backend/app/schemas/` | Pydantic 요청·응답 모델 | 직접 수정 |
| `backend/app/api/routes/` | 경로·메서드·상태·응답 모델 선언 | 직접 수정 |
| `contracts/openapi.json` | FastAPI에서 내보낸 검토용 OpenAPI snapshot | 백엔드 명령으로 재생성 |
| `frontend/src/lib/api-schema.generated.d.ts` | snapshot에서 생성한 요청·응답 TypeScript 타입 | 프론트 명령으로 재생성 |
| `frontend/src/features/<기능>/api.ts` | endpoint 호출·Zod 응답 검증 | 계약 변경과 함께 수정 |

Pydantic 모델과 FastAPI route가 전송 계약의 원본입니다. ORM 모델은 저장 구조이며 API DTO와 분리합니다. 생성 파일을 직접 고치거나 프론트에 같은 DTO interface를 다시 작성하지 않습니다. 기능별 API에서 생성된 operation의 해당 상태 코드 응답 타입을 참조합니다. 요청·응답에 같은 모델을 쓰더라도 OpenAPI가 입력과 출력의 필수성을 다르게 표현할 수 있으므로 두 방향을 혼동하지 않습니다.

OpenAPI는 데이터 형태와 HTTP 계약을 표현합니다. 권한·멱등성·재시도·시간 제한처럼 schema만으로 설명되지 않는 동작은 필요한 기능 명세에 적습니다. 생성물은 현재 계약의 기록이며 과거 클라이언트와의 호환성을 자동 보장하지 않습니다.

## 변경 순서와 명령

1. 관련 기능 명세와 API 소비자에 미치는 영향을 확인합니다.
2. Pydantic·route와 실제 동작을 수정하고 API 테스트를 추가합니다.
3. 저장소 루트에서 다음 순서로 계약과 타입을 재생성합니다. 각 폴더의 lockfile 기준 의존성이 설치되어 있어야 합니다.

```bash
cd backend
uv run python -m scripts.export_openapi
cd ../frontend
npm run api:generate
```

4. 기능의 Zod schema·호출 코드·테스트를 맞추고 생성물 차이를 함께 검토합니다.
5. 변경에 해당하는 [검사](testing.md)를 실행하고 코드·snapshot·생성 타입·관련 문서를 같은 PR에 포함합니다.

파일을 바꾸지 않고 최신 상태인지 검사할 때는 각각 `backend/`, `frontend/`에서 실행합니다.

```bash
# backend/
uv run python -m scripts.export_openapi --check
# frontend/
npm run api:check
```

exporter는 명시적인 비운영 Settings로 앱을 구성하며 `.env`를 읽거나 lifespan·DB 연결·서버를 시작하지 않습니다. 설정이 필요한 런타임 진입점은 `app.main:app`, 계약 생성에 쓰는 factory는 `app.factory.create_app`입니다.

TypeScript 생성기는 `@hey-api/openapi-ts` 0.99.0의 TypeScript plugin만 사용합니다. 이 버전은 현재 Node 22.22.1·TypeScript 6 조합을 지원합니다. `frontend/scripts/api-contract.mjs`는 로컬 snapshot을 임시 폴더에 생성하고 Prettier로 정규화한 타입만 저장합니다. HTTP client·TanStack Query hook·Zod schema를 자동 생성하지 않습니다. 생성기와 설정을 바꾸면 같은 PR에서 재생성 결과와 검사를 확인합니다.

생성 타입 파일은 사람이 작성하는 코드의 ESLint 스타일 검사에서 제외하고, 재생성 일치 검사·Prettier·타입 소비 코드의 TypeScript 검사로 확인합니다.

생성기의 parser가 고정한 `js-yaml` 4.2.0에는 CPU 사용량 관련 보안 권고가 있어 해당 dependency에만 4.3.2 override를 적용합니다. 생성기 갱신 시 `npm audit`와 생성·검사 결과를 확인하고 upstream이 수정되면 override를 제거합니다.

## 필드·오류·호환성

- JSON 이름과 날짜·시간의 기본 표기는 [작성 컨벤션](conventions.md)을 따릅니다. JSON은 snake_case를 유지하며 화면용 camelCase 변환은 기능 경계에서 명시합니다.
- 키 누락과 `null`은 다릅니다. 요청·응답 모델에서 필수 여부와 null 허용 여부를 각각 선언합니다. PATCH를 도입할 때 누락은 변경하지 않음, null은 허용된 필드를 비움으로 구분하고 기능별 예외를 명세에 적습니다. 서버에서는 `exclude_unset` 등으로 실제 전송한 필드를 구분하며, 무조건 `exclude_none`으로 null을 지우지 않습니다.
- 응답에서 항상 직렬화하는 필드는 OpenAPI에도 필수로 나타나야 합니다. health의 `status`처럼 기본값을 항상 보내는 응답은 serialization schema의 required 설정과 실제 응답을 함께 검사합니다.
- timestamp는 시간대가 있는 ISO 8601·UTC를 사용합니다. 전송 타입은 문자열이며 표시용 날짜 객체로의 변환은 UI 경계에서 수행합니다. 날짜 전용 값과 timestamp를 구분하고 naive datetime 허용 여부·정규화는 해당 필드의 테스트로 확인합니다.
- enum 값은 서버 모델에서 정의하고 생성 타입으로 전달합니다. 값 추가도 Zod enum·exhaustive 분기를 깨뜨릴 수 있으므로 소비자 영향을 확인합니다.
- 오류는 HTTP 실패 상태를 유지합니다. FastAPI 기본 `detail`·validation error 형식과 호환되게 처리하며, 모든 오류가 JSON이거나 같은 body 형태라고 가정하지 않습니다. 공통 `ApiError`는 status와 unknown body를 보존하고 기능이 필요한 정보를 검증해 해석합니다. 도메인 오류 형식은 실제 기능이 필요할 때 프론트와 함께 정하고 route의 추가 응답에도 문서화합니다.
- 필드 삭제·이름/타입 변경·required 요청 필드 추가·응답 null 허용·enum 변경은 호환성 검토 대상입니다. `/api/v1` 안에서 소비자 가정을 조용히 깨뜨리지 않습니다. 프론트와 백엔드가 다른 시점에 배포될 수 있으면 이전 클라이언트와의 동작도 검토합니다.

## 타입과 런타임 검증

생성 TypeScript 타입은 네트워크 응답을 검사하지 않습니다. `lib/api.ts`는 unknown을 반환하며 기능별 Zod `parse`를 통과한 값만 앱에서 사용합니다. `as DTO`로 검증을 대체하지 않습니다. 폼 Zod는 입력 경험을 위한 별도 책임이며 서버 검증을 대신하지 않습니다.

health에서는 `expectTypeOf`로 Zod 출력과 생성 응답 타입을 양방향 비교합니다. 이 검사는 `npm run typecheck`가 수행하며 Vitest 실행만으로 타입 검사가 수행된다고 가정하지 않습니다. 다른 API도 수동 Zod schema를 유지한다면 같은 방식으로 타입 차이를 확인합니다. 문자열 길이·숫자 범위·날짜 형식처럼 TypeScript 타입에 표현되지 않는 제약은 정상·실패 사례 테스트로 검사합니다.

응답 Zod의 추가 필드 처리도 호환성에 영향을 줍니다. 현재 health는 알 수 없는 필드를 제거하고 처리합니다. 모든 응답에 strict 검증을 일괄 적용하지 않습니다.

## CI가 확인하는 범위

- `Backend`: 서버 코드에서 만든 OpenAPI와 커밋된 snapshot의 일치, exporter의 환경 독립성·재현성·오래된 파일 탐지, 기존 API·DB 검사.
- `Frontend`: 커밋된 snapshot과 생성 타입의 일치, Zod와 생성 타입 비교, 실제 응답 검증·화면 상태 테스트, 기존 정적 검사·빌드.

두 job은 병렬로 실행합니다. snapshot을 커밋하므로 프론트 job에서 Python이나 API 서버를 실행하지 않습니다. 두 최신성 검사가 통과해도 의미상 호환성이 검증된 것은 아닙니다. 명세·변경 diff·이전 소비자 영향은 리뷰에서 확인합니다.

## 근거

- [FastAPI OpenAPI 생성](https://fastapi.tiangolo.com/how-to/extending-openapi/)
- [FastAPI 입력·출력 schema](https://fastapi.tiangolo.com/how-to/separate-openapi-schemas/)
- [FastAPI 부분 수정](https://fastapi.tiangolo.com/tutorial/body-updates/)
- [Hey API TypeScript plugin](https://heyapi.dev/docs/openapi/typescript/plugins/typescript)
