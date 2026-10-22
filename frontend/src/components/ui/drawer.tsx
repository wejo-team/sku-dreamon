/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 바텀 시트 곡률(radius-panel: 12px) 및 모바일 팝업 스타일
 * 2. docs/design/screens.md - 필터/공개설정/캐릭터/공모전선택 모바일 Drawer 명세
 * 3. docs/development/frontend.md - 반응형 바텀 드로어 및 접근성(role="dialog", aria-modal="true", Escape 닫기)
 * 4. design-reference/src/components/ui/drawer.tsx - shadcn Drawer 인터페이스 규격
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { cn } from '@/lib/utils';

interface DrawerContextType {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DrawerContext = createContext<DrawerContextType | null>(null);

export function Drawer({
  open: controlledOpen,
  onOpenChange: setControlledOpen,
  children,
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: ReactNode;
}) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : uncontrolledOpen;
  const onOpenChange = isControlled ? setControlledOpen! : setUncontrolledOpen;

  // [출처 3] ESC 키를 누르면 드로어가 닫히는 키보드 접근성 처리
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onOpenChange(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onOpenChange]);

  // [출처 3] 모바일 팝업 오픈 시 배경 스크롤 방지
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  return (
    <DrawerContext.Provider value={{ open, onOpenChange }}>
      {children}
    </DrawerContext.Provider>
  );
}

export function DrawerTrigger({
  children,
  onClick,
  ...props
}: {
  asChild?: boolean;
  children: ReactNode;
  onClick?: () => void;
  [key: string]: unknown;
}) {
  const ctx = useContext(DrawerContext);
  return (
    <div
      className="contents cursor-pointer"
      onClick={() => {
        onClick?.();
        ctx?.onOpenChange(true);
      }}
      {...props}
    >
      {children}
    </div>
  );
}

export function DrawerContent({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const ctx = useContext(DrawerContext);
  if (!ctx?.open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 backdrop-blur-xs transition-opacity"
      onClick={() => ctx.onOpenChange(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        className={cn(
          'w-full max-w-[480px] max-h-[85vh] overflow-y-auto rounded-t-2xl bg-card p-5 shadow-2xl transition-transform animate-in slide-in-from-bottom duration-200',
          className,
        )}
      >
        {/* [출처 1, 2] 드로어 상단 핸들 바 */}
        <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-muted-foreground/30" />
        {children}
      </div>
    </div>
  );
}

export function DrawerHeader({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn('mb-4 flex flex-col space-y-1.5 text-left', className)}>
      {children}
    </div>
  );
}

export function DrawerTitle({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <h2
      className={cn(
        'text-lg font-bold tracking-tight text-foreground',
        className,
      )}
    >
      {children}
    </h2>
  );
}

export function DrawerDescription({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <p className={cn('text-sm text-muted-foreground', className)}>{children}</p>
  );
}

export function DrawerFooter({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn('mt-5 flex flex-col gap-2', className)}>{children}</div>
  );
}

export function DrawerClose({
  asChild = false,
  children,
  onClick,
  ...props
}: {
  asChild?: boolean;
  children: ReactNode;
  onClick?: () => void;
  [key: string]: unknown;
}) {
  const ctx = useContext(DrawerContext);
  return (
    <div
      onClick={() => {
        onClick?.();
        ctx?.onOpenChange(false);
      }}
      className="contents cursor-pointer"
      {...props}
    >
      {children}
    </div>
  );
}
