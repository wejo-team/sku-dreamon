// 가입 비밀번호의 입력 조건을 제출 검증과 같은 기준으로 안내합니다.
import { CheckCircle2, Circle } from 'lucide-react';
import { getPasswordRequirements } from '@/features/design-preview/auth-policy';

export function PasswordRequirements({ value }: { value: string }) {
  const requirements = getPasswordRequirements(value);
  const items = [
    { label: '8자 이상', met: requirements.length },
    { label: '기호 1개 이상 (!, @, # 등)', met: requirements.symbol },
  ];

  return (
    <ul
      id="signup-password-requirements"
      className="dreamon-password-requirements"
      aria-label="비밀번호 조건"
      aria-live="polite"
      aria-atomic="true"
    >
      {items.map(({ label, met }) => {
        const Icon = met ? CheckCircle2 : Circle;
        return (
          <li key={label} data-met={met}>
            <Icon size={16} aria-hidden="true" />
            <span>{label}</span>
            <span className="sr-only">{met ? '충족' : '미충족'}</span>
          </li>
        );
      })}
    </ul>
  );
}
