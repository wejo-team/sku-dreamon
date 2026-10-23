/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ContestCover.tsx - 공모전 커버 원본
 * 2. docs/design/assets.md - 공모전 기본 커버(스콘) 출처와 빈 이미지·로드 실패 fallback
 * 3. docs/design/tokens.md - 포스터 영역 옅은 녹색 바탕, 2:3 비율, object-fit: contain
 * 4. docs/design/assets/default-cover-390.png - 기본 커버 화면
 */

import { useState } from 'react';

const defaultCover = '/contest-covers/skon-default.png';

// [출처 2, 3, 4] 이미지 없음·로드 실패 시 스콘 기본 커버, 원본 비율 보존
export function ContestCover({
  src,
  className,
  loading = 'lazy',
}: {
  src?: string;
  className?: string;
  loading?: 'eager' | 'lazy';
}) {
  const [failedSource, setFailedSource] = useState<string>();
  const source = src?.trim();
  const displayedSource =
    !source || failedSource === source ? defaultCover : source;

  return (
    <img
      className={className}
      src={displayedSource}
      alt=""
      width={1254}
      height={1254}
      loading={loading}
      decoding="async"
      onError={() => {
        if (displayedSource !== defaultCover) setFailedSource(source);
      }}
    />
  );
}
