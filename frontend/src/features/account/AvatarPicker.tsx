/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/AvatarPicker.tsx - 프로필 캐릭터 선택 원본
 * 2. docs/design/tokens.md - Drawer + RadioGroup, 제목 sr-only, 작은 설명만 표시
 * 3. docs/design/assets/avatar-picker-390.png - 실제 화면
 */

import { useId, useState } from 'react';
import { Pencil } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from '@/components/ui/drawer';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Avatar } from '@/components/common/CommonUi';
import { defaultMascotAvatarId } from '@/features/demo/mascot-avatars';
import { useLabels } from '@/features/catalogs/queries';

// [출처 2, 3] 선택·적용·취소와 포커스 복귀. 값은 profileImageCode, 미선택(null)은 기본 스콘으로 표시
export function AvatarPicker({
  value,
  onChange,
}: {
  value?: string | null;
  onChange: (value: string) => void;
}) {
  // docs/api/catalogs.md#catalog-item: 프로필 이미지 선택지는 Catalogs.avatarPresets(새 선택은 isSelectable만)
  const presets = useLabels().avatarPresets.filter((item) => item.isSelectable);
  const presetOf = (code: string) =>
    presets.find((item) => item.code === code) ?? presets[0]!;
  const current = value ?? defaultMascotAvatarId;
  const id = useId();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(current);
  const selected = presetOf(current);
  const preview = presetOf(draft);
  return (
    <Drawer
      open={open}
      onOpenChange={(nextOpen) => {
        if (nextOpen) setDraft(current);
        setOpen(nextOpen);
      }}
    >
      <DrawerTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className="preview-avatar-picker-trigger"
          aria-label={`프로필 이미지 변경, 현재 ${selected.displayName}`}
        >
          <Avatar name={selected.displayName} imageCode={current} />
          <span>
            <strong>프로필 이미지 변경</strong>
            <span>{selected.displayName} · 선택사항</span>
          </span>
          <Pencil size={16} aria-hidden="true" />
        </Button>
      </DrawerTrigger>
      <DrawerContent className="dreamon-preview preview-drawer preview-avatar-picker">
        <DrawerHeader>
          <DrawerTitle className="sr-only">프로필 이미지 변경</DrawerTitle>
          <DrawerDescription>
            마음에 드는 파워프렌즈를 골라보세요.
          </DrawerDescription>
        </DrawerHeader>
        <div className="preview-avatar-picker-body">
          <div className="preview-avatar-picker-preview" aria-live="polite">
            <Avatar name={preview.displayName} imageCode={draft} size="large" />
            <p>
              선택한 캐릭터: <strong>{preview.displayName}</strong>
            </p>
          </div>
          <RadioGroup
            aria-label="프로필 캐릭터"
            value={draft}
            onValueChange={(next) => {
              const option = presets.find((item) => item.code === next);
              if (option) setDraft(option.code);
            }}
            className="preview-avatar-options"
          >
            {presets.map((item) => (
              <Label
                key={item.code}
                htmlFor={`${id}-${item.code}`}
                className="preview-avatar-option"
                data-selected={draft === item.code}
              >
                <RadioGroupItem id={`${id}-${item.code}`} value={item.code} />
                <Avatar name={item.displayName} imageCode={item.code} />
                <span>{item.displayName}</span>
              </Label>
            ))}
          </RadioGroup>
        </div>
        <DrawerFooter>
          <Button
            type="button"
            className="preview-button"
            onClick={() => {
              onChange(draft);
              setOpen(false);
            }}
          >
            이 캐릭터로 선택
          </Button>
          <DrawerClose asChild>
            <Button type="button" variant="outline" className="preview-button">
              취소
            </Button>
          </DrawerClose>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
