// 서버의 교과목 카탈로그를 검색하고 검색·페이지 변경과 무관하게 선택 과목을 유지합니다.

import { useEffect, useId, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { CourseSummary } from '@/features/catalogs/api';
import { coursesQueryOptions } from '@/features/catalogs/queries';
import { ApiError } from '@/lib/api';

export function CoursePicker({
  value,
  onChange,
  unavailable = false,
}: {
  value: CourseSummary[];
  onChange: (courses: CourseSummary[]) => void;
  unavailable?: boolean;
}) {
  const id = useId();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState({ q: '', page: 1, pageSize: 20 });
  const searching = search.trim() !== query.q;
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery((current) =>
        current.q === search.trim()
          ? current
          : { ...current, q: search.trim(), page: 1 },
      );
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);
  const courses = useQuery({
    ...coursesQueryOptions(query),
    enabled: !unavailable,
  });
  const unsupported =
    unavailable ||
    (courses.error instanceof ApiError && courses.error.status === 404);
  const loading = searching || courses.isPending;
  const selected = new Set(value.map((course) => course.code));
  const remove = (code: string) =>
    onChange(value.filter((course) => course.code !== code));
  const pagination = courses.data?.pagination;

  return (
    <fieldset className="preview-field profile-courses">
      <legend>
        수강과목 <span className="preview-muted">(선택 · 복수 선택)</span>
      </legend>
      <p id={`${id}-help`} className="preview-muted">
        수강했거나 수강 중인 과목을 선택해 주세요.
      </p>
      <p className="preview-muted">
        지금 선택하지 않아도 나중에 프로필에서 추가할 수 있어요.
      </p>
      <Label htmlFor={`${id}-search`}>과목명 또는 학수번호</Label>
      <Input
        id={`${id}-search`}
        type="search"
        disabled={unsupported}
        autoComplete="off"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
            event.preventDefault();
            setQuery({ q: search.trim(), page: 1, pageSize: 20 });
          }
        }}
        aria-describedby={`${id}-help`}
        placeholder="예: 데이터베이스, GE1394"
      />
      <div className="profile-course-selection">
        {(!unsupported || value.length > 0) && (
          <p className="preview-muted" role="status">
            선택한 과목 {value.length}개
          </p>
        )}
        {value.length > 0 && (
          <ul className="profile-course-chips" aria-label="선택한 수강과목">
            {value.map((course) => (
              <li key={course.code}>
                <span>
                  {course.name}{' '}
                  <span className="profile-course-code">{course.code}</span>
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`${course.name} (${course.code}) 선택 해제`}
                  onClick={() => remove(course.code)}
                >
                  <X aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div aria-busy={!unsupported && (loading || courses.isFetching)}>
        {unsupported ? (
          <p className="preview-muted" role="status">
            {value.length > 0
              ? '지금은 수강과목 선택을 사용할 수 없어요. 선택한 과목은 이 화면에 남아 있어요.'
              : unavailable
                ? '지금은 수강과목 선택을 사용할 수 없어요.'
                : '지금은 수강과목 선택을 사용할 수 없어요. 과목 선택 없이 계속할 수 있어요.'}
          </p>
        ) : loading ? (
          <p className="preview-muted" role="status">
            과목을 검색하고 있어요…
          </p>
        ) : courses.isError ? (
          <div className="preview-stack">
            <p className="preview-error" role="alert">
              과목을 불러오지 못했어요. 다시 시도해 주세요.
            </p>
            <Button
              type="button"
              variant="outline"
              onClick={() => void courses.refetch()}
            >
              과목 다시 불러오기
            </Button>
          </div>
        ) : courses.data?.data.length === 0 ? (
          <p className="preview-muted" role="status">
            {query.q
              ? '검색 결과가 없어요. 다른 과목명이나 학수번호로 검색해 주세요.'
              : '아직 선택할 수 있는 과목이 없어요. 나중에 프로필에서 추가할 수 있어요.'}
          </p>
        ) : (
          <>
            <p className="preview-muted" role="status">
              검색 결과 {pagination?.total}개
            </p>
            <ul className="profile-course-results" aria-label="과목 검색 결과">
              {courses.data?.data.map((course) => (
                <li key={course.code}>
                  <Label
                    className="profile-course-option"
                    htmlFor={`${id}-${course.code}`}
                  >
                    <Checkbox
                      id={`${id}-${course.code}`}
                      checked={selected.has(course.code)}
                      aria-label={`${course.name} (${course.code})`}
                      onCheckedChange={(checked) => {
                        if (checked === true && !selected.has(course.code))
                          onChange([
                            ...value,
                            { code: course.code, name: course.name },
                          ]);
                        else if (checked === false) remove(course.code);
                      }}
                    />
                    <span>
                      <span className="profile-course-name">{course.name}</span>
                      <span className="profile-course-meta">
                        {course.code}
                        {course.departments.length > 0
                          ? ` · ${course.departments.join(' · ')}`
                          : ''}
                      </span>
                      {course.aliases.some((name) => name !== course.name) && (
                        <span className="profile-course-meta">
                          다른 과목명:{' '}
                          {course.aliases
                            .filter((name) => name !== course.name)
                            .join(' · ')}
                        </span>
                      )}
                    </span>
                  </Label>
                </li>
              ))}
            </ul>
            {pagination && pagination.totalPages > 1 && (
              <nav
                className="profile-course-pagination"
                aria-label="과목 검색 페이지"
              >
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  aria-label="이전 과목 페이지"
                  disabled={query.page <= 1}
                  onClick={() => setQuery({ ...query, page: query.page - 1 })}
                >
                  <ChevronLeft aria-hidden="true" />
                </Button>
                <p className="preview-muted">
                  {query.page} / {pagination.totalPages} 페이지
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  aria-label="다음 과목 페이지"
                  disabled={query.page >= pagination.totalPages}
                  onClick={() => setQuery({ ...query, page: query.page + 1 })}
                >
                  <ChevronRight aria-hidden="true" />
                </Button>
              </nav>
            )}
          </>
        )}
      </div>
    </fieldset>
  );
}
