/**
 * [참조 출처]
 * 1. docs/specs/contests.md#exploration-ui - 탐색 필터의 선택·적용·취소
 * 2. docs/design/screens.md - 「확인할 상태와 연결」 초안 선택·적용 시 URL 반영, 취소·Escape 시 미적용 선택 제거
 * 3. docs/design/tokens.md - Drawer + RadioGroup + Checkbox, 선택 개수 안내, 44px 아이콘 버튼
 * 4. docs/design/assets/explore-filters-390.png - 실제 필터 화면
 */

import { useId, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
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
import { useLabels } from '@/features/catalogs/queries';

// [출처 2, 3, 4] 분야/역할 초안 선택과 적용
export function ExploreFilters({
  kind,
  value,
  onlyOpen,
  onApply,
}: {
  kind: 'contests' | 'teams' | 'people';
  value: string;
  onlyOpen: boolean;
  onApply: (value: string, onlyOpen: boolean) => void;
}) {
  const { fieldLabel, fieldOptions, roleLabel, roleOptions } = useLabels();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value || 'all');
  const [draftOnlyOpen, setDraftOnlyOpen] = useState(onlyOpen);
  const category = kind === 'contests';
  const name = category ? '분야' : '역할';
  const activeCount =
    Number(Boolean(value)) + Number(kind === 'teams' && onlyOpen);
  const valueLabel = value
    ? (category ? fieldLabel : roleLabel)(value)
    : `모든 ${name}`;
  const summary = [valueLabel, kind === 'teams' && onlyOpen ? '모집중만' : '']
    .filter(Boolean)
    .join(' · ');

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        if (next) {
          setDraft(value || 'all');
          setDraftOnlyOpen(onlyOpen);
        }
        setOpen(next);
      }}
    >
      <DrawerTrigger asChild>
        <Button
          variant="ghost"
          className="preview-filter-trigger"
          aria-label="탐색 필터"
          aria-describedby={`${id}-summary`}
          title={`탐색 필터: ${summary}`}
          data-active={activeCount > 0}
        >
          <span>필터</span>
          <SlidersHorizontal size={18} aria-hidden="true" />
          {activeCount > 0 && (
            <span className="preview-filter-count" aria-hidden="true">
              {activeCount}
            </span>
          )}
        </Button>
      </DrawerTrigger>
      <span id={`${id}-summary`} className="sr-only">
        {summary}
      </span>
      <DrawerContent className="dreamon-preview preview-drawer preview-explore-filter-drawer">
        <DrawerHeader>
          <DrawerTitle>탐색 필터</DrawerTitle>
          <DrawerDescription>
            원하는 {category ? '분야를' : '역할을'} 골라 결과를 좁혀보세요.
          </DrawerDescription>
        </DrawerHeader>
        <div className="preview-drawer-body preview-explore-filter-body">
          <RadioGroup
            aria-label={name}
            value={draft}
            onValueChange={setDraft}
            className="preview-explore-filter-options"
          >
            {/* [출처 3] 값은 카탈로그 코드, 표시는 displayName */}
            {[
              { code: 'all', displayName: `모든 ${name}` },
              ...(category ? fieldOptions : roleOptions),
            ].map((option, index) => (
              <Label
                key={option.code}
                htmlFor={`${id}-${index}`}
                className="preview-choice"
              >
                <RadioGroupItem id={`${id}-${index}`} value={option.code} />
                {option.displayName}
              </Label>
            ))}
          </RadioGroup>
          {kind === 'teams' && (
            <Label className="preview-inline-check" htmlFor={`${id}-open`}>
              <Checkbox
                id={`${id}-open`}
                checked={draftOnlyOpen}
                onCheckedChange={(checked) =>
                  setDraftOnlyOpen(checked === true)
                }
              />
              모집중만
            </Label>
          )}
        </div>
        <DrawerFooter>
          <Button
            className="preview-button"
            onClick={() => {
              onApply(draft === 'all' ? '' : draft, draftOnlyOpen);
              setOpen(false);
            }}
          >
            필터 적용
          </Button>
          <DrawerClose asChild>
            <Button variant="outline" className="preview-button">
              취소
            </Button>
          </DrawerClose>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
