/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/auth-policy.ts - 인증 입력 규칙 원본
 * 2. docs/specs/authentication.md#login-identifier - 아이디 ASCII 소문자·숫자 4~24자 정규화
 * 3. docs/specs/authentication.md#password-policy - 비밀번호 NFC 8~128 코드 포인트, 가입 시 기호 포함·한글과 공백 금지
 * 4. docs/design/handoff.md - 공개 UI 테스트 계정은 실제 계정·비밀값이 아님
 *
 * 고정 문자열 검사만 하며 계정 발급·해시·서버 세션을 구현하지 않습니다(출처 4).
 */

import { z } from 'zod';

// [출처 4] 공개 UI 확인용 아이디
export const demoId = 'dreamondemo';
export const demoPassword = 'DreamonReview2026!';

// [출처 2] 대문자·주변 공백 정규화
export const normalizeLoginId = (value: string) =>
  value.trim().replace(/[A-Z]/g, (letter) => letter.toLowerCase());
// [출처 3] NFC 정규화, 공백 보존
export const normalizePassword = (value: string) => value.normalize('NFC');

// [출처 2] 아이디 형식 검증
export const loginIdSchema = z
  .string()
  .transform(normalizeLoginId)
  .pipe(
    z
      .string()
      .regex(
        /^[a-z0-9]{4,24}$/,
        '아이디는 영문 소문자와 숫자로 4~24자 입력해 주세요.',
      ),
  );

// [출처 3] 화면의 체크 표시와 제출 검증이 같은 정규화·조건을 사용합니다.
export function getPasswordRequirements(value: string) {
  const normalized = normalizePassword(value);
  const length = Array.from(normalized).length;
  return {
    length: length >= 8,
    characters: !/[\p{Script=Hangul}\p{White_Space}\uFEFF]/u.test(normalized),
    symbol: /[\p{P}\p{S}]/u.test(normalized),
  };
}

// [출처 3] 로그인에는 새 가입의 기호 조건을 적용하지 않습니다.
export const passwordSchema = z
  .string()
  .transform(normalizePassword)
  .refine(
    (value) => getPasswordRequirements(value).length,
    '비밀번호는 8자 이상 입력해 주세요.',
  )
  .refine(
    (value) => Array.from(value).length <= 128,
    '비밀번호는 128자 이하로 입력해 주세요.',
  );

// Interaction fixtures only. Production must use an approved, maintained
// compromised-password source; this set does not claim breach coverage.
export const commonPasswordFixtures = new Set([
  '123456789012345',
  '1234567890123456',
  'passwordpassword',
  'qwertyqwertyqwerty',
  'password!',
  '1234567!',
]);
// [출처 3] 가입: 기호 포함과 흔한 비밀번호 예시 차단
export const signupPasswordSchema = passwordSchema
  .refine(
    (value) => getPasswordRequirements(value).characters,
    '한글과 공백은 사용할 수 없어요.',
  )
  .refine(
    (value) => getPasswordRequirements(value).symbol,
    '기호를 1개 이상 포함해 주세요. (!, @, # 등)',
  )
  .refine(
    (value) => !commonPasswordFixtures.has(value.toLowerCase()),
    '쉽게 추측할 수 있는 비밀번호예요. 다른 비밀번호를 선택해 주세요.',
  );
