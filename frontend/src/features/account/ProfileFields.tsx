/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ProfileFields.tsx - 프로필 입력 필드 원본
 * 2. docs/specs/profile-options.md - 학적·학년·역량·주당 시간 선택지
 * 3. docs/specs/profile.md#experience - 경험 미입력/경험 없음/서술 3상태
 * 4. docs/design/assets/profile-320.png - 실제 수정 화면
 */

import {
  Controller,
  useWatch,
  type Control,
  type UseFormRegister,
  type UseFormSetValue,
} from 'react-hook-form';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import {
  NativeSelect,
  NativeSelectOption,
} from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import type { Profile } from '@/features/demo/data';
import {
  academicOptions,
  academicStatuses,
  grades,
  skillOptions,
  profileTextLength,
} from '@/features/demo/profile-fields';

function SelectOptions({
  options,
  value,
}: {
  options: readonly string[];
  value: string;
}) {
  return (
    <>
      <NativeSelectOption value="">선택 안 함</NativeSelectOption>
      {value && !options.includes(value) && (
        <NativeSelectOption value={value} disabled>
          {value} (기존 소속)
        </NativeSelectOption>
      )}
      {options.map((option) => (
        <NativeSelectOption key={option} value={option}>
          {option}
        </NativeSelectOption>
      ))}
    </>
  );
}

// [출처 2, 4] 학사 종속 선택, 다른 소속 관계로 이동하면 무효 하위값만 비움
export function AcademicFields({
  control,
  setValue,
}: {
  control: Control<Profile>;
  setValue: UseFormSetValue<Profile>;
}) {
  const college = useWatch({ control, name: 'college' }) ?? '';
  const department = useWatch({ control, name: 'department' }) ?? '';
  const major = useWatch({ control, name: 'major' }) ?? '';
  const options = academicOptions(college, department);
  return (
    <section
      className="preview-form-section"
      aria-labelledby="profile-academic-heading"
    >
      <h2 id="profile-academic-heading" className="preview-section-title">
        학사 정보
      </h2>
      <p className="preview-muted">
        선택 입력이에요. 비워 두어도 지원할 수 있으며, 참가 자격은 공고 원문을
        확인해 주세요.
      </p>
      <div className="profile-academic-fields">
        {(
          [
            ['academicStatus', '학적 상태', academicStatuses],
            ['grade', '학년', grades],
          ] as const
        ).map(([name, label, choices]) => (
          <div className="preview-field" key={name}>
            <Label htmlFor={`profile-${name}`}>{label} (선택)</Label>
            <Controller
              control={control}
              name={name}
              render={({ field }) => (
                <NativeSelect
                  {...field}
                  value={field.value ?? ''}
                  id={`profile-${name}`}
                >
                  <SelectOptions options={choices} value={field.value ?? ''} />
                </NativeSelect>
              )}
            />
          </div>
        ))}
      </div>
      <div className="preview-field">
        <Label htmlFor="profile-college">단과대학 (선택)</Label>
        <Controller
          control={control}
          name="college"
          render={({ field }) => (
            <NativeSelect
              {...field}
              value={college}
              id="profile-college"
              onChange={(event) => {
                const nextCollege = event.target.value;
                field.onChange(event);
                // Display names alone cannot prove identity across colleges.
                // Keep the existing relationship when it remains the same.
                if (nextCollege !== college) {
                  setValue('department', '', { shouldDirty: true });
                  setValue('major', '', { shouldDirty: true });
                }
              }}
            >
              <SelectOptions options={options.colleges} value={college} />
            </NativeSelect>
          )}
        />
      </div>
      <div className="preview-field">
        <Label htmlFor="profile-department">학부·학과 (선택)</Label>
        <Controller
          control={control}
          name="department"
          render={({ field }) => (
            <NativeSelect
              {...field}
              value={department}
              disabled={!college}
              id="profile-department"
              onChange={(event) => {
                const nextDepartment = event.target.value;
                field.onChange(event);
                if (nextDepartment !== department) {
                  setValue('major', '', { shouldDirty: true });
                }
              }}
            >
              <SelectOptions options={options.departments} value={department} />
            </NativeSelect>
          )}
        />
      </div>
      {(options.majors.length > 0 || major) && (
        <div className="preview-field">
          <Label htmlFor="profile-major">세부전공 (선택)</Label>
          <Controller
            control={control}
            name="major"
            render={({ field }) => (
              <NativeSelect
                {...field}
                value={major}
                disabled={!department}
                id="profile-major"
              >
                <SelectOptions options={options.majors} value={major} />
              </NativeSelect>
            )}
          />
        </div>
      )}
      <p className="preview-muted">
        소속을 바꾸면 새 소속에 맞지 않는 하위 항목만 비워요. 저장 전까지는 기존
        프로필이 유지돼요.
      </p>
    </section>
  );
}

