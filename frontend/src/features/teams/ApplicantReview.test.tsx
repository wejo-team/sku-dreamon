import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { setupUser } from '@/test/user';
import { describe, expect, it, vi } from 'vitest';
import { ApplicantReview } from '@/features/teams/ApplicantReview';
import { useSession } from '@/features/auth/queries';
import { createDemoRecords, demoIds } from '@/features/demo/fixtures';
import { CatalogProviders, TestSessionButton } from '@/test/providers';
import { renderWithApi } from '@/test/render';

// 시연용 점수·기존 검토 권한을 검증합니다. 실제 JSON API는 TargetAiPanel.test.tsx에서 검증합니다.
vi.mock('@/lib/clock', async (original) => ({
  ...(await original<typeof import('@/lib/clock')>()),
  isMockApi: true,
}));

// 김서연의 그린웨이브 지원(Application DTO)과 현재 프로필(Profile DTO)
const records = createDemoRecords();
const seoyeonApplication = records.applications.find(
  (item) => item.id === demoIds.applications.seoyeon,
)!;
const seoyeonProfile = records.profiles.find(
  (item) => item.accountId === demoIds.accounts.seoyeon,
)!;

describe('applicant AI review reference', () => {
  it('labels demo scores and keeps missing data unscored without exposing explanations', async () => {
    const user = setupUser();
    render(
      <CatalogProviders>
        <ApplicantReview
          mayReviewExistingApplication
          application={seoyeonApplication}
          profile={{
            ...seoyeonProfile,
            skillCodes: [],
            experienceState: 'unspecified',
            experienceBody: null,
          }}
        />
      </CatalogProviders>,
    );
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(
      await screen.findByRole('img', { name: '역할: 85점' }),
    ).toBeInTheDocument();
    expect(screen.getByText('시연 점수')).toBeVisible();
    for (const label of ['역량', '경험', '참여 시간']) {
      expect(
        screen.getByRole('img', { name: `${label}: 정보 부족으로 점수 없음` }),
      ).toBeInTheDocument();
    }
    expect(screen.getAllByText('—')).toHaveLength(3);
    expect(screen.queryByText('정보 부족')).not.toBeInTheDocument();
    expect(
      screen.queryByText(seoyeonApplication.message!),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('등록한 지원 역할의 시연 점수입니다.'),
    ).not.toBeInTheDocument();
  });

  it('uses the latest private applicant profile on each explicit request', async () => {
    const user = setupUser();
    const applicant = seoyeonApplication;
    const profile = {
      ...seoyeonProfile,
      isPublic: false,
      experienceState: 'provided' as const,
      experienceBody: '지원 후 새로 등록한 경험',
    };
    const view = render(
      <CatalogProviders>
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={profile}
        />
      </CatalogProviders>,
    );
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(
      await screen.findByRole('img', { name: '경험: 65점' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('지원 후 새로 등록한 경험'),
    ).not.toBeInTheDocument();
    view.rerender(
      <CatalogProviders>
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={{
            ...profile,
            experienceState: 'none',
            experienceBody: null,
          }}
        />
      </CatalogProviders>,
    );
    expect(screen.queryByText('다시 수정한 경험')).not.toBeInTheDocument();
    expect(
      screen.getByText(/검토 이후 프로필 정보가 변경/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '다시 검토하기' }));
    expect(
      await screen.findByRole('img', { name: '경험: 20점' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('지원 후 새로 등록한 경험'),
    ).not.toBeInTheDocument();
  });

  it.each(['selected', 'rejected', 'canceled', 'discarded'] as const)(
    'allows factual review but excludes %s from new selection candidates',
    async (status) => {
      const user = setupUser();
      const applicant = { ...seoyeonApplication, status };
      render(
        <CatalogProviders>
          <ApplicantReview
            mayReviewExistingApplication
            application={applicant}
            profile={seoyeonProfile}
          />
        </CatalogProviders>,
      );
      await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
      expect(await screen.findByRole('status')).toHaveTextContent(
        '항목별 평가',
      );
      expect(
        screen.getByText(/새 선발 후보 추천에서 제외/),
      ).toBeInTheDocument();
    },
  );

  it('preserves factual review after a selection decision and allows a latest-profile refresh without restoring candidacy', async () => {
    const user = setupUser();
    const applicant = seoyeonApplication;
    const profile = seoyeonProfile;
    const view = render(
      <CatalogProviders>
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={profile}
        />
      </CatalogProviders>,
    );
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(await screen.findByRole('status')).toHaveTextContent('항목별 평가');
    view.rerender(
      <CatalogProviders>
        <ApplicantReview
          mayReviewExistingApplication
          application={{ ...applicant, status: 'selected' as const }}
          profile={profile}
        />
      </CatalogProviders>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('항목별 평가');
    expect(screen.getByText(/새 선발 후보 추천에서 제외/)).toBeInTheDocument();
    view.rerender(
      <CatalogProviders>
        <ApplicantReview
          mayReviewExistingApplication
          application={{ ...applicant, status: 'selected' as const }}
          profile={{ ...profile, experienceBody: '선발 이후 수정한 경험' }}
        />
      </CatalogProviders>,
    );
    expect(
      screen.getByText(/검토 이후 프로필 정보가 변경/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '다시 검토하기' }));
    await waitFor(() =>
      expect(
        screen.queryByText(/검토 이후 프로필 정보가 변경/),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByText('선발 이후 수정한 경험')).not.toBeInTheDocument();
    expect(screen.getByText(/새 선발 후보 추천에서 제외/)).toBeInTheDocument();
  });

  it('shows a failed request distinctly and supports retry', async () => {
    const user = setupUser();
    const applicant = seoyeonApplication;
    render(
      <CatalogProviders initialEntries={['/?scenario=review-error']}>
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={seoyeonProfile}
        />
      </CatalogProviders>,
    );
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '검토 결과를 가져오지 못했어요',
    );
    await user.click(screen.getByRole('button', { name: '검토 다시 시도' }));
    expect(await screen.findByRole('status')).toHaveTextContent('항목별 평가');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('hides existing review results and requests when the current leader relationship is unavailable', async () => {
    const user = setupUser();
    const applicant = { ...seoyeonApplication, status: 'discarded' as const };
    const view = render(
      <CatalogProviders>
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={seoyeonProfile}
        />
      </CatalogProviders>,
    );
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(await screen.findByRole('status')).toHaveTextContent('항목별 평가');
    view.rerender(
      <CatalogProviders>
        <ApplicantReview
          mayReviewExistingApplication={false}
          application={applicant}
          profile={seoyeonProfile}
        />
      </CatalogProviders>,
    );
    expect(
      screen.queryByRole('region', { name: 'AI 검토 도움' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(applicant.message!)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /검토/ }),
    ).not.toBeInTheDocument();
  });
});

function ReviewSessionHarness() {
  const { signedIn } = useSession();
  const [show, setShow] = useState(true);
  const applicant = seoyeonApplication;
  return (
    <>
      <TestSessionButton />
      <button onClick={() => setShow((previous) => !previous)}>
        화면 전환
      </button>
      {signedIn && show && (
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={seoyeonProfile}
        />
      )}
    </>
  );
}

it('retains review results across navigation in the current session and clears them after logout', async () => {
  const user = setupUser();
  renderWithApi(<ReviewSessionHarness />);
  await user.click(
    await screen.findByRole('button', { name: '테스트 로그인' }),
  );
  await user.click(await screen.findByRole('button', { name: 'AI 검토 요청' }));
  expect(await screen.findByRole('status')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '화면 전환' }));
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '화면 전환' }));
  expect(screen.getByRole('status')).toHaveTextContent('항목별 평가');
  await user.click(screen.getByRole('button', { name: '테스트 로그아웃' }));
  await user.click(
    await screen.findByRole('button', { name: '테스트 로그인' }),
  );
  expect(
    await screen.findByRole('button', { name: 'AI 검토 요청' }),
  ).toBeEnabled();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});
