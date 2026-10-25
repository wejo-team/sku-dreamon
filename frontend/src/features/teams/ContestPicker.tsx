/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ContestPicker.tsx - 공모전 검색 선택 원본
 * 2. docs/design/tokens.md - Drawer + Command 공모전 검색 선택
 * 3. docs/design/screens.md - 「확인할 상태와 연결」 검색·선택·취소·닫기, 결과가 많을 때 추가 표시
 * 4. docs/design/assets/contest-picker-320.png - 실제 화면
 */

import { useMemo, useRef, useState, type Ref } from 'react';
import { Check, ChevronsUpDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
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
import type { ContestDetail } from '@/features/contests/api';
import { fieldLabel } from '@/features/demo/labels';
import { deadlineLabel } from '@/features/demo/contest-state';
import { ContestCover } from '@/components/common/ContestCover';

const pageSize = 20;

function normalizeSearch(value: string) {
  return value.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, '');
}

type ContestPickerProps = {
  contests: readonly ContestDetail[];
  value: string;
  onChange: (value: string) => void;
  id: string;
  invalid?: boolean;
  describedBy?: string;
  onBlur?: () => void;
  ref?: Ref<HTMLButtonElement>;
};

// [출처 2, 3, 4] 검색·선택·취소
export function ContestPicker({
  contests,
  value,
  onChange,
  id,
  invalid = false,
  describedBy,
  onBlur,
  ref,
}: ContestPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [visibleLimit, setVisibleLimit] = useState(pageSize);
  const inputRef = useRef<HTMLInputElement>(null);
  const selected = contests.find((contest) => contest.id === value);
  const matched = useMemo(() => {
    const terms = query
      .normalize('NFKC')
      .toLocaleLowerCase()
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    return contests.filter((contest) => {
      const source = normalizeSearch(
        `${contest.title} ${contest.organizer} ${contest.fieldCodes.map(fieldLabel).join(' ')}`,
      );
      return terms.every((term) => source.includes(term));
    });
  }, [contests, query]);
  const visible = matched.slice(0, visibleLimit);
  const remaining = matched.length - visible.length;

  function updateQuery(nextQuery: string) {
    setQuery(nextQuery);
    setVisibleLimit(pageSize);
  }

  return (
    <Drawer
      open={open}
      onOpenChange={(nextOpen) => {
        if (nextOpen) updateQuery('');
        setOpen(nextOpen);
      }}
    >
      <DrawerTrigger asChild>
        <Button
          ref={ref}
          id={id}
          type="button"
          variant="outline"
          className="preview-button preview-contest-picker-trigger"
          aria-invalid={invalid}
          aria-describedby={describedBy}
          onBlur={onBlur}
        >
          <span className="preview-contest-picker-value">
            <strong>{selected?.title ?? '공모전 검색해서 선택'}</strong>
            {selected && (
              <span>
                {selected.organizer} ·{' '}
                {selected.fieldCodes.map(fieldLabel).join(' · ')} · 마감{' '}
                {deadlineLabel(selected.timing.closing)}
              </span>
            )}
          </span>
          <ChevronsUpDown aria-hidden="true" />
        </Button>
      </DrawerTrigger>
      <DrawerContent className="dreamon-preview preview-drawer preview-contest-picker">
        <DrawerHeader>
          <DrawerTitle>공모전 선택</DrawerTitle>
          <DrawerDescription>
            공모전 이름이나 주최자로 검색해 주세요.
          </DrawerDescription>
        </DrawerHeader>
        <Command
          className="preview-contest-command"
          label="공모전 검색"
          shouldFilter={false}
        >
          <CommandInput
            ref={inputRef}
            aria-label="공모전 검색"
            placeholder="공모전명 또는 주최자"
            value={query}
            onValueChange={updateQuery}
          />
          <p
            className="preview-contest-picker-count"
            role="status"
            aria-live="polite"
          >
            검색 결과 {matched.length}개
            {remaining > 0 && ` · ${visible.length}개 표시`}
          </p>
          <CommandList
            className="preview-contest-picker-list"
            label="공모전 검색 결과"
          >
            <CommandEmpty className="preview-contest-picker-empty">
              <p>검색 결과가 없어요</p>
              <p>다른 공모전 이름이나 주최자로 검색해 보세요.</p>
            </CommandEmpty>
            {visible.length > 0 && (
              <CommandGroup value="contests">
                {visible.map((contest) => (
                  <CommandItem
                    key={contest.id}
                    value={contest.id}
                    className="preview-contest-option"
                    data-current={contest.id === value}
                    aria-label={`${contest.title}, ${contest.organizer}, ${contest.fieldCodes.map(fieldLabel).join(' ')}, 마감 ${deadlineLabel(contest.timing.closing)}${contest.id === value ? ', 현재 선택됨' : ''}`}
                    onSelect={() => {
                      onChange(contest.id);
                      setOpen(false);
                    }}
                  >
                    <ContestCover
                      src={contest.posterUrl ?? undefined}
                      className="preview-contest-option-cover"
                    />
                    <span className="preview-contest-option-copy">
                      <strong>{contest.title}</strong>
                      <span className="preview-contest-option-organizer">
                        {contest.organizer}
                      </span>
                      <span className="preview-contest-option-meta">
                        {contest.fieldCodes.map(fieldLabel).join(' · ')} · 마감{' '}
                        {deadlineLabel(contest.timing.closing)}
                      </span>
                    </span>
                    {contest.id === value && (
                      <>
                        <Check aria-hidden="true" />
                        <span className="sr-only">현재 선택됨</span>
                      </>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
        <DrawerFooter>
          {matched.length === 0 && query && (
            <Button
              type="button"
              variant="outline"
              className="preview-button"
              onClick={() => {
                updateQuery('');
                inputRef.current?.focus();
              }}
            >
              검색어 지우기
            </Button>
          )}
          {remaining > 0 && (
            <Button
              type="button"
              variant="outline"
              className="preview-button preview-contest-picker-more"
              onClick={() => setVisibleLimit((limit) => limit + pageSize)}
            >
              {Math.min(pageSize, remaining)}개 더 보기
            </Button>
          )}
          <DrawerClose asChild>
            <Button type="button" variant="outline" className="preview-button">
              닫기
            </Button>
          </DrawerClose>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
