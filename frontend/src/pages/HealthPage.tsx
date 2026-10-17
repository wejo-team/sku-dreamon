import { useQuery } from '@tanstack/react-query';
import {
  CircleAlert,
  CircleCheck,
  LoaderCircle,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { healthQueryOptions } from '@/features/health/queries';

export function HealthPage() {
  const health = useQuery(healthQueryOptions);

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-lg flex-col px-5 pt-[max(2rem,env(safe-area-inset-top))] pb-[max(2rem,env(safe-area-inset-bottom))] sm:justify-center">
      <header className="mb-8">
        <p className="mb-3 text-sm font-medium text-muted-foreground">
          서경드림온 · 개발 환경
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">연결 상태</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          프론트엔드에서 API 서버에 요청을 보내 연결을 확인합니다.
        </p>
      </header>

      <section
        aria-labelledby="api-heading"
        className="rounded-lg border bg-card p-5 shadow-sm sm:p-6"
      >
        <h2 id="api-heading" className="mb-5 font-semibold">
          API 서버
        </h2>
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="min-h-24"
        >
          {health.isPaused ? (
            <p className="text-sm text-muted-foreground">
              네트워크 연결을 기다리고 있어요.
            </p>
          ) : health.isFetching ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle
                aria-hidden="true"
                className="size-5 motion-safe:animate-spin"
              />
              연결 확인 중…
            </p>
          ) : health.isError ? (
            <>
              <p className="flex items-center gap-2 font-medium text-destructive">
                <CircleAlert aria-hidden="true" className="size-5 shrink-0" />
                API 연결을 확인하지 못했어요
              </p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                백엔드 실행 상태와 API 주소를 확인한 뒤 다시 시도해 주세요.
              </p>
            </>
          ) : health.isSuccess ? (
            <>
              <p className="flex items-center gap-2 font-medium">
                <CircleCheck aria-hidden="true" className="size-5 shrink-0" />
                API 서버가 응답했어요
              </p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                데이터베이스 연결은 별도로 확인해야 합니다.
              </p>
            </>
          ) : null}
        </div>
        <Button
          className="mt-6 w-full"
          disabled={health.isFetching || health.isPaused}
          onClick={() => void health.refetch()}
        >
          <RefreshCw aria-hidden="true" />
          {health.isFetching ? '확인 중' : '다시 확인'}
        </Button>
      </section>
      <p className="mt-5 text-xs leading-5 text-muted-foreground">
        초기 개발 연결을 확인하는 화면입니다. 서비스 기능은 이후 명세 검토를
        거쳐 추가합니다.
      </p>
    </main>
  );
}
