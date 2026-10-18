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
import { Avatar } from './PreviewUi';
import {
  defaultMascotAvatarId,
  mascotAvatars,
  type MascotAvatarId,
} from './mascot-avatars';

export function AvatarPicker({
  value = defaultMascotAvatarId,
  onChange,
}: {
  value?: MascotAvatarId;
  onChange: (value: MascotAvatarId) => void;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const selected = mascotAvatars.find((item) => item.id === value)!;
  const preview = mascotAvatars.find((item) => item.id === draft)!;
  return (
    <Drawer
      open={open}
      onOpenChange={(nextOpen) => {
        if (nextOpen) setDraft(value);
        setOpen(nextOpen);
      }}
    >
      <DrawerTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className="preview-avatar-picker-trigger"
          aria-label={`프로필 이미지 변경, 현재 ${selected.name}`}
        >
          <Avatar name={selected.name} avatarId={value} />
          <span>
            <strong>프로필 이미지 변경</strong>
            <span>{selected.name} · 선택사항</span>
          </span>
          <Pencil size={16} aria-hidden="true" />
        </Button>
      </DrawerTrigger>
      <DrawerContent className="dreamon-preview preview-drawer preview-avatar-picker">
        <DrawerHeader>
          <DrawerTitle>나를 닮은 캐릭터</DrawerTitle>
          <DrawerDescription>
            마음에 드는 파워프렌즈를 골라보세요.
          </DrawerDescription>
        </DrawerHeader>
        <div className="preview-avatar-picker-body">
          <div className="preview-avatar-picker-preview" aria-live="polite">
            <Avatar name={preview.name} avatarId={draft} size="large" />
            <p>
              선택한 캐릭터: <strong>{preview.name}</strong>
            </p>
          </div>
          <RadioGroup
            aria-label="프로필 캐릭터"
            value={draft}
            onValueChange={(next) => {
              const option = mascotAvatars.find((item) => item.id === next);
              if (option) setDraft(option.id);
            }}
            className="preview-avatar-options"
          >
            {mascotAvatars.map((item) => (
              <Label
                key={item.id}
                htmlFor={`${id}-${item.id}`}
                className="preview-avatar-option"
                data-selected={draft === item.id}
              >
                <RadioGroupItem id={`${id}-${item.id}`} value={item.id} />
                <Avatar name={item.name} avatarId={item.id} />
                <span>{item.name}</span>
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
