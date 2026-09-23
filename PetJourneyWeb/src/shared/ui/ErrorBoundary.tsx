import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  scope: string;
  compact?: boolean;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** 组件级错误边界：插槽贡献与页面各自隔离，单个模块崩溃不拖垮整个应用。 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[petsoul] ${this.props.scope} crashed`, error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    if (this.props.compact) {
      return (
        <div className="ps-error-boundary" role="alert">
          这一块暂时没显示出来（{this.props.scope}）。
          <button type="button" className="ps-btn ps-btn--ghost ps-btn--sm" onClick={() => this.setState({ error: null })}>
            重试
          </button>
        </div>
      );
    }
    return (
      <div className="ps-state ps-state--error" role="alert">
        <div className="ps-state__title">页面出了点问题</div>
        <div className="ps-muted">{this.props.scope}</div>
        <button type="button" className="ps-btn ps-btn--primary" onClick={() => this.setState({ error: null })}>
          重新加载这一页
        </button>
      </div>
    );
  }
}
