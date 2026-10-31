/** 차트 청크·렌더링 오류를 차트 영역 안에서 처리합니다. */
import { Component, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';

type Props = { children: ReactNode };
type State = { failed: boolean };

export class ApplicantChartBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="comparison-chart-empty gap-3">
        <p role="alert">
          차트를 불러오지 못했어요.
          <br />
          새로고침 후 평가를 다시 요청해 주세요.
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => window.location.reload()}
        >
          화면 새로고침
        </Button>
      </div>
    );
  }
}
