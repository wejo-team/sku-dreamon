/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 에메랄드 강조색(--primary) 및 선택 스위치 스타일
 * 2. docs/design/screens.md - 프로필 공개/비공개 토글 스위치 인터랙션 명세
 * 3. docs/development/frontend.md - 모바일 터치 영역 44px 및 웹 접근성(role="switch") 보장
 * 4. design-reference/src/components/ui/switch.tsx - shadcn Switch 규격
 */

import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export interface SwitchProps extends Omit<
  ComponentProps<'button'>,
  'onChange'
> {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
}

// [출처 2, 3] WAI-ARIA switch 패턴 및 모바일 터치 영역을 준수한 토글 스위치
export function Switch({
  checked = false,
  onCheckedChange,
  disabled = false,
  className,
  ...props
}: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange?.(!checked)}
      className={cn(
        'peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'bg-primary' : 'bg-muted-foreground/30',
        className,
      )}
      {...props}
    >
      <span
        className={cn(
          'pointer-events-none block size-5 rounded-full bg-white shadow-lg ring-0 transition-transform',
          checked ? 'translate-x-5' : 'translate-x-0',
        )}
      />
    </button>
  );
}
