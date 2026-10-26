import { render, screen, waitFor } from '@testing-library/react';
import { setupUser } from '@/test/user';
import { describe, expect, it } from 'vitest';
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerTitle,
  DrawerTrigger,
} from './drawer';

function Example() {
  return (
    <>
      <Drawer>
        <DrawerTrigger>알림 열기</DrawerTrigger>
        <DrawerContent>
          <DrawerTitle>알림함</DrawerTitle>
          <DrawerDescription>업무 알림</DrawerDescription>
          <button type="button">모두 읽음</button>
          <DrawerClose>닫기</DrawerClose>
        </DrawerContent>
      </Drawer>
      <button type="button">배경 버튼</button>
    </>
  );
}

describe('Drawer', () => {
  it('열면 포커스를 안에 가두고, Escape로 닫으면 호출 버튼으로 돌려준다', async () => {
    const user = setupUser();
    render(<Example />);
    const trigger = screen.getByRole('button', { name: '알림 열기' });

    trigger.focus();
    await user.keyboard('{Enter}');

    const dialog = await screen.findByRole('dialog', { name: '알림함' });
    expect(dialog).toHaveAccessibleDescription('업무 알림');
    await waitFor(() =>
      expect(dialog).toContainElement(document.activeElement as HTMLElement),
    );

    const readAll = screen.getByRole('button', { name: '모두 읽음' });
    const close = screen.getByRole('button', { name: '닫기' });
    // Tab / Shift+Tab은 dialog 내부에서만 순환하고 배경 버튼으로 나가지 않는다.
    for (let i = 0; i < 4; i += 1) {
      await user.tab();
      expect(dialog).toContainElement(document.activeElement as HTMLElement);
    }
    readAll.focus();
    await user.tab({ shift: true });
    expect(close).toHaveFocus();
    await user.tab();
    expect(readAll).toHaveFocus();

    await user.keyboard('{Escape}');
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
    expect(trigger).toHaveFocus();
  });
});
