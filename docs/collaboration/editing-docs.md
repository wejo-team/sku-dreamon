# GitHub 웹에서 문서 수정하기

기존 문서를 수정하거나 새 명세를 추가해 PR을 만드는 순서입니다. 처음이라면 [계정·권한 준비](README.md)를 먼저 확인합니다. 아래 버튼 이름은 GitHub 영문 화면 기준입니다.

## 1. 내 작업 브랜치 만들기

1. [팀 저장소](https://github.com/wejo-team/sku-dreamon)의 **Code** 탭을 엽니다.
2. 파일 목록 위의 브랜치 선택 메뉴에서 `main`을 선택합니다. 새 작업은 항상 최신 `main`에서 시작합니다.
3. 같은 메뉴의 검색창에 새 이름을 입력합니다. 문서 작업은 `docs/수정-주제` 형태이며, 주제는 소문자 영문·숫자·하이픈으로 적습니다. 예: `docs/recruitment-spec`.
4. **Create branch**를 누르고, 현재 브랜치 이름이 입력한 이름으로 바뀌었는지 확인합니다. 같은 이름이 이미 있으면 다른 이름을 사용합니다.

이후 파일을 열 때마다 브랜치 이름을 확인합니다. 사이트의 편집 링크나 `main`이 들어간 주소로 이동하면 기준 브랜치로 돌아갈 수 있습니다. 이 경우 브랜치 메뉴에서 내 작업 브랜치를 다시 고릅니다.

## 2. 문서 작성하고 저장하기

**기존 문서를 수정한다면:** 내 브랜치에서 `docs/` 아래 대상 파일을 열고 연필 모양 **Edit this file**을 누릅니다. 내용을 수정한 다음 **Preview**에서 제목·목록·링크가 읽기 좋게 보이는지 확인합니다.

**새 기능 명세를 만든다면:** [명세 작성 안내](writing-specs.md)로 내용을 준비하고 다음과 같이 파일을 만듭니다. 아래 `recruitment`는 작성 방법을 설명하는 예시 이름입니다.

1. [명세 템플릿 원본](https://github.com/wejo-team/sku-dreamon/blob/main/docs/templates/spec.md)을 별도 탭에서 엽니다. **Code** 또는 **Raw** 보기로 Markdown 원문을 복사합니다.
2. 내 작업 브랜치의 `docs/specs/` 폴더로 돌아와 **Add file → Create new file**을 선택합니다.
3. 파일 이름에 `recruitment.md`처럼 소문자 영문·하이픈 이름과 `.md` 확장자를 입력합니다. 이미 `docs/specs/` 안이므로 전체 폴더 경로를 다시 입력하지 않습니다.
4. 복사한 양식을 붙여 넣고 제목과 내용을 바꿉니다. 템플릿 자체는 수정하지 않습니다. **Preview**로 확인합니다.

작성한 내용은 다음 순서로 저장합니다.

1. **Commit changes…**를 누릅니다.
2. 저장 설명에 `docs: 모집 명세 초안 작성`처럼 바뀐 내용을 적습니다.
3. 저장 대상이 **내 작업 브랜치**인지 확인합니다. 이미 만든 브랜치이므로 현재 브랜치에 저장하는 선택지를 사용합니다.
4. **Commit changes**를 눌러 저장합니다. 저장 전에는 편집 화면을 닫지 않습니다.

새 명세를 만들었다면 **같은 브랜치**에서 `docs/specs/README.md`도 편집해 문서 링크와 한 줄 설명을 추가하고 저장합니다. 예: `[모집 명세](recruitment.md) — 모집글의 작성·마감 동작`. 기존 명세와 같은 기능이라면 새 문서를 중복 생성하지 않고 해당 명세를 수정합니다.

여러 파일을 저장해도 한 작업이면 같은 브랜치를 사용합니다. GitHub가 중간에 PR 생성을 제안해도 나머지 파일을 먼저 수정할 수 있습니다.

## 3. PR로 검토 요청하기

1. 저장소에서 **Compare & pull request**를 누릅니다. 보이지 않으면 **Pull requests → New pull request**로 들어갑니다.
2. 받는 쪽 **base**는 `main`, 변경을 보내는 쪽 **compare**는 내 작업 브랜치인지 확인합니다.
3. 제목을 `docs: 모집 기능 명세 초안 작성`처럼 씁니다. 문서 PR은 `docs: 설명`이면 충분하며, 제목 형식은 자동 검사합니다.
4. 자동으로 표시되는 PR 양식에 변경 이유·범위·확인한 내용·검토할 질문을 적습니다. 모르는 항목은 추측해서 채우지 않고 미확인이라고 씁니다.
5. 내용을 함께 검토할 준비가 되었다면 **Create pull request**를 누릅니다. 아직 정리 중이라면 옆 메뉴에서 **Create draft pull request**를 선택하고, 준비된 뒤 PR의 **Ready for review**로 전환합니다.
6. PR의 **Reviewers**에서 내용에 합의할 팀원을 지정합니다. 명세는 기획 관점의 검토와 개발자의 구현 가능성 검토가 필요합니다. 선택이 안 되면 PR 링크와 함께 리더에게 리뷰어 지정을 요청합니다.

Draft는 작성 중이라는 표시입니다. `Ready for review`는 검토 요청을 뜻하며 기능 구현 완료를 뜻하지 않습니다.

PR 설명에는 다음 정도가 있으면 검토하기 쉽습니다. 실제 입력란은 저장소의 [PR 양식](../../.github/pull_request_template.md)을 따릅니다.

| 설명할 내용 | 명세 PR의 작성 예시 |
| --- | --- |
| 바꾸는 이유와 범위 | 모집글 작성과 마감 동작을 합의하려고 명세를 추가했습니다. 알림은 이번 범위에서 제외했습니다. |
| 관련 문서 | `docs/specs/recruitment.md`와 관련 Issue 링크. 아직 없는 작업은 없다고 표시합니다. |
| 직접 확인한 내용 | Markdown 미리보기, 명세 인덱스 링크 확인. 기능 구현·실행 검증은 이번 명세 PR 대상이 아닙니다. |
| 팀이 판단할 질문 | 마감 후 작성자가 내용을 수정할 수 있어야 하는지 검토해 주세요. |

문서 예시는 실제 서비스 정책이 아닙니다. **CI 통과는 실제 결과를 확인한 뒤에만** 기록합니다.

새 명세의 `명세 검토` 항목에는 PR을 만든 뒤 생긴 주소를 넣습니다. 같은 브랜치의 명세를 다시 수정·저장하면 현재 PR에 자동으로 추가됩니다. `구현 작업`은 아직 없다면 `미정`으로 둡니다.

## 4. 수정하거나 나중에 이어서 하기

- 내 PR은 [열린 PR 목록](https://github.com/wejo-team/sku-dreamon/pulls)에서 찾습니다. 제목 아래의 작업 브랜치 이름을 누르거나 Code 탭의 브랜치 메뉴에서 선택합니다.
- 해당 브랜치의 문서를 편집하고 커밋하면 **기존 PR이 갱신**됩니다. 리뷰 반영 때마다 브랜치나 PR을 새로 만들지 않습니다.
- 병합된 뒤 다른 작업을 시작할 때는 `main`에서 새 브랜치를 만듭니다. 이전 PR의 브랜치를 재사용하지 않습니다.

이어서 [리뷰 요청에 답하고 게시 확인하기](review-and-publish-docs.md)를 참고합니다.

## 문서 편집에 필요한 Markdown

파일 안에는 아래처럼 적습니다. 제목 아래와 목록 앞에는 빈 줄을 둡니다.

```markdown
# 문서 제목

## 사용자 흐름

- 사용자가 하는 행동
- 그 행동의 결과

**중요한 정책**

[명세 인덱스](README.md)

- [ ] AC-01: 확인 가능한 완료 조건
```

`#`은 문서 제목, `##`는 소제목입니다. 문서 안의 다른 파일은 `[표시할 이름](상대경로.md)`로 연결합니다. 위 `README.md` 링크는 `docs/specs/` 안에서 작성할 때의 예시입니다. 완료 조건의 체크는 구현·검증 결과이므로 초안 작성이나 명세 승인만으로 체크하지 않습니다.

## GitHub 공식 사용 안내

- [브랜치 만들기](https://docs.github.com/en/pull-requests/how-tos/commit-changes/managing-branches-within-your-repository)
- [파일 수정](https://docs.github.com/en/repositories/working-with-files/managing-files/editing-files) · [새 파일 만들기](https://docs.github.com/en/repositories/working-with-files/managing-files/creating-new-files)
- [PR 만들기](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-a-pull-request)
