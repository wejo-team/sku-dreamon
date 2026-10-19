import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router';
import { contests, type Team } from './data';
import { Badge, TeamStatusBadge } from './PreviewUi';

export function TeamCard({
  team,
  to,
  showContest = true,
}: {
  team: Team;
  to: string;
  showContest?: boolean;
}) {
  return (
    <Link className="preview-card preview-team-card" to={to}>
      <div className="preview-row preview-split">
        <TeamStatusBadge team={team} />
        <span className="preview-muted">{team.members}명 활동 중</span>
      </div>
      <h3>{team.name}</h3>
      <p className="preview-card-description">{team.summary}</p>
      <div className="preview-row preview-team-card-roles">
        {team.roles.map((role) => (
          <Badge key={role}>{role}</Badge>
        ))}
        {!showContest && <ChevronRight size={20} aria-hidden="true" />}
      </div>
      {showContest && (
        <div className="preview-card-footer">
          <span>
            {contests.find((item) => item.id === team.contestId)?.title}
          </span>
          <ChevronRight size={20} aria-hidden="true" />
        </div>
      )}
    </Link>
  );
}
