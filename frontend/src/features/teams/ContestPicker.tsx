/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ContestPicker.tsx - 공모전 검색 선택 원본
 * 2. docs/design/tokens.md - Drawer + Command 공모전 검색 선택
 * 3. docs/design/screens.md - 「확인할 상태와 연결」 검색·선택·취소·닫기, 결과가 많을 때 추가 표시
 * 4. docs/design/assets/contest-picker-320.png - 실제 화면
 * 5. docs/api/contests.md#queries - GET /contests의 q(제목·주최자·분야 표시명), registrationStatus, page·pageSize
 *
 * 검색과 더 보기는 서버 목록(접수 중 공모전)을 조회합니다. 받은 목록 밖의 공모전도 검색·추가 페이지로 찾을 수 있습니다.
 */

import { useEffect, useRef, useState, type Ref } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Check, ChevronsUpDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Command,
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
import type { ContestSummary } from '@/features/contests/api';
import { openContestSearchOptions } from '@/features/contests/queries';
import { useLabels } from '@/features/catalogs/queries';
import { endsAtLabel } from '@/features/demo/contest-state';
import { DemoBadge } from '@/components/common/CommonUi';
import { ContestCover } from '@/components/common/ContestCover';

// 입력이 멈춘 뒤 검색 요청을 보냅니다.
const searchDelay = 250;

/** 선택 버튼에 표시할 공모전 정보(목록 요약 또는 상세) */
export type ContestChoice = Pick<
  ContestSummary,
  'id' | 'title' | 'organizer' | 'fieldCodes' | 'endsAt' | 'isDemo'
>;

type ContestPickerProps = {
  /** 현재 선택한 공모전 정보. 선택창 목록에 없더라도 버튼에 표시합니다. */
  selected?: ContestChoice;
  value: string;
  onChange: (value: string) => void;
  id: string;
  invalid?: boolean;
  describedBy?: string;
  onBlur?: () => void;
  ref?: Ref<HTMLButtonElement>;
};

function useDebounced(value: string) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), searchDelay);
    return () => clearTimeout(timer);
  }, [value]);
  return debounced;
}

// [출처 2, 3, 4, 5] 서버 검색·더 보기·선택·취소
export function ContestPicker({
  selected,
  value,
  onChange,
  id,
  invalid = false,
  describedBy,
  onBlur,
  ref,
}: ContestPickerProps) {
  const { fieldLabel } = useLabels();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  // 선택창에서 고른 공모전(상위가 상세를 받기 전에도 버튼에 표시)
  const [picked, setPicked] = useState<ContestChoice>();
  const inputRef = useRef<HTMLInputElement>(null);
  const q = useDebounced(query.trim());
  // 검색어마다 첫 페이지부터 보여 줍니다(이미 받은 다음 페이지는 더 보기에서 다시 씁니다).
  const [shown, setShown] = useState({ q: '', pages: 1 });
  const pageCount = shown.q === q ? shown.pages : 1;
  const search = useInfiniteQuery({
    ...openContestSearchOptions(q),
    enabled: open,
  });
  const current =
    selected?.id === value
      ? selected
      : picked?.id === value
        ? picked
        : undefined;
  const loadedPages = search.data?.pages ?? [];
  const visible = loadedPages.slice(0, pageCount).flatMap((page) => page.data);
  const total = search.data?.pages.at(-1)?.pagination.total ?? 0;
  const remaining = Math.max(total - visible.length, 0);
  // 입력 중(요청 전)이거나 첫 페이지를 받는 중
  const searching = q !== query.trim() || search.isPending;
  const empty = !searching && !search.isError && total === 0;

  // 검색어를 바꾸면 결과를 첫 페이지부터 다시 보여 줍니다.
  function updateQuery(nextQuery: string) {
    setQuery(nextQuery);
    setShown({ q: '', pages: 1 });
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
          aria-describedby={
            [describedBy, current?.isDemo ? `${id}-demo` : undefined]
              .filter(Boolean)
              .join(' ') || undefined
          }
          onBlur={onBlur}
        >
          <span className="preview-contest-picker-value">
            <strong>{current?.title ?? '공모전 검색해서 선택'}</strong>
            {current?.isDemo && (
              <span id={`${id}-demo`}>
                <DemoBadge isDemo={current.isDemo} kind="contest" />
              </span>
            )}
            {current && (
              <span>
                {current.organizer} ·{' '}
                {current.fieldCodes.map(fieldLabel).join(' · ')} · 마감{' '}
                {endsAtLabel(current.endsAt)}
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
            {searching
              ? '검색 중…'
              : search.isError
                ? '공모전을 불러오지 못했어요.'
                : `검색 결과 ${total}개${remaining > 0 ? ` · ${visible.length}개 표시` : ''}`}
          </p>
          <CommandList
            className="preview-contest-picker-list"
            label="공모전 검색 결과"
          >
            {empty && (
              <div className="preview-contest-picker-empty">
                <p>검색 결과가 없어요</p>
                <p>다른 공모전 이름이나 주최자로 검색해 보세요.</p>
              </div>
            )}
            {!searching && visible.length > 0 && (
              <CommandGroup value="contests">
                {visible.map((contest) => (
                  <CommandItem
                    key={contest.id}
                    value={contest.id}
                    className="preview-contest-option"
                    data-current={contest.id === value}
                    aria-label={`${contest.title}, ${contest.organizer}, ${contest.fieldCodes.map(fieldLabel).join(' ')}, 마감 ${endsAtLabel(contest.endsAt)}${contest.isDemo ? ', 시연 공고' : ''}${contest.id === value ? ', 현재 선택됨' : ''}`}
                    onSelect={() => {
                      setPicked(contest);
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
                      <DemoBadge isDemo={contest.isDemo} kind="contest" />
                      <span className="preview-contest-option-organizer">
                        {contest.organizer}
                      </span>
                      <span className="preview-contest-option-meta">
                        {contest.fieldCodes.map(fieldLabel).join(' · ')} · 마감{' '}
                        {endsAtLabel(contest.endsAt)}
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
          {search.isError && (
            <Button
              type="button"
              variant="outline"
              className="preview-button"
              onClick={() => void search.refetch()}
            >
              다시 시도
            </Button>
          )}
          {empty && query && (
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
          {!searching && remaining > 0 && (
            <Button
              type="button"
              variant="outline"
              className="preview-button preview-contest-picker-more"
              disabled={search.isFetchingNextPage}
              onClick={() => {
                if (loadedPages.length <= pageCount)
                  void search.fetchNextPage();
                setShown({ q, pages: pageCount + 1 });
              }}
            >
              {Math.min(20, remaining)}개 더 보기
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
