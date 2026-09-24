/**
 * 把代码说成人话（方案 §5：不把原始代码当日常界面）。
 *
 * - 词表只有一份，在后端 `app/web_admin/labels.py`，由用例和领域里的枚举双向核对；登录后取一次（`GET /labels`）。
 * - 员工号换成名字（`GET /staff/names`）：账本的操作者、批次的提交人、价格的录入人……都显示名字。
 * - `<Term>` 显示说法；**没收录的代码照原样显示并标「未收录」**，不猜、不藏。
 * - 右上角「显示技术代码」打开后，说法后面带上原始代码，各种编号、内部键也显示出来，方便对日志、对工程师。
 *   这个开关只记在这台电脑的浏览器里（记不住就当关着），不影响别人。
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api/client";

export type LabelFamilies = Record<string, Record<string, string>>;
interface StaffName { username: string; display_name: string; disabled: boolean }
interface Glossary { families: LabelFamilies; hints: Record<string, string>; staff: Record<string, StaffName>; operators: Record<string, string> }

const EMPTY: Glossary = { families: {}, hints: {}, staff: {}, operators: {} };
const GlossaryContext = createContext<Glossary>(EMPTY);
const TechContext = createContext<{ on: boolean; set: (on: boolean) => void }>({ on: false, set: () => {} });
const TECH_KEY = "petsoul-admin-show-codes";

function readTech(): boolean {
  try { return window.localStorage.getItem(TECH_KEY) === "1"; } catch { return false; }
}

export function GlossaryProvider({ children }: { children: ReactNode }) {
  const [glossary, setGlossary] = useState<Glossary>(EMPTY);
  const [on, setOn] = useState(readTech);
  useEffect(() => {
    // 取不到时界面照样能用：代码照原样显示（标未收录）、员工显示编号，不会空白
    let alive = true;
    Promise.allSettled([
      api.get<{ families: LabelFamilies; silence_hints: Record<string, string> }>("/labels"),
      api.get<{ staff: Record<string, StaffName>; operators: Record<string, string> }>("/staff/names"),
    ]).then(([labels, names]) => {
      if (!alive) return;
      setGlossary({
        families: labels.status === "fulfilled" ? labels.value.families : {},
        hints: labels.status === "fulfilled" ? labels.value.silence_hints : {},
        staff: names.status === "fulfilled" ? names.value.staff : {},
        operators: names.status === "fulfilled" ? names.value.operators : {},
      });
    });
    return () => { alive = false; };
  }, []);
  const set = (value: boolean) => {
    setOn(value);
    try { window.localStorage.setItem(TECH_KEY, value ? "1" : "0"); } catch { /* 记不住就只在这一页生效 */ }
  };
  return (
    <GlossaryContext.Provider value={glossary}>
      <TechContext.Provider value={{ on, set }}>{children}</TechContext.Provider>
    </GlossaryContext.Provider>
  );
}

export function useTech() { return useContext(TechContext); }

/** 查一个说法；没收录返回 null（调用方决定怎么如实显示）。 */
export function useLabel() {
  const { families } = useContext(GlossaryContext);
  return (family: string, code: string | null | undefined): string | null =>
    code == null ? null : families[family]?.[code] ?? null;
}

/** 一整组说法（下拉框列选项用）；词表还没取到时是空的。 */
export function useFamily(family: string): Record<string, string> {
  const { families } = useContext(GlossaryContext);
  return families[family] ?? {};
}

/** 安静原因的「还能做什么」。 */
export function useSilenceHint() {
  const { hints } = useContext(GlossaryContext);
  return (code: string | null | undefined) => (code ? hints[code] ?? null : null);
}

/** 原始代码：只在打开「显示技术代码」时出现。 */
export function Code({ value }: { value: string | number | null | undefined }) {
  const { on } = useTech();
  if (!on || value == null || value === "") return null;
  return <code className="tech">{value}</code>;
}

/** 一个代码的人话。没收录照原样显示并标出来；`label` 由后端直接给了说法时优先用它。 */
export function Term({ family, code, label, fallback }: {
  family?: string; code: string | null | undefined; label?: string | null; fallback?: string;
}) {
  const lookup = useLabel();
  if (code == null || code === "") return <>{fallback ?? "—"}</>;
  const text = label ?? (family ? lookup(family, code) : null);
  if (text == null) {
    return <span title="这个代码还没有收录说法，照原样显示">{code}<span className="unlabeled">未收录</span></span>;
  }
  return <span title={`代码：${code}`}>{text}<Code value={code} /></span>;
}

/** 内容字段名：代码（小写字母、数字、下划线）查词表；已经是说明文字的（如「任意外链图」）照原样显示。 */
export function FieldName({ field }: { field: string }) {
  return /^[a-z0-9_]+$/.test(field) ? <Term family="content_field" code={field} /> : <>{field}</>;
}

/** 员工号 → 名字。账本里的 web 是玩家那一侧自己产生的，不是员工。 */
export function Staff({ id }: { id: string | null | undefined }) {
  const { staff, operators } = useContext(GlossaryContext);
  if (!id) return <>—</>;
  const known = staff[id];
  if (known) {
    return (
      <span title={`员工号：${id}`}>
        {known.display_name && known.display_name !== known.username ? `${known.display_name}（${known.username}）` : known.username}
        {known.disabled && <span className="unlabeled">已停用</span>}
        <Code value={id} />
      </span>
    );
  }
  if (operators[id]) return <span title={`代码：${id}`}>{operators[id]}<Code value={id} /></span>;
  return <span className="mono" title="不是后台员工，照原样显示">{id}</span>;
}

/** 权限代码 → 人话（「需要什么权限」这种提示用）。 */
export function PermissionName({ code }: { code: string }) {
  return <Term family="permission" code={code} />;
}

/** 只在打开「显示技术代码」时出现的整块内容：编号、幂等键、表名、原始错误串。 */
export function Tech({ children }: { children: ReactNode }) {
  const { on } = useTech();
  return on ? <div className="tech-block">{children}</div> : null;
}

/** 右上角的开关。 */
export function TechToggle() {
  const { on, set } = useTech();
  return (
    <label className="tech-toggle" title="打开后，每个说法后面会带上原始代码，编号与内部键也会显示出来">
      <input type="checkbox" checked={on} onChange={(e) => set(e.target.checked)} /> 显示技术代码
    </label>
  );
}
