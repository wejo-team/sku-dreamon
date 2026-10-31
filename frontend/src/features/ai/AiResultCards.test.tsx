/** 구조화된 AI 결과의 근거 펼치기·표시 내 필터·사람 비교를 검증합니다. */
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CatalogProviders } from '@/test/providers';
import { setupUser } from '@/test/user';
import { AiResultCards } from './AiResultCards';
import type { PersonDetails, RichResourceCard } from './contract';

const person = (
  id: string,
  title: string,
  skills: PersonDetails['skillCodes'],
): RichResourceCard => ({
  kind: 'person',
  resourceId: id,
  title,
  reason: `${title} 님이 등록한 개발 경험을 참고할 수 있어요.`,
  fieldCodes: ['it_technology'],
  roleCodes: ['development'],
  isDemo: true,
  evidence: [`${title} 님은 동아리 웹 서비스를 개발했다고 등록했어요.`],
  details: {
    kind: 'person',
    skillCodes: skills,
    weeklyAvailabilityCode: null,
    experienceState: 'provided',
    experienceBody: '동아리 웹 서비스 개발',
    introduction: null,
  },
});
const cards = [
  person('first', '김하늘', ['programming']),
  person('second', '이도윤', ['ui_ux']),
];

describe('AiResultCards', () => {
  it('separates evidence disclosure from the detail link and keeps missing time distinct', async () => {
    const user = setupUser();
    render(
      <CatalogProviders>
        <AiResultCards cards={cards} returnTo="/ai" />
      </CatalogProviders>,
    );
    const first = screen.getByRole('article', { name: '김하늘' });
    expect(within(first).getByRole('link', { name: /김하늘/ })).toHaveAttribute(
      'href',
      '/people/first?from=%2Fai',
    );
    const disclosure = within(first).getByText('추천 근거와 등록 정보');
    await user.click(disclosure);
    expect(disclosure.closest('details')).toHaveAttribute('open');
    expect(within(first).getByText('주당 시간 미입력')).toBeInTheDocument();
    expect(
      within(first).getByText(
        '김하늘 님은 동아리 웹 서비스를 개발했다고 등록했어요.',
      ),
    ).toBeVisible();
    expect(
      screen.queryByText(/일치율|적합도|가능 요일/),
    ).not.toBeInTheDocument();
  });

  it('filters only displayed people by their registered skill and resets comparison selection', async () => {
    const user = setupUser();
    render(
      <CatalogProviders>
        <AiResultCards cards={cards} />
      </CatalogProviders>,
    );
    await user.click(
      screen.getByRole('checkbox', { name: '김하늘 비교에 포함' }),
    );
    await user.click(
      screen.getByRole('checkbox', { name: '이도윤 비교에 포함' }),
    );
    await user.click(screen.getByRole('button', { name: '선택한 2명 비교' }));
    expect(
      screen.getByRole('table', { name: '선택한 사람의 등록 정보 비교' }),
    ).toBeInTheDocument();
    await user.selectOptions(
      screen.getByRole('combobox', { name: '현재 표시된 사람의 등록 역량' }),
      'programming',
    );
    expect(
      screen.queryByRole('article', { name: '이도윤' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('article', { name: '김하늘' })).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('현재 표시된 사람 2명 중 1명')).toBeInTheDocument();
  });

  it('limits comparison to three people and preserves an applicant-specific destination', async () => {
    const user = setupUser();
    const many = [
      ...cards,
      person('third', '박하윤', []),
      person('fourth', '최서준', []),
    ];
    render(
      <CatalogProviders>
        <AiResultCards
          cards={many}
          getHref={(card) => `/applicants/${card.resourceId}`}
        />
      </CatalogProviders>,
    );
    for (const name of ['김하늘', '이도윤', '박하윤'])
      await user.click(
        screen.getByRole('checkbox', { name: `${name} 비교에 포함` }),
      );
    expect(
      screen.getByRole('checkbox', { name: '최서준 비교에 포함' }),
    ).toBeDisabled();
    expect(screen.getByRole('link', { name: /김하늘/ })).toHaveAttribute(
      'href',
      '/applicants/first',
    );
  });
});
