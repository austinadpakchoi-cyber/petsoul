/**
 * claude-6c2b · “认识 TA”页（pets 的 .ps-own-pet-page，入住准备 02/04）跟着主题走（主窗口 2026-09-25）。
 * - pets.css 里这一页的规则（.ps-own-pet* / .ps-pet-photo* / .ps-pet-species*）不许写死颜色：只用主题变量（var(--c-…)、它们的 color-mix、transparent）；
 *   url(...) 里的插画不算颜色。
 * - identity.css 不再替这一页钉原色（原来那 6 条 .ps-own-pet-page 选择器已删，注册 / 登录的 .ps-auth-sheet 照旧）。
 * - 浅色、深色两套主题下，这一页主要的字对它所在的底都 ≥ 4.5（读真主题色、按 color-mix 的 sRGB 混合算，不写死数值）。
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const read = (rel: string) => readFileSync(join(process.cwd(), rel), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const pets = read("src/features/pets/pets.css");
const identity = read("src/features/identity/identity.css");
const tokens = read("src/shared/theme/tokens.css");

type Rule = { selector: string; decls: Map<string, string> };

/** 扁平地取出所有“选择器 { 声明 }”（@media 里的也取；选择器按逗号拆开、去空白）。 */
function rules(text: string): Rule[] {
  const out: Rule[] = [];
  for (const m of text.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const decls = new Map<string, string>();
    for (const part of m[2].split(";")) {
      const i = part.indexOf(":");
      if (i > 0) decls.set(part.slice(0, i).trim(), part.slice(i + 1).trim());
    }
    for (const selector of m[1].split(",")) out.push({ selector: selector.replace(/\s+/g, " ").trim(), decls });
  }
  return out;
}

const PAGE = /\.ps-own-pet|\.ps-pet-photo|\.ps-pet-species/;
const pageRules = rules(pets).filter((rule) => PAGE.test(rule.selector));
const decl = (selector: string, prop: string) => pageRules.find((rule) => rule.selector === selector)?.decls.get(prop) ?? null;

/* ---------- 主题色与 color-mix（sRGB 逐通道混合，与浏览器 color-mix(in srgb, …) 一致） ---------- */
function darkBlock(text: string): string {
  const at = text.indexOf("@media (prefers-color-scheme: dark)");
  const open = text.indexOf("{", at);
  let depth = 0;
  let i = open;
  for (; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}" && (depth -= 1) === 0) break;
  }
  return text.slice(open + 1, i);
}
const varsOf = (block: string) => Object.fromEntries([...block.matchAll(/(--c-[a-z0-9-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2].toLowerCase()]));
const LIGHT = varsOf(tokens.slice(0, tokens.indexOf("@media (prefers-color-scheme: dark)")));
const DARK = { ...LIGHT, ...varsOf(darkBlock(tokens)) };
type Rgb = [number, number, number];
const hex = (h: string): Rgb => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as Rgb;

function resolve(value: string, theme: Record<string, string>): Rgb {
  const v = value.trim();
  const single = v.match(/^var\((--c-[a-z0-9-]+)\)$/);
  if (single) return hex(theme[single[1]]);
  const mix = v.match(/^color-mix\(in srgb,\s*var\((--c-[a-z0-9-]+)\)\s+(\d+)%,\s*var\((--c-[a-z0-9-]+)\)\)$/);
  if (mix) {
    const p = Number(mix[2]) / 100;
    const [a, b] = [hex(theme[mix[1]]), hex(theme[mix[3]])];
    return a.map((c, i) => c * p + b[i] * (1 - p)) as Rgb;
  }
  throw new Error(`算不了这个颜色：${value}`);
}
const luminance = ([r, g, b]: Rgb) =>
  [r, g, b].map((c) => c / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a: Rgb, b: Rgb) => {
  const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
};

describe("“认识 TA”页不写死颜色", () => {
  it("前提：真读到了这一页的规则（页面、头图、照片框、表单、物种格、下一站、另一种相遇、主按钮）", () => {
    const selectors = pageRules.map((rule) => rule.selector);
    for (const s of [".ps-own-pet-page", ".ps-own-pet-page .ps-entry-heading", ".ps-pet-photo__stage", ".ps-own-pet-form__details", ".ps-pet-species__choice span", ".ps-own-pet-next", ".ps-own-pet-alternative", ".ps-own-pet-form > .ps-btn--primary"]) {
      expect(selectors, s).toContain(s);
    }
  });

  it("这一页的每条声明里都没有 #十六进制、rgb()/rgba()、hsl()（url() 里的插画不算）", () => {
    const literal = /#[0-9a-f]{3,8}\b|\brgba?\(|\bhsla?\(/i;
    const offenders = pageRules.flatMap((rule) =>
      [...rule.decls].filter(([, value]) => literal.test(value.replace(/url\([^)]*\)/g, ""))).map(([prop, value]) => `${rule.selector} { ${prop}: ${value} }`),
    );
    expect(offenders).toEqual([]);
  });

  it("页面底色与头图遮罩用当前主题的面色（深色下是深的）", () => {
    expect(decl(".ps-own-pet-page", "background")).toBe("var(--c-surface)");
    expect(decl(".ps-own-pet-page .ps-entry-heading", "background")).toContain("color-mix(in srgb, var(--c-surface) 95%, transparent) 0%");
  });

  it("identity.css 不再替这一页钉原色：没有任何 .ps-own-pet-page 选择器", () => {
    expect(rules(identity).filter((rule) => rule.selector.includes(".ps-own-pet-page")).map((rule) => rule.selector)).toEqual([]);
  });
});

