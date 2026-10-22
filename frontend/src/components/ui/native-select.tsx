/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 입력 및 선택 컨트롤 스타일 규격
 * 2. docs/design/screens.md - 학사 전공 종속 선택 및 정렬 셀렉트 명세
 * 3. docs/development/frontend.md - 모바일 OS 기본 피커를 활용한 네이티브 드롭다운 권장
 * 4. design-reference/src/components/ui/native-select.tsx - NativeSelect 컴포넌트 원본
 */

import type { ComponentProps } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

// [출처 3, 4] 모바일 친화적 OS 네이티브 휠 피커와 결합된 NativeSelect 컴포넌트
export function NativeSelect({
  className,
  children,
  ...props
}: ComponentProps<'select'>) {
  return (
    <div className="relative w-full">
      <select
        data-slot="native-select"
        className={cn(
          'flex h-11 w-full appearance-none rounded-control border border-input bg-card px-3 py-2 pr-9 text-base shadow-xs transition-colors outline-none',
          'focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40',
          'disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive',
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        size={18}
        className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
    </div>
  );
}

export function NativeSelectOption({
  className,
  ...props
}: ComponentProps<'option'>) {
  return (
    <option className={cn('bg-card text-foreground', className)} {...props} />
  );
}
