/** 실제 0점과 누락된 점수를 구별하는 공통 SVG 막대입니다. */
export function ApplicantScoreBar({
  x,
  y,
  width,
  height,
  trackWidth,
  score,
  color,
  label,
  patternId,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  trackWidth: number;
  score: number | null;
  color: string;
  label: string;
  patternId: string;
}) {
  const missing = score === null;
  return (
    <g
      role="img"
      aria-label={`${label}: ${missing ? '정보 부족으로 점수 없음' : `${score}점`}`}
      data-information-status={missing ? 'insufficient' : 'sufficient'}
      data-score={score ?? undefined}
      className="assessment-score-mark"
    >
      <rect
        x={x}
        y={y}
        width={trackWidth}
        height={height}
        rx={height / 2}
        fill={missing ? `url(#${patternId})` : 'var(--comparison-track)'}
        stroke={missing ? color : 'none'}
        strokeOpacity={missing ? 0.55 : undefined}
        strokeDasharray={missing ? '3 4' : undefined}
      />
      {!missing && score > 0 && (
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          rx={height / 2}
          fill={color}
        />
      )}
      {!missing && score === 0 && (
        <line
          x1={x}
          x2={x}
          y1={y + 2}
          y2={y + height - 2}
          stroke={color}
          strokeWidth={2}
        />
      )}
      <text
        x={x + trackWidth + 9}
        y={y + height / 2}
        dominantBaseline="central"
        fill={missing ? 'var(--muted-foreground)' : 'var(--foreground)'}
        fontSize={12}
        fontWeight={missing ? 400 : 650}
        className="assessment-score-value"
        aria-hidden="true"
      >
        {missing ? '—' : score}
      </text>
    </g>
  );
}

export function AssessmentMissingPattern({ id }: { id: string }) {
  return (
    <pattern
      id={id}
      width={6}
      height={6}
      patternUnits="userSpaceOnUse"
      patternTransform="rotate(35)"
    >
      <rect width={6} height={6} fill="var(--comparison-track)" />
      <line
        x1={0}
        x2={0}
        y1={0}
        y2={6}
        stroke="var(--comparison-missing)"
        strokeWidth={1}
      />
    </pattern>
  );
}
