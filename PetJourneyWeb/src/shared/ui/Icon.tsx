import type { SVGProps } from "react";

/**
 * 内联图标集（无外部字体/CDN 依赖）。stroke 使用 currentColor。
 * 用 satisfies 而不是声明成 Record<string, string>：这样 IconName 是实际图标名的联合类型，
 * 写一个不存在的名字（例如 "map"）tsc 就会报错，而不是在页面上悄悄画出空图标。
 */
const PATHS = {
  home: "M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-4.5v-5.5h-5V21H5a1 1 0 0 1-1-1z",
  journey: "M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6zM9 4v14M15 6v14",
  planet: "M12 19a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM3 14.5c-1.2 1.6-1.4 2.9-.6 3.6 1.6 1.4 7.1-1 12.3-5.4S22.5 4.6 21 3.3c-.7-.6-2-.4-3.6.5",
  chat: "M5 5h14a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H10l-4 3v-3H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z",
  plane: "M10.5 21 12 17l-1-5-7 2.5V12l7-4.5V4.2a1.2 1.2 0 0 1 2.4 0V7.5L20.5 12v2.5l-7-2.5-1 5 1.5 4z",
  train: "M7 3h10a2 2 0 0 1 2 2v10a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V5a2 2 0 0 1 2-2zM5 11h14M9 15h.01M15 15h.01M8 18l-2 3M16 18l2 3",
  ship: "M4 15l1.5 4.5c2 .7 4.3.7 6.5 0 2.2.7 4.5.7 6.5 0L20 15l-8-3zM7 13V8h10v5M10 8V5h4v3",
  car: "M5 16v2.5M19 16v2.5M4 16h16v-4l-2-5H6l-2 5zM7.5 13.5h.01M16.5 13.5h.01",
  music: "M9 18V6l10-2v12M9 18a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM19 16a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z",
  tv: "M4 7h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1zM8 3l4 4 4-4",
  pause: "M8 5v14M16 5v14",
  play: "M7 4.5v15l12-7.5z",
  back: "M15 5l-7 7 7 7",
  close: "M6 6l12 12M18 6 6 18",
  lock: "M7 11V8a5 5 0 0 1 10 0v3M6 11h12v9H6z",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5M12 8h.01",
  coin: "M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM12 8v8M9.5 10.5c0-1 1.1-1.5 2.5-1.5s2.5.6 2.5 1.6c0 2.3-5 1.2-5 3.6 0 1 1.1 1.8 2.5 1.8s2.5-.6 2.5-1.5",
  sprout: "M12 21v-8M12 13c0-4 3-6 7-6 0 4-3 6-7 6zM12 15c0-3-2.5-5-6-5 0 3 2.5 5 6 5z",
  sparkle: "M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z",
  camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z",
  cup: "M5 8h11v6a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5zM16 10h1.5a2.5 2.5 0 0 1 0 5H16M8 3v2M11 3v2",
  seat: "M7 4h8v9H7zM5 13h12v3H5zM7 16v4M15 16v4",
  wave: "M3 12c2-2 4-2 6 0s4 2 6 0 4-2 6 0M3 17c2-2 4-2 6 0s4 2 6 0 4-2 6 0",
  check: "M5 12.5l4.5 4.5L19 7",
  alert: "M12 4l9 16H3zM12 10v4M12 17h.01",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  bookmark: "M7 4h10v17l-5-4-5 4z",
  pin: "M12 21s7-6.2 7-11.5a7 7 0 0 0-14 0C5 14.8 12 21 12 21zM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  heart: "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z",
  comment: "M4 5h16v11H9l-5 4z",
  compass: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM15.5 8.5l-2 5-5 2 2-5z",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  locate: "M12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM12 2v4M12 18v4M2 12h4M18 12h4",
  chevron: "M9 5l7 7-7 7",
  mail: "M4 6h16v12H4zM4 7l8 6 8-6",
  gift: "M4 10h16v4H4zM6 14h12v7H6zM12 10v11M12 10c-2.5 0-4.5-1-4.5-3S9 4.5 12 10zM12 10c2.5 0 4.5-1 4.5-3S15 4.5 12 10z",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14.2 3h-4.4l-.4 2.7a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2l.4 2.7h4.4l.4-2.7a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z",
} satisfies Record<string, string>;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, strokeWidth = 1.8, ...rest }: { name: IconName; size?: number; strokeWidth?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
