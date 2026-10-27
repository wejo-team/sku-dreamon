/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/CreateTeamPage.tsx - 팀 만들기 원본
 * 2. docs/design/screens.md - 팀명 2~40자·소개 10~1,000자·역할 1~6개, 공식 인원 범위, 정원 1명은 역할 생략
 * 3. docs/specs/team-recruitment.md#official-capacity - 팀장 포함 정원과 공식 인원
 * 4. docs/development/frontend.md - 「화면과 상태」 작성 폼은 React Hook Form + Zod, 로딩·오류 상태 제공
 * 5. docs/design/assets/create-team-320.png - 실제 화면
 * 6. docs/api/teams.md#team-create, #transitions - POST /teams(requestId 재전송), 409 CONTEST_NOT_OPEN·
 *    CAPACITY_OUT_OF_RANGE·MEMBERSHIP_CONFLICT·INVALID_CATALOG_SELECTION·PROFILE_REQUIRED
 * 7. docs/api/contests.md#endpoints - 접수 중 공고 검색(registrationStatus=open), 선택한 공고의 정원·마감 원문
 * 8. docs/api/conventions.md#types - 경로 Id는 UUID 문자열(형식이 다르면 422)
 */

import { useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery, useQueryClient } from '@tanstack/react-query';
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
import type { ContestDetail } from '@/features/contests/api';
import { contestQueryOptions } from '@/features/contests/queries';
import { useLabels } from '@/features/catalogs/queries';
import { koreanDate } from '@/features/catalogs/labels';
import { useSession } from '@/features/auth/queries';
import { useCreateTeam } from '@/features/teams/queries';
import {
  capacityBounds,
  memberLimitLabel,
  deadlineLabel,
} from '@/features/demo/contest-state';
import { ContestPicker } from '@/features/teams/ContestPicker';
import {
  ActionLink,
  BackLink,
  EmptyState,
  PageIntro,
} from '@/components/common/CommonUi';
import { profileTextLength } from '@/features/demo/profile-fields';
import { ApiError } from '@/lib/api';
import { Id } from '@/lib/api-contract';
import { appNow } from '@/lib/clock';

// [출처 3] 공식 인원이 고정(range의 최소=최대)이면 그 값을 정원으로 사용
const fixedCapacityOf = (contest: ContestDetail | undefined) => {
  if (!contest || contest.capacity.kind !== 'range') return undefined;
  const { min, max } = capacityBounds(contest.capacity);
  return min !== null && min === max ? min : undefined;
};

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
    introduction: z
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
    roleCodes: z.array(z.string()),
    capacity: z
      .number({ error: '총 정원을 숫자로 입력해 주세요.' })
      .int()
      .min(1, '총 정원은 1명 이상이어야 해요.'),
    recruitmentDeadline: z.string().min(1, '모집 마감을 설정해 주세요.'),
  })
  .superRefine((values, context) => {
    if (
      values.capacity >= 2 &&
      (values.roleCodes.length < 1 || values.roleCodes.length > 6)
    )
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['roleCodes'],
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

// [출처 6] 서버 오류 코드 → 화면 문구
function createErrorMessage(
  error: unknown,
  contest: ContestDetail | undefined,
) {
  const code = error instanceof ApiError ? error.code : null;
  switch (code) {
    case 'MEMBERSHIP_CONFLICT':
      return '이미 이 공모전의 팀에 소속되어 있어요. 내 팀에서 확인해 주세요.';
    case 'CONTEST_NOT_OPEN':
      return '접수 중인 공모전을 선택해 주세요.';
    case 'CAPACITY_OUT_OF_RANGE':
      return contest
        ? `공식 참가 인원 ${memberLimitLabel(contest.capacity)}에 맞춰 총 정원을 입력해 주세요.`
        : '공식 참가 인원을 확인한 뒤 팀을 만들 수 있어요.';
    case 'PROFILE_REQUIRED':
      return '필수 프로필을 먼저 작성해 주세요.';
    case 'INVALID_CATALOG_SELECTION':
      return '모집할 역할을 목록에서 다시 선택해 주세요.';
    default:
      return '팀을 만들지 못했어요. 현재 소속과 모집 조건을 확인해 주세요.';
  }
}

// [출처 2, 3, 4, 5, 7] 로그인 확인 → 접수 중 공고 목록·URL로 지정한 공고 상세를 받은 뒤 폼 표시
export function CreateTeamPage() {
  const session = useSession();
  const [search] = useSearchParams();
  const contestId = search.get('contestId') ?? search.get('contest') ?? '';
  // [출처 7, 8] URL로 지정한 공모전은 목록 페이지와 무관하게 상세로 확인하고, 접수 중일 때만 미리 선택합니다.
  const initialId = Id.safeParse(contestId).success ? contestId : '';
  const initialContest = useQuery({
    ...contestQueryOptions(initialId),
    enabled: session.signedIn && !!initialId,
  });
  const initialMissing =
    initialContest.error instanceof ApiError &&
    initialContest.error.status === 404;
  const returnTo = `/teams/new${search.size ? `?${search.toString()}` : ''}`;
  if (session.isPending) return <LoadingState />;
  if (!session.signedIn)
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
  if (initialContest.isError && !initialMissing)
    return (
      <div className="preview-detail preview-stack">
        <EmptyState
          title="공모전 정보를 불러오지 못했어요"
          description="잠시 후 다시 시도해 주세요."
        >
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void initialContest.refetch();
            }}
          >
            다시 시도
          </Button>
        </EmptyState>
      </div>
    );
  if (initialId && initialContest.isPending) return <LoadingState />;
  const initial = initialContest.data;
  return (
    <CreateTeamForm
      initialContest={
        initial?.registrationStatus === 'open' && !initialMissing
          ? initial
          : undefined
      }
    />
  );
}

