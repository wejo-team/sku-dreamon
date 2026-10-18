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
import { contests, interestOptions, previewPath, roleOptions } from './data';
import { ContestPicker } from './ContestPicker';
import { ActionLink, BackLink, PageIntro } from './PreviewUi';
import { usePreview } from './preview-context';
import { createTeamIssue, dateValue, referenceDate } from './team-state';

const teamSchema = z.object({
  contestId: z.string().min(1, '참여할 공모전을 선택해 주세요.'),
  name: z
    .string()
    .trim()
    .min(2, '팀 이름을 2자 이상 입력해 주세요.')
    .max(40, '팀 이름은 40자까지 입력할 수 있어요.'),
  summary: z
    .string()
    .trim()
    .min(10, '팀 소개와 목표를 10자 이상 적어 주세요.')
    .max(1000, '팀 소개는 1,000자까지 입력할 수 있어요.'),
  roles: z.array(z.string()).min(1, '모집할 역할을 선택해 주세요.'),
  interests: z.array(z.string()),
  capacity: z
    .number({ invalid_type_error: '총 정원을 숫자로 입력해 주세요.' })
    .int()
    .min(1, '총 정원은 1명 이상이어야 해요.'),
  recruitmentDeadline: z.string().min(1, '모집 마감을 설정해 주세요.'),
});
type Fields = z.infer<typeof teamSchema>;

function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? (
    <p id={id} className="preview-error" role="alert">
      {message}
    </p>
  ) : null;
}

export function CreateTeamPage() {
  const { signedIn, createTeam, teams } = usePreview();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const [submitError, setSubmitError] = useState('');
  const contestId = search.get('contestId') ?? search.get('contest') ?? '';
  const {
    register,
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
      interests: [],
      capacity: 4,
      recruitmentDeadline: '',
    },
  });
  const selectedId = useWatch({ control, name: 'contestId' });
  const selected = contests.find((contest) => contest.id === selectedId);
  const returnTo = `${previewPath('/teams/new')}${search.size ? `?${search.toString()}` : ''}`;
  if (!signedIn)
    return (
      <div className="preview-detail preview-stack">
        <PageIntro
          title="새로운 팀 만들기"
          description="로그인하고 함께할 팀원을 만나보세요."
        />
        <ActionLink
          to={`${previewPath('/login')}?returnTo=${encodeURIComponent(returnTo)}`}
        >
          로그인하기
        </ActionLink>
      </div>
    );
  return (
    <div className="preview-detail preview-stack preview-account-page">
      <BackLink to={previewPath('/explore?tab=teams')}>팀 탐색으로</BackLink>
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
            kind:
              selected?.participation === 'individual'
                ? ('preparation' as const)
                : ('entry' as const),
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
          navigate(previewPath(`/teams/${id}?view=space`));
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
                contests={contests.filter(
                  (contest) => contest.status !== 'closed',
                )}
                value={field.value}
                onChange={field.onChange}
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
          {selected?.participation === 'individual' && (
            <Alert role="note">
              <AlertDescription>
                개인 참가 공모전이에요. 함께 준비하는 팀을 만들고, 출전과 제출은
                각자 진행해요.
              </AlertDescription>
            </Alert>
          )}
        </div>
        <div className="preview-field">
          <Label htmlFor="team-name">팀 이름</Label>
          <Input
            id="team-name"
            {...register('name')}
            maxLength={40}
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
            maxLength={1000}
            placeholder="어떤 아이디어를 누구와 함께 만들고 싶나요?"
            aria-invalid={!!errors.summary}
            aria-describedby={errors.summary ? 'team-summary-error' : undefined}
          />
          <FieldError
            id="team-summary-error"
            message={errors.summary?.message}
          />
        </div>
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
        <div className="preview-field">
          <Label htmlFor="team-capacity">팀장 포함 총 정원</Label>
          <Input
            id="team-capacity"
            type="number"
            min={
              selected?.participation === 'individual'
                ? 1
                : (selected?.minMembers ?? 1)
            }
            max={
              selected?.participation === 'individual'
                ? undefined
                : selected?.maxMembers
            }
            {...register('capacity', { valueAsNumber: true })}
            aria-invalid={!!errors.capacity}
            aria-describedby="team-capacity-help team-capacity-error"
          />
          <p id="team-capacity-help" className="preview-muted">
            팀장인 나를 포함한 전체 인원이에요.
            {selected &&
            selected.participation !== 'individual' &&
            selected.minMembers != null &&
            selected.maxMembers != null
              ? ` 공식 참가 인원: ${selected.minMembers}~${selected.maxMembers}명.`
              : ''}
          </p>
          <FieldError
            id="team-capacity-error"
            message={errors.capacity?.message}
          />
        </div>
        <div className="preview-field">
          <Label htmlFor="team-deadline">팀 모집 마감</Label>
          <Input
            id="team-deadline"
            type="date"
            min={referenceDate}
            max={selected ? dateValue(selected.deadline) : undefined}
            {...register('recruitmentDeadline')}
            aria-invalid={!!errors.recruitmentDeadline}
            aria-describedby="team-deadline-help team-deadline-error"
          />
          <p id="team-deadline-help" className="preview-muted">
            {selected
              ? `공모전 마감일 ${selected.deadline}까지 설정할 수 있어요.`
              : '공모전을 선택한 뒤 모집 마감일을 정해 주세요.'}
          </p>
          <FieldError
            id="team-deadline-error"
            message={errors.recruitmentDeadline?.message}
          />
        </div>
        <fieldset className="preview-field">
          <legend>
            팀 관심 분야 <span className="preview-muted">선택</span>
          </legend>
          <Controller
            control={control}
            name="interests"
            render={({ field }) => (
              <div className="preview-choice-grid">
                {interestOptions.map((interest) => (
                  <Label className="preview-choice" key={interest}>
                    <Checkbox
                      checked={field.value.includes(interest)}
                      onCheckedChange={(checked) =>
                        field.onChange(
                          checked
                            ? [...field.value, interest]
                            : field.value.filter((item) => item !== interest),
                        )
                      }
                    />
                    <span>{interest}</span>
                  </Label>
                ))}
              </div>
            )}
          />
        </fieldset>
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
