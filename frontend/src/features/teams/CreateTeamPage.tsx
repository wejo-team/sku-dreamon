/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/CreateTeamPage.tsx - 팀 만들기 원본
 * 2. docs/design/screens.md - 팀명 2~40자·소개 10~1,000자·역할 1~6개, 공식 인원 범위, 정원 1명은 역할 생략
 * 3. docs/specs/team-recruitment.md#official-capacity - 팀장 포함 정원과 공식 인원
 * 4. docs/development/frontend.md - 「화면과 상태」 작성 폼은 React Hook Form + Zod
 * 5. docs/design/assets/create-team-320.png - 실제 화면
 */

import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router';
import { z } from 'zod';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { contests, roleOptions } from '@/features/demo/data';
import {
  isContestOpen,
  memberLimitLabel,
  deadlineLabel,
} from '@/features/demo/contest-state';
import { ContestPicker } from '@/features/teams/ContestPicker';
import { ActionLink, BackLink, PageIntro } from '@/components/common/CommonUi';
import { useDemo } from '@/features/demo/demo-context';
import { profileTextLength } from '@/features/demo/profile-fields';
import {
  createTeamIssue,
  dateValue,
  referenceDate,
} from '@/features/demo/team-state';

const teamSchema = z
  .object({
    contestId: z.string().min(1, '참여할 공모전을 선택해 주세요.'),
    name: z
      .string()
      .trim()
      .refine(
        (value) => profileTextLength(value) >= 2,
        '팀 이름을 2자 이상 입력해 주세요.',
      )
      .refine(
        (value) => profileTextLength(value) <= 40,
        '팀 이름은 40자까지 입력할 수 있어요.',
      ),
    summary: z
      .string()
      .trim()
      .refine(
        (value) => profileTextLength(value) >= 10,
        '팀 소개와 목표를 10자 이상 적어 주세요.',
      )
      .refine(
        (value) => profileTextLength(value) <= 1000,
        '팀 소개는 1,000자까지 입력할 수 있어요.',
      ),
    roles: z.array(z.string()),
    capacity: z
      .number({ invalid_type_error: '총 정원을 숫자로 입력해 주세요.' })
      .int()
      .min(1, '총 정원은 1명 이상이어야 해요.'),
    recruitmentDeadline: z.string().min(1, '모집 마감을 설정해 주세요.'),
  })
  .superRefine((values, context) => {
    if (
      values.capacity >= 2 &&
      (values.roles.length < 1 || values.roles.length > 6)
    )
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['roles'],
        message: '모집할 역할을 1~6개 선택해 주세요.',
      });
  });
type Fields = z.infer<typeof teamSchema>;

function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? (
    <p id={id} className="preview-error" role="alert">
      {message}
    </p>
  ) : null;
}

