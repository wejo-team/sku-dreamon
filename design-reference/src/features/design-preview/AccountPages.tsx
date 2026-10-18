import { useId, useState, type ChangeEvent } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowRight, Check, Eye, EyeOff, UserRound } from 'lucide-react';
import {
  Controller,
  useForm,
  useWatch,
  type UseFormRegister,
} from 'react-hook-form';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { z } from 'zod';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from '@/components/ui/drawer';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  NativeSelect,
  NativeSelectOption,
} from '@/components/ui/native-select';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  getPublicProfile,
  interestOptions,
  previewBase,
  previewPath,
  roleOptions,
  type Profile,
} from './data';
import { usePreview } from './preview-context';
import { Avatar, BackLink, Badge, PageIntro } from './PreviewUi';
import { AcademicFields, ExperienceFields, SkillFields } from './ProfileFields';
import './login.css';
import './profile-fields.css';

const demoId = 'dreamon-demo';
const demoPassword = 'dreamon-demo';
const days = ['월', '화', '수', '목', '금', '토', '일'];
const timeSlots = [
  '00:00~03:00',
  '03:00~06:00',
  '06:00~09:00',
  '09:00~12:00',
  '12:00~15:00',
  '15:00~18:00',
  '18:00~21:00',
  '21:00~24:00',
];

function isWebUrl(value: string) {
  try {
    return ['http:', 'https:'].includes(new URL(value).protocol);
  } catch {
    return false;
  }
}

const requiredProfileSchema = z.object({
  name: z.string().trim().min(1, '이름을 입력해 주세요.'),
  roles: z.array(z.string()).min(1, '희망 역할을 하나 이상 선택해 주세요.'),
  interests: z.array(z.string()).min(1, '관심 분야를 하나 이상 선택해 주세요.'),
});
const profileSchema = requiredProfileSchema.extend({
  intro: z.string().trim(),
  experience: z.string().trim(),
  experienceState: z.enum(['unspecified', 'none', 'provided']),
  academicStatus: z.string().optional(),
  grade: z.string().optional(),
  college: z.string().optional(),
  department: z.string().optional(),
  major: z.string().optional(),
  skills: z.array(z.string()),
  interestOther: z.string().trim(),
  skillOther: z.string().trim(),
  portfolioTitle: z.string().trim(),
  visibility: z.object({
    discoverable: z.boolean(),
    interests: z.boolean(),
    experience: z.boolean(),
    intro: z.boolean(),
  }),
  portfolio: z
    .string()
    .trim()
    .refine(
      (value) => !value || isWebUrl(value),
      'http:// 또는 https://로 시작하는 링크를 입력해 주세요.',
    ),
  portfolioConsent: z.boolean(),
  availability: z.string(),
});
const accountSchema = z.object({
  username: z.string().trim().min(1, '아이디를 입력해 주세요.'),
  password: z.string().min(1, '비밀번호를 입력해 주세요.'),
});
const signupSchema = requiredProfileSchema.merge(accountSchema);
type SignupValues = z.infer<typeof signupSchema>;

function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? (
    <p id={id} className="preview-error" role="alert">
      {message}
    </p>
  ) : null;
}

function ChoiceField({
  label,
  options,
  value,
  onChange,
  error,
  id,
}: {
  label: string;
  options: string[];
  value: string[];
  onChange: (value: string[]) => void;
  error?: string;
  id: string;
}) {
  return (
    <fieldset
      className="preview-field"
      aria-describedby={error ? `${id}-error` : undefined}
    >
      <legend>
        {label} <span className="preview-muted">(필수 · 복수 선택)</span>
      </legend>
      <div className="preview-row">
        {options.map((option) => (
          <Label
            key={option}
            htmlFor={`${id}-${option}`}
            className="preview-choice"
          >
            <Checkbox
              id={`${id}-${option}`}
              checked={value.includes(option)}
              aria-invalid={!!error}
              onCheckedChange={(checked) =>
                onChange(
                  checked === true
                    ? [...value, option]
                    : value.filter((item) => item !== option),
                )
              }
            />
            {option}
          </Label>
        ))}
      </div>
      <FieldError id={`${id}-error`} message={error} />
    </fieldset>
  );
}

