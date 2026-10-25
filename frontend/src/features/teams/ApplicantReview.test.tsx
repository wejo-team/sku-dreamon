import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import { ApplicantReview } from '@/features/teams/ApplicantReview';
import { ApplicantReviewProvider } from '@/features/teams/ApplicantReviewProvider';
import { DemoProvider } from '@/features/demo/DemoProvider';
import { useDemo } from '@/features/demo/demo-context';
import { createDemoRecords, demoIds } from '@/features/demo/fixtures';

// 김서연의 그린웨이브 지원(Application DTO)과 현재 프로필(Profile DTO)
const records = createDemoRecords();
const seoyeonApplication = records.applications.find(
  (item) => item.id === demoIds.applications.seoyeon,
)!;
const seoyeonProfile = records.profiles.find(
  (item) => item.accountId === demoIds.accounts.seoyeon,
)!;

describe('applicant AI review reference', () => {
  it('uses the latest private applicant profile on each explicit request', async () => {
    const user = userEvent.setup();
    const applicant = seoyeonApplication;
    const profile = {
      ...seoyeonProfile,
      isPublic: false,
      experienceState: 'provided' as const,
      experienceBody: '지원 후 새로 등록한 경험',
    };
    const view = render(
      <MemoryRouter>
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={profile}
        />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(
      await screen.findByText('지원 후 새로 등록한 경험'),
    ).toBeInTheDocument();
    view.rerender(
      <MemoryRouter>
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={{
            ...profile,
            experienceBody: '다시 수정한 경험',
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.queryByText('다시 수정한 경험')).not.toBeInTheDocument();
    expect(
      screen.getByText(/검토 이후 프로필 정보가 변경/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '다시 검토하기' }));
    expect(await screen.findByText('다시 수정한 경험')).toBeInTheDocument();
    expect(
      screen.queryByText('지원 후 새로 등록한 경험'),
    ).not.toBeInTheDocument();
  });

  it.each(['selected', 'rejected', 'canceled', 'discarded'] as const)(
    'allows factual review but excludes %s from new selection candidates',
    async (status) => {
      const user = userEvent.setup();
      const applicant = { ...seoyeonApplication, status };
      render(
        <MemoryRouter>
          <ApplicantReview
            mayReviewExistingApplication
            application={applicant}
            profile={seoyeonProfile}
          />
        </MemoryRouter>,
      );
      await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
      expect(await screen.findByRole('status')).toHaveTextContent(
        applicant.message!,
      );
      expect(
        screen.getByText(/새 선발 후보 추천에서 제외/),
      ).toBeInTheDocument();
    },
  );

  it('preserves factual review after a selection decision and allows a latest-profile refresh without restoring candidacy', async () => {
    const user = userEvent.setup();
    const applicant = seoyeonApplication;
    const profile = seoyeonProfile;
    const view = render(
      <MemoryRouter>
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={profile}
        />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      applicant.message!,
    );
    view.rerender(
      <MemoryRouter>
        <ApplicantReview
          mayReviewExistingApplication
          application={{ ...applicant, status: 'selected' as const }}
          profile={profile}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole('status')).toHaveTextContent(applicant.message!);
    expect(screen.getByText(/새 선발 후보 추천에서 제외/)).toBeInTheDocument();
    view.rerender(
      <MemoryRouter>
        <ApplicantReview
          mayReviewExistingApplication
          application={{ ...applicant, status: 'selected' as const }}
          profile={{ ...profile, experienceBody: '선발 이후 수정한 경험' }}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/검토 이후 프로필 정보가 변경/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '다시 검토하기' }));
    expect(
      await screen.findByText('선발 이후 수정한 경험'),
    ).toBeInTheDocument();
    expect(screen.getByText(/새 선발 후보 추천에서 제외/)).toBeInTheDocument();
  });

  it('shows a failed request distinctly and supports retry', async () => {
    const user = userEvent.setup();
    const applicant = seoyeonApplication;
    render(
      <MemoryRouter initialEntries={['/?scenario=review-error']}>
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={seoyeonProfile}
        />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '검토 결과를 가져오지 못했어요',
    );
    await user.click(screen.getByRole('button', { name: '검토 다시 시도' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      applicant.message!,
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('hides existing review results and requests when the current leader relationship is unavailable', async () => {
    const user = userEvent.setup();
    const applicant = { ...seoyeonApplication, status: 'discarded' as const };
    const view = render(
      <MemoryRouter>
        <ApplicantReview
          mayReviewExistingApplication
          application={applicant}
          profile={seoyeonProfile}
        />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      applicant.message!,
    );
    view.rerender(
      <MemoryRouter>
        <ApplicantReview
          mayReviewExistingApplication={false}
          application={applicant}
          profile={seoyeonProfile}
        />
      </MemoryRouter>,
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
  const { signedIn, signIn, signOut } = useDemo();
  const [show, setShow] = useState(true);
  const applicant = seoyeonApplication;
  return (
    <>
      <button onClick={signedIn ? signOut : signIn}>
        {signedIn ? '로그아웃' : '로그인'}
      </button>
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
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <DemoProvider>
        <ApplicantReviewProvider>
          <ReviewSessionHarness />
        </ApplicantReviewProvider>
      </DemoProvider>
    </MemoryRouter>,
  );
  await user.click(screen.getByRole('button', { name: '로그인' }));
  await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
  expect(await screen.findByRole('status')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '화면 전환' }));
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '화면 전환' }));
  expect(screen.getByRole('status')).toHaveTextContent(
    seoyeonApplication.message!,
  );
  await user.click(screen.getByRole('button', { name: '로그아웃' }));
  await user.click(screen.getByRole('button', { name: '로그인' }));
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'AI 검토 요청' })).toBeEnabled();
});
