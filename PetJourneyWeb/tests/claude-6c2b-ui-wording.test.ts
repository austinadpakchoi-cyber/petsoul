/**
 * 静态守卫（2026-09-24 全站文字清理，claude-6c2b 分身）：给玩家看的文字里——
 * 1. 不再出现“便笺”“入住叮嘱”：那份叮嘱本身和列表页叫“生活叮嘱”，新加一条的动作叫“补充叮嘱”；
 * 2. “旅费”不当钱、余额、单位讲：货币只叫“星币”，“旅费”只当用途讲（“攒一点旅费”“「去香港」的旅费”“星币只用于 TA 在星球上的旅费”可以）；
 * 3. 不说开发说法（巡检 P1 追加）：“接口”“搭建中”“未接入”“这项能力”。出错、还没开放时用人话，原话与错误码只进折叠的“技术信息”。
 *
 * 扫描范围：src/features 下除 driving_school 以外的全部源码，加上各模块的 fixture.ts（含 driving_school/fixture.ts）
 * 与 src/fixtures/**——演示数据也是给玩家看的文字（主窗口 2026-09-24 13:3x 追加）；
 * 以及 src/shared/ui、src/shared/api、src/shared/services、src/app：全站共用的出错、还没开放、404 页的说法在这里（巡检 P1 追加）。
 *
 * “界面文字”＝源码里会被显示出来的文字：字符串字面量、模板字符串的各段、JSX 文字（用 TypeScript 语法树取，不用正则扫全文）。
 * 不算：注释；import / export 的模块路径；类型位置上的字面量；正则字面量（只拿来匹配后端原文，不上页面，
 * 例如接待页认后端说明里的“引导便笺模式”——那是后端文案，前端不改写）。
 *
 * “旅费作余额 / 单位标签”的判据（任一条成立就算）：
 * - 这一段文字去掉空白后就是“旅费”（图标旁边单独一个“旅费”当标签）；
 * - 紧跟数字（“旅费 100”“30 旅费”“付了 30 旅费”）、紧跟单位斜杠（“旅费/个”）、或说余额（“旅费余额”“旅费未因…”“旅费：”）；
 * - 把一笔星币叫成“…旅费”（“入住欢迎旅费”）；把东西“换成 / 变成”旅费、“扣旅费”、“星球旅费”（都是把旅费当钱）；
 * - 这一段以“旅费”开头、而前面紧挨着一个表达式：JSX 里 {n} 旅费、模板里 ${n} 旅费、字符串拼接里 "+" + n + " 旅费"；
 * - 这一段以“旅费”结尾、而后面紧挨着一个表达式（“旅费 {n}”、`旅费 ${n}`、"旅费 " + n）。
 * 说用途的（“先攒一点旅费”“「去香港」的旅费”“星币只用于 TA 在星球上的旅费”“工资和旅费都记在这里”）不在其中。
 *
 * 覆盖不到的（别当成“全站都守住了”）：driving_school 的页面源码（四个驾校分身在改）、src/shared 的其余目录（contracts 等）；
 * 服务端下发的原文不在前端源码里，这里看不到；按表达式拼出来的“旅”+“费”也看不到。
 *
 * 变异自检用 UI_WORDING_OVERRIDES 指向一个 JSON（{ 绝对路径: 替换后的全文 }），只在内存里替换读到的文件，不写盘；
 * 从别处跑这份测试时用 UI_WORDING_ROOT 指明项目根。
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const ROOT = process.env.UI_WORDING_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), "..");
const FEATURES = resolve(ROOT, "src/features");
const FIXTURES = resolve(ROOT, "src/fixtures");
/** 全站共用的说法（出错、还没开放、404 页）：巡检 P1 追加的扫描目录。 */
const SHARED_ROOTS = ["src/shared/ui", "src/shared/api", "src/shared/services", "src/app"].map((dir) => resolve(ROOT, dir));
const EXCLUDED = ["driving_school"];

