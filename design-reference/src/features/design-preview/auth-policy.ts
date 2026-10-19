import { z } from 'zod';

export const demoId = 'dreamondemo';
export const demoPassword = 'DreamonReview2026!';

export const normalizeLoginId = (value: string) =>
  value.trim().replace(/[A-Z]/g, (letter) => letter.toLowerCase());
export const normalizePassword = (value: string) => value.normalize('NFC');

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
export const signupPasswordSchema = passwordSchema.refine(
  (value) => !commonPasswordFixtures.has(value.toLowerCase()),
  '쉽게 추측할 수 있는 비밀번호예요. 다른 비밀번호를 선택해 주세요.',
);
