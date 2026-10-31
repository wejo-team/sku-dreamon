/** 공통 100점 축에서 항목별 점수와 별도 정보 상태를 비교합니다. */
import { useId } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
  YAxis,
  type BarShapeProps,
  type YAxisTickContentProps,
} from 'recharts';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import type { ApplicantRecommendation } from '@/features/ai/contract';
import { criterionKeys, criterionLabels } from './assessment-ui';
import {
  ApplicantScoreBar,
  AssessmentMissingPattern,
} from './ApplicantScoreBar';

export default function ApplicantComparisonChart({
  candidates,
  colorSlots,
}: {
  candidates: ApplicantRecommendation[];
  colorSlots: number[];
}) {
  const patternId = `missing-${useId().replace(/:/g, '')}`;
  const config: ChartConfig = Object.fromEntries(
    candidates.map((candidate, index) => [
      `candidate${index}`,
      {
        label: candidate.title,
        color: `var(--comparison-series-${colorSlots[index]})`,
      },
    ]),
  );
  const data = criterionKeys.map((key) => {
    const scores: Record<string, number | null> = Object.fromEntries(
      candidates.map((candidate, index) => [
        `candidate${index}`,
        candidate.assessment.criteria.find((criterion) => criterion.key === key)
          ?.score ?? null,
      ]),
    );
    return {
      label: criterionLabels[key],
      scores,
      // 누락값은 좌표 계산에만 원점을 사용합니다. 막대·숫자·툴팁은 원본 null을 유지합니다.
      ...Object.fromEntries(
        Object.entries(scores).map(([name, score]) => [name, score ?? 0]),
      ),
    };
  });
  return (
    <ChartContainer
      config={config}
      className="h-full w-full aspect-auto"
      initialDimension={{ width: 320, height: 340 }}
    >
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 36, bottom: 0, left: 0 }}
        barGap={6}
        barCategoryGap="24%"
        accessibilityLayer
      >
        <defs>
          <AssessmentMissingPattern id={patternId} />
        </defs>
        <CartesianGrid
          horizontal={false}
          stroke="var(--comparison-grid)"
          strokeDasharray="2 5"
        />
        <XAxis
          type="number"
          domain={[0, 100]}
          ticks={[0, 25, 50, 75, 100]}
          allowDecimals={false}
          axisLine={false}
          tickLine={false}
          tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
          tickMargin={10}
          height={28}
        />
        <YAxis
          type="category"
          dataKey="label"
          axisLine={false}
          tickLine={false}
          tick={({ x, y, payload }: YAxisTickContentProps) => (
            <text
              x={x}
              y={y}
              textAnchor="end"
              dominantBaseline="central"
              fill="var(--foreground)"
              fontSize={12}
              fontWeight={500}
            >
              {payload.value}
            </text>
          )}
          width={68}
          tickMargin={10}
        />
        <ChartTooltip
          position={{ x: 0 }}
          cursor={{ fill: 'var(--comparison-hover)' }}
          content={(props) => (
            <ChartTooltipContent
              className="comparison-score-tooltip"
              active={props.active}
              label={props.label}
              payload={props.payload?.map((entry) => ({
                ...entry,
                value: entry.payload.scores[String(entry.dataKey)] ?? '—',
              }))}
              formatter={(value, name, entry) => (
                <div className="comparison-tooltip-row">
                  <i aria-hidden="true" style={{ background: entry.color }} />
                  <span>{config[String(name)]?.label ?? name}</span>
                  <strong>{String(value)}</strong>
                </div>
              )}
            />
          )}
        />
        {candidates.map((candidate, index) => (
          <Bar
            key={candidate.applicationId}
            dataKey={`candidate${index}`}
            fill={`var(--color-candidate${index})`}
            maxBarSize={18}
            isAnimationActive={false}
            shape={(props: BarShapeProps) => (
              <ApplicantScoreBar
                x={props.x}
                y={props.y}
                width={props.width}
                height={props.height}
                trackWidth={props.background?.width ?? 0}
                score={
                  data[props.originalDataIndex]?.scores[`candidate${index}`] ??
                  null
                }
                color={`var(--color-candidate${index})`}
                label={`${candidate.title}, ${data[props.originalDataIndex]?.label ?? ''}`}
                patternId={patternId}
              />
            )}
          />
        ))}
      </BarChart>
    </ChartContainer>
  );
}
