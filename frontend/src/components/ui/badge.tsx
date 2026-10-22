/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 배지 색상 및 상태 스타일 토큰 (recruiting, closed, neutral, leaf, warning, destructive)
 * 2. docs/design/verification.md - UI/UX 배지 명도 대비 및 상태 문구 표시 규칙
 * 3. docs/development/frontend.md - shadcn/ui 기반 컴포넌트 구조 및 유연한 모바일 확장
 * 4. design-reference/src/components/ui/badge.tsx - shadcn Badge 구현 원본
 * 5. design-reference/src/features/design-preview/PreviewUi.tsx - 상태 배지 톤 매핑 규칙
 */

import type { ComponentProps } from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

// [출처 1, 4] shadcn cva 기반 배지 스타일 변형 정의
const badgeVariants = cva(
  'inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border border-transparent px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap transition-[color,box-shadow]',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground',
        secondary: 'bg-secondary text-secondary-foreground',
        outline: 'border-border text-foreground',
        destructive: 'bg-destructive text-white',
        // [출처 1, 5] 서경드림온 전용 상태 톤 배지 (모집 중, 마감, 완료 등)
        recruiting: 'bg-recruiting-bg text-recruiting-text',
        closed: 'bg-closed-bg text-closed-text',
        leaf: 'bg-leaf-soft text-leaf-ink',
        warning: 'bg-warning-soft text-warning-ink',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export interface BadgeProps
  extends ComponentProps<'span'>, VariantProps<typeof badgeVariants> {
  asChild?: boolean;
}

// [출처 3, 4] Radix Slot 지원 Badge 컴포넌트
export function Badge({
  className,
  variant = 'default',
  asChild = false,
  ...props
}: BadgeProps) {
  const Comp = asChild ? Slot : 'span';
  return (
    <Comp
      data-slot="badge"
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}
