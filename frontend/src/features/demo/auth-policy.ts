/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/auth-policy.ts - 인증 입력 규칙 원본
 * 2. docs/specs/authentication.md#login-identifier - 아이디 ASCII 소문자·숫자 4~24자 정규화
 * 3. docs/specs/authentication.md#password-policy - 비밀번호 NFC 15~128 코드 포인트, 공백 보존
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

// [출처 3] 비밀번호 길이 검증
export const passwordSchema = z
  .string()
  .transform(normalizePassword)
  .refine(
    (value) =>
      Array.from(value).length >= 15 && Array.from(value).length <= 128,
    '비밀번호는 공백을 포함해 15~128자로 입력해 주세요.',
  );

// Interaction fixtures only. Production must use an approved, maintained
// compromised-password source; this set does not claim breach coverage.
const commonPasswordFixtures = new Set([
  '123456789012345',
  '1234567890123456',
  'passwordpassword',
  'qwertyqwertyqwerty',
]);
// [출처 3] 가입: 흔한 비밀번호 예시 4개 차단
export const signupPasswordSchema = passwordSchema.refine(
  (value) => !commonPasswordFixtures.has(value.toLowerCase()),
  '쉽게 추측할 수 있는 비밀번호예요. 다른 비밀번호를 선택해 주세요.',
);
