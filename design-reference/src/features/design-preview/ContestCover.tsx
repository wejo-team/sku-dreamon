import { useState } from 'react';

const defaultCover = '/contest-covers/skon-default.png';

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