const norm = (file: string) => resolve(file).replace(/\\/g, "/").toLowerCase();
const OVERRIDES: Record<string, string> = process.env.UI_WORDING_OVERRIDES
  ? Object.fromEntries(Object.entries(JSON.parse(readFileSync(process.env.UI_WORDING_OVERRIDES, "utf8")) as Record<string, string>).map(([k, v]) => [norm(k), v]))
  : {};

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (dir === FEATURES && EXCLUDED.includes(name)) {
        // 驾校的页面源码不扫（四个驾校分身在改），它的演示数据 fixture.ts 照样扫：演示数据也是给玩家看的文字
        const demo = join(path, "fixture.ts");
        try {
          if (statSync(demo).isFile()) out.push(demo);
        } catch {
          /* 没有演示数据文件就算了 */
        }
        continue;
      }
      sourceFiles(path, out);
    } else if (/\.(ts|tsx)$/.test(name) && !/\.d\.ts$/.test(name)) out.push(path);
  }
  return out;
}

/** 扫描范围：src/features（驾校只扫 fixture.ts）＋ src/fixtures/** ＋ 全站共用的说法（SHARED_ROOTS）。 */
function allSourceFiles(): string[] {
  return [...sourceFiles(FEATURES), ...sourceFiles(FIXTURES), ...SHARED_ROOTS.flatMap((dir) => sourceFiles(dir))];
}

export interface UiText {
  line: number;
  text: string;
  /** 前面紧挨着一个 {表达式} / ${表达式} */
  afterExpr: boolean;
  /** 后面紧挨着一个 {表达式} / ${表达式} */
  beforeExpr: boolean;
}

function jsxNeighbours(node: ts.JsxText): { afterExpr: boolean; beforeExpr: boolean } {
  const parent = node.parent;
  const children = ts.isJsxElement(parent) || ts.isJsxFragment(parent) ? parent.children : undefined;
  if (!children) return { afterExpr: false, beforeExpr: false };
  const index = children.indexOf(node);
  return { afterExpr: index > 0 && ts.isJsxExpression(children[index - 1]), beforeExpr: index >= 0 && index < children.length - 1 && ts.isJsxExpression(children[index + 1]) };
}

const isPlus = (node: ts.Node): node is ts.BinaryExpression => ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken;
const isText = (node: ts.Expression) => ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node);
const rightmost = (node: ts.Expression): ts.Expression => (isPlus(node) ? rightmost(node.right) : node);
const leftmost = (node: ts.Expression): ts.Expression => (isPlus(node) ? leftmost(node.left) : node);

/** 字符串拼接（"杂货铺收下了 " + qty + " 个" …，左结合）里，这一段前后是不是紧挨着一个非文字的表达式。 */
function concatNeighbours(node: ts.StringLiteral | ts.NoSubstitutionTemplateLiteral): { afterExpr: boolean; beforeExpr: boolean } {
  const parent = node.parent;
  if (!isPlus(parent)) return { afterExpr: false, beforeExpr: false };
  if (parent.left === node) return { afterExpr: false, beforeExpr: !isText(leftmost(parent.right)) };
  const grand = parent.parent;
  return {
    afterExpr: !isText(rightmost(parent.left)),
    beforeExpr: isPlus(grand) && grand.left === parent && !isText(leftmost(grand.right)),
  };
}