function AvailabilityField({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const [day, setDay] = useState('월');
  const selected = draft
    .split('; ')
    .filter((item) =>
      days.some((d) => timeSlots.some((slot) => item === `${d} ${slot}`)),
    );
  function toggle(slot: string, checked: boolean) {
    const key = `${day} ${slot}`;
    const next = checked
      ? [...selected, key]
      : selected.filter((item) => item !== key);
    setDraft(
      days
        .flatMap((d) => timeSlots.map((time) => `${d} ${time}`))
        .filter((item) => next.includes(item))
        .join('; '),
    );
  }
  return (
    <fieldset
      className="preview-field preview-availability-summary"
      aria-describedby="availability-summary"
    >
      <legend>
        활동 가능 시간 <span className="preview-muted">(선택)</span>
      </legend>
      <p id="availability-summary" className="preview-muted" aria-live="polite">
        {value || '미설정'}
      </p>
      <Drawer
        open={open}
        onOpenChange={(nextOpen) => {
          if (nextOpen) {
            setDraft(value);
            setDay('월');
          }
          setOpen(nextOpen);
        }}
        shouldScaleBackground={false}
        autoFocus
      >
        <DrawerTrigger asChild>
          <Button type="button" variant="outline" className="preview-button">
            활동 시간 설정
          </Button>
        </DrawerTrigger>
        <DrawerContent className="dreamon-preview preview-drawer">
          <DrawerHeader>
            <DrawerTitle>활동 가능 시간</DrawerTitle>
            <DrawerDescription>
              개인 일정은 공개되지 않아요. 시간을 선택해 적용한 뒤 프로필을
              저장해 주세요.
            </DrawerDescription>
          </DrawerHeader>
          <div className="preview-drawer-body">
            <div className="preview-field">
              <Label htmlFor="availability-day">요일</Label>
              <NativeSelect
                id="availability-day"
                value={day}
                onChange={(event) => setDay(event.target.value)}
              >
                {days.map((item) => (
                  <NativeSelectOption value={item} key={item}>
                    {item}요일
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            <fieldset className="preview-field">
              <legend>가능한 시간 (복수 선택)</legend>
              <div className="preview-row">
                {timeSlots.map((slot) => (
                  <Label
                    className="preview-choice"
                    key={slot}
                    htmlFor={`availability-${slot}`}
                  >
                    <Checkbox
                      type="button"
                      id={`availability-${slot}`}
                      checked={selected.includes(`${day} ${slot}`)}
                      onCheckedChange={(checked) =>
                        toggle(slot, checked === true)
                      }
                      aria-label={`${day}요일 ${slot}`}
                    />
                    {slot}
                  </Label>
                ))}
              </div>
            </fieldset>
            <p className="preview-muted" aria-live="polite">
              선택한 시간: {draft || '미설정'}
            </p>
            {draft && (
              <Button
                type="button"
                variant="outline"
                className="preview-button"
                onClick={() => setDraft('')}
              >
                시간 선택 지우기
              </Button>
            )}
          </div>
          <DrawerFooter>
            <Button
              type="button"
              className="preview-button"
              onClick={() => {
                onChange(draft);
                setOpen(false);
              }}
            >
              선택 적용
            </Button>
            <DrawerClose asChild>
              <Button
                type="button"
                variant="outline"
                className="preview-button"
              >
                취소
              </Button>
            </DrawerClose>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>
    </fieldset>
  );
}

function LoginGate({ returnTo, title }: { returnTo: string; title: string }) {
  return (
    <div className="preview-detail preview-stack">
      <BackLink />
      <PageIntro title={title} />
      <div className="preview-panel preview-stack">
        <UserRound size={28} aria-hidden="true" />
        <p>로그인하고 계속해 주세요.</p>
        <Button asChild className="preview-button">
          <Link
            to={`${previewPath('/login')}?returnTo=${encodeURIComponent(returnTo)}`}
          >
            로그인
          </Link>
        </Button>
      </div>
    </div>
  );
}

function VisibilitySwitch({
  label,
  checked,
  onChange,
  disabled = false,
  describedBy,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  describedBy?: string;
}) {
  const id = useId();
  return (
    <Label
      htmlFor={id}
      className="dreamon-privacy-switch"
      data-disabled={disabled}
    >
      <span>{label}</span>
      <span className="dreamon-privacy-state" aria-hidden="true">
        {checked ? '공개' : '비공개'}
      </span>
      <Switch
        id={id}
        className="preview-control-switch"
        aria-label={label}
        aria-describedby={describedBy}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
      />
    </Label>
  );
}

function ProfileEditor({
  onDone,
  onCancel,
}: {
  onDone: () => void;
  onCancel: () => void;
}) {
  const { profile, saveProfile } = usePreview();
  const {
    register,
    control,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<Profile>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      ...profile,
      portfolioConsent: isWebUrl(profile.portfolio) && profile.portfolioConsent,
    },
  });
  const portfolio = useWatch({ control, name: 'portfolio' });
  const validPortfolio = isWebUrl(portfolio.trim());
  const interests = useWatch({ control, name: 'interests' });
  return (
    <form
      className="preview-panel preview-form"
      noValidate
      onSubmit={handleSubmit((values) => {
        saveProfile({
          ...values,
          interestOther: values.interests.includes('기타')
            ? values.interestOther
            : '',
          skillOther: values.skills.includes('기타') ? values.skillOther : '',
          experienceState:
            values.experienceState === 'provided' && !values.experience
              ? 'unspecified'
              : values.experienceState,
          experience:
            values.experienceState === 'provided' ? values.experience : '',
          portfolioTitle: values.portfolio ? values.portfolioTitle : '',
          portfolioConsent:
            isWebUrl(values.portfolio) && values.portfolioConsent,
        });
        onDone();
      })}
    >
      <fieldset className="dreamon-privacy-settings">
        <legend>공개 설정</legend>
        <p id="profile-save-help" className="preview-muted">
          변경사항은 아래 저장 버튼을 눌러야 적용돼요.
        </p>
        <Controller
          control={control}
          name="visibility.discoverable"
          render={({ field }) => (
            <VisibilitySwitch
              label="사람 탐색에 공개"
              checked={field.value}
              onChange={field.onChange}
              describedBy="profile-visibility-help profile-save-help"
            />
          )}
        />
        <p id="profile-visibility-help" className="preview-muted">
          사람 탐색 공개는 목록에 나타날지 정하는 설정이에요. 아래 항목별 공개
          설정은 지원한 팀의 팀장에게도 적용돼요.
        </p>
        <div className="dreamon-privacy-fields">
          {(
            [
              ['interests', '관심 분야 공개'],
              ['experience', '경험 공개'],
              ['intro', '자기소개 공개'],
            ] as const
          ).map(([key, label]) => (
            <Controller
              key={key}
              control={control}
              name={`visibility.${key}`}
              render={({ field }) => (
                <VisibilitySwitch
                  label={label}
                  checked={field.value}
                  onChange={field.onChange}
                  describedBy="profile-visibility-help profile-save-help"
                />
              )}
            />
          ))}
        </div>
      </fieldset>
      <Separator className="preview-form-separator" />
      <section
        className="preview-form-section"
        aria-labelledby="profile-basic-heading"
      >
        <h2 id="profile-basic-heading" className="preview-section-title">
          기본 프로필
        </h2>
        <div className="preview-field">
          <Label htmlFor="profile-name">이름 (필수)</Label>
          <Input
            id="profile-name"
            {...register('name')}
            autoComplete="off"
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? 'profile-name-error' : undefined}
          />
          <FieldError id="profile-name-error" message={errors.name?.message} />
        </div>
        <Controller
          control={control}
          name="interests"
          render={({ field }) => (
            <ChoiceField
              id="profile-interests"
              label="관심 분야"
              options={interestOptions}
              {...field}
              error={errors.interests?.message}
            />
          )}
        />
        {interests.includes('기타') && (
          <div className="preview-field">
            <Label htmlFor="profile-interest-other">
              기타 관심 분야 설명 (선택)
            </Label>
            <Input
              id="profile-interest-other"
              {...register('interestOther')}
              placeholder="관심 있는 분야를 알려 주세요."
            />
          </div>
        )}
        <Controller
          control={control}
          name="roles"
          render={({ field }) => (
            <ChoiceField
              id="profile-roles"
              label="희망 역할"
              options={roleOptions}
              {...field}
              error={errors.roles?.message}
            />
          )}
        />
      </section>
      <Separator className="preview-form-separator" />
      <AcademicFields control={control} setValue={setValue} />
      <Separator className="preview-form-separator" />
      <section
        className="preview-form-section"
        aria-labelledby="profile-experience-heading"
      >
        <h2 id="profile-experience-heading" className="preview-section-title">
          활동과 경험
        </h2>
        <SkillFields control={control} register={register} />
        <ExperienceFields
          control={control}
          register={register}
          setValue={setValue}
        />
        <div className="preview-field">
          <Label htmlFor="profile-intro">자기소개 (선택)</Label>
          <Textarea
            id="profile-intro"
            rows={3}
            {...register('intro')}
            placeholder="함께하고 싶은 활동을 소개해 주세요."
          />
        </div>
        <Controller
          control={control}
          name="availability"
          render={({ field }) => (
            <AvailabilityField value={field.value} onChange={field.onChange} />
          )}
        />
      </section>
      <Separator className="preview-form-separator" />
      <section
        className="preview-form-section"
        aria-labelledby="profile-portfolio-heading"
      >
        <h2 id="profile-portfolio-heading" className="preview-section-title">
          포트폴리오
        </h2>
        <div className="preview-field">
          <Label htmlFor="profile-portfolio">포트폴리오 링크 (선택)</Label>
          <Input
            id="profile-portfolio"
            type="url"
            {...register('portfolio', {
              onChange: (event: ChangeEvent<HTMLInputElement>) => {
                if (!isWebUrl(event.target.value.trim())) {
                  setValue('portfolioConsent', false, { shouldDirty: true });
                }
              },
            })}
            placeholder="https://example.com/portfolio"
            autoComplete="off"
            aria-invalid={!!errors.portfolio}
            aria-describedby={`portfolio-help${errors.portfolio ? ' portfolio-error' : ''}`}
          />
          <p id="portfolio-help" className="preview-muted">
            외부 페이지의 공유 권한을 확인해 주세요.
          </p>
          <FieldError
            id="portfolio-error"
            message={errors.portfolio?.message}
          />
        </div>
        <div className="preview-field">
          <Label htmlFor="profile-portfolio-title">
            포트폴리오 제목 (선택)
          </Label>
          <Input
            id="profile-portfolio-title"
            {...register('portfolioTitle')}
            placeholder="작업 모음, 프로젝트 소개 등"
          />
        </div>
        <div className="preview-field preview-portfolio-visibility">
          <Controller
            control={control}
            name="portfolioConsent"
            render={({ field }) => (
              <VisibilitySwitch
                label="포트폴리오 링크 공개"
                checked={validPortfolio && field.value}
                onChange={field.onChange}
                disabled={!validPortfolio}
                describedBy="portfolio-visibility-help portfolio-visibility-status profile-save-help"
              />
            )}
          />
          <p id="portfolio-visibility-help" className="preview-muted">
            지금까지 지원했거나 앞으로 지원할 모든 팀의 팀장에게 동일하게
            적용돼요. 취소·미선발된 지원에도 적용되며 사람 탐색에는 표시되지
            않아요.
          </p>
          <p
            id="portfolio-visibility-status"
            className="preview-muted"
            aria-live="polite"
          >
            {validPortfolio
              ? '공개할지 선택한 뒤 변경사항을 저장해 주세요.'
              : '유효한 링크를 먼저 입력하면 공개 여부를 선택할 수 있어요.'}
          </p>
        </div>
      </section>
      <Separator className="preview-form-separator" />
      <div className="preview-row">
        <Button
          type="submit"
          className="preview-button"
          disabled={isSubmitting}
        >
          {isSubmitting ? '저장 중' : '변경사항 저장'}
        </Button>
        <Button
          type="button"
          variant="outline"
          className="preview-button"
          onClick={onCancel}
        >
          취소
        </Button>
      </div>
    </form>
  );
}

export function ProfilePage() {
  const { signedIn, profile, signOut } = usePreview();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const returnTo = search.get('returnTo');
  const [editing, setEditing] = useState(
    ['visibility', 'details'].includes(search.get('edit') ?? ''),
  );
  const [saved, setSaved] = useState(false);
  if (!signedIn)
    return <LoginGate returnTo={previewPath('/profile')} title="내 프로필" />;
  return (
    <div
      className={`preview-detail preview-stack preview-own-profile${editing ? ' preview-account-page' : ''}`}
    >
      <PageIntro
        title="내 프로필"
        action={
          !editing && (
            <Button
              variant="outline"
              className="preview-button"
              onClick={() => {
                setSaved(false);
                setEditing(true);
              }}
            >
              프로필 수정
            </Button>
          )
        }
      />
      {saved && (
        <Alert role="status" className="preview-notice">
          <Check size={18} aria-hidden="true" />
          <AlertDescription>프로필을 저장했어요.</AlertDescription>
        </Alert>
      )}
      {editing ? (
        <ProfileEditor
          onDone={() => {
            setEditing(false);
            setSaved(true);
            if (returnTo) navigate(safeReturnTo(returnTo));
          }}
          onCancel={() => {
            setEditing(false);
            if (returnTo) navigate(safeReturnTo(returnTo));
          }}
        />
      ) : (
        <>
          <section
            className="preview-panel preview-stack preview-profile-summary"
            aria-label="내 기본 정보"
          >
            <div className="preview-row">
              <Avatar name={profile.name} />
              <div>
                <h2>{profile.name}</h2>
                <Badge>교내 미인증</Badge>
                <p className="preview-muted">
                  학교 인증은 아직 제공하지 않아요.
                </p>
              </div>
            </div>
            <div className="dreamon-privacy-summary">
              <div className="preview-row">
                <h3 className="preview-section-title">사람 탐색에 공개</h3>
                <Badge>
                  {profile.visibility.discoverable ? '공개 중' : '비공개'}
                </Badge>
              </div>
              <Button asChild variant="outline" className="preview-button">
                <Link to={previewPath('/profile/public')}>
                  공개된 모습 보기
                </Link>
              </Button>
            </div>
            <div>
              <h3 className="preview-section-title">희망 역할</h3>
              <div className="preview-row">
                {profile.roles.map((role) => (
                  <Badge key={role}>{role}</Badge>
                ))}
              </div>
            </div>
            <div>
              <div className="preview-row">
                <h3 className="preview-section-title">관심 분야</h3>
                <Badge>
                  {profile.visibility.interests ? '공개' : '비공개'}
                </Badge>
              </div>
              <p>{profile.interests.join(' · ')}</p>
              {profile.interests.includes('기타') && profile.interestOther && (
                <p className="preview-muted">{profile.interestOther}</p>
              )}
            </div>
            <div>
              <div className="preview-row">
                <h3 className="preview-section-title">관련 경험</h3>
                <Badge>
                  {profile.visibility.experience ? '공개' : '비공개'}
                </Badge>
              </div>
              <p>
                {profile.experienceState === 'none'
                  ? '관련 경험 없음'
                  : profile.experience || '아직 경험을 입력하지 않았어요.'}
              </p>
            </div>
            <div>
              <div className="preview-row">
                <h3 className="preview-section-title">자기소개</h3>
                <Badge>{profile.visibility.intro ? '공개' : '비공개'}</Badge>
              </div>
              <p>{profile.intro || '아직 자기소개를 작성하지 않았어요.'}</p>
            </div>
          </section>
          <section className="preview-panel preview-stack">
            <h2 className="preview-section-title">학사 정보와 보유 역량</h2>
            <p>
              {[
                profile.academicStatus,
                profile.grade,
                profile.college,
                profile.department,
                profile.major,
              ]
                .filter(Boolean)
                .join(' · ') || '등록한 학사 정보가 없어요.'}
            </p>
            <div>
              <h3 className="preview-section-title">보유 역량</h3>
              <p>
                {profile.skills.join(' · ') || '아직 역량을 선택하지 않았어요.'}
              </p>
              {profile.skills.includes('기타') && profile.skillOther && (
                <p className="preview-muted">{profile.skillOther}</p>
              )}
            </div>
          </section>
          <div className="preview-detail-grid">
            <section className="preview-panel preview-stack">
              <h2 className="preview-section-title">활동 가능 시간</h2>
              <p>{profile.availability || '아직 시간을 선택하지 않았어요.'}</p>
              <p className="preview-muted">나만 보기</p>
            </section>
            <section className="preview-panel preview-stack">
              <h2 className="preview-section-title">포트폴리오</h2>
              {profile.portfolio && isWebUrl(profile.portfolio) ? (
                <>
                  <a
                    className="preview-text-link"
                    href={profile.portfolio}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {profile.portfolioTitle || '등록한 링크 열기'} (새 창)
                  </a>
                  <p className="preview-muted">
                    {profile.portfolioConsent
                      ? '모든 지원 팀의 팀장에게 공개 동의함'
                      : '비공개'}
                  </p>
                </>
              ) : (
                <p className="preview-muted">등록한 링크가 없어요.</p>
              )}
            </section>
          </div>
          <Button
            type="button"
            variant="outline"
            className="preview-button"
            onClick={signOut}
          >
            로그아웃
          </Button>
        </>
      )}
    </div>
  );
}

export function PublicProfilePage() {
  const { signedIn, profile } = usePreview();
  if (!signedIn)
    return (
      <LoginGate
        returnTo={previewPath('/profile/public')}
        title="공개 프로필"
      />
    );
  const person = getPublicProfile(profile);
  return (
    <div className="preview-detail preview-stack preview-account-page">
      <BackLink to={previewPath('/profile')}>내 프로필</BackLink>
      <PageIntro
        title="공개 프로필"
        action={
          <Link
            className="preview-text-link"
            to={previewPath('/profile?edit=visibility')}
          >
            공개 설정 변경
          </Link>
        }
      />
      {person ? (
        <section
          className="preview-panel preview-stack"
          aria-label="공개된 내 프로필"
        >
          <div className="preview-row">
            <Avatar name={person.name} personId={person.id} size="large" />
            <div>
              <h2>{person.name}</h2>
              <Badge>교내 미인증</Badge>
            </div>
          </div>
          <div>
            <h3 className="preview-section-title">희망 역할</h3>
            <div className="preview-row">
              {person.roles.map((role) => (
                <Badge key={role}>{role}</Badge>
              ))}
            </div>
          </div>
          {person.interests && (
            <div>
              <h3 className="preview-section-title">관심 분야</h3>
              <div className="preview-row">
                {person.interests.map((interest) => (
                  <Badge key={interest}>{interest}</Badge>
                ))}
              </div>
            </div>
          )}
          {person.experience && (
            <div>
              <h3 className="preview-section-title">관련 경험</h3>
              <p>{person.experience}</p>
            </div>
          )}
          {person.intro && (
            <div>
              <h3 className="preview-section-title">자기소개</h3>
              <p>{person.intro}</p>
            </div>
          )}
        </section>
      ) : (
        <div className="preview-panel">
          <p>현재 비공개 상태입니다.</p>
        </div>
      )}
    </div>
  );
}

function AccountFields({
  register,
  errors,
}: {
  register: UseFormRegister<z.infer<typeof accountSchema>>;
  errors: { username?: { message?: string }; password?: { message?: string } };
}) {
  const [showPassword, setShowPassword] = useState(false);
  return (
    <>
      <div className="dreamon-login-field">
        <Label htmlFor="login-username">아이디</Label>
        <Input
          id="login-username"
          {...register('username')}
          autoComplete="off"
          placeholder="아이디를 입력해 주세요"
          spellCheck={false}
          aria-invalid={!!errors.username}
          aria-describedby={
            errors.username ? 'login-username-error' : undefined
          }
        />
        <FieldError
          id="login-username-error"
          message={errors.username?.message}
        />
      </div>
      <div className="dreamon-login-field">
        <Label htmlFor="login-password">비밀번호</Label>
        <div className="dreamon-login-password">
          <Input
            id="login-password"
            type={showPassword ? 'text' : 'password'}
            {...register('password')}
            placeholder="비밀번호를 입력해 주세요"
            autoComplete="off"
            aria-invalid={!!errors.password}
            aria-describedby={
              errors.password ? 'login-password-error' : undefined
            }
          />
          <Button
            type="button"
            variant="ghost"
            className="dreamon-login-reveal"
            aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
            aria-controls="login-password"
            aria-pressed={showPassword}
            onClick={() => setShowPassword((value) => !value)}
          >
            {showPassword ? (
              <EyeOff size={20} aria-hidden="true" />
            ) : (
              <Eye size={20} aria-hidden="true" />
            )}
          </Button>
        </div>
        <FieldError
          id="login-password-error"
          message={errors.password?.message}
        />
      </div>
    </>
  );
}

function safeReturnTo(value: string | null) {
  if (!value || !value.startsWith('/')) return previewPath('/workspace');
  try {
    const url = new URL(value, 'https://preview.invalid');
    if (
      url.origin !== 'https://preview.invalid' ||
      (url.pathname !== previewBase &&
        !url.pathname.startsWith(`${previewBase}/`))
    )
      return previewPath('/workspace');
    if ([previewPath('/login'), previewPath('/signup')].includes(url.pathname))
      return previewPath('/workspace');
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return previewPath('/workspace');
  }
}

export function LoginPage() {
  const { signIn } = usePreview();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const {
    register,
    handleSubmit,
    resetField,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof accountSchema>>({
    resolver: zodResolver(accountSchema),
    defaultValues: { username: '', password: '' },
  });
  const returnTo = safeReturnTo(search.get('returnTo') ?? search.get('from'));
  return (
    <div className="dreamon-login">
      <section
        className="dreamon-login-story"
        aria-labelledby="login-story-title"
      >
        <div>
          <h2 id="login-story-title">
            함께할 팀을
            <br />
            만나는 시작.
          </h2>
          <p className="dreamon-login-story-summary">
            공모전과 사람, 다음 도전을 연결해요.
          </p>
        </div>
        <p className="dreamon-login-story-signature">서경드림온</p>
      </section>
      <section className="dreamon-login-content" aria-labelledby="login-title">
        <header className="dreamon-login-heading">
          <h1 id="login-title">로그인</h1>
          <p>아이디와 비밀번호를 입력해 주세요.</p>
        </header>
        <form
          className="dreamon-login-form"
          noValidate
          onSubmit={handleSubmit((values) => {
            if (
              values.username !== demoId ||
              values.password !== demoPassword
            ) {
              setError('root', {
                message: '아이디 또는 비밀번호를 확인해 주세요.',
              });
              return;
            }
            resetField('password', { defaultValue: '' });
            signIn();
            navigate(returnTo, { replace: true });
          })}
        >
          <AccountFields register={register} errors={errors} />
          <FieldError id="login-error" message={errors.root?.message} />
          <Button
            type="submit"
            className="preview-button dreamon-login-submit"
            disabled={isSubmitting}
          >
            {isSubmitting ? '로그인 중' : '로그인'}
            <ArrowRight size={18} aria-hidden="true" />
          </Button>
        </form>
        <div className="dreamon-login-signup">
          <p>처음이신가요?</p>
          <Link
            to={`${previewPath('/signup')}?returnTo=${encodeURIComponent(returnTo)}`}
          >
            회원가입
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </section>
    </div>
  );
}

export function SignupPage() {
  const { saveProfile, signOut } = usePreview();
  const [search] = useSearchParams();
  const returnTo = safeReturnTo(search.get('returnTo') ?? search.get('from'));
  const [complete, setComplete] = useState(false);
  const {
    register,
    control,
    handleSubmit,
    resetField,
    formState: { errors, isSubmitting },
  } = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      username: '',
      password: '',
      name: '',
      roles: [],
      interests: [],
    },
  });
  if (complete)
    return (
      <div className="preview-detail preview-stack preview-account-page">
        <PageIntro title="가입이 완료됐어요" />
        <div className="preview-panel preview-stack">
          <Check size={32} aria-hidden="true" />
          <p role="status">서경드림온에 오신 것을 환영해요.</p>
          <p className="preview-muted">로그인하고 프로필을 완성해 보세요.</p>
          <Button asChild className="preview-button">
            <Link
              to={`${previewPath('/login')}?returnTo=${encodeURIComponent(previewPath('/profile'))}`}
            >
              로그인
            </Link>
          </Button>
        </div>
      </div>
    );
  return (
    <div className="preview-detail preview-stack preview-account-page">
      <BackLink
        to={`${previewPath('/login')}?returnTo=${encodeURIComponent(returnTo)}`}
      >
        로그인으로
      </BackLink>
      <PageIntro title="회원가입" />
      <form
        className="preview-panel preview-form"
        noValidate
        onSubmit={handleSubmit((values) => {
          saveProfile({
            name: values.name,
            roles: values.roles,
            interests: values.interests,
            intro: '',
            experience: '',
            academicStatus: '',
            grade: '',
            college: '',
            department: '',
            major: '',
            skills: [],
            experienceState: 'unspecified',
            portfolioTitle: '',
            interestOther: '',
            skillOther: '',
            visibility: {
              discoverable: false,
              interests: false,
              experience: false,
              intro: false,
            },
            portfolio: '',
            portfolioConsent: false,
            availability: '',
          });
          resetField('password', { defaultValue: '' });
          signOut();
          setComplete(true);
        })}
      >
        <div className="preview-field">
          <Label htmlFor="signup-username">아이디 (필수)</Label>
          <Input
            id="signup-username"
            {...register('username')}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={!!errors.username}
            aria-describedby={
              errors.username ? 'signup-username-error' : undefined
            }
          />
          <FieldError
            id="signup-username-error"
            message={errors.username?.message}
          />
        </div>
        <div className="preview-field">
          <Label htmlFor="signup-password">비밀번호 (필수)</Label>
          <Input
            id="signup-password"
            type="password"
            {...register('password')}
            autoComplete="off"
            aria-invalid={!!errors.password}
            aria-describedby={
              errors.password ? 'signup-password-error' : undefined
            }
          />
          <FieldError
            id="signup-password-error"
            message={errors.password?.message}
          />
        </div>
        <div className="preview-field">
          <Label htmlFor="signup-name">이름 (필수)</Label>
          <Input
            id="signup-name"
            {...register('name')}
            autoComplete="off"
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? 'signup-name-error' : undefined}
          />
          <FieldError id="signup-name-error" message={errors.name?.message} />
        </div>
        <Controller
          control={control}
          name="interests"
          render={({ field }) => (
            <ChoiceField
              id="signup-interests"
              label="관심 분야"
              options={interestOptions}
              {...field}
              error={errors.interests?.message}
            />
          )}
        />
        <Controller
          control={control}
          name="roles"
          render={({ field }) => (
            <ChoiceField
              id="signup-roles"
              label="희망 역할"
              options={roleOptions}
              {...field}
              error={errors.roles?.message}
            />
          )}
        />
        <Badge>교내 미인증</Badge>
        <Button
          type="submit"
          className="preview-button"
          disabled={isSubmitting}
        >
          {isSubmitting ? '가입 중' : '회원가입'}
        </Button>
      </form>
    </div>
  );
}
