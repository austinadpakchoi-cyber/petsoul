/**
 * 平台调用费用的显示：一处决定「未知 / 在途 / 未计入 / 部分未定价 / 按币种的估算」长什么样。
 *
 * 规则与后端一致：没有适用价格就是「未知」，**不显示 0**；人民币与美元分开写，不相加、不换算；
 * 结清的与未确认的分开写。这里不出现任何星币字样——两本账没有兑换关系。
 */
import type { CostState, CurrencyCosts } from "../api/types";
import { Pill } from "./ui";

const CURRENCY_LABEL: Record<string, string> = { CNY: "¥", USD: "$" };

export function money(currency: string, amount: string): string {
  return `${CURRENCY_LABEL[currency] ?? `${currency} `}${amount}`;
}

/** 按币种分开的一组估算（「两本账」页的行、用户汇总）。 */
export function CostCell({ state, costs }: { state: CostState; costs: CurrencyCosts | null }) {
  if (state === "unknown_no_price_table") return <Pill tone="unknown">未知（没有有效价格）</Pill>;
  if (state === "unknown_no_price") return <Pill tone="unknown">未知（没有适用价格）</Pill>;
  if (state === "not_counted") return <span style={{ color: "var(--ink-faint)" }}>—（没有计入用量）</span>;
  if (state === "in_flight") return <Pill tone="warn">在途</Pill>;
  return (
    <span>
      {Object.entries(costs ?? {}).map(([currency, value]) => (
        <div key={currency}>
          {money(currency, value.estimated)}
          {value.unconfirmed !== "0" && <span style={{ color: "var(--unknown)" }}>（未确认 {money(currency, value.unconfirmed)}）</span>}
        </div>
      ))}
      {state === "partial" && <Pill tone="warn">部分用量没有适用价格</Pill>}
    </span>
  );
}

/** 单条调用的估算（宠物调用账）。 */
export function RowCost({ state, amount, currency }: { state: CostState; amount: string | null; currency?: string | null }) {
  if (state === "estimated" && amount && currency) return <span>{money(currency, amount)}</span>;
  if (state === "unconfirmed_estimate" && amount && currency) {
    return <span style={{ color: "var(--unknown)" }}>{money(currency, amount)}（未确认）</span>;
  }
  return <CostCell state={state} costs={null} />;
}
