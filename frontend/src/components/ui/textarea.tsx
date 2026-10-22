/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 텍스트영역 입력 컨트롤 스타일 및 테두리 토큰
 * 2. docs/design/verification.md - 초과 입력 글자 수 보존 및 모바일 입력 편의성
 * 3. docs/development/frontend.md - React Hook Form 폼 검증 연동 및 오류 상태 표시
 * 4. design-reference/src/components/ui/textarea.tsx - shadcn Textarea 컴포넌트 원본
 */

import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

// [출처 2, 4] 내용 가변 높이 및 글자 수 표시를 지원하는 Textarea 컴포넌트
export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        'flex min-h-24 w-full rounded-md border border-input bg-card px-3 py-2 text-base shadow-xs transition-colors outline-none',
        'placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40',
        'disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive',
        className,
      )}
      {...props}
    />
  );
}