// [출처 2] 목록 내 역량 선택
export function SkillFields({ control }: { control: Control<Profile> }) {
  return (
    <fieldset className="preview-field">
      <legend>
        보유 역량 <span className="preview-muted">(선택 · 복수 선택)</span>
      </legend>
      <Controller
        control={control}
        name="skills"
        render={({ field }) => (
          <div className="preview-row">
            {skillOptions.map((skill) => (
              <Label
                key={skill}
                htmlFor={`profile-skill-${skill}`}
                className="preview-choice"
              >
                <Checkbox
                  id={`profile-skill-${skill}`}
                  checked={field.value.includes(skill)}
                  onCheckedChange={(checked) =>
                    field.onChange(
                      checked === true
                        ? [...field.value, skill]
                        : field.value.filter((value) => value !== skill),
                    )
                  }
                />
                {skill}
              </Label>
            ))}
          </div>
        )}
      />
    </fieldset>
  );
}

// [출처 3] 경험 3상태
export function ExperienceFields({
  control,
  register,
  setValue,
  error,
}: {
  control: Control<Profile>;
  register: UseFormRegister<Profile>;
  setValue: UseFormSetValue<Profile>;
  error?: string;
}) {
  const experience = useWatch({ control, name: 'experience' });
  const experienceState = useWatch({ control, name: 'experienceState' });
  return (
    <div className="preview-field">
      <Label htmlFor="profile-experience-state">경험 등록 상태 (선택)</Label>
      <Controller
        control={control}
        name="experienceState"
        render={({ field }) => (
          <NativeSelect
            {...field}
            id="profile-experience-state"
            onChange={(event) => {
              field.onChange(event);
              if (event.target.value !== 'provided')
                setValue('experience', '', {
                  shouldDirty: true,
                  shouldValidate: true,
                });
            }}
          >
            <NativeSelectOption value="unspecified">
              아직 입력하지 않음
            </NativeSelectOption>
            <NativeSelectOption value="none">관련 경험 없음</NativeSelectOption>
            <NativeSelectOption value="provided">경험 작성</NativeSelectOption>
          </NativeSelect>
        )}
      />
      <Label htmlFor="profile-experience">관련 경험 (선택)</Label>
      <Textarea
        id="profile-experience"
        rows={3}
        aria-invalid={!!error}
        aria-describedby="profile-experience-help profile-experience-count profile-experience-error"
        disabled={experienceState === 'none'}
        {...register('experience', {
          onChange: (event: { target: { value: string } }) =>
            setValue(
              'experienceState',
              event.target.value.trim() ? 'provided' : 'unspecified',
              { shouldDirty: true },
            ),
        })}
        placeholder="프로젝트나 공모전에서 맡았던 역할"
      />
      <p id="profile-experience-count" className="preview-field-count">
        {profileTextLength(experience)} / 500자
      </p>
      {error && (
        <p id="profile-experience-error" className="preview-error" role="alert">
          {error}
        </p>
      )}
      <p id="profile-experience-help" className="preview-muted">
        경험이 없어도 참여할 수 있어요. 미입력과 경험 없음은 구분해서 저장해요.
      </p>
    </div>
  );
}
