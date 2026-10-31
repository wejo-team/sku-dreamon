# 서경드림온 문서

사람과 에이전트가 함께 사용하는 문서입니다. **현재 작업에 필요한 문서만 선택해서 읽습니다.**

## 폴더별 문서

메뉴의 카테고리는 저장소의 `docs/` 폴더 구조와 같습니다. 각 폴더의 인덱스에서 필요한 문서를 고릅니다.

| 경로 | 내용 |
| --- | --- |
| [collaboration/](collaboration/README.md) | GitHub에서 문서 작성·PR·리뷰·게시 확인을 하는 방법 |
| [development/](development/README.md) | 설치·실행, 기술 규칙, 개발·리뷰·검증 방법 |
| [development-plans/](development-plans/README.md) | 기능 명세에 연결된 상세 설계·구현 순서·검증 계획 |
| [specs/](specs/README.md) | 팀이 검토하는 기능 동작·정책·예외·완료 조건 |
| [database/](database/README.md) | 물리 ERD·테이블 정의·DB 제약·트랜잭션 설계안 |
| [data/](data/README.md) | 개발·시연 데이터 제작 규칙·버전·분포·재구성 방법 |
| [api/](api/README.md) | 요청·응답 필드·권한·오류·페이지네이션의 Markdown 설계 |
| [design/](design/README.md) | 공식 모바일 디자인 실행·화면별 명세·프론트엔드 인계 |
| [templates/](templates/README.md) | 새 문서를 작성할 때 복사하는 양식 |
| [branding.md](branding.md) | 서경드림온의 의미와 이름·기술 식별자 표기 기준 |
| [agent-guide.md](agent-guide.md) | 에이전트의 문서 선택과 작업·보고 원칙 |

## 자주 찾는 문서

- 현재 구현 상태와 다음 작업을 확인할 때: [구현 현황과 다음 작업](development/implementation-status.md)
- 서비스명을 쓰거나 소개 문구를 작성할 때: [이름과 표기](branding.md)
- 기획 팀원 등 GitHub가 처음인 팀원이 참여할 때: [문서 협업 시작하기](collaboration/README.md)
- 처음 실행할 때: [로컬 실행](development/local-development.md)
- 실제 프론트·서버·DB를 함께 검증할 때: [통합테스트와 bug bash](development/bug-bash.md)
- 제품 화면을 구현할 때: [공식 디자인 레퍼런스](design/README.md)
- DB와 서버 인터페이스를 검토할 때: [DB 설계](database/README.md) → [API 명세](api/README.md)
- 명세·계획·PR과 `작업 브랜치 → develop → main` 릴리스를 검토할 때: [팀 작업 흐름](development/workflow.md)
- `main` CI 이후 운영 배포를 확인할 때: [운영 CD](development/continuous-deployment.md)
- 공식 모바일 디자인을 참고할 때: [디자인 실행 안내](design/README.md)과 [버전·검증 기록](specs/prototype-alignment.md)
- 현재 프로토타입과 기능 명세를 대조할 때: [디자인 기능·명세 대조](specs/prototype-alignment.md)
- 문서를 추가하거나 게시할 때: [문서 관리](development/documentation.md)

## 읽기 원칙

1. 현재 작업에 맞는 폴더 인덱스에서 필요한 문서와 절만 읽습니다. 에이전트는 먼저 [에이전트 안내](agent-guide.md)를 확인합니다.
2. 연결된 문서를 모두 재귀적으로 읽지 않습니다. 작업 범위가 넓어지거나 모르는 계약이 나올 때만 추가로 읽습니다.
3. 문서가 실제 파일·설정과 다르면 차이를 확인하고 해당 변경에서 함께 정리합니다.

원본은 저장소의 `docs/`이며 기본 브랜치는 `develop`입니다. [문서 사이트](https://wejo-team.github.io/sku-dreamon/)는 릴리스가 `main`에 병합되고 문서 검증을 통과한 뒤 갱신됩니다. `develop`의 변경과 검토 중인 PR은 저장소에서 확인하며, 명세의 구현 여부는 각 명세의 상태와 연결된 PR로 구분합니다. 템플릿은 실제 서비스 명세가 아닙니다.
