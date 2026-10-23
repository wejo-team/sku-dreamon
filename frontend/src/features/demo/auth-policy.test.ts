import { describe, expect, it } from 'vitest';
import {
  demoId,
  demoPassword,
  loginIdSchema,
  normalizePassword,
  passwordSchema,
  signupPasswordSchema,
} from '@/features/demo/auth-policy';

describe('account input policy', () => {
  it('normalizes ASCII uppercase and edge whitespace consistently and rejects internal whitespace and punctuation', () => {
    expect(loginIdSchema.parse('  DREAMONDEMO  ')).toBe(demoId);
    for (const value of [
      'abc',
      'a'.repeat(25),
      'ab cd',
      'ab_cd',
      'ab-cd',
      '가나다라',
      '１２３４',
      'K123',
    ]) {
      expect(loginIdSchema.safeParse(value).success, value).toBe(false);
    }
    expect(loginIdSchema.parse('abcd')).toBe('abcd');
    expect(loginIdSchema.parse('a'.repeat(24))).toHaveLength(24);
  });

  it('counts NFC-normalized Unicode code points and preserves all password spaces and case', () => {
    expect(passwordSchema.parse(demoPassword)).toBe(demoPassword);
    expect(passwordSchema.parse('가'.repeat(15).normalize('NFD'))).toBe(
      '가'.repeat(15),
    );
    expect(passwordSchema.parse('😀'.repeat(128))).toBe('😀'.repeat(128));
    expect(passwordSchema.safeParse('😀'.repeat(129)).success).toBe(false);
    expect(passwordSchema.safeParse('a'.repeat(14)).success).toBe(false);
    expect(passwordSchema.parse('  a'.repeat(5))).toBe('  a'.repeat(5));
    expect(normalizePassword(' A b ')).toBe(' A b ');
  });

  it('blocks known common fixtures at signup without imposing character-class rules', () => {
    expect(signupPasswordSchema.safeParse('passwordpassword').success).toBe(
      false,
    );
    expect(signupPasswordSchema.safeParse('123456789012345').success).toBe(
      false,
    );
    expect(
      signupPasswordSchema.safeParse('한글로만입력하는충분히긴비밀번호예요')
        .success,
    ).toBe(true);
    expect(signupPasswordSchema.safeParse(demoPassword).success).toBe(true);
  });
});
