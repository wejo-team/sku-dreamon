# WEJO 문서

사람과 에이전트가 함께 사용하는 문서입니다. **현재 작업에 필요한 문서만 선택해서 읽습니다.**

## 폴더별 문서

메뉴의 카테고리는 저장소의 `docs/` 폴더 구조와 같습니다. 각 폴더의 인덱스에서 필요한 문서를 고릅니다.

| 경로 | 내용 |
| --- | --- |
| [collaboration/](collaboration/README.md) | GitHub에서 문서 작성·PR·리뷰·게시 확인을 하는 방법 |
| [development/](development/README.md) | 설치·실행, 기술 규칙, 개발·리뷰·검증 방법 |
| [specs/](specs/README.md) | 팀이 검토하는 기능 동작·정책·예외·완료 조건 |
| [templates/](templates/README.md) | 새 문서를 작성할 때 복사하는 양식 |
| [agent-guide.md](agent-guide.md) | 에이전트의 문서 선택과 작업·보고 원칙 |

## 자주 찾는 문서

- 기획 팀원 등 GitHub가 처음인 팀원이 참여할 때: [문서 협업 시작하기](collaboration/README.md)
- 처음 실행할 때: [로컬 실행](development/local-development.md)
- 명세·계획·PR을 검토할 때: [팀 작업 흐름](development/workflow.md)
- 문서를 추가하거나 게시할 때: [문서 관리](development/documentation.md)

## 읽기 원칙

1. 현재 작업에 맞는 폴더 인덱스에서 필요한 문서와 절만 읽습니다. 에이전트는 먼저 [에이전트 안내](agent-guide.md)를 확인합니다.
2. 연결된 문서를 모두 재귀적으로 읽지 않습니다. 작업 범위가 넓어지거나 모르는 계약이 나올 때만 추가로 읽습니다.
3. 문서가 실제 파일·설정과 다르면 차이를 확인하고 해당 변경에서 함께 정리합니다.

원본은 저장소의 `docs/`입니다. [문서 사이트](https://wejo-team.github.io/wejo-app/)와 [GitHub Wiki](https://github.com/wejo-team/wejo-app/wiki)는 `main` 병합 후 갱신됩니다. 검토 중인 변경은 PR에서 확인하며, 명세의 구현 여부는 각 명세의 상태와 연결된 PR로 구분합니다. 템플릿은 실제 서비스 명세가 아닙니다.
