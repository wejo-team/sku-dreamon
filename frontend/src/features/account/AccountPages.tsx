/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/AccountPages.tsx - 로그인·가입·내 프로필·공개 미리보기 원본
 * 2. docs/specs/authentication.md#acceptance-criteria - 아이디·비밀번호 규칙, 보기/숨기기·붙여넣기
 * 3. docs/specs/profile.md#acceptance-criteria - 프로필 필수·선택 항목, 공개 전환 확인
 * 4. docs/design/tokens.md - 수정 아이콘·공개 스위치·미리보기 묶음, 교내 미인증 배지 안내 Drawer
 * 5. docs/design/screens.md - 「확인할 상태와 연결」 프로필 수정·공개·이미지 선택 흐름
 * 6. docs/design/assets/wordmark-login-320.png, profile-view-390.png, profile-320.png, profile-public-confirm-390.png, profile-private-confirm-390.png, profile-school-390.png - 실제 화면
 */

import { useId, useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  ArrowRight,
  Check,
  Eye,
  EyeOff,
  SquarePen,
  UserRound,
} from 'lucide-react';
import {
  Controller,
  useForm,
  useWatch,
  type UseFormRegister,
} from 'react-hook-form';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router';
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
import type { CatalogItem } from '@/features/catalogs/api';
import { getPublicProfile } from '@/features/demo/data';
import {
  academicPath,
  academicStatusLabel,
  fieldLabel,
  fieldOptions,
  gradeLabel,
  roleLabel,
  roleOptions,
  skillLabel,
  weeklyAvailabilityLabel,
  weeklyAvailabilityOptions,
} from '@/features/demo/labels';
import {
  fromFormValues,
  toFormValues,
  type ProfileFormValues,
} from '@/features/account/profile-form';
import { useDemo } from '@/features/demo/demo-context';
import {
  Avatar,
  BackLink,
  Badge,
  PageIntro,
  SchoolVerificationBadge,
} from '@/components/common/CommonUi';
import { AvatarPicker } from '@/features/account/AvatarPicker';
import { ProfileDetails } from '@/components/common/ProfileDetails';
import {
  AcademicFields,
  ExperienceFields,
  SkillFields,
} from '@/features/account/ProfileFields';
import {
  demoId,
  demoPassword,
  loginIdSchema,
  passwordSchema,
  signupPasswordSchema,
} from '@/features/demo/auth-policy';
import {
  normalizeWebUrl,
  profileTextLength,
} from '@/features/demo/profile-fields';

// [출처 3] 저장·공개 변환과 같은 기준(normalizeWebUrl)으로 포트폴리오 주소를 판단합니다.
function isWebUrl(value: string) {
  return normalizeWebUrl(value) !== '';
}