/** 一份源码里的界面文字（见文件头的口径）。 */
export function uiTexts(fileName: string, source: string): UiText[] {
  const sf = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, fileName.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const out: UiText[] = [];
  const add = (node: ts.Node, text: string, afterExpr: boolean, beforeExpr: boolean) => {
    if (text.trim()) out.push({ line: sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1, text, afterExpr, beforeExpr });
  };
  const visit = (node: ts.Node) => {
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      const p = node.parent;
      const skip = ts.isImportDeclaration(p) || ts.isExportDeclaration(p) || ts.isLiteralTypeNode(p) || ts.isExternalModuleReference(p);
      if (!skip) {
        const around = concatNeighbours(node);
        add(node, node.text, around.afterExpr, around.beforeExpr);
      }
    } else if (ts.isTemplateHead(node)) add(node, node.text, false, true);
    else if (ts.isTemplateMiddle(node)) add(node, node.text, true, true);
    else if (ts.isTemplateTail(node)) add(node, node.text, true, false);
    else if (ts.isJsxText(node)) {
      const around = jsxNeighbours(node);
      add(node, node.text, around.afterExpr, around.beforeExpr);
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return out;
}

const BANNED = /便笺|入住叮嘱/;
/** 开发说法（巡检 P1）：玩家看不懂、也不该看到的词。 */
const TECH = /接口|搭建中|未接入|这项能力/;

/** 这一段是不是把“旅费”当成钱、余额、单位（判据见文件头）。 */
export function travelFeeAsLabel(piece: Pick<UiText, "text" | "afterExpr" | "beforeExpr">): boolean {
  const text = piece.text;
  if (!text.includes("旅费")) return false;
  if (text.trim() === "旅费") return true;
  if (/\d\s*旅费|旅费\s*\d|旅费\s*[/／]|旅费\s*(?:余额|未因|[:：])/.test(text)) return true;
  // 把一笔星币叫成“…旅费”：入住欢迎旅费（后端已改叫“入住欢迎星币”）
  if (/欢迎旅费/.test(text)) return true;
  // 把旅费当钱讲（巡检 P1 追加）：收成“换成 / 变成”旅费、“扣旅费”（含“不扣旅费”）、“星球旅费”
  if (/(?:换成|变成)旅费|扣旅费|星球旅费/.test(text)) return true;
  if (piece.afterExpr && /^\s*[+＋\-−]?\s*旅费/.test(text)) return true;
  if (piece.beforeExpr && /旅费\s*$/.test(text)) return true;
  return false;
}

function scan() {
  const files = allSourceFiles();
  const banned: string[] = [];
  const labels: string[] = [];
  const tech: string[] = [];
  let pieces = 0;
  for (const file of files) {
    const source = OVERRIDES[norm(file)] ?? readFileSync(file, "utf8");
    const rel = relative(ROOT, file).replace(/\\/g, "/");
    for (const piece of uiTexts(file, source)) {
      pieces += 1;
      const where = `${rel}:${piece.line} ${piece.text.replace(/\s+/g, " ").trim().slice(0, 60)}`;
      if (BANNED.test(piece.text)) banned.push(where);
      if (travelFeeAsLabel(piece)) labels.push(where);
      if (TECH.test(piece.text)) tech.push(where);
    }
  }
  return { files, banned, labels, tech, pieces };
}

describe("判据本身：分得开“标签”和“用途”，注释与正则不算界面文字", () => {
  const texts = (source: string) => uiTexts("probe.tsx", source);
  const flagged = (source: string) => texts(source).filter(travelFeeAsLabel).map((t) => t.text.trim());

  it("作标签的都会被认出来", () => {
    expect(flagged("const a = <span>{n} 旅费</span>;")).toEqual(["旅费"]);
    expect(flagged("const a = `旅费 ${n}，去集市`;")).toEqual(["旅费"]);
    expect(flagged('const a = <div>收购价 {p} 旅费/个</div>;')).toEqual(["旅费/个"]);
    expect(flagged('const a = <p>出价 {r} 旅费（卖给杂货铺是 {s}）</p>;')).toEqual(["旅费（卖给杂货铺是"]);
    expect(flagged('const a = <p>{items}。旅费未因收获增加。</p>;')).toEqual(["。旅费未因收获增加。"]);
    expect(flagged('const a = <span><Icon /> 旅费</span>;')).toEqual(["旅费"]);
    expect(flagged('const a = "余额 30 旅费";')).toEqual(["余额 30 旅费"]);
    expect(flagged('const a = `+${coins} 旅费。`;')).toEqual(["旅费。"]);
    // 演示数据里的写法（主窗口 13:3x 追加）：一笔星币叫成“…旅费”、字符串拼接里的“+N 旅费”“付了 N 旅费”
    expect(flagged('const a = { reason: "入住欢迎旅费（每个家一次，不可交易）" };')).toEqual(["入住欢迎旅费（每个家一次，不可交易）"]);
    expect(flagged('const a = "杂货铺收下了 " + qty + " 个" + label + "，+" + coins + " 旅费。（演示）";')).toEqual(["旅费。（演示）"]);
    expect(flagged('const a = resident + "收到了 " + qty + " 个" + label + "，付了 " + reward + " 旅费。";')).toEqual(["旅费。"]);
    expect(flagged('const a = "付了 30 旅费";')).toEqual(["付了 30 旅费"]);
    expect(flagged('const a = "余额：" + "旅费 " + n;')).toEqual(["旅费"]);
    // 把旅费当钱讲（巡检 P1 追加）：换成 / 变成旅费、扣旅费、星球旅费
    expect(flagged('const a = "把仓库里的收成换成旅费";')).toEqual(["把仓库里的收成换成旅费"]);
    expect(flagged("const a = <p>{msg} 卖给杂货铺就能换成旅费。</p>;")).toEqual(["卖给杂货铺就能换成旅费。"]);
    expect(flagged('const a = "成熟后收进仓库，卖掉或交订单变成旅费";')).toEqual(["成熟后收进仓库，卖掉或交订单变成旅费"]);
    expect(flagged('const a = "不扣旅费、不发勋章";')).toEqual(["不扣旅费、不发勋章"]);
    expect(flagged('const a = "不是星球旅费或玩家充值";')).toEqual(["不是星球旅费或玩家充值"]);
  });

  it("说用途的不算；注释、正则、import 路径不算界面文字", () => {
    expect(flagged("const a = <p>先攒旅费，再出门</p>;")).toEqual([]);
    // 讲用途的必须仍然合规（主窗口 13:3x 点名的三种）
    expect(flagged("const a = `「${dest}」的旅费`;")).toEqual([]);
    expect(flagged('const a = "「" + dest + "」的旅费";')).toEqual([]);
    expect(flagged('const a = { reason: "「去香港（演示）」的旅费" };')).toEqual([]);
    expect(flagged("const a = <p>先攒一点旅费，再出门</p>;")).toEqual([]);
    expect(flagged('const a = "星币只用于 TA 在星球上的旅费";')).toEqual([]);
    expect(flagged('const a = "工资和旅费都记在这里";')).toEqual([]);
    const commented = texts('// 旅费 {n} 便笺\n/* 入住叮嘱 */\nconst re = /引导便笺模式/;\nimport x from "./便笺";\nconst ok = "生活叮嘱";');
    expect(commented.map((t) => t.text)).toEqual(["生活叮嘱"]);
  });

  it("开发说法认得出，人话不误伤", () => {
    for (const bad of ["没有找到这个接口。", "这里还在搭建中", "这项能力尚未接入。", "能力未接入"]) expect(TECH.test(bad), bad).toBe(true);
    for (const ok of ["这里暂时还没开放，准备好了会出现在这里。", "星球接待员", "没有找到要看的内容", "TA 的驾驶本领"]) expect(TECH.test(ok), ok).toBe(false);
  });
});

describe("src/features（驾校只扫演示数据）＋ src/fixtures 的界面文字", () => {
  const result = scan();

  it("确实扫到了东西（防空转）：文件、文字段数都不是 0，演示数据文件都在范围里，也确实读到了说用途的“旅费”", () => {
    expect(result.files.length).toBeGreaterThan(100);
    expect(result.pieces).toBeGreaterThan(2000);
    const rels = result.files.map((file) => relative(ROOT, file).replace(/\\/g, "/"));
    for (const demo of ["src/fixtures/home.ts", "src/fixtures/social.ts", "src/fixtures/reception.ts", "src/features/life/fixture.ts", "src/features/driving_school/fixture.ts"]) {
      expect(rels, demo).toContain(demo);
    }
    expect(rels.filter((rel) => rel.startsWith("src/features/driving_school/"))).toEqual(["src/features/driving_school/fixture.ts"]);
    for (const shared of ["src/shared/ui/StateView.tsx", "src/shared/api/errors.ts", "src/shared/services/registry.tsx", "src/app/RouteErrorPage.tsx"]) {
      expect(rels, shared).toContain(shared);
    }
    // 这几句是有意保留的用途说法：扫得到它们，才说明“旅费”这条判据在真的源码上跑过（「去香港（演示）」的旅费 在卡包演示账单里）
    const all = result.files.flatMap((file) => uiTexts(file, OVERRIDES[norm(file)] ?? readFileSync(file, "utf8")).map((t) => t.text));
    expect(all.some((text) => text.includes("」的旅费"))).toBe(true);
    expect(all.some((text) => text.includes("生活叮嘱"))).toBe(true);
    expect(all.some((text) => text.includes("这里暂时还没开放"))).toBe(true);
  });

  it("不再出现“便笺”“入住叮嘱”", () => {
    expect(result.banned).toEqual([]);
  });

  it("“旅费”不当钱、余额、单位讲（货币只叫星币）", () => {
    expect(result.labels).toEqual([]);
  });

  it("不说开发说法：“接口”“搭建中”“未接入”“这项能力”", () => {
    expect(result.tech).toEqual([]);
  });
});
