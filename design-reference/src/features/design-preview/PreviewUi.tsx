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
import { previewPath } from './data';
import { PreviewContext } from './preview-context';
import {
  defaultMascotAvatarId,
  mascotAvatarSource,
  type MascotAvatarId,
} from './mascot-avatars';
import './mascot-profile.css';

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
export function BackLink({
  to = previewPath('/explore'),
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
export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'neutral' | 'lime' | 'warm' | 'dark';
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
  const state = useContext(PreviewContext);
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
export function Notice({ children }: { children: ReactNode }) {
  return (
    <Alert role="note" className="preview-notice">
      <Info aria-hidden="true" />
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}
