# PR #121 추가 리뷰 반영 내역

> 리뷰 답글 초안입니다. 커밋하지 않습니다. 아래 각 절을 해당 코멘트의 답글로 사용합니다.

## 전체 답글

입력 경계와 화면 이동 검토 감사합니다. 지적하신 3건을 모두 수정했습니다. 항목마다 재현 테스트를 먼저 추가했고, 세 테스트가 수정 전 코드에서 실패하는 것을 확인한 뒤 수정했습니다.

| 검사 (frontend/) | 결과 |
| --- | --- |
| `npm run lint` | 통과 |
| `npm run format:check` | 통과 |
| `npm run typecheck` | 통과 |
| `npm test` | 17개 파일, 229개 통과 (기존 226개 + 신규 3개) |
| `npm run build` | 통과 (번들 500KB 경고는 기존과 동일) |
| Chromium 직접 확인 | 세 흐름 모두 기대 동작 확인 |

전체 테스트를 처음 실행했을 때, 기존 프로필 흐름 테스트 2개가 병렬 실행 부하로 기본 5초 제한을 넘긴 적이 한 번 있었습니다. 해당 파일만 따로 실행하면 41개 모두 통과했고, 전체 재실행 2회에서도 229개 모두 통과했습니다. 이번 수정과는 무관한 시간 제한 문제지만 CI에서 간헐적으로 실패할 수 있어 함께 공유합니다.

---

## 1. [P2] 같은 공모전 재선택 시 작성값 초기화 — `frontend/src/features/teams/CreateTeamPage.tsx`

**원인**: `ContestPicker`의 `onChange`가 받은 `id`를 현재 값과 비교하지 않았습니다. 그래서 같은 공모전을 다시 골라도 `capacity`·`roles`를 항상 초기화했습니다.

**수정**: `const changed = id !== field.value;`로 먼저 비교하고, 실제로 공모전이 바뀐 경우에만 정원·역할을 초기화합니다. 정원과 역할은 공모전의 공식 인원에 따라 달라지므로, 다른 공모전을 고를 때 초기화하는 기존 동작은 유지합니다.

**검증**: `AccountPages.test.tsx` — "keeps capacity and roles when the same contest is chosen again and resets them for a different contest"
1. `/teams/new?contestId=campus`에서 정원 4와 역할 `기획`을 입력합니다.
2. 같은 공모전을 다시 선택하면 두 값이 유지됩니다.
3. 다른 공모전(로컬 브랜딩)을 선택하면 초기화됩니다.

브라우저에서도 같은 흐름을 확인했습니다.

## 2. [P2] 포트폴리오 저장 기준과 공개 기준 불일치 — `features/demo/profile-fields.ts`, `features/account/AccountPages.tsx`, `features/demo/data.ts`

**원인**: 폼 검증(`new URL`)과 공개 변환(`/^https?:\/\//` 정규식)이 서로 다른 기준을 썼습니다. 그래서 `https:/example.com/portfolio`가 저장은 되지만 공개 미리보기에서는 사라졌습니다.

**수정**: 기준을 `normalizeWebUrl()` 하나로 합쳤습니다. http/https 주소이면 `new URL(value).href`, 아니면 `''`를 반환합니다.
- 폼 검증·링크 표시(`isWebUrl`), 저장, 공개 변환(`profileToPerson`)이 모두 이 함수를 씁니다.
- 저장 시 정규화된 주소(`https://example.com/portfolio`)를 저장하므로, 내 프로필과 공개 미리보기가 같은 링크를 보여 줍니다.
- 포트폴리오 제목 비우기 조건도 정규화된 값을 기준으로 바꿨습니다.

**검증**: "normalizes an accepted portfolio URL so the saved and public links match"
1. `https:/example.com/portfolio`를 입력하고 저장합니다.
2. 내 프로필의 링크가 `https://example.com/portfolio`인지 확인합니다.
3. 공개로 전환한 뒤 공개 미리보기에서도 같은 링크인지 확인합니다.

브라우저에서도 확인했습니다. 기존의 `javascript:` 등 허용하지 않는 주소 차단 테스트도 그대로 통과합니다.

## 3. [P3] 로그인 후 편집·팀 복귀 경로 유실 — `features/account/AccountPages.tsx`

**원인**: 비로그인 `ProfilePage`가 `LoginGate`에 `returnTo="/profile"`를 고정으로 넘겨, `edit=details`와 `returnTo=/teams/makers`가 빠졌습니다.

**수정**: 현재 경로 전체(`location.pathname + location.search`)를 넘깁니다. 복귀 주소의 안전성은 기존처럼 `LoginPage`의 `safeReturnTo`가 다시 검사합니다(외부 주소·`//`·`..` 차단 유지).

**검증**: "keeps the profile edit intent and team return path through login"
1. 비로그인으로 `/profile?edit=details&returnTo=%2Fteams%2Fmakers`에 들어갑니다. 로그인 링크에 전체 경로가 인코딩되어 담깁니다.
2. 로그인하면 `프로필 수정` 화면이 열립니다.
3. 저장하면 `/teams/makers`로 이동합니다.

브라우저에서도 같은 흐름을 확인했습니다.
