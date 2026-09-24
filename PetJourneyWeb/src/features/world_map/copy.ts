/**
 * 主状态面板的文案：只描述已知事实，不替 TA 编内容。
 * “去打工的路上”和“在打工”严格分开；没有时间就不写“还要几分钟”。
 */
import { minutesLeft, type WorldPet } from "./model";

const HHMM = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });

/** 几点几分（看的人所在时区）。 */
export function clockText(ms: number): string {
  return HHMM.format(ms);
}

export interface PanelCopy {
  /** 一句话：谁在哪、在做什么。 */
  headline: string;
  /** 第二行：地点 / 时间 / 工钱等补充。 */
  detail: string | null;
  /** 路上的进度（0–1）；不在路上为 null。 */
  progress: number | null;
}

function minutesText(minutes: number | null, prefix: string): string | null {
  if (minutes == null) return null;
  return minutes <= 1 ? `${prefix}马上就到` : `${prefix}还要 ${minutes} 分钟`;
}

function joinParts(parts: Array<string | null | undefined>): string | null {
  const kept = parts.filter((p): p is string => Boolean(p && p.trim()));
  return kept.length ? kept.join(" · ") : null;
}

export function panelCopy(pet: WorldPet, nowMs: number, progress: number | null): PanelCopy {
  const { name } = pet;
  const a = pet.activity;
  const left = minutesLeft(a.until, nowMs);
  switch (a.phase) {
    case "home": {
      // 在家时按结构化姿态说一句（后端只在事实确定时给 sleeping 等；idle 就只说在小窝里）。
      const headline =
        pet.activity.pose === "sleeping"
          ? `${name}在小窝里睡觉`
          : pet.activity.pose === "eating"
            ? `${name}在小窝里吃东西`
            : pet.activity.pose === "sunbathing"
              ? `${name}在院子里晒太阳`
              : `${name}在小窝里`;
      return { headline, detail: a.doing ?? (pet.home ? `家在${pet.home.label}` : null), progress: null };
    }
    case "going":
      if (a.kind === "job") {
        return {
          headline: `${name}在去打工的路上`,
          detail: joinParts([a.place ? `去${a.place.name}` : null, a.job?.title, minutesText(left, "")]),
          progress,
        };
      }
      return {
        headline: a.kind === "stroll" ? `${name}出门走走` : a.kind === "cafe" ? `${name}去喝一杯` : `${name}出门了`,
        detail: joinParts([a.place ? `往${a.place.name}去` : a.title, minutesText(left, "")]),
        progress,
      };
    case "there":
      if (a.kind === "job") {
        return {
          headline: `${name}在${a.place?.name ?? "干活的地方"}打工`,
          detail: joinParts([a.doing ?? a.job?.title, a.until != null ? `${clockText(a.until)} 收工` : null, a.job ? `工钱 ${a.job.pay} 星币，收工后到账` : null]),
          progress: null,
        };
      }
      return {
        headline: a.place ? `${name}在${a.place.name}` : `${name}到地方了`,
        detail: joinParts([a.doing, a.since != null ? `待了 ${Math.max(1, Math.floor((nowMs - a.since) / 60_000))} 分钟` : null]),
        progress: null,
      };
    case "returning":
      return {
        headline: a.kind === "job" ? `${name}收工了，在回家的路上` : `${name}在回家的路上`,
        detail: joinParts([
          minutesText(left, "到家"),
          a.kind === "job" && a.job ? (a.job.paid ? `工钱 ${a.job.pay} 星币已进银行卡` : `工钱 ${a.job.pay} 星币稍后到账`) : null,
        ]),
        progress,
      };
    default:
      return { headline: `还没同步到${name}此刻在哪`, detail: "世界状态更新后这里会跟着变。", progress: null };
  }
}
