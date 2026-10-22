/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/PreviewUi.tsx - 공통 표시 컴포넌트 원본
 * 2. docs/design/tokens.md - 「shadcn/ui 사용 맵」 TeamStatusBadge·SchoolVerificationBadge, 상태는 색과 문구로 함께 표시
 * 3. docs/design/screens.md - 루트 화면 h1.sr-only, 상세 제목 표시, 로그인 안내와 복귀 링크
 * 4. docs/design/assets.md - 파워프렌즈 마스코트 이미지 출처
 * 5. docs/design/assets/workspace-390.png - 모집 중(녹색)/모집 마감(회색) 배지
 */

import { useContext, useState, type ReactNode } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  CircleHelp,
  Info,
  LockKeyhole,
  SearchX,
} from 'lucide-react';
import { Link } from 'react-router';
import { Badge as UiBadge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
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
import { type Team } from '@/features/demo/data';
import { DemoContext } from '@/features/demo/demo-context';
import { recruitmentIssue, teamStatusLabel } from '@/features/demo/team-state';
import {
  defaultMascotAvatarId,
  mascotAvatarSource,
  type MascotAvatarId,
} from '@/features/demo/mascot-avatars';

// [출처 3] 화면 제목·설명 (루트 화면은 sr-only)
export function PageIntro({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="preview-page-intro">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}
// [출처 3] 상세 화면의 복귀 링크
export function BackLink({
  to = '/explore',
  children = '탐색으로',
}: {
  to?: string;
  children?: ReactNode;
}) {
  return (
    <Link to={to} className="preview-back">
      <ArrowLeft size={18} aria-hidden="true" />
      {children}
    </Link>
  );
}
// [출처 2] 읽기 전용 상태 배지
export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'neutral' | 'lime' | 'warm' | 'dark' | 'recruiting' | 'closed';
}) {
  return (
    <UiBadge
      variant="secondary"
      className={`preview-badge preview-badge--${tone} shrink overflow-visible border-0 whitespace-normal`}
    >
      {children === '비공개' && <LockKeyhole size={12} aria-hidden="true" />}
      {children}
    </UiBadge>
  );
}
// [출처 2, 5] 모집 상태: 녹색·회색 면 + 상태 문구
export function TeamStatusBadge({ team }: { team: Team }) {
  return (
    <Badge tone={recruitmentIssue(team) ? 'closed' : 'recruiting'}>
      {teamStatusLabel(team)}
    </Badge>
  );
}
// [출처 2] 교내 미인증(빨강)/인증(파랑) 배지, 현재 계정은 모두 미인증
export function SchoolVerificationBadge({
  verified = false,
  interactive = false,
}: {
  verified?: boolean;
  interactive?: boolean;
}) {
  const badge = (
    <UiBadge className="preview-school-badge" data-verified={verified}>
      {verified ? (
        <BadgeCheck aria-hidden="true" />
      ) : (
        <CircleHelp aria-hidden="true" />
      )}
      {verified ? '교내 인증' : '교내 미인증'}
    </UiBadge>
  );
  if (verified || !interactive) return badge;
  return (
    <Drawer shouldScaleBackground={false} autoFocus>
      <DrawerTrigger asChild>
        <button
          type="button"
          className="preview-school-trigger"
          aria-label="교내 미인증, 학교 인증 안내"
        >
          {badge}
        </button>
      </DrawerTrigger>
      <DrawerContent className="dreamon-preview preview-drawer">
        <DrawerHeader>
          <DrawerTitle>학교 인증 안내</DrawerTitle>
          <DrawerDescription>
            학교 인증은 아직 제공하지 않는 기능이에요. 현재는 모든 계정이 교내
            미인증으로 표시돼요.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerFooter>
          <DrawerClose asChild>
            <Button type="button" className="preview-button">
              확인
            </Button>
          </DrawerClose>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
// [출처 3] 빈 결과·로그인 안내·없는 경로
export function EmptyState({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="preview-empty">
      <SearchX size={32} strokeWidth={1.5} aria-hidden="true" />
      <h2>{title}</h2>
      <p>{description}</p>
      {children}
    </div>
  );
}
const avatarByPersonId: Record<string, MascotAvatarId> = {
  me: 'skon',
  seoyeon: 'arti',
  doyun: 'dmo',
  sua: 'bart',
  minjae: 'conver',
  'app-seoyeon': 'arti',
  'app-sua': 'bart',
};

// [출처 4] 선택형 마스코트 아바타, 기본 스콘
export function Avatar({
  name,
  personId = 'me',
  avatarId,
  size = 'normal',
}: {
  name: string;
  personId?: string;
  avatarId?: MascotAvatarId;
  size?: 'normal' | 'large';
}) {
  const state = useContext(DemoContext);
  const profileAvatar =
    personId === 'me'
      ? state?.profile.avatarId
      : state?.applicants.find((applicant) => applicant.personId === personId)
          ?.profile?.avatarId;
  const source = mascotAvatarSource(
    avatarId ??
      profileAvatar ??
      avatarByPersonId[personId] ??
      defaultMascotAvatarId,
  );
  const [failedSource, setFailedSource] = useState<string | null>(null);
  return (
    <span
      className={`preview-avatar preview-avatar--mascot preview-avatar--${size}`}
      aria-hidden="true"
    >
      {failedSource === source ? (
        name.slice(-2)
      ) : (
        <img
          key={source}
          src={source}
          alt=""
          width={80}
          height={80}
          decoding="async"
          onError={() => setFailedSource(source)}
        />
      )}
    </span>
  );
}
// [출처 2] 주요 행동 링크(Button + Link)
export function ActionLink({
  to,
  children,
  secondary = false,
}: {
  to: string;
  children: ReactNode;
  secondary?: boolean;
}) {
  return (
    <Button
      asChild
      variant={secondary ? 'outline' : 'default'}
      className="preview-button"
    >
      <Link to={to}>
        {children}
        <ArrowRight size={17} aria-hidden="true" />
      </Link>
    </Button>
  );
}
// [출처 2] 확인·주의 안내 문구
export function Notice({ children }: { children: ReactNode }) {
  return (
    <Alert role="note" className="preview-notice">
      <Info aria-hidden="true" />
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}
