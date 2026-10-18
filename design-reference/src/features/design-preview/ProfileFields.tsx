import {
  Controller,
  useWatch,
  type Control,
  type UseFormRegister,
  type UseFormSetValue,
} from 'react-hook-form';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  NativeSelect,
  NativeSelectOption,
} from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import type { Profile } from './data';
import {
  academicOptions,
  academicStatuses,
  grades,
  skillOptions,
} from './profile-fields';

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
        공고에 학적·학년 조건이 있으면 지원할 때 필요한 정보를 확인해요.
      </p>
      <div className="profile-academic-fields">
        {(
          [
            ['academicStatus', '학적 상태', academicStatuses],
            ['grade', '학년', grades],
          ] as const
        ).map(([name, label, choices]) => (
          <div className="preview-field" key={name}>
            <Label htmlFor={`profile-${name}`}>{label}</Label>
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
                field.onChange(event);
                setValue('department', '', { shouldDirty: true });
                setValue('major', '', { shouldDirty: true });
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
                field.onChange(event);
                setValue('major', '', { shouldDirty: true });
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
        소속을 바꾸면 하위 학부·전공을 다시 선택해 주세요. 기존 소속은 변경하기
        전까지 유지돼요.
      </p>
    </section>
  );
}

export function SkillFields({
  control,
  register,
}: {
  control: Control<Profile>;
  register: UseFormRegister<Profile>;
}) {
  const skills = useWatch({ control, name: 'skills' });
  return (
    <fieldset className="preview-field">
      <legend>
        보유 역량 <span className="preview-muted">(권장 · 복수 선택)</span>
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
      {skills.includes('기타') && (
        <div className="preview-field">
          <Label htmlFor="profile-skill-other">기타 역량 설명 (선택)</Label>
          <Input
            id="profile-skill-other"
            {...register('skillOther')}
            placeholder="목록에 없는 역량을 알려 주세요."
          />
        </div>
      )}
    </fieldset>
  );
}

export function ExperienceFields({
  control,
  register,
  setValue,
}: {
  control: Control<Profile>;
  register: UseFormRegister<Profile>;
  setValue: UseFormSetValue<Profile>;
}) {
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
                setValue('experience', '', { shouldDirty: true });
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
      <p className="preview-muted">
        경험이 없어도 참여할 수 있어요. 미입력과 경험 없음은 구분해서 저장해요.
      </p>
    </div>
  );
}
