// docs/api/ai.md: 결과 표시는 검증 후에만 허용하며 선발 동작은 지원서 화면에서 수행합니다.
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router';
import { Copy, LoaderCircle, RotateCcw, Sparkles } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import type { AiResult, ProfileVersion } from '@/features/ai/contract';
import { useSession } from '@/features/auth/queries';
import { sessionGeneration } from '@/lib/query-keys';
import { useTargetAi } from './use-target-ai';

type Props = {
  purpose: 'applicant_review' | 'applicant_recommendation';
  targetId: string;
  revision: string;
};
function resultText(value: AiResult) {
  if (value.kind === 'chat') return value.answer;
  if (value.kind === 'applicant_review')
    return [value.summary, ...value.evidence].join('\n\n');
  return [
    value.summary,
    ...value.candidates.map((candidate) => candidate.reason),
  ].join('\n\n');
}
function ProfileVersionNote({ version }: { version: ProfileVersion }) {
  return (
    <p className="preview-muted">
      검토한 프로필 버전 {version.usedVersion} · 현재 버전{' '}
      {version.currentVersion}
    </p>
  );
}

export function TargetAiPanel(props: Props) {
  const client = useQueryClient();
  const { account } = useSession();
  if (!account) return null;
  const generation = sessionGeneration(client);
  return (
    <TargetAiSession
      key={`${account.id}:${generation}:${props.purpose}:${props.targetId}`}
      {...props}
      ownerId={account.id}
      generation={generation}
    />
  );
}

function TargetAiSession(
  props: Props & { ownerId: string; generation: number },
) {
  const ai = useTargetAi(props);
  const review = props.purpose === 'applicant_review';
  const heading = review ? 'AI 검토 도움' : 'AI 지원자 추천';
  const titleId = `${props.purpose}-${props.targetId}`;
  const pending = ai.state.phase === 'pending' || ai.state.phase === 'checking';
  return (
    <section
      className="preview-panel preview-stack min-w-0"
      aria-labelledby={titleId}
    >
      <div className="preview-row">
        <Sparkles size={20} aria-hidden="true" />
        <h2 id={titleId}>{heading}</h2>
      </div>
      <p className="preview-muted">
        {review
          ? '현재 지원서와 프로필로 검토해요. 모집이 마감되거나 정원이 차도 검토할 수 있어요.'
          : '접수된 지원서 중 현재 선발 가능한 후보를 추천해요. 추천을 받아도 지원 상태는 바뀌지 않아요.'}
      </p>
      {pending && (
        <div className="preview-stack" aria-busy="true">
          <p role="status" className="preview-muted">
            {ai.state.message}
          </p>
          {ai.state.text && (
            <p className="whitespace-pre-wrap break-words">{ai.state.text}</p>
          )}
          <div className="preview-row">
            <Button
              type="button"
              variant="outline"
              disabled={ai.canceling}
              onClick={() => void ai.cancel()}
            >
              요청 취소
            </Button>
            {ai.state.phase === 'checking' && (
              <Button
                type="button"
                variant="outline"
                disabled={ai.canceling}
                onClick={() => void ai.checkStatus()}
              >
                요청 상태 확인
              </Button>
            )}
          </div>
        </div>
      )}
      {ai.validating && (
        <p role="status" className="preview-muted">
          결과와 현재 지원 정보를 확인하고 있어요.
        </p>
      )}
      {!pending && ai.state.message && (
        <p
          role={ai.state.phase === 'failed' ? 'alert' : 'status'}
          className="preview-muted"
        >
          {ai.state.message}
        </p>
      )}
      {ai.validationError && (
        <Alert role="alert">
          <AlertDescription>{ai.validationError}</AlertDescription>
        </Alert>
      )}
      {ai.result && ai.result.kind !== 'chat' && (
        <div
          className="preview-stack"
          role="region"
          aria-label={review ? 'AI 지원자 검토 결과' : 'AI 지원자 추천 결과'}
        >
          {ai.result.isStale && (
            <Alert role="note">
              <AlertDescription>
                검토 이후 프로필이 변경됐어요. 아래는 이전 정보를 사용한
                결과예요. 최신 정보로 다시 요청해 주세요.
              </AlertDescription>
            </Alert>
          )}
          <p className="whitespace-pre-wrap break-words">{ai.result.summary}</p>
          {ai.result.kind === 'applicant_review' ? (
            <>
              {!!ai.result.evidence.length && (
                <ul className="preview-stack list-disc pl-5">
                  {ai.result.evidence.map((evidence, index) => (
                    <li key={index} className="whitespace-pre-wrap break-words">
                      {evidence}
                    </li>
                  ))}
                </ul>
              )}
              {ai.result.profileVersions.map((version) => (
                <ProfileVersionNote key={version.accountId} version={version} />
              ))}
              {!ai.result.isSelectionCandidate && (
                <p className="preview-muted">
                  현재 선발 후보가 아닌 지원서예요. 이 결과는 기존 지원 내용을
                  검토하는 참고 자료예요.
                </p>
              )}
            </>
          ) : ai.result.candidates.length ? (
            <ol className="preview-stack list-decimal pl-5">
              {ai.result.candidates.map((candidate, index) => (
                <li
                  key={candidate.applicationId}
                  className="preview-stack min-w-0"
                >
                  <Link
                    className="preview-text-link"
                    to={`/applicants/${candidate.applicationId}`}
                  >
                    추천 후보 {index + 1} 지원서 확인
                  </Link>
                  <p className="whitespace-pre-wrap break-words">
                    {candidate.reason}
                  </p>
                  <ProfileVersionNote version={candidate.profileVersion} />
                </li>
              ))}
            </ol>
          ) : (
            <p className="preview-muted">
              현재 추천할 수 있는 지원자가 없어요.
            </p>
          )}
          <Button
            type="button"
            variant="outline"
            onClick={() => void ai.copy(resultText)}
          >
            <Copy size={16} aria-hidden="true" />
            결과 복사
          </Button>
        </div>
      )}
      {ai.copied && <p role="status">결과를 복사했어요.</p>}
      <div className="preview-row">
        <Button
          type="button"
          variant="outline"
          disabled={pending || ai.validating}
          onClick={() => void ai.run(false)}
        >
          {pending || ai.validating ? (
            <LoaderCircle
              size={16}
              className="animate-spin motion-reduce:animate-none"
              aria-hidden="true"
            />
          ) : (
            <Sparkles size={16} aria-hidden="true" />
          )}
          {pending
            ? review
              ? '검토하는 중…'
              : '추천하는 중…'
            : ai.result
              ? review
                ? '다시 검토하기'
                : '다시 추천받기'
              : review
                ? 'AI 검토 요청'
                : 'AI 지원자 추천 요청'}
        </Button>
        {ai.canRetry && !pending && (
          <Button
            type="button"
            variant="outline"
            onClick={() => void ai.run(true)}
          >
            <RotateCcw size={16} aria-hidden="true" />
            {review ? '검토 다시 시도' : '추천 다시 시도'}
          </Button>
        )}
        {ai.validationError && ai.canValidate && (
          <Button
            type="button"
            variant="outline"
            disabled={ai.validating}
            onClick={() => void ai.revalidate()}
          >
            결과 다시 확인
          </Button>
        )}
      </div>
      <p className="preview-muted">
        AI 결과는 참고용이에요. 지원 내용은 직접 확인하고, 선발 여부는 팀장이
        결정해 주세요.
      </p>
    </section>
  );
}
