/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 바텀 시트 곡률(radius-panel: 12px) 및 모바일 팝업 스타일
 * 2. docs/design/screens.md - 필터/공개설정/캐릭터/공모전선택 모바일 Drawer 명세
 * 3. docs/development/frontend.md - 반응형 바텀 드로어 및 접근성(role="dialog", aria-modal="true", Escape 닫기)
 * 4. design-reference/src/components/ui/drawer.tsx - Vaul 기반 shadcn Drawer 원본
 * 5. WAI-ARIA APG Dialog (Modal) Pattern - 열 때 내부 포커스, Tab 순환, 닫을 때 호출 요소로 복귀, 제목으로 이름 연결
 *
 * [PR #120 리뷰 반영] 직접 구현한 div Drawer는 포커스가 배경에 남고 제목 연결·포커스 복귀가 없었습니다.
 * 레퍼런스와 같은 Vaul(Radix Dialog) primitive로 교체해 출처 5의 포커스·이름 기준과 Escape·스크롤 잠금을
 * primitive에 맡기고, 여기서는 프로젝트 스타일만 입힙니다. Trigger/Close는 기본 button이며 asChild는 Slot 합성입니다.
 */

import type { ComponentProps } from 'react';
import { Drawer as DrawerPrimitive } from 'vaul';
import { cn } from '@/lib/utils';

function Drawer(props: ComponentProps<typeof DrawerPrimitive.Root>) {
  return (
    <DrawerPrimitive.Root
      data-slot="drawer"
      shouldScaleBackground={false}
      autoFocus
      {...props}
    />
  );
}

function DrawerTrigger(props: ComponentProps<typeof DrawerPrimitive.Trigger>) {
  return <DrawerPrimitive.Trigger data-slot="drawer-trigger" {...props} />;
}

function DrawerPortal(props: ComponentProps<typeof DrawerPrimitive.Portal>) {
  return <DrawerPrimitive.Portal data-slot="drawer-portal" {...props} />;
}

function DrawerClose(props: ComponentProps<typeof DrawerPrimitive.Close>) {
  return <DrawerPrimitive.Close data-slot="drawer-close" {...props} />;
}

function DrawerOverlay({
  className,
  ...props
}: ComponentProps<typeof DrawerPrimitive.Overlay>) {
  return (
    <DrawerPrimitive.Overlay
      data-slot="drawer-overlay"
      className={cn('fixed inset-0 z-50 bg-black/40', className)}
      {...props}
    />
  );
}

function DrawerContent({
  className,
  children,
  ...props
}: ComponentProps<typeof DrawerPrimitive.Content>) {
  return (
    <DrawerPortal>
      <DrawerOverlay />
      {/* [출처 1, 3] 모바일 뷰포트(최대 480px) 하단 중앙에 붙는 시트 */}
      <DrawerPrimitive.Content
        data-slot="drawer-content"
        className={cn(
          'fixed inset-x-0 bottom-0 z-50 mx-auto flex max-h-[85vh] w-full max-w-[480px] flex-col overflow-y-auto rounded-t-2xl bg-card p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-2xl outline-none',
          className,
        )}
        {...props}
      >
        {/* [출처 1, 2] 드로어 상단 핸들 바 */}
        <div
          data-slot="drawer-handle"
          aria-hidden="true"
          className="mx-auto mb-4 h-1.5 w-12 shrink-0 rounded-full bg-muted-foreground/30"
        />
        {children}
      </DrawerPrimitive.Content>
    </DrawerPortal>
  );
}

function DrawerHeader({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="drawer-header"
      className={cn('mb-4 flex flex-col gap-1.5 text-left', className)}
      {...props}
    />
  );
}

function DrawerFooter({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="drawer-footer"
      className={cn('mt-5 flex flex-col gap-2', className)}
      {...props}
    />
  );
}

// [출처 5] Title·Description은 Radix가 dialog의 aria-labelledby·aria-describedby로 연결합니다.
function DrawerTitle({
  className,
  ...props
}: ComponentProps<typeof DrawerPrimitive.Title>) {
  return (
    <DrawerPrimitive.Title
      data-slot="drawer-title"
      className={cn(
        'text-lg font-bold tracking-tight text-foreground',
        className,
      )}
      {...props}
    />
  );
}

function DrawerDescription({
  className,
  ...props
}: ComponentProps<typeof DrawerPrimitive.Description>) {
  return (
    <DrawerPrimitive.Description
      data-slot="drawer-description"
      className={cn('text-sm text-muted-foreground', className)}
      {...props}
    />
  );
}

export {
  Drawer,
  DrawerPortal,
  DrawerOverlay,
  DrawerTrigger,
  DrawerClose,
  DrawerContent,
  DrawerHeader,
  DrawerFooter,
  DrawerTitle,
  DrawerDescription,
};
