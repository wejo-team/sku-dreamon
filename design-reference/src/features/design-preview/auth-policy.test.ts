import { describe, expect, it } from 'vitest';
import {
  demoId,
  demoPassword,
  getPasswordRequirements,
  loginIdSchema,
  normalizePassword,
  passwordSchema,
  signupPasswordSchema,
} from '@/features/design-preview/auth-policy';

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
    expect(passwordSchema.safeParse('a'.repeat(7)).success).toBe(false);
    expect(passwordSchema.parse('a'.repeat(8))).toBe('a'.repeat(8));
    expect(passwordSchema.parse('  a'.repeat(5))).toBe('  a'.repeat(5));
    expect(normalizePassword(' A b ')).toBe(' A b ');
  });

  it('requires a symbol at signup while allowing existing passwords at login', () => {
    expect(signupPasswordSchema.safeParse('passwordpassword').success).toBe(
      false,
    );
    expect(signupPasswordSchema.safeParse('123456789012345').success).toBe(
      false,
    );
    expect(
      signupPasswordSchema.safeParse('한글로만입력하는충분히긴비밀번호예요')
        .success,
    ).toBe(false);
    for (const value of [
      'abcdefg!',
      '1234567@',
      'é'.repeat(7) + '!',
      '😀'.repeat(8),
    ]) {
      expect(signupPasswordSchema.safeParse(value).success, value).toBe(true);
    }
    for (const value of [
      'abcdef!',
      'abcdefgh',
      'abcdefg ',
      'abcdefg\n',
      'é'.repeat(6) + '!',
      '가나다라마바사!',
    ]) {
      expect(signupPasswordSchema.safeParse(value).success, value).toBe(false);
    }
    expect(signupPasswordSchema.safeParse('password!').success).toBe(false);
    expect(signupPasswordSchema.safeParse(demoPassword).success).toBe(true);
  });

  it.each([
    '가나다라마바사!',
    '가abcdef!',
    'ㄱabcdef!',
    'ﾡabcdef!',
    '㈝abcdef!',
    ' abcdefg!',
    'abcdefg! ',
    'abcd efg!',
    'abcd\tefg!',
    'abcd\nefg!',
    'abcd\u0085efg!',
    'abcd\u00a0efg!',
    'abcd\u3000efg!',
    'abcd\ufeffefg!',
  ])(
    'rejects forbidden signup characters without breaking legacy login: %s',
    (value) => {
      expect(signupPasswordSchema.safeParse(value).success).toBe(false);
      expect(passwordSchema.parse(value)).toBe(value.normalize('NFC'));
    },
  );

  it('uses the server Unicode 15.1 symbol set regardless of browser Unicode support', () => {
    for (const symbol of ['\u{1FAE9}', '\u{1FAEA}']) {
      const value = `abcdefg${symbol}`;
      expect(getPasswordRequirements(value).symbol).toBe(false);
      expect(signupPasswordSchema.safeParse(value).success).toBe(false);
      expect(signupPasswordSchema.safeParse(`abcdef!${symbol}`).success).toBe(
        true,
      );
    }
    for (const symbol of ['!', '€', '😀', '\u{1FAE8}']) {
      expect(signupPasswordSchema.safeParse(`abcdefg${symbol}`).success).toBe(
        true,
      );
    }
  });

  it('reports each requirement independently using the same NFC length as validation', () => {
    expect(getPasswordRequirements('')).toEqual({
      length: false,
      symbol: false,
      characters: true,
    });
    expect(getPasswordRequirements('!')).toEqual({
      length: false,
      symbol: true,
      characters: true,
    });
    expect(getPasswordRequirements('abcdefgh')).toEqual({
      length: true,
      symbol: false,
      characters: true,
    });
    expect(getPasswordRequirements('e\u0301'.repeat(7) + '!')).toEqual({
      length: true,
      symbol: true,
      characters: true,
    });
    expect(getPasswordRequirements('a'.repeat(128) + '!')).toEqual({
      length: true,
      symbol: true,
      characters: true,
    });
    expect(signupPasswordSchema.safeParse('a'.repeat(128) + '!').success).toBe(
      false,
    );
    expect(getPasswordRequirements('abcdefg! ')).toEqual({
      length: true,
      symbol: true,
      characters: false,
    });
  });
});
