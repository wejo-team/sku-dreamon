/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 입력 컨트롤 테두리(--border, --input) 및 포커스 링(--ring) 토큰
 * 2. docs/design/verification.md - 터치 영역 최소 44px 및 모바일 키보드 대응
 * 3. docs/development/frontend.md - 모바일 접근성 및 라벨/포커스 이동 보장
 * 4. design-reference/src/components/ui/input.tsx - shadcn Input 베이스 컴포넌트
 */

import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

// [출처 2, 4] 모바일 최소 터치 및 조작 영역(h-11, 44px)을 확보한 Input 컴포넌트
export function Input({
  className,
  type = 'text',
  ...props
}: ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'flex h-11 w-full min-w-0 rounded-md border border-input bg-card px-3 py-2 text-base shadow-xs transition-colors outline-none',
        'placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40',
        'disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive',
        className,
      )}
      {...props}
    />
  );
}
