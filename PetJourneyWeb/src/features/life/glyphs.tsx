/**
 * 卡包图标。证件种类的小图标用 UI-ASSET-005 v1 交付的线性图标（24 网格、描边 1.75、currentColor），
 * 以 CSS mask 着色，颜色跟随文字；交付里没有的（照护档案的文件夹）、徽记里的实心爪印与地球仍用这里手画的，登机牌用共享图标的飞机。
 * 只有符号，不画任何动物形象。
 */
import type { CSSProperties } from "react";
import type { CredentialField, CredentialSummary } from "@/shared/contracts";
import { Icon } from "@/shared/ui";

export type GlyphName = "paw" | "pawline" | "globe" | "folder";

const STROKES: Record<Exclude<GlyphName, "paw">, string> = {
  pawline:
    "M8.5 13.5c-1.9 0-3.5 1.9-3.5 3.6 0 1.4 1.2 1.9 2.4 1.9 1.1 0 1.9-.5 3.1-.5s2 .5 3.1.5c1.2 0 2.4-.5 2.4-1.9 0-1.7-1.6-3.6-3.5-3.6zM5.5 11.5a1.6 2 0 1 0 0-.01zM9.3 8.6a1.7 2.1 0 1 0 0-.01zM14.7 8.6a1.7 2.1 0 1 0 0-.01zM18.5 11.5a1.6 2 0 1 0 0-.01z",
  globe: "M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17zM12 3.5c-2.5 2.3-3.8 5.2-3.8 8.5s1.3 6.2 3.8 8.5M12 3.5c2.5 2.3 3.8 5.2 3.8 8.5s-1.3 6.2-3.8 8.5M3.6 12h16.8M5.2 7.6h13.6M5.2 16.4h13.6",
  folder: "M3.5 7.5a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v8.5a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1zM3.5 10.5h17",
};

export function Glyph({ name, size = 20, className }: { name: GlyphName; size?: number; className?: string }) {
  if (name === "paw") {
    return (
      <svg className={className} viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true" focusable="false">
        <circle cx="6.3" cy="10" r="2.1" />
        <circle cx="9.7" cy="6" r="2.2" />
        <circle cx="14.3" cy="6" r="2.2" />
        <circle cx="17.7" cy="10" r="2.1" />
        <path d="M12 11.8c-2.9 0-5.6 3-5.6 5.4 0 1.7 1.3 2.8 2.9 2.8 1.1 0 1.8-.5 2.7-.5s1.6.5 2.7.5c1.6 0 2.9-1.1 2.9-2.8 0-2.4-2.7-5.4-5.6-5.4z" />
      </svg>
    );
  }
  return (
    <svg className={className} viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={STROKES[name]} />
    </svg>
  );
}

/**
 * UI-ASSET-005 v1 交付的图标（public/ui-assets/UI-ASSET-005/v1/icon-<name>.svg）。
 * 登机牌不用交付的 plane（那一枚是纸飞机 / 发送箭头的样子），仍用共享图标里的飞机，更好认。
 */
export type AssetIconName = "id-card" | "passport" | "ticket" | "key" | "steering-wheel" | "wallet" | "ship" | "train";

export function AssetIcon({ name, size = 18 }: { name: AssetIconName; size?: number }) {
  const style = { width: size, height: size, "--icon": `url("/ui-assets/UI-ASSET-005/v1/icon-${name}.svg")` } as CSSProperties;
  return <span className="ps-asset-icon" data-icon={name} aria-hidden="true" style={style} />;
}

/** 船票车票不单独给交通方式；按服务端写的承运人、班次文字认船还是火车，认不出就用票的图标。 */
function transportIcon(text: string): "ship" | "train" | null {
  if (/轮|船|渡|码头|港口/.test(text)) return "ship";
  if (/铁|列车|火车|动车|高铁/.test(text)) return "train";
  return null;
}

export function KindMark({ summary, fields = [], size = 18 }: { summary: Pick<CredentialSummary, "kind" | "title">; fields?: CredentialField[]; size?: number }) {
  switch (summary.kind) {
    case "boarding_pass":
      return <Icon name="plane" size={size} />;
    case "transport_ticket":
      return <AssetIcon name={transportIcon([summary.title ?? "", ...fields.map((field) => field.value)].join(" ")) ?? "ticket"} size={size} />;
    case "bank_card":
      return <AssetIcon name="wallet" size={size} />;
    case "care_profile":
      return <Glyph name="folder" size={size} />;
    case "passport":
      return <AssetIcon name="passport" size={size} />;
    case "driver_license":
      return <AssetIcon name="steering-wheel" size={size} />;
    case "hotel_key":
      return <AssetIcon name="key" size={size} />;
    default:
      return <AssetIcon name="id-card" size={size} />;
  }
}
