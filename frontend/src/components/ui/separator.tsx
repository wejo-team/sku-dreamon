/**
 * [참조 출처]
 * 1. design-reference/src/components/ui/separator.tsx - shadcn/ui 원본
 * 2. docs/design/tokens.md - 「shadcn/ui 사용 맵」 구분선
 * 3. docs/development/frontend.md - 「모바일 UI」 필요한 shadcn/ui만 추가, 44px 조작 영역
 */

import type { ComponentProps } from 'react';
import * as SeparatorPrimitive from '@radix-ui/react-separator';
import { cn } from '@/lib/utils';

// [출처 1, 2] 구분선
function Separator({
  className,
  orientation = 'horizontal',
  decorative = true,
  ...props
}: ComponentProps<typeof SeparatorPrimitive.Root>) {
  return (
    <SeparatorPrimitive.Root
      data-slot="separator"
      decorative={decorative}
      orientation={orientation}
      className={cn(
        'shrink-0 bg-border data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px',
        className,
      )}
      {...props}
    />
  );
}

export { Separator };