describe("浅色、深色两套主题下，字对底都 ≥ 4.5", () => {
  const heading = rules(identity);
  const identityDecl = (selector: string, prop: string) => heading.find((rule) => rule.selector === selector && rule.decls.has(prop))?.decls.get(prop) ?? null;
  const pairs: Array<[string, string, string]> = [
    // [说的是什么, 字色, 底色]
    ["小标题（01 / 一张照片 等）对页面", decl(".ps-own-pet-form__lead span", "color")!, decl(".ps-own-pet-page", "background")!],
    ["表单里的小标题对表单卡", decl(".ps-pet-species legend", "color")!, decl(".ps-own-pet-form__details", "background")!],
    ["照片说明对页面", decl(".ps-pet-photo__note", "color")!, decl(".ps-own-pet-page", "background")!],
    ["物种格文字对格子", decl(".ps-pet-species__choice span", "color")!, decl(".ps-pet-species__choice span", "background")!],
    ["选中的物种格文字对选中底", decl(".ps-pet-species__choice input:checked + span", "color")!, decl(".ps-pet-species__choice input:checked + span", "background")!],
    ["下一站的眉标对卡片", decl(".ps-own-pet-next small", "color")!, decl(".ps-own-pet-next", "background")!],
    ["下一站的标题对卡片", decl(".ps-own-pet-next strong", "color")!, decl(".ps-own-pet-next", "background")!],
    ["另一种相遇的链接对卡片", decl(".ps-own-pet-alternative a", "color")!, decl(".ps-own-pet-alternative", "background")!],
    ["缺什么的提示对页面", decl(".ps-own-pet-missing", "color")!, decl(".ps-own-pet-page", "background")!],
    ["头图标题（通用入住标题色）对页面面色", identityDecl(".ps-entry-heading", "color")!, decl(".ps-own-pet-page", "background")!],
    ["头图说明对页面面色", identityDecl(".ps-entry-heading p", "color")!, decl(".ps-own-pet-page", "background")!],
  ];

  it("前提：每一对都取到了值", () => {
    for (const [name, fg, bg] of pairs) expect([name, fg, bg].every(Boolean), name).toBe(true);
  });

  it.each([["浅色", LIGHT], ["深色", DARK]] as const)("%s", (_theme, theme) => {
    const low = pairs.map(([name, fg, bg]) => ({ name, ratio: Math.round(contrast(resolve(fg, theme), resolve(bg, theme)) * 100) / 100 })).filter(({ ratio }) => ratio < 4.5);
    expect(low).toEqual([]);
  });
});
