import React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type LazyBoundaryProps = {
  children: React.ReactNode;
  resetKey?: string;
  fallback?: React.ReactNode;
  className?: string;
};

type LazyBoundaryState = {
  error: Error | null;
};

export class LazyBoundary extends React.Component<LazyBoundaryProps, LazyBoundaryState> {
  state: LazyBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): LazyBoundaryState {
    return { error };
  }

  componentDidUpdate(previousProps: LazyBoundaryProps) {
    if (this.state.error && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className={cn("grid min-h-48 place-items-center rounded-md border border-dashed bg-muted/20 p-4", this.props.className)}>
          <div className="grid max-w-md gap-3 text-center">
            <div className="font-medium">页面资源加载失败</div>
            <div className="break-anywhere text-sm text-muted-foreground">{this.state.error.message}</div>
            <Button variant="outline" onClick={() => window.location.reload()}>
              重新加载
            </Button>
          </div>
        </div>
      );
    }

    return <React.Suspense fallback={this.props.fallback || <LazyFallback className={this.props.className} />}>{this.props.children}</React.Suspense>;
  }
}

export function LazyFallback({ className, label = "正在加载页面..." }: { className?: string; label?: string }) {
  return (
    <div className={cn("grid min-h-48 place-items-center rounded-md border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground", className)}>
      {label}
    </div>
  );
}
