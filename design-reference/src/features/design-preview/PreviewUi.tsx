import { useState, type ReactNode } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Info,
  LockKeyhole,
  SearchX,
} from 'lucide-react';
import { Link } from 'react-router';
import { Badge as UiBadge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { previewPath } from './data';

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
const avatarByPersonId: Record<string, string> = {
  me: 'avatar-01',
  seoyeon: 'avatar-02',
  doyun: 'avatar-03',
  sua: 'avatar-04',
  'app-seoyeon': 'avatar-02',
  'app-sua': 'avatar-04',
};

export function Avatar({
  name,
  personId = 'me',
  size = 'normal',
}: {
  name: string;
  personId?: string;
  size?: 'normal' | 'large';
}) {
  const source = `/profile-avatars/${avatarByPersonId[personId] ?? 'avatar-01'}.webp`;
  const [failedSource, setFailedSource] = useState<string | null>(null);
  return (
    <span
      className={`preview-avatar preview-avatar--${size}`}
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
