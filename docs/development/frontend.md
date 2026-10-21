# 프론트엔드 규칙

## 화면과 상태

- React + TypeScript + Vite + React Router를 사용합니다. 라우트별 화면은 `pages/`, 특정 기능 구현은 `features/`에 둡니다.
- 서버에서 받은 데이터와 요청 상태는 TanStack Query로 관리합니다. 같은 데이터를 별도 전역 store에 중복 저장하지 않습니다.
- 화면 내부의 짧은 상태는 React state, 공유 가능한 검색·필터·페이지 값은 URL을 우선 검토합니다.
- React Hook Form + Zod는 검증이 필요한 작성 폼에 사용합니다. 단순 검색 입력까지 일률적으로 적용하지 않습니다.
- Zustand 등 전역 상태 도구는 실제로 필요한 공유 상태가 생기면 도입합니다.

## API와 query

- HTTP 전송·공통 오류 처리는 `lib/api.ts`, 기능별 endpoint 호출은 `features/<기능>/api.ts`에 둡니다.
- 공통 클라이언트는 HTTP 실패를 정상 응답으로 취급하지 않고, 응답 내용이 없는 204도 처리합니다. 요청 취소를 위한 AbortSignal을 전달할 수 있게 합니다.
- 인증은 [서버 세션 쿠키](../specs/authentication.md#session-policy)를 사용합니다. 세션 토큰을 JavaScript에서 읽거나 localStorage·sessionStorage에 저장하지 않습니다. 실패·만료 시 [단순 안내와 재로그인](../specs/authentication.md#auth-failures)을 적용하며, CSRF 전달 세부는 [인증 계약](../api/conventions.md#access)을 확정한 뒤 적용합니다.
- query key에는 리소스와 조회 조건을 포함합니다. 목록·상세·필터 변경이 서로 잘못된 캐시를 사용하지 않도록 구분합니다.
- mutation 성공 시 영향받은 query를 갱신하거나 무효화합니다. 모든 요청을 일괄 재시도하지 않고, 권한·검증 오류와 일시적 오류를 구분합니다.
- 각 화면은 로딩·빈 결과·오류 상태를 제공합니다. `useEffect`로 공통 요청 수명주기를 반복 구현하지 않습니다.
- API 요청·응답 타입과 전송용 Zod schema는 [컨벤션](conventions.md)의 「API JSON 필드명」에 정한 camelCase 이름을 사용합니다. 응답을 검증한 뒤 UI에서 같은 이름으로 사용합니다.
- Zod의 폼 검증과 TypeScript 타입은 서버의 검증을 대신하지 않습니다. API 타입 자동 생성은 계약이 생길 때 검토합니다.

## 모바일 UI

- Tailwind CSS와 shadcn/ui를 사용합니다. 기본 버튼·입력·Dialog·Drawer부터 필요한 컴포넌트만 추가합니다.
- 화면은 유동 너비로 만들고, 320px부터 주요 모바일 너비와 넓은 화면을 확인합니다. 페이지 전체에 고정 393px 너비를 강제하지 않습니다.
- 모바일에서는 충분한 터치 영역, safe-area 여백, 키보드가 열린 상태의 스크롤과 하단 버튼 가림을 확인합니다.
- 상호작용은 의미에 맞는 button·link·label을 사용합니다. 포커스 이동과 오류 안내를 유지합니다.
- 색상·간격·둥근 모서리 등 반복 디자인은 공통 토큰을 사용합니다. 개별 페이지마다 임의의 테마를 추가하지 않습니다.
- 공통 UI에 특정 기능의 API 호출을 넣지 않습니다. 폼·목록 등 기능 UI에서 조합합니다.

## 근거

- [TanStack Query](https://tanstack.com/query/latest/docs/framework/react/overview)
- [Tailwind 모바일 우선 반응형](https://tailwindcss.com/docs/responsive-design)
- [shadcn/ui 반응형 Dialog·Drawer](https://ui.shadcn.com/docs/components/radix/drawer#responsive-dialog)