// [출처 2, 3, 4, 5] 공모전 선택·정원·역할 검증 폼
export function CreateTeamPage() {
  const { signedIn, createTeam, teams } = useDemo();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const [submitError, setSubmitError] = useState('');
  const contestId = search.get('contestId') ?? search.get('contest') ?? '';
  const initialContest = contests.find((item) => item.id === contestId);
  const {
    register,
    setValue,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Fields>({
    resolver: zodResolver(teamSchema),
    defaultValues: {
      contestId: contests.some((contest) => contest.id === contestId)
        ? contestId
        : '',
      name: '',
      summary: '',
      roles: [],
      capacity:
        initialContest?.memberLimit === 'range' &&
        initialContest.minMembers === initialContest.maxMembers
          ? initialContest.minMembers
          : undefined,
      recruitmentDeadline: '',
    },
  });
  const selectedId = useWatch({ control, name: 'contestId' });
  const selected = contests.find((contest) => contest.id === selectedId);
  const capacity = useWatch({ control, name: 'capacity' });
  const fixedCapacity =
    selected?.memberLimit === 'range' &&
    selected.minMembers === selected.maxMembers;
  const returnTo = `/teams/new${search.size ? `?${search.toString()}` : ''}`;
  if (!signedIn)
    return (
      <div className="preview-detail preview-stack">
        <PageIntro
          title="새로운 팀 만들기"
          description="로그인하고 함께할 팀원을 만나보세요."
        />
        <ActionLink to={`/login?returnTo=${encodeURIComponent(returnTo)}`}>
          로그인하기
        </ActionLink>
      </div>
    );
  return (
    <div className="preview-detail preview-stack preview-account-page">
      <BackLink to="/explore?tab=teams">팀 탐색으로</BackLink>
      <PageIntro
        title="팀 만들기"
        description="어떤 도전을 함께할지 알려주세요."
      />
      <form
        className="preview-panel preview-form"
        noValidate
        onSubmit={handleSubmit((values) => {
          const team = {
            ...values,
            roles: values.capacity === 1 ? [] : values.roles,
            interests: [...(selected?.interests ?? [])],
          };
          const issue = createTeamIssue(team, teams);
          if (issue) {
            setSubmitError(issue);
            return;
          }
          const id = createTeam(team);
          if (!id) {
            setSubmitError(
              '팀을 만들지 못했어요. 현재 소속과 모집 조건을 확인해 주세요.',
            );
            return;
          }
          navigate(`/teams/${id}?view=space`);
        })}
      >
        <div className="preview-field">
          <Label htmlFor="team-contest">참여 공모전</Label>
          <Controller
            control={control}
            name="contestId"
            render={({ field }) => (
              <ContestPicker
                id="team-contest"
                contests={contests.filter((contest) => isContestOpen(contest))}
                value={field.value}
                onChange={(id) => {
                  // [출처 2] 정원·역할은 공모전의 공식 인원에 따라 달라지므로 공모전이 실제로 바뀔 때만 초기화합니다.
                  // 같은 공모전을 다시 고르면 작성 중인 값을 유지합니다(PR #121 리뷰).
                  const changed = id !== field.value;
                  field.onChange(id);
                  if (!changed) return;
                  const contest = contests.find((item) => item.id === id);
                  setValue(
                    'capacity',
                    contest?.memberLimit === 'range' &&
                      contest.minMembers === contest.maxMembers
                      ? contest.minMembers!
                      : Number.NaN,
                  );
                  setValue('roles', []);
                }}
                onBlur={field.onBlur}
                ref={field.ref}
                invalid={!!errors.contestId}
                describedBy={`team-contest-help${errors.contestId ? ' team-contest-error' : ''}`}
              />
            )}
          />
          <p id="team-contest-help" className="preview-muted">
            공모전 이름이나 주최자로 검색할 수 있어요.
          </p>
          <FieldError
            id="team-contest-error"
            message={errors.contestId?.message}
          />
        </div>
        <div className="preview-field">
          <Label htmlFor="team-name">팀 이름</Label>
          <Input
            id="team-name"
            {...register('name')}
            placeholder="우리 팀을 소개할 이름"
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? 'team-name-error' : undefined}
          />
          <FieldError id="team-name-error" message={errors.name?.message} />
        </div>
        <div className="preview-field">
          <Label htmlFor="team-summary">팀 소개와 목표</Label>
          <Textarea
            id="team-summary"
            rows={4}
            {...register('summary')}
            placeholder="어떤 아이디어를 누구와 함께 만들고 싶나요?"
            aria-invalid={!!errors.summary}
            aria-describedby={errors.summary ? 'team-summary-error' : undefined}
          />
          <FieldError
            id="team-summary-error"
            message={errors.summary?.message}
          />
        </div>
        <div className="preview-field">
          <Label htmlFor="team-capacity">팀장 포함 총 정원</Label>
          <Input
            id="team-capacity"
            type="number"
            min={selected?.minMembers ?? 1}
            max={
              selected?.memberLimit === 'range'
                ? selected.maxMembers
                : undefined
            }
            readOnly={fixedCapacity}
            placeholder="총 정원을 입력해 주세요"
            {...register('capacity', { valueAsNumber: true })}
            aria-invalid={!!errors.capacity}
            aria-describedby="team-capacity-help team-capacity-error"
          />
          <p id="team-capacity-help" className="preview-muted">
            {selected
              ? `공식 참가 인원: ${memberLimitLabel(selected)}. ${fixedCapacity ? '공식 인원으로 고정돼요.' : '팀장을 포함한 목표 정원을 입력해 주세요.'}`
              : '공모전을 선택한 뒤 목표 정원을 입력해 주세요.'}
          </p>
          <FieldError
            id="team-capacity-error"
            message={errors.capacity?.message}
          />
        </div>
        {capacity >= 2 && (
          <fieldset className="preview-field">
            <legend>모집할 역할</legend>
            <p className="preview-muted">
              팀에서 필요한 역할을 알려주세요. 다른 역할의 지원자도 지원할 수
              있어요.
            </p>
            <Controller
              control={control}
              name="roles"
              render={({ field }) => (
                <div className="preview-choice-grid">
                  {roleOptions.map((role) => (
                    <Label className="preview-choice" key={role}>
                      <Checkbox
                        checked={field.value.includes(role)}
                        onCheckedChange={(checked) =>
                          field.onChange(
                            checked
                              ? [...field.value, role]
                              : field.value.filter((item) => item !== role),
                          )
                        }
                      />
                      <span>{role}</span>
                    </Label>
                  ))}
                </div>
              )}
            />
            <FieldError id="team-roles-error" message={errors.roles?.message} />
          </fieldset>
        )}
        <div className="preview-field">
          <Label htmlFor="team-deadline">팀 모집 마감</Label>
          <Input
            id="team-deadline"
            type="date"
            min={referenceDate}
            max={
              selected ? dateValue(selected.deadline).slice(0, 10) : undefined
            }
            {...register('recruitmentDeadline')}
            aria-invalid={!!errors.recruitmentDeadline}
            aria-describedby="team-deadline-help team-deadline-error"
          />
          <p id="team-deadline-help" className="preview-muted">
            {selected
              ? `공모전 마감일 ${deadlineLabel(selected)}까지 설정할 수 있어요. 해당 날짜 끝까지 모집하며 공모전이 먼저 마감되면 함께 마감돼요.`
              : '공모전을 선택한 뒤 모집 마감일을 정해 주세요.'}
          </p>
          <FieldError
            id="team-deadline-error"
            message={errors.recruitmentDeadline?.message}
          />
        </div>
        {selected && (
          <div className="preview-field">
            <Label>관심 분야</Label>
            <p>{selected.interests.join(' · ')}</p>
            <p className="preview-muted">공모전의 관심 분야를 사용해요.</p>
          </div>
        )}
        {submitError && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{submitError}</AlertDescription>
          </Alert>
        )}
        <Button
          type="submit"
          className="preview-button"
          disabled={isSubmitting}
        >
          <Plus size={18} aria-hidden="true" />
          {isSubmitting ? '팀 만드는 중' : '팀 만들기'}
        </Button>
      </form>
    </div>
  );
}
