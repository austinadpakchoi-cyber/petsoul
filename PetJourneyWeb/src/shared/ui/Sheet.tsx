import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";

/**
 * 底部面板：不遮挡上方地图、不接管整页（非模态）。Esc / 关闭按钮 / 浏览器返回（由调用方 URL 驱动）均可关闭。
 */
export function Sheet({
  title,
  subtitle,
  onClose,
  children,
  actions,
  className = "",
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  const titleId = useId();
  const root = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    root.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus({ preventScroll: true });
    };
  }, []);
  return createPortal(
    <section
      ref={root}
      tabIndex={-1}
      className={`ps-sheet ${className}`}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
    >
      <div className="ps-sheet__handle" aria-hidden="true" />
      <div className="ps-sheet__head">
        <div className="ps-sheet__title" id={titleId}>
          {title}
          {subtitle ? (
            <div className="ps-muted" style={{ fontWeight: 500 }}>
              {subtitle}
            </div>
          ) : null}
        </div>
        {actions}
        <button
          type="button"
          className="ps-btn ps-btn--ghost ps-btn--icon"
          aria-label="收起面板"
          onClick={onClose}
        >
          <Icon name="close" />
        </button>
      </div>
      <div className="ps-sheet__body">{children}</div>
    </section>,
    document.body,
  );
}
