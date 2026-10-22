/**
 * [참조 출처]
 * 1. design-reference/src/components/ui/label.tsx - shadcn/ui 원본
 * 2. docs/design/tokens.md - 「shadcn/ui 사용 맵」 폼 라벨
 * 3. docs/development/frontend.md - 「모바일 UI」 필요한 shadcn/ui만 추가, 44px 조작 영역
 */

import type { ComponentProps } from 'react';
import * as LabelPrimitive from '@radix-ui/react-label';
import { cn } from '@/lib/utils';

// [출처 1, 2] 폼 라벨
function Label({
  className,
  ...props
}: ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        'flex items-center gap-2 text-sm leading-none font-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50',
        className,
      )}
      {...props}
    />
  );
}

export { Label };
