/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 안내 및 경고 박스 스타일 (--destructive, --muted, --leaf-soft)
 * 2. docs/design/verification.md - 알림 및 피드백 메시지 명확성 규칙
 * 3. docs/development/frontend.md - 성공/오류/주의 상태의 명확한 전달
 * 4. design-reference/src/components/ui/alert.tsx - shadcn Alert 컴포넌트 원본
 */

import type { ComponentProps } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

// [출처 1, 4] cva 기반 Alert 변형 정의
const alertVariants = cva(
  'relative flex w-full gap-3 rounded-panel border p-4 text-sm [&>svg]:size-5 [&>svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'bg-card text-card-foreground border-border',
        destructive:
          'bg-coral-soft text-destructive border-destructive/20 [&>svg]:text-destructive',
        info: 'bg-muted text-foreground border-border',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export function Alert({
  className,
  variant = 'default',
  ...props
}: ComponentProps<'div'> & VariantProps<typeof alertVariants>) {
  return (
    <div
      data-slot="alert"
      role="alert"
      className={cn(alertVariants({ variant }), className)}
      {...props}
    />
  );
}

export function AlertTitle({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="alert-title"
      className={cn('font-semibold leading-tight tracking-tight', className)}
      {...props}
    />
  );
}

export function AlertDescription({
  className,
  ...props
}: ComponentProps<'div'>) {
  return (
    <div
      data-slot="alert-description"
      className={cn('text-sm leading-relaxed [&_p]:leading-relaxed', className)}
      {...props}
    />
  );
}
