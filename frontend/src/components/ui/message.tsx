/**
 * [참조 출처]
 * 1. design-reference/src/components/ui/message.tsx - shadcn/ui 원본
 * 2. docs/design/tokens.md - 「shadcn/ui 사용 맵」 AI 대화 메시지
 * 3. docs/development/frontend.md - 「모바일 UI」 필요한 shadcn/ui만 추가, 44px 조작 영역
 * 4. design-reference/src/components/ui/LICENSE.shadcn - 채팅 구성 요소 출처·라이선스
 */

// Adapted from shadcn/ui (MIT). See LICENSE.shadcn.
// Source: https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/message.tsx
import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

// [출처 1, 2] AI 대화 메시지
function MessageGroup({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="message-group"
      className={cn('flex min-w-0 flex-col gap-2', className)}
      {...props}
    />
  );
}

function Message({
  className,
  align = 'start',
  ...props
}: ComponentProps<'div'> & { align?: 'start' | 'end' }) {
  return (
    <div
      data-slot="message"
      data-align={align}
      className={cn(
        'group/message relative flex w-full min-w-0 gap-2 text-sm data-[align=end]:flex-row-reverse',
        className,
      )}
      {...props}
    />
  );
}

function MessageAvatar({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="message-avatar"
      className={cn(
        'flex w-fit min-w-8 shrink-0 items-center justify-center self-end overflow-hidden rounded-full bg-muted group-has-data-[slot=message-footer]/message:-translate-y-8',
        className,
      )}
      {...props}
    />
  );
}

function MessageContent({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="message-content"
      className={cn(
        'flex w-full min-w-0 flex-col gap-2.5 wrap-break-word group-data-[align=end]/message:*:data-slot:self-end',
        className,
      )}
      {...props}
    />
  );
}

function MessageHeader({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="message-header"
      className={cn(
        'flex max-w-full min-w-0 items-center px-3 text-xs font-medium text-muted-foreground group-has-data-[variant=ghost]/message:px-0',
        className,
      )}
      {...props}
    />
  );
}

function MessageFooter({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="message-footer"
      className={cn(
        'flex max-w-full min-w-0 items-center px-3 text-xs font-medium text-muted-foreground group-has-data-[variant=ghost]/message:px-0 group-data-[align=end]/message:justify-end',
        className,
      )}
      {...props}
    />
  );
}

export {
  MessageGroup,
  Message,
  MessageAvatar,
  MessageContent,
  MessageFooter,
  MessageHeader,
};