function LoadingState() {
  return (
    <div className="preview-detail preview-stack" role="status">
      <p className="preview-muted">불러오는 중…</p>
    </div>
  );
}

function CreateTeamForm({
  initialContest,
}: {
  initialContest: ContestDetail | undefined;
}) {
  const { fieldLabel, roleOptions } = useLabels();
  const navigate = useNavigate();
  const client = useQueryClient();
  const createTeam = useCreateTeam();
  const [submitError, setSubmitError] = useState('');
  // [출처 6] 같은 생성 시도의 재전송은 같은 requestId를 씁니다. 성공하면 새 시도로 바꿉니다.
  const requestId = useRef(crypto.randomUUID());
  const {
    register,
    setValue,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Fields>({
    resolver: zodResolver(teamSchema),
    defaultValues: {
      contestId: initialContest?.id ?? '',
      name: '',
      introduction: '',
      roleCodes: [],
      capacity: fixedCapacityOf(initialContest),
      recruitmentDeadline: '',
    },
  });
  const selectedId = useWatch({ control, name: 'contestId' });
  // [출처 7] 선택한 공고의 정원·마감 원문(상세)
  const selectedQuery = useQuery({
    ...contestQueryOptions(selectedId),
    enabled: !!selectedId,
  });
  const selected = selectedQuery.data;
  const capacity = useWatch({ control, name: 'capacity' });
  const fixedCapacity = fixedCapacityOf(selected) !== undefined;
  const bounds = selected ? capacityBounds(selected.capacity) : null;
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
        // requestId ref는 제출 이벤트 안에서만 읽습니다.
        onSubmit={(event) =>
          void handleSubmit(async (values) => {
            setSubmitError('');
            // [출처 3] 분야는 공모전에서 상속하므로 입력하지 않음. 정원 1명은 역할 없음
            const roleCodes = values.capacity === 1 ? [] : values.roleCodes;
            // 서버도 같은 조건을 검사하지만(409 CAPACITY_OUT_OF_RANGE) 요청 전에 먼저 안내합니다.
            if (
              selected &&
              bounds &&
              ((bounds.min !== null && values.capacity < bounds.min) ||
                (bounds.max !== null && values.capacity > bounds.max))
            ) {
              setSubmitError(
                `공식 참가 인원 ${memberLimitLabel(selected.capacity)}에 맞춰 총 정원을 입력해 주세요.`,
              );
              return;
            }
            try {
              const { team } = await createTeam.mutateAsync({
                requestId: requestId.current,
                contestId: values.contestId,
                name: values.name,
                introduction: values.introduction,
                capacity: String(values.capacity),
                roleCodes,
                // 화면은 날짜만 입력. 시각·시간대가 없으면 한국시간 날짜 끝으로 해석(docs/api/teams.md#deadline-input)
                recruitmentDeadline: { date: values.recruitmentDeadline },
              });
              requestId.current = crypto.randomUUID();
              navigate(`/teams/${team.id}?view=space`);
            } catch (error) {
              setSubmitError(createErrorMessage(error, selected));
            }
          })(event)
        }
      >
        <div className="preview-field">
          <Label htmlFor="team-contest">참여 공모전</Label>
          <Controller
            control={control}
            name="contestId"
            render={({ field }) => (
              <ContestPicker
                id="team-contest"
                selected={selected}
                value={field.value}
                onChange={(id) => {
                  // [출처 2] 정원·역할은 공모전의 공식 인원에 따라 달라지므로 공모전이 실제로 바뀔 때만 초기화합니다.
                  // 같은 공모전을 다시 고르면 작성 중인 값을 유지합니다(PR #121 리뷰).
                  const changed = id !== field.value;
                  field.onChange(id);
                  if (!changed) return;
                  setValue('capacity', Number.NaN);
                  setValue('roleCodes', []);
                  // [출처 7] 고정 정원 공모전이면 상세를 받아 정원을 채웁니다.
                  void client
                    .fetchQuery(contestQueryOptions(id))
                    .then((contest) => {
                      const fixed = fixedCapacityOf(contest);
                      if (fixed !== undefined) setValue('capacity', fixed);
                    })
                    .catch(() => undefined);
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
            {...register('introduction')}
            placeholder="어떤 아이디어를 누구와 함께 만들고 싶나요?"
            aria-invalid={!!errors.introduction}
            aria-describedby={
              errors.introduction ? 'team-summary-error' : undefined
            }
          />
          <FieldError
            id="team-summary-error"
            message={errors.introduction?.message}
          />
        </div>
        <div className="preview-field">
          <Label htmlFor="team-capacity">팀장 포함 총 정원</Label>
          <Input
            id="team-capacity"
            type="number"
            min={bounds?.min ?? 1}
            max={bounds?.max ?? undefined}
            readOnly={fixedCapacity}
            placeholder="총 정원을 입력해 주세요"
            {...register('capacity', { valueAsNumber: true })}
            aria-invalid={!!errors.capacity}
            aria-describedby="team-capacity-help team-capacity-error"
          />
          <p id="team-capacity-help" className="preview-muted">
            {selected
              ? `공식 참가 인원: ${memberLimitLabel(selected.capacity)}. ${fixedCapacity ? '공식 인원으로 고정돼요.' : '팀장을 포함한 목표 정원을 입력해 주세요.'}`
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
              name="roleCodes"
              render={({ field }) => (
                <div className="preview-choice-grid">
                  {roleOptions.map((role) => (
                    <Label className="preview-choice" key={role.code}>
                      <Checkbox
                        checked={field.value.includes(role.code)}
                        onCheckedChange={(checked) =>
                          field.onChange(
                            checked
                              ? [...field.value, role.code]
                              : field.value.filter(
                                  (item) => item !== role.code,
                                ),
                          )
                        }
                      />
                      <span>{role.displayName}</span>
                    </Label>
                  ))}
                </div>
              )}
            />
            <FieldError
              id="team-roles-error"
              message={errors.roleCodes?.message}
            />
          </fieldset>
        )}
        <div className="preview-field">
          <Label htmlFor="team-deadline">팀 모집 마감</Label>
          <Input
            id="team-deadline"
            type="date"
            min={koreanDate(new Date(appNow()).toISOString())}
            max={selected?.timing.closing.sourceDate}
            {...register('recruitmentDeadline')}
            aria-invalid={!!errors.recruitmentDeadline}
            aria-describedby="team-deadline-help team-deadline-error"
          />
          <p id="team-deadline-help" className="preview-muted">
            {selected
              ? `공모전 마감일 ${deadlineLabel(selected.timing.closing)}까지 설정할 수 있어요. 해당 날짜 끝까지 모집하며 공모전이 먼저 마감되면 함께 마감돼요.`
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
            <p>{selected.fieldCodes.map(fieldLabel).join(' · ')}</p>
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
