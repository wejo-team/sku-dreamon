// 지원 가능 여부처럼 전체 목록이 필요한 판단에서 첫 페이지 밖의 이력을 누락하지 않습니다.
import type { Page } from '@/lib/api-contract';

export async function allPages<T>(load: (page: number) => Promise<Page<T>>) {
  const rows: T[] = [];
  for (let page = 1; ; page++) {
    const result = await load(page);
    // 조회 중 삭제로 마지막 페이지가 당겨지면 이미 읽은 페이지를 중복 추가하지 않습니다.
    if (result.pagination.page < page) return rows;
    rows.push(...result.data);
    if (result.pagination.page >= result.pagination.totalPages) return rows;
  }
}