const requiredProfileSchema = z.object({
  realName: z
    .string()
    .trim()
    .min(1, '이름을 입력해 주세요.')
    .refine(
      (value) => profileTextLength(value) <= 50,
      '이름은 50자 이내로 입력해 주세요.',
    ),
  roleCodes: z
    .array(z.string())
    .min(1, '희망 역할을 하나 이상 선택해 주세요.')
    .max(2, '희망 역할은 최대 2개까지 선택해 주세요.'),
  fieldCodes: z
    .array(z.string())
    .min(1, '관심 분야를 하나 이상 선택해 주세요.')
    .max(3, '관심 분야는 최대 3개까지 선택해 주세요.'),
});
const profileSchema = requiredProfileSchema.extend({
  profileImageCode: z.string().nullable(),
  introduction: z
    .string()
    .trim()
    .refine(
      (value) => profileTextLength(value) <= 300,
      '자기소개는 300자 이내로 입력해 주세요.',
    ),
  experienceBody: z
    .string()
    .trim()
    .refine(
      (value) => profileTextLength(value) <= 500,
      '관련 경험은 500자 이내로 입력해 주세요.',
    ),
  experienceState: z.enum(['unspecified', 'none', 'provided']),
  academicStatusCode: z.string(),
  gradeCode: z.string(),
  collegeId: z.string(),
  departmentId: z.string(),
  majorId: z.string(),
  skillCodes: z.array(z.string()),
  portfolioTitle: z
    .string()
    .trim()
    .refine(
      (value) => profileTextLength(value) <= 50,
      '포트폴리오 제목은 50자 이내로 입력해 주세요.',
    ),
  portfolioUrl: z
    .string()
    .trim()
    .refine(
      (value) => !value || isWebUrl(value),
      'http:// 또는 https://로 시작하는 링크를 입력해 주세요.',
    ),
  weeklyAvailabilityCode: z
    .string()
    .refine(
      (value) =>
        !value || weeklyAvailabilityOptions.some((item) => item.code === value),
      '주당 참여 가능 시간을 다시 선택해 주세요.',
    ),
});
const accountSchema = z.object({
  username: loginIdSchema,
  password: passwordSchema,
});
const signupSchema = requiredProfileSchema.merge(accountSchema).extend({
  username: loginIdSchema.refine(
    (value) => value !== demoId,
    '이미 사용 중인 아이디예요.',
  ),
  password: signupPasswordSchema,
});
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
  options: CatalogItem[];
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
        {label}{' '}
        <span className="preview-muted">
          (필수 · {label === '관심 분야' ? '1~3개' : '1~2개'})
        </span>
      </legend>
      <div className="preview-row">
        {options.map((option) => (
          <Label
            key={option.code}
            htmlFor={`${id}-${option.code}`}
            className="preview-choice"
          >
            <Checkbox
              id={`${id}-${option.code}`}
              checked={value.includes(option.code)}
              aria-invalid={!!error}
              onCheckedChange={(checked) =>
                onChange(
                  checked === true
                    ? [...value, option.code]
                    : value.filter((item) => item !== option.code),
                )
              }
            />
            {option.displayName}
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
  return (
    <div className="preview-field">
      <Label htmlFor="profile-weekly-availability">
        주당 참여 가능 시간 (선택)
      </Label>
      <NativeSelect
        id="profile-weekly-availability"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby="weekly-availability-help"
      >
        <NativeSelectOption value="">미입력</NativeSelectOption>
        {weeklyAvailabilityOptions.map((option) => (
          <NativeSelectOption value={option.code} key={option.code}>
            {option.displayName}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      <p id="weekly-availability-help" className="preview-muted">
        참여 중인 모든 프로젝트를 합한 주당 예상 시간이에요. 팀마다 쓸 수 있는
        시간이나 남은 시간을 뜻하지 않아요.
      </p>
    </div>
  );
}

// [출처 5] 로그인 필요한 화면의 안내와 복귀 경로
export function LoginGate({
  returnTo,
  title,
  rootPage = false,
}: {
  returnTo: string;
  title: string;
  rootPage?: boolean;
}) {
  return (
    <div className="preview-detail preview-stack">
      {rootPage ? (
        <h1 className="sr-only">{title}</h1>
      ) : (
        <>
          <BackLink />
          <PageIntro title={title} />
        </>
      )}
      <div className="preview-panel preview-stack">
        <UserRound size={28} aria-hidden="true" />
        <p>로그인하고 계속해 주세요.</p>
        <Button asChild className="preview-button">
          <Link to={`/login?returnTo=${encodeURIComponent(returnTo)}`}>
            로그인
          </Link>
        </Button>
      </div>
    </div>
  );
}

// [출처 3, 4, 6] 전체 공개 전환 전 설명 Drawer, 취소 시 기존 상태 유지
export function ProfileVisibilityControl({
  checked,
  onConfirm,
  triggerLabel,
  className,
}: {
  checked: boolean;
  onConfirm: (next: boolean) => void | Promise<void>;
  triggerLabel?: string;
  className?: string;
}) {
  const [pending, setPending] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const triggerRef = useRef<HTMLButtonElement>(null);
  const id = useId();
  return (
    <Drawer
      open={pending !== null}
      onOpenChange={(open) => {
        if (!saving) {
          setSaveError('');
          setPending(open ? !checked : null);
        }
      }}
      shouldScaleBackground={false}
      autoFocus
    >
      {triggerLabel ? (
        <Button
          ref={triggerRef}
          type="button"
          className={className ?? 'preview-button'}
          aria-haspopup="dialog"
          onClick={() => {
            setSaveError('');
            setPending(!checked);
          }}
        >
          {triggerLabel}
        </Button>
      ) : (
        <Label
          className="preview-profile-visibility"
          htmlFor={id}
          title="프로필 공개 설정"
        >
          <Switch
            ref={triggerRef}
            id={id}
            aria-label="프로필 공개"
            aria-haspopup="dialog"
            checked={checked}
            onCheckedChange={(next) => {
              setSaveError('');
              setPending(next);
            }}
          />
          <span>{checked ? '공개' : '비공개'}</span>
        </Label>
      )}
      <DrawerContent
        className="dreamon-preview preview-drawer"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          triggerRef.current?.focus();
        }}
      >
        <DrawerHeader>
          <DrawerTitle>
            {pending ? '프로필을 공개할까요?' : '프로필을 비공개로 바꿀까요?'}
          </DrawerTitle>
          <DrawerDescription>
            {pending
              ? '일반 사람 검색·AI 사람 추천의 후보가 되고, 로그인한 사용자에게 등록한 모든 프로필 항목이 보여요. 주당 참여 가능 시간과 포트폴리오도 포함돼요. 공개 전환만으로 지원이 접수되지는 않아요.'
              : '일반 검색·AI 사람 추천에서 숨겨져요. 기존 지원과 팀 소속은 유지되며, 새 지원은 다시 공개한 뒤 할 수 있어요.'}{' '}
            이미 지원받은 팀장은 전체 현재 프로필을 볼 수 있고, AI 지원자
            검토에도 최신 프로필이 반영돼요.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerFooter>
          {saveError && (
            <p role="alert" className="preview-error">
              {saveError}
            </p>
          )}
          <Button
            type="button"
            className="preview-button"
            disabled={saving}
            onClick={async () => {
              if (pending === null || saving) return;
              setSaving(true);
              setSaveError('');
              try {
                await onConfirm(pending);
                setPending(null);
              } catch {
                setSaveError(
                  '공개 설정을 저장하지 못했어요. 다시 시도해 주세요.',
                );
              } finally {
                setSaving(false);
              }
            }}
          >
            {saving ? '저장 중' : pending ? '공개로 전환' : '비공개로 전환'}
          </Button>
          <DrawerClose asChild>
            <Button type="button" variant="outline" className="preview-button">
              취소
            </Button>
          </DrawerClose>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function ProfileEditor({
  onDone,
  onCancel,
}: {
  onDone: () => void;
  onCancel: () => void;
}) {
  const { profile, saveProfile } = useDemo();
  const {
    register,
    control,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: toFormValues(profile),
    mode: 'onChange',
  });
  const name = useWatch({ control, name: 'realName' });
  const intro = useWatch({ control, name: 'introduction' });
  const portfolioTitle = useWatch({ control, name: 'portfolioTitle' });
  return (
    <form
      className="preview-panel preview-form"
      noValidate
      onSubmit={handleSubmit((values) => {
        // [출처 3] 폼 값을 Profile DTO로 변환(빈 선택은 null, 포트폴리오 URL은 정규화해 저장)
        saveProfile(fromFormValues(values, profile));
        onDone();
      })}
    >
      <Controller
        control={control}
        name="profileImageCode"
        render={({ field }) => (
          <AvatarPicker value={field.value} onChange={field.onChange} />
        )}
      />
      <p className="preview-muted">
        공개 상태에서는 등록한 모든 항목이 보여요. 지원한 팀의 팀장은 공개
        여부와 관계없이 전체 프로필을 볼 수 있어요.
      </p>
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
            {...register('realName')}
            autoComplete="off"
            aria-invalid={!!errors.realName}
            aria-describedby={
              errors.realName ? 'profile-name-error' : undefined
            }
          />
          <p className="preview-field-count">
            {profileTextLength(name)} / 50자
          </p>
          <FieldError
            id="profile-name-error"
            message={errors.realName?.message}
          />
        </div>
        <Controller
          control={control}
          name="fieldCodes"
          render={({ field }) => (
            <ChoiceField
              id="profile-interests"
              label="관심 분야"
              options={fieldOptions}
              {...field}
              error={errors.fieldCodes?.message}
            />
          )}
        />

        <Controller
          control={control}
          name="roleCodes"
          render={({ field }) => (
            <ChoiceField
              id="profile-roles"
              label="희망 역할"
              options={roleOptions}
              {...field}
              error={errors.roleCodes?.message}
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
        <SkillFields control={control} />
        <ExperienceFields
          control={control}
          register={register}
          setValue={setValue}
          error={errors.experienceBody?.message}
        />
        <div className="preview-field">
          <Label htmlFor="profile-intro">자기소개 (선택)</Label>
          <Textarea
            id="profile-intro"
            rows={3}
            {...register('introduction')}
            aria-invalid={!!errors.introduction}
            aria-describedby="profile-intro-count profile-intro-error"
            placeholder="함께하고 싶은 활동을 소개해 주세요."
          />
          <p id="profile-intro-count" className="preview-field-count">
            {profileTextLength(intro)} / 300자
          </p>
          <FieldError
            id="profile-intro-error"
            message={errors.introduction?.message}
          />
        </div>
        <Controller
          control={control}
          name="weeklyAvailabilityCode"
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
            {...register('portfolioUrl')}
            placeholder="https://example.com/portfolio"
            autoComplete="off"
            aria-invalid={!!errors.portfolioUrl}
            aria-describedby={`portfolio-help${errors.portfolioUrl ? ' portfolio-error' : ''}`}
          />
          <p id="portfolio-help" className="preview-muted">
            외부 페이지의 공유 권한을 확인해 주세요.
          </p>
          <FieldError
            id="portfolio-error"
            message={errors.portfolioUrl?.message}
          />
        </div>
        <div className="preview-field">
          <Label htmlFor="profile-portfolio-title">
            포트폴리오 제목 (선택)
          </Label>
          <Input
            id="profile-portfolio-title"
            {...register('portfolioTitle')}
            aria-invalid={!!errors.portfolioTitle}
            aria-describedby="profile-title-count profile-title-error"
            placeholder="작업 모음, 프로젝트 소개 등"
          />
          <p id="profile-title-count" className="preview-field-count">
            {profileTextLength(portfolioTitle)} / 50자
          </p>
          <FieldError
            id="profile-title-error"
            message={errors.portfolioTitle?.message}
          />
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

// [출처 3, 4, 5, 6] 프로필 보기·수정
export function ProfilePage() {
  const { signedIn, profile, signOut, saveProfile } = useDemo();
  const [search] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const returnTo = search.get('returnTo');
  const [editing, setEditing] = useState(
    ['visibility', 'details'].includes(search.get('edit') ?? ''),
  );
  const [saved, setSaved] = useState(false);
  // [출처 5] 로그인 후에도 편집 의도(edit)와 팀 복귀 주소(returnTo)를 잃지 않도록 현재 경로 전체를 넘깁니다.
  // 복귀 주소의 안전성은 LoginPage의 safeReturnTo가 다시 검사합니다(PR #121 리뷰).
  if (!signedIn)
    return (
      <LoginGate
        returnTo={`${location.pathname}${location.search}`}
        title="내 프로필"
        rootPage
      />
    );
  return (
    <div
      className={`preview-detail preview-stack preview-own-profile${editing ? ' preview-account-page' : ''}`}
    >
      {editing ? (
        <PageIntro title="프로필 수정" />
      ) : (
        <h1 className="sr-only">내 프로필</h1>
      )}
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
            <div className="preview-row preview-profile-heading">
              <div className="preview-profile-identity">
                <Avatar
                  name={profile.realName}
                  accountId={profile.accountId}
                  imageCode={profile.profileImageCode}
                />
                <div>
                  <h2>{profile.realName}</h2>
                  <SchoolVerificationBadge interactive />
                </div>
              </div>
              <div
                className="preview-profile-actions"
                role="group"
                aria-label="프로필 관리"
              >
                <Button
                  type="button"
                  variant="outline"
                  className="preview-profile-edit"
                  aria-label="프로필 수정"
                  title="프로필 수정"
                  onClick={() => {
                    setSaved(false);
                    setEditing(true);
                  }}
                >
                  <SquarePen size={20} aria-hidden="true" />
                </Button>
                <ProfileVisibilityControl
                  checked={profile.isPublic}
                  onConfirm={(isPublic) => {
                    setSaved(false);
                    // docs/api/profiles.md#visibility-write: 공개 전환은 별도 저장, 버전 증가
                    saveProfile({
                      ...profile,
                      isPublic,
                      version: (BigInt(profile.version) + 1n).toString(),
                    });
                  }}
                />
                <Button
                  asChild
                  variant="outline"
                  className="preview-profile-edit"
                >
                  <Link
                    to="/profile/public"
                    aria-label="공개된 모습 보기"
                    title="공개된 모습 보기"
                  >
                    <Eye size={20} aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            </div>
            <div>
              <h3 className="preview-section-title preview-info-label">
                희망 역할
              </h3>
              <div className="preview-row">
                {profile.roleCodes.map((code) => (
                  <Badge key={code}>{roleLabel(code)}</Badge>
                ))}
              </div>
            </div>
            <div>
              <div className="preview-row">
                <h3 className="preview-section-title preview-info-label">
                  관심 분야
                </h3>
              </div>
              <p className="preview-info-value">
                {profile.fieldCodes.map(fieldLabel).join(' · ')}
              </p>
            </div>
            <div>
              <div className="preview-row">
                <h3 className="preview-section-title preview-info-label">
                  관련 경험
                </h3>
              </div>
              <p className="preview-info-copy">
                {profile.experienceState === 'none'
                  ? '관련 경험 없음'
                  : profile.experienceBody || '아직 경험을 입력하지 않았어요.'}
              </p>
            </div>
            <div>
              <div className="preview-row">
                <h3 className="preview-section-title preview-info-label">
                  자기소개
                </h3>
              </div>
              <p className="preview-info-copy">
                {profile.introduction || '아직 자기소개를 작성하지 않았어요.'}
              </p>
            </div>
          </section>
          <section className="preview-panel preview-stack">
            <h2 className="preview-section-title">학사 정보와 보유 역량</h2>
            <p>
              {[
                profile.academicStatusCode &&
                  academicStatusLabel(profile.academicStatusCode),
                profile.gradeCode && gradeLabel(profile.gradeCode),
                ...academicPath(profile.academicUnitId).map(
                  (unit) => unit.name,
                ),
              ]
                .filter(Boolean)
                .join(' · ') || '등록한 학사 정보가 없어요.'}
            </p>
            <div>
              <h3 className="preview-section-title preview-info-label">
                보유 역량
              </h3>
              <p
                className={
                  profile.skillCodes.length
                    ? 'preview-info-value'
                    : 'preview-muted'
                }
              >
                {profile.skillCodes.map(skillLabel).join(' · ') ||
                  '아직 역량을 선택하지 않았어요.'}
              </p>
            </div>
          </section>
          <div className="preview-detail-grid">
            <section className="preview-panel preview-stack">
              <h2 className="preview-section-title">주당 참여 가능 시간</h2>
              <p
                className={
                  profile.weeklyAvailabilityCode
                    ? 'preview-info-value'
                    : 'preview-muted'
                }
              >
                {profile.weeklyAvailabilityCode
                  ? weeklyAvailabilityLabel(profile.weeklyAvailabilityCode)
                  : '미입력'}
              </p>
              <p className="preview-muted">
                모든 참여 프로젝트의 예상 시간이에요. 팀별 약속이나 남은 시간이
                아니에요.
              </p>
            </section>
            <section className="preview-panel preview-stack">
              <h2 className="preview-section-title">포트폴리오</h2>
              {profile.portfolio && isWebUrl(profile.portfolio.url) ? (
                <>
                  <a
                    className="preview-text-link"
                    href={profile.portfolio.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {profile.portfolio.title || '등록한 링크 열기'} (새 창)
                  </a>
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

// [출처 3, 5] 본인 공개 결과 미리보기
export function PublicProfilePage() {
  const { signedIn, profile } = useDemo();
  if (!signedIn)
    return <LoginGate returnTo="/profile/public" title="공개 프로필" />;
  const person = getPublicProfile(profile);
  return (
    <div className="preview-detail preview-stack preview-account-page">
      <BackLink to="/profile">내 프로필</BackLink>
      <PageIntro
        title="공개 프로필"
        action={
          <Link className="preview-text-link" to="/profile">
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
            <Avatar
              name={person.realName}
              accountId={person.accountId}
              imageCode={person.profileImageCode}
              size="large"
            />
            <div>
              <h2>{person.realName}</h2>
              <SchoolVerificationBadge />
            </div>
          </div>
          <ProfileDetails profile={person} />
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
          autoComplete="username"
          autoCapitalize="none"
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
            autoComplete="current-password"
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
  if (!value || !value.startsWith('/')) return '/workspace';
  try {
    const url = new URL(value, 'https://preview.invalid');
    // 외부 주소·프로토콜 상대 주소·경로 이동(./, ../) 세그먼트는 앱 안의 기본 화면으로 돌립니다.
    if (
      url.origin !== 'https://preview.invalid' ||
      /(^|\/)\.\.?(\/|$)/.test(value.split(/[?#]/)[0] ?? '')
    )
      return '/workspace';
    if (['/login', '/signup'].includes(url.pathname)) return '/workspace';
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return '/workspace';
  }
}

// [출처 2, 6] 로그인, 안전한 returnTo 복귀
export function LoginPage() {
  const { signIn } = useDemo();
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
        <p className="dreamon-login-story-signature">
          <img
            src="/brand/dreamon-wordmark.svg"
            alt="서경드림온"
            width={180}
            height={42}
          />
        </p>
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
          <Link to={`/signup?returnTo=${encodeURIComponent(returnTo)}`}>
            회원가입
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </section>
    </div>
  );
}

// [출처 2] 가입 입력 규칙 확인(실제 계정 발급 없음)
export function SignupPage() {
  const { saveProfile, signOut, profile } = useDemo();
  const [search] = useSearchParams();
  const returnTo = safeReturnTo(search.get('returnTo') ?? search.get('from'));
  const [complete, setComplete] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const {
    register,
    control,
    handleSubmit,
    resetField,
    formState: { errors, isSubmitting },
  } = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    mode: 'onChange',
    defaultValues: {
      username: '',
      password: '',
      realName: '',
      roleCodes: [],
      fieldCodes: [],
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
            <Link to={`/login?returnTo=${encodeURIComponent('/profile')}`}>
              로그인
            </Link>
          </Button>
        </div>
      </div>
    );
  return (
    <div className="preview-detail preview-stack preview-account-page">
      <BackLink to={`/login?returnTo=${encodeURIComponent(returnTo)}`}>
        로그인으로
      </BackLink>
      <PageIntro title="회원가입" />
      <form
        className="preview-panel preview-form"
        noValidate
        onSubmit={handleSubmit((values) => {
          // 가입 화면 확인용: 필수 항목만 담은 새 프로필(기본 비공개). 계정 정보는 프로필에 넣지 않음
          saveProfile({
            ...profile,
            realName: values.realName.trim(),
            roleCodes: values.roleCodes,
            fieldCodes: values.fieldCodes,
            profileImageCode: null,
            academicStatusCode: null,
            gradeCode: null,
            weeklyAvailabilityCode: null,
            academicUnitId: null,
            experienceState: 'unspecified',
            experienceBody: null,
            introduction: null,
            skillCodes: [],
            portfolio: null,
            isPublic: false,
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
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            aria-invalid={!!errors.username}
            aria-describedby={
              errors.username ? 'signup-username-error' : undefined
            }
          />
          <p className="preview-muted">
            영문 소문자와 숫자 4~24자. 대문자는 소문자로 바뀌어요.
          </p>
          <FieldError
            id="signup-username-error"
            message={errors.username?.message}
          />
        </div>
        <div className="preview-field">
          <Label htmlFor="signup-password">비밀번호 (필수)</Label>
          <div className="dreamon-login-password">
            <Input
              id="signup-password"
              type={showPassword ? 'text' : 'password'}
              {...register('password')}
              autoComplete="new-password"
              aria-invalid={!!errors.password}
              aria-describedby={
                errors.password
                  ? 'signup-password-error signup-password-help'
                  : 'signup-password-help'
              }
            />
            <Button
              type="button"
              variant="ghost"
              className="dreamon-login-reveal"
              aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
              aria-controls="signup-password"
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
          <p id="signup-password-help" className="preview-muted">
            15~128자. 한글과 공백을 사용할 수 있으며 앞뒤 공백도 비밀번호에
            포함돼요.
          </p>
          <FieldError
            id="signup-password-error"
            message={errors.password?.message}
          />
        </div>
        <div className="preview-field">
          <Label htmlFor="signup-name">이름 (필수)</Label>
          <Input
            id="signup-name"
            {...register('realName')}
            autoComplete="off"
            aria-invalid={!!errors.realName}
            aria-describedby={errors.realName ? 'signup-name-error' : undefined}
          />
          <FieldError
            id="signup-name-error"
            message={errors.realName?.message}
          />
        </div>
        <Controller
          control={control}
          name="fieldCodes"
          render={({ field }) => (
            <ChoiceField
              id="signup-interests"
              label="관심 분야"
              options={fieldOptions}
              {...field}
              error={errors.fieldCodes?.message}
            />
          )}
        />
        <Controller
          control={control}
          name="roleCodes"
          render={({ field }) => (
            <ChoiceField
              id="signup-roles"
              label="희망 역할"
              options={roleOptions}
              {...field}
              error={errors.roleCodes?.message}
            />
          )}
        />
        <SchoolVerificationBadge />
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
