/**
 * [참조 출처]
 * 1. docs/development/testing.md - 「의미 있는 테스트」 사용자 동작으로 검증
 *
 * 테스트용 사용자 입력 도우미입니다. 이벤트 순서는 userEvent 기본과 같고, 하위 이벤트 사이의
 * 빈 대기(setTimeout)만 없앱니다. 입력마다 화면을 다시 그리는 비용이 커서 기본 지연이 테스트 시간을 크게 늘립니다.
 * 가짜 타이머로 시간을 진행하는 테스트는 userEvent.setup({ advanceTimers })를 직접 씁니다.
 */

import userEvent from '@testing-library/user-event';

export const setupUser = () => userEvent.setup({ delay: null });

type User = ReturnType<typeof setupUser>;

/**
 * 키 입력 하나하나가 검증 대상이 아닌 채우기 입력: 입력란을 눌러 기존 값 끝에 붙여 넣습니다.
 * 한 번의 입력 이벤트로 끝나 글자마다 화면을 다시 그리지 않습니다.
 * IME·Enter·글자 단위 변환처럼 키 입력 자체를 확인할 때는 user.type을 씁니다.
 */
export async function fill(
  user: User,
  element: HTMLElement,
  text: string,
): Promise<void> {
  await user.click(element);
  if (
    element instanceof HTMLTextAreaElement ||
    (element instanceof HTMLInputElement &&
      ['text', 'search', 'password', 'tel'].includes(element.type))
  ) {
    const end = element.value.length;
    element.setSelectionRange(end, end);
  }
  await user.paste(text);
}
