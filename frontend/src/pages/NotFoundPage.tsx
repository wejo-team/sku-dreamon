import { Link } from 'react-router';
import { Button } from '@/components/ui/button';

export function NotFoundPage() {
  return (
    <main className="mx-auto flex min-h-svh max-w-lg flex-col justify-center gap-5 p-6">
      <h1 className="text-2xl font-semibold">페이지를 찾을 수 없어요</h1>
      <Button asChild>
        <Link to="/">처음으로 돌아가기</Link>
      </Button>
    </main>
  );
}
