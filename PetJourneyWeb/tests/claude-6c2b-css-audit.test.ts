/**
 * 旧页面视觉巡检（claude-6c2b，2026-09-24）修过的样式，只读 CSS 文件断言：
 * - 深色下看不清 / 亮斑：逐条列出修过的规则，去掉注释后不再含写死的颜色（#十六进制、rgb()/hsl()、white/black），
 *   并且指定的颜色属性确实来自令牌。规则整条被删也会红（找不到规则）。
 * - 令牌要用对“族”：跟主题走的卡面上，颜色必须来自 var(--c-*)，不许用纸质固定色 --paper*（纸墨是深色，
 *   卡面在深色下变深后就是深字压深底——作物名原来就是这样）；纸卡（明信片、驾校报名卡、星球纸色底栏）上的字
 *   反过来必须用纸质令牌：纸面昼夜不变，用会变浅的 --c-ink / --c-ink-2 在深色下看不见。
 * - 点按区与 320 宽的修复：小号按钮在这些位置放大到 40px、窄屏布局改动还在。
 * 变异自检用：环境变量 CSS_AUDIT_ROOT 可指向一份 features 目录副本（只读），默认读 src/features。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const ROOT = process.env.CSS_AUDIT_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "features");
const HARDCODED = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(|(?<![\w-])(?:white|black)(?![\w-])/g;
const TOKEN = /var\(--(?:c-|paper)/;

type Rule = { selector: string; context: string; body: string };

/** 去掉注释后逐条取规则：选择器（空白归一）、所在 @ 规则上下文、声明体。 */
function parseRules(file: string): Rule[] {
  const src = readFileSync(resolve(ROOT, file), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const rules: Rule[] = [];
  const stack: string[] = [];
  let buf = "";
  for (const ch of src) {
    if (ch === "{") {
      stack.push(buf.trim().replace(/\s+/g, " "));
      buf = "";
    } else if (ch === "}") {
      const prelude = stack.pop() ?? "";
      if (!prelude.startsWith("@")) rules.push({ selector: prelude, context: stack.filter((s) => s.startsWith("@")).join(" "), body: buf.trim() });
      buf = "";
    } else {
      buf += ch;
    }
  }
  return rules;
}

function declarations(body: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const part of body.split(";")) {
    const at = part.indexOf(":");
    if (at > 0) map.set(part.slice(0, at).trim(), part.slice(at + 1).trim());
  }
  return map;
}

function findRules(file: string, selector: string, context = ""): Rule[] {
  return parseRules(file).filter((r) => r.selector === selector && r.context === context);
}

type ColorFix = { selector: string; context?: string; props: string[]; paper?: boolean };

const DARK = "@media (prefers-color-scheme: dark)";
const NARROW = "@media (max-width: 350px)";

const COLOR_FIXES: Record<string, ColorFix[]> = {
  "collection/collection.css": [
    { selector: ".ps-collection-item", props: ["background"] },
    { selector: ".ps-collection-item.ps-card--paper", context: DARK, props: ["background"], paper: true },
    // 第三轮：卡里 .ps-muted / .ps-origin / .ps-chip 的三条深色规则已删，颜色交给 ui.css 的纸卡规则（见文件末尾的守卫与实算）
  ],
  "journey/journey.css": [
    { selector: ".ps-journey-links a", props: ["border", "background", "color"] },
    { selector: ".ps-scenario-disclosure", props: ["border", "background", "color"] },
    { selector: ".ps-trip-card", props: ["border", "background", "box-shadow"] },
    { selector: ".ps-trip-card__icon", props: ["background", "color"] },
    { selector: ".ps-trip-card__eyebrow", props: ["color"] },
    { selector: ".ps-trip-card__eyebrow i", props: ["background", "box-shadow"] },
    { selector: ".ps-trip-card__text small", props: ["color"] },
    { selector: ".ps-trip-card__chevron", props: ["color"] },
    { selector: ".ps-trip-card__body", props: ["border-top"] },
    { selector: ".ps-trip-card__body h3", props: ["color"] },
    { selector: ".ps-trip-legs li.is-current", props: ["background"] },
    { selector: ".ps-trip-legs__time", props: ["color"] },
    { selector: ".ps-trip-legs__what small", props: ["color"] },
    { selector: ".ps-trip-card__foot", props: ["color"] },
  ],
  "journey/guide.css": [
    { selector: ".ps-guide-page", props: ["background"] },
    { selector: ".ps-guide-intro", props: ["border", "background", "color"] },
    { selector: ".ps-guide-intro p", props: ["color"] },
    { selector: ".ps-guide-image figcaption", props: ["color"] },
    { selector: ".ps-guide-image-state", props: ["border", "background", "color"] },
    { selector: ".ps-guide-budget", props: ["border-left", "background"] },
    { selector: ".ps-guide-stops li", props: ["border-top"] },
    { selector: ".ps-guide-stops__number", props: ["color"] },
    { selector: ".ps-guide-stops p", props: ["color"] },
    { selector: ".ps-guide-stops address", props: ["color"] },
    { selector: ".ps-guide-stops small", props: ["color"] },
    { selector: ".ps-guide-stops a", props: ["color"] },
    { selector: ".ps-guide-stops__tip", props: ["background"] },
    { selector: ".ps-guide-copy button", props: ["color"] },
    { selector: ".ps-guide-copy textarea", props: ["border", "background", "color"] },
    { selector: ".ps-guide-copy p", props: ["color"] },
  ],
  "companion_media/companion.css": [
    { selector: ".ps-media-heading", props: ["border", "background"] },
    { selector: ".ps-media-actions", props: ["border", "background"] },
    { selector: ".ps-media-sheet", props: ["border", "background"] },
    { selector: ".ps-media-progress .ps-progress", props: ["background"] },
  ],
  "farm/farm.css": [
    { selector: ".ps-crop-sheet", props: ["border", "background"] },
    { selector: ".ps-garden-wallet", props: ["border", "background", "color"] },
    { selector: ".ps-crop-list > li", props: ["border", "background", "box-shadow"] },
    { selector: ".ps-crop-list > li > div strong", props: ["color"] },
  ],
  "household/household.css": [{ selector: ".ps-family-page", props: ["background", "color"] }],
  "pets/pets.css": [
    { selector: ".ps-photo-page", props: ["background", "color"] },
    { selector: ".ps-photo-hero", props: ["background"] },
    { selector: ".ps-photo-hero::after", props: ["color"] },
    { selector: ".ps-photo-scenes button", props: ["border", "background", "color"] },
    { selector: '.ps-photo-scenes button[aria-pressed="true"]', props: ["border", "background"] },
    { selector: ".ps-photo-scenes small", props: ["color"] },
    { selector: ".ps-photo-scenes span", props: ["color"] },
    { selector: ".ps-photo-command", props: ["border", "background"] },
    { selector: ".ps-photo-command p", props: ["color"] },
    { selector: ".ps-photo-command > button", props: ["background", "color"] },
    { selector: ".ps-photo-command > button:disabled", props: [] },
    { selector: ".ps-photo-feedback", props: ["background", "color"] },
    { selector: ".ps-photo-consent", props: ["border", "background"] },
    { selector: ".ps-photo-consent strong", props: ["color"] },
    { selector: ".ps-photo-consent p", props: ["color"] },
    { selector: ".ps-photo-consent a", props: ["color"] },
    { selector: ".ps-photo-cafe-note", props: ["background", "color"] },
    { selector: ".ps-photo-cafe-note a", props: ["color"] },
    { selector: ".ps-photo-list__title span", props: ["color"] },
    { selector: ".ps-photo-list__title button", props: ["border", "background", "color"] },
    { selector: ".ps-photo-result", props: ["border", "background"] },
    { selector: ".ps-photo-result figcaption", props: ["color"] },
    { selector: ".ps-photo-result__empty", props: ["color", "background"] },
    { selector: ".ps-photo-result__empty--unknown", props: ["background", "color"] },
    { selector: ".ps-photo-result__empty--failed", props: ["background", "color"] },
    { selector: ".ps-photo-result__heading small", props: ["color"] },
    { selector: ".ps-photo-result__body p", props: ["color"] },
    { selector: ".ps-photo-result__body button", props: ["background", "color"] },
    { selector: ".ps-public-resident", props: ["border", "background", "box-shadow"] },
    { selector: ".ps-public-resident__portrait", props: ["background", "color"] },
    { selector: ".ps-public-resident:nth-child(3n + 2) .ps-public-resident__portrait", props: ["background", "color"] },
    { selector: ".ps-public-resident:nth-child(3n) .ps-public-resident__portrait", props: ["background", "color"] },
    { selector: ".ps-public-resident__body", props: ["color"] },
    { selector: ".ps-public-resident__number", props: ["color"] },
    { selector: ".ps-public-resident__body strong", props: ["color"] },
    { selector: ".ps-public-resident__body em", props: ["color"] },
    { selector: ".ps-public-resident__arrow", props: ["color"] },
  ],
  // 2026-09-24 星球访客页重做（claude-6c2b 分身）：纸色底栏 .ps-planet-dock 已撤，演示标记改由 ui.css 的主题规则上色；
  // 新页面跟主题走的表面逐条钉住，品牌字底下那枚纸色小牌反过来必须是纸质固定色（深绿品牌字在夜里的天空上才看得清）。
  "pets/planet.css": [
    { selector: ".ps-world-page.ps-page", props: ["background", "color"] },
    { selector: ".ps-world-hero__back", props: ["border", "background", "color"] },
    { selector: ".ps-world-hero__bar .ps-brand-logo", props: ["background"], paper: true },
    { selector: ".ps-world-sheet", props: ["background"] },
    { selector: ".ps-world-sheet__head h1", props: ["color"] },
    { selector: ".ps-world-sheet__head p", props: ["color"] },
    { selector: ".ps-world-now li", props: ["border", "background", "color"] },
    { selector: ".ps-world-resident", props: ["border", "background", "box-shadow"] },
    { selector: ".ps-world-resident__who p", props: ["color"] },
    { selector: ".ps-world-resident__facts dt", props: ["color"] },
    { selector: ".ps-world-resident__facts dd", props: ["color"] },
    { selector: ".ps-world-resident__post", props: ["border-left", "background"] },
    { selector: ".ps-world-resident__post footer", props: ["color"] },
    { selector: ".ps-world-resident__more", props: ["background", "color"] },
    { selector: ".ps-resident-portrait > small", props: ["background", "color"] },
    { selector: ".ps-world-cta", props: ["border-top", "background"] },
    { selector: ".ps-world-cta__login", props: ["color"] },
  ],
  "venue/venue.css": [{ selector: ".ps-visit-memento-link", props: ["border", "background", "color"] }],
  "driving_school/school.css": [
    // 驾校页面分身第三批：报名卡挪到教练卡前面（首屏加了横幅），原选择器“教练卡后面的纸卡”不再成立，改按报名卡自己的类名；要求不变（纸质令牌）
    { selector: ".ds-enroll .ds-quote", props: ["color"], paper: true },
    // 第三轮：纸卡里 .ps-muted 的两处规则已删，交给 ui.css 的 .ps-card--paper .ps-muted
  ],
};

describe("巡检修过的颜色规则：不再写死颜色，确实用主题令牌", () => {
  for (const [file, fixes] of Object.entries(COLOR_FIXES)) {
    describe(file, () => {
      for (const fix of fixes) {
        const label = `${fix.context ? fix.context + " " : ""}${fix.selector}`;
        it(label, () => {
          const found = findRules(file, fix.selector, fix.context ?? "");
          expect(found.length, `${label} 规则不见了`).toBeGreaterThan(0);
          for (const rule of found) {
            expect(rule.body.match(HARDCODED) ?? [], `${label} 仍有写死颜色`).toEqual([]);
            const decl = declarations(rule.body);
            for (const prop of fix.props) {
              const value = decl.get(prop) ?? "";
              expect(value, `${label} 的 ${prop}`).toMatch(TOKEN);
              if (fix.paper) {
                // 纸面上的字只能用纸质固定色（可掺主题的强调色），不能只靠会随深浅变化的 --c-ink 系列。
                expect(value, `${label} 的 ${prop} 要用纸质令牌`).toMatch(/var\(--paper/);
              } else {
                // 跟主题走的表面：只用主题令牌，不混入昼夜不变的纸色。
                expect(value, `${label} 的 ${prop} 要用主题令牌`).toMatch(/var\(--c-/);
                expect(value, `${label} 的 ${prop} 不应用纸质固定色`).not.toMatch(/--paper/);
              }
            }
          }
          if (fix.props.length === 0) expect(found[0].body, `${label} 禁用态要靠透明度表达`).toMatch(/opacity\s*:/);
        });
      }
    });
  }

  it("星球页的演示标记跟随主题：planet.css 不再单独给 .ps-origin 上色（纸色底栏已撤，交给 ui.css 的主题规则）", () => {
    expect(parseRules("pets/planet.css").filter((rule) => /\.ps-origin\b/.test(rule.selector))).toEqual([]);
  });
});

type SizeFix = { file: string; selector: string; context?: string; expect: Record<string, RegExp> };

const SIZE_FIXES: SizeFix[] = [
  { file: "collection/collection.css", selector: ".ps-market-row .ps-btn", expect: { "min-height": /^40px$/ } },
  // 标记让出星形的位置，且整体不换行、不收缩（320 宽时曾被挤成“演示数 / 据”）
  { file: "collection/collection.css", selector: ".ps-collection-item__head .ps-origin", expect: { "margin-right": /^(2[89]|[3-9]\d)px$/, "white-space": /^nowrap$/, flex: /^none$/ } },
  { file: "collection/collection.css", selector: ".ps-collection-item__head > div", expect: { "min-width": /^0$/ } },
  { file: "farm/farm.css", selector: ".ps-garden-wallet", expect: { "min-height": /^40px$/ } },
  { file: "farm/farm.css", selector: ".ps-crop-list > li .ps-btn--sm", expect: { "min-height": /^40px$/ } },
  { file: "farm/farm.css", selector: ".ps-steal-page > .ps-row > .ps-btn--sm", expect: { "min-height": /^40px$/ } },
  { file: "journey/journey.css", selector: ".ps-scenario-disclosure summary", expect: { padding: /^11px 0 12px$/ } },
  { file: "journey/guide.css", selector: ".ps-guide-copy button", expect: { "min-height": /^40px$/ } },
  { file: "companion_media/companion.css", selector: ".ps-media-actions .ps-btn--sm", expect: { "min-height": /^40px$/ } },
  { file: "household/household.css", selector: ".ps-family-card button", expect: { "min-height": /^40px$/ } },
  { file: "pets/pets.css", selector: ".ps-photo-list__title button", expect: { "min-height": /^40px$/ } },
  { file: "pets/pets.css", selector: ".ps-photo-result__body button", expect: { "min-height": /^40px$/ } },
  { file: "pets/pets.css", selector: ".ps-photo-content", context: NARROW, expect: { "padding-left": /^0$/, "padding-right": /^0$/ } },
  // 星球访客页重做后（示意地图与按地图高度算的底栏已撤）：登录链接 40px，主按钮 48px，“认识 TA”与返回 44px
  { file: "pets/planet.css", selector: ".ps-world-cta__login", expect: { "min-height": /^40px$/, display: /^inline-flex$/ } },
  { file: "pets/planet.css", selector: ".ps-world-cta .ps-btn", expect: { "min-height": /^48px$/ } },
  { file: "pets/planet.css", selector: ".ps-world-resident__more", expect: { "min-height": /^44px$/ } },
  { file: "pets/planet.css", selector: ".ps-world-hero__back", expect: { width: /^44px$/, height: /^44px$/ } },
  { file: "food_discovery/food.css", selector: ".ps-rec .ps-btn--sm", expect: { "min-height": /^40px$/ } },
  { file: "food_discovery/food.css", selector: ".ps-food-ctx > svg", expect: { "box-sizing": /^content-box$/ } },
  { file: "social/social.css", selector: ".ps-post .ps-btn--sm", expect: { "min-height": /^40px$/ } },
  { file: "social/social.css", selector: ".ps-link-btn", expect: { "min-height": /^40px$/ } },
  // 行内链接：上下内边距扩大点按区（21px 字高 + 20px ≥ 40px），左右用负外边距抵消，不改排版
  { file: "social/social.css", selector: ".ps-actor a", expect: { padding: /^10px 6px$/, margin: /^0 -6px$/ } },
  { file: "pets/pets.css", selector: ".ps-photo-cafe-note a", expect: { padding: /^12px 0$/ } },
  { file: "venue/venue.css", selector: ".ps-cafe__tag", expect: { left: /^8px$/ } },
];

describe("巡检修过的点按区与窄屏布局", () => {
  for (const fix of SIZE_FIXES) {
    const label = `${fix.file} ${fix.context ? fix.context + " " : ""}${fix.selector}`;
    it(label, () => {
      const found = findRules(fix.file, fix.selector, fix.context ?? "");
      expect(found.length, `${label} 规则不见了`).toBeGreaterThan(0);
      const decl = declarations(found[found.length - 1].body);
      for (const [prop, pattern] of Object.entries(fix.expect)) expect(decl.get(prop) ?? "", `${label} 的 ${prop}`).toMatch(pattern);
    });
  }

  it("到访页场景标签挪到左下角后，不再同时写 right（否则会被拉成整条）", () => {
    const [rule] = findRules("venue/venue.css", ".ps-cafe__tag");
    expect(declarations(rule.body).has("right")).toBe(false);
  });
});

/* ---------------- 第二轮（2026-09-24）：shared/ui/ui.css 的三条共享改动 ----------------
 * 1) 小号按钮 .ps-btn--sm 与按钮式标签 button.ps-chip：min-height 36px → 40px，字号、内边距不变；
 * 2) 深色下 .ps-btn--leaf 的字色改用 --c-deep-ink（--c-leaf 深色下是浅绿，原来的浅字约 2.2:1），浅色不变；
 *    第三轮起只写跟随系统深色一处，写法与 tokens.css 相同（原来的 data-theme 那条从不生效，已删，见文件末尾的一致性断言）；
 * 3) 纸卡 .ps-card--paper 里的 .ps-muted、.ps-origin、不带色调的 .ps-chip 用纸墨系令牌，特异性保持 (0,2,0)。
 * 变异自检用：环境变量 CSS_AUDIT_SHARED_UI 可指向一份 shared/ui 目录副本（只读），默认读 src/shared/ui。
 * 这里直接复用上面的 findRules / parseRules：传绝对路径时 path.resolve(ROOT, 绝对路径) 返回它本身。
 */
const UI_CSS = resolve(process.env.CSS_AUDIT_SHARED_UI ?? resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "shared", "ui"), "ui.css");
const LEAF = ".ps-btn--leaf";
const PAPER_CHIP = '.ps-card--paper .ps-chip:where(:not([class*="ps-chip--"]):not([aria-pressed="true"]))';

function uiRule(selector: string, context = ""): Rule {
  const found = findRules(UI_CSS, selector, context);
  expect(found.length, `ui.css 里 ${context ? context + " " : ""}${selector} 应恰好一条`).toBe(1);
  return found[0];
}

describe("第二轮：小号按钮与按钮式标签的点按区 40px（字号、内边距不变）", () => {
  it(".ps-btn--sm", () => {
    const d = declarations(uiRule(".ps-btn--sm").body);
    expect(d.get("min-height")).toBe("40px");
    expect(d.get("padding")).toBe("0 var(--space-3)");
    expect(d.get("font-size")).toBe("var(--fs-sm)");
  });

  it("button.ps-chip", () => {
    const d = declarations(uiRule("button.ps-chip").body);
    expect(d.get("min-height")).toBe("40px");
    expect(d.get("padding")).toBe("0 14px");
    expect(d.get("font-size")).toBe("var(--fs-sm)");
  });

  it("ui.css 里凡是按钮（.ps-btn*）和按钮式标签（button.ps-chip*）写了 min-height 的，都不小于 40px", () => {
    const offenders = parseRules(UI_CSS)
      .filter((r) => /\.ps-btn\b|button\.ps-chip/.test(r.selector))
      .map((r) => ({ selector: r.selector, h: declarations(r.body).get("min-height") }))
      .filter((r) => r.h !== undefined && !(/^\d+px$/.test(r.h) && parseInt(r.h, 10) >= 40));
    expect(offenders).toEqual([]);
  });
});

describe("第二轮：深色下 leaf 按钮改用深色字（浅色不变）", () => {
  it("跟随系统深色：@media (prefers-color-scheme: dark) 里的 .ps-btn--leaf 用 --c-deep-ink（不带 data-theme 前缀，与 tokens.css 同一写法）", () => {
    expect(declarations(uiRule(LEAF, DARK).body).get("color")).toBe("var(--c-deep-ink)");
  });

  it("浅色原样：.ps-btn--leaf 仍是 --c-leaf 底、--c-on-deep 字", () => {
    const d = declarations(uiRule(LEAF).body);
    expect(d.get("background")).toBe("var(--c-leaf)");
    expect(d.get("color")).toBe("var(--c-on-deep)");
  });
});

describe("第二轮：纸卡里的次要字、来源标记、无色调标签用纸墨系", () => {
  it(".ps-card--paper .ps-muted 用 --paper-secondary-ink", () => {
    expect(declarations(uiRule(".ps-card--paper .ps-muted").body).get("color")).toBe("var(--paper-secondary-ink)");
  });

  it(".ps-card--paper .ps-origin 掺纸墨（--paper-ink）", () => {
    expect(declarations(uiRule(".ps-card--paper .ps-origin").body).get("color")).toMatch(/var\(--paper-ink\)/);
  });

  it("不带色调的 .ps-chip：选择器排除 ps-chip--* 变体与按下态、用 :where 不抬高特异性；边框、底、字都是纸质令牌", () => {
    const d = declarations(uiRule(PAPER_CHIP).body);
    expect(d.get("border-color")).toBe("var(--paper-shade)");
    expect(d.get("background")).toMatch(/var\(--paper\)/);
    expect(d.get("color")).toBe("var(--paper-ink)");
  });

  it("这几条新规则都不含写死的颜色", () => {
    for (const [selector, context] of [[".ps-card--paper .ps-muted", ""], [".ps-card--paper .ps-origin", ""], [PAPER_CHIP, ""], [LEAF, DARK]]) {
      expect(uiRule(selector, context).body.match(HARDCODED) ?? [], selector).toEqual([]);
    }
  });
});

describe("第二轮追加：状态组件的标题与说明 text-wrap: balance（只作用在 .ps-state 里）", () => {
  const STATE_TEXT = ".ps-state__title, .ps-state > div:not([class]), .ps-state > .ps-muted";

  it("标题、StateView 的说明（无类名 div）、RouteErrorPage / ErrorBoundary 的说明（.ps-muted）都设 text-wrap: balance", () => {
    expect(declarations(uiRule(STATE_TEXT).body).get("text-wrap")).toBe("balance");
  });

  it("不做全局：ui.css 里凡是写了 text-wrap 的规则，选择器列表里每一项都限定在 .ps-state 内", () => {
    const withWrap = parseRules(UI_CSS).filter((r) => /(?:^|;)\s*text-wrap(?:-style)?\s*:/.test(r.body));
    expect(withWrap.length, "至少有这一条").toBeGreaterThan(0);
    for (const rule of withWrap) {
      for (const part of rule.selector.split(",").map((s) => s.trim())) expect(part, `${rule.selector} 里的 ${part}`).toMatch(/^\.ps-state(?:__title\b|\s*>)/);
    }
  });
});

/* ---------------- 第三轮（2026-09-24）：去掉不生效的 data-theme 写法、删被共享规则覆盖的模块规则、照片页小标签 ----------------
 * 1) 主题切换写法一致：ui.css 出现 data-theme 选择器，当且仅当 tokens.css 也有。tokens.css 现在只跟随系统深浅色，
 *    ui.css 单独写 data-theme 的规则要么永不生效，要么在只改了一边的主题开关下造出深字压深绿底（约 2.75:1）这类组合。
 * 2) 按 tokens.css 的浅深两套值实算对比度（WCAG 相对亮度）：leaf 按钮、纸卡里的次要字 / 来源标记 / 标签、
 *    照片页场景卡的 9px 小标签，都不低于 4.5:1。颜色写法只认 #rrggbb、var(--x)、color-mix(in srgb, A p%, B)，
 *    认不出的写法直接报错，不会悄悄算成通过。
 * 3) 收藏页、驾校的模块 CSS 不再另写纸卡里 .ps-muted / .ps-origin / .ps-chip 的颜色，统一由 ui.css 的纸卡规则负责。
 * 变异自检用：环境变量 CSS_AUDIT_THEME 可指向一份 shared/theme 目录副本（只读），默认读 src/shared/theme。
 */
const THEME_TOKENS = resolve(process.env.CSS_AUDIT_THEME ?? resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "shared", "theme"), "tokens.css");
const DATA_THEME_SELECTOR = /\[\s*data-theme\b/;
const withoutComments = (file: string) => readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

type Scheme = "light" | "dark";
type RGB = [number, number, number];

/** tokens.css 的令牌表：浅色取顶层 :root，深色再叠上 @media (prefers-color-scheme: dark) 里的 :root。 */
function tokenTable(scheme: Scheme): Map<string, string> {
  const table = new Map<string, string>();
  for (const context of scheme === "dark" ? ["", DARK] : [""]) {
    const found = findRules(THEME_TOKENS, ":root", context);
    expect(found.length, `tokens.css 里${context ? " " + context + " 里" : "顶层"}的 :root 应恰好一条`).toBe(1);
    for (const [name, value] of declarations(found[0].body)) if (name.startsWith("--")) table.set(name, value);
  }
  return table;
}

/** 把颜色值算成 sRGB 分量（0–255，保留小数）。 */
function resolveColor(value: string, table: Map<string, string>, depth = 0): RGB {
  if (depth > 8) throw new Error(`令牌引用太深或成环：${value}`);
  const v = value.trim();
  const ref = /^var\(\s*(--[\w-]+)\s*\)$/.exec(v);
  if (ref) {
    const next = table.get(ref[1]);
    if (next === undefined) throw new Error(`令牌表里没有 ${ref[1]}`);
    return resolveColor(next, table, depth + 1);
  }
  const hex = /^#([0-9a-f]{6})$/i.exec(v);
  if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16)) as RGB;
  const mix = /^color-mix\(\s*in srgb\s*,\s*(.+?)\s+(\d+(?:\.\d+)?)%\s*,\s*(.+?)\s*\)$/.exec(v);
  if (mix) {
    const p = Number(mix[2]) / 100;
    const a = resolveColor(mix[1], table, depth + 1);
    const b = resolveColor(mix[3], table, depth + 1);
    return a.map((c, i) => c * p + b[i] * (1 - p)) as RGB;
  }
  throw new Error(`不认识的颜色写法（实算只认 #rrggbb、var()、color-mix(in srgb, A p%, B)）：${value}`);
}

function contrast(a: RGB, b: RGB): number {
  const channel = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const lum = ([r, g, bl]: RGB) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(bl);
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** 取一条规则的某个属性值（规则必须恰好一条，属性必须写了）。 */
function valueOf(file: string, selector: string, prop: string, context = ""): string {
  const found = findRules(file, selector, context);
  expect(found.length, `${file} 里 ${context ? context + " " : ""}${selector} 应恰好一条`).toBe(1);
  const value = declarations(found[0].body).get(prop);
  expect(value, `${selector} 的 ${prop}`).toBeDefined();
  return value as string;
}

function ratioOf(fg: string, bg: string, scheme: Scheme): number {
  const table = tokenTable(scheme);
  return contrast(resolveColor(fg, table), resolveColor(bg, table));
}

describe("第三轮：深色 leaf 规则只跟随系统深浅色，写法与 tokens.css 一致", () => {
  it("ui.css 里出现 data-theme 选择器，当且仅当 tokens.css 里也有（现在两边都没有）", () => {
    const ui = DATA_THEME_SELECTOR.test(withoutComments(UI_CSS));
    const tokens = DATA_THEME_SELECTOR.test(withoutComments(THEME_TOKENS));
    expect(ui, `ui.css ${ui ? "有" : "没有"} data-theme 选择器，tokens.css ${tokens ? "有" : "没有"}：加手动主题开关时两边要一起按同一个属性切换`).toBe(tokens);
  });

  it("深色那条写在基础 .ps-btn--leaf 之后：去掉前缀后两条特异性都是 (0,1,0)，靠先后顺序生效", () => {
    const rules = parseRules(UI_CSS);
    const base = rules.findIndex((r) => r.selector === LEAF && r.context === "");
    const dark = rules.findIndex((r) => r.selector === LEAF && r.context === DARK);
    expect(base, "基础 .ps-btn--leaf").toBeGreaterThanOrEqual(0);
    expect(dark, "深色 .ps-btn--leaf 要在基础规则之后").toBeGreaterThan(base);
  });
});

describe("第三轮：按 tokens.css 浅深两套值实算对比度，不低于 4.5:1", () => {
  it("实算器自检：黑白 21:1，#777 对白约 4.48:1，color-mix 按 sRGB 分量线性混合，认不出的写法报错", () => {
    const t = new Map<string, string>([["--a", "#000000"], ["--b", "var(--a)"]]);
    expect(contrast(resolveColor("#000000", t), resolveColor("#ffffff", t))).toBeCloseTo(21, 5);
    expect(contrast(resolveColor("#777777", t), resolveColor("#ffffff", t))).toBeCloseTo(4.48, 2);
    expect(resolveColor("color-mix(in srgb, var(--b) 25%, #ffffff)", t)).toEqual([191.25, 191.25, 191.25]);
    expect(() => resolveColor("rgba(0, 0, 0, 0.5)", t)).toThrow();
    expect(() => resolveColor("var(--missing)", t)).toThrow();
  });

  for (const scheme of ["light", "dark"] as Scheme[]) {
    it(`${scheme}：leaf 按钮的字与底`, () => {
      const bg = valueOf(UI_CSS, LEAF, "background");
      const fg = scheme === "dark" ? valueOf(UI_CSS, LEAF, "color", DARK) : valueOf(UI_CSS, LEAF, "color");
      expect(ratioOf(fg, bg, scheme)).toBeGreaterThanOrEqual(4.5);
    });

    it(`${scheme}：纸卡里的次要字、来源标记在纸面上，无色调标签在自己的底上`, () => {
      const paper = valueOf(UI_CSS, ".ps-card--paper", "background");
      expect(ratioOf(valueOf(UI_CSS, ".ps-card--paper .ps-muted", "color"), paper, scheme), "次要字").toBeGreaterThanOrEqual(4.5);
      expect(ratioOf(valueOf(UI_CSS, ".ps-card--paper .ps-origin", "color"), paper, scheme), "来源标记").toBeGreaterThanOrEqual(4.5);
      expect(ratioOf(valueOf(UI_CSS, PAPER_CHIP, "color"), valueOf(UI_CSS, PAPER_CHIP, "background"), scheme), "标签").toBeGreaterThanOrEqual(4.5);
    });

    it(`${scheme}：照片页场景卡的 9px 小标签，在未选中与选中的卡面上`, () => {
      const fg = valueOf("pets/pets.css", ".ps-photo-scenes small", "color");
      for (const card of [".ps-photo-scenes button", '.ps-photo-scenes button[aria-pressed="true"]']) {
        expect(ratioOf(fg, valueOf("pets/pets.css", card, "background"), scheme), card).toBeGreaterThanOrEqual(4.5);
      }
    });
  }
});

describe("第三轮：收藏页、驾校不再另写纸卡里次要字、来源标记、标签的颜色（交给 ui.css 的纸卡规则）", () => {
  const PAPER_KIDS = /\.ps-card--paper\b[^,]*?\.ps-(?:muted|origin|chip)\b/;
  const REMOVED = [".ds-license-mini .ps-muted", ".ds-photo .ps-muted"];
  const COLOR_DECL = /(?:^|;)\s*(?:color|background(?:-color)?|border-color)\s*:/;

  it("collection.css、school.css 里没有这类规则", () => {
    const offenders: string[] = [];
    for (const file of ["collection/collection.css", "driving_school/school.css"]) {
      for (const rule of parseRules(file)) {
        const parts = rule.selector.split(",").map((s) => s.trim());
        if (parts.some((part) => PAPER_KIDS.test(part) || REMOVED.includes(part)) && COLOR_DECL.test(rule.body)) offenders.push(`${file} ${rule.context} ${rule.selector}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

/* ---------------- 第四轮（2026-09-24）：浅色下带色调标签与“演示数据”的字色 ----------------
 * 浅色下色调字压在同色系浅底（标签）或页面 / 卡面底（演示标记）上只有 1.7～4.0:1：基础规则里字色掺 --c-ink 加深，
 * 深色段恢复原色调令牌（深色本来就在 4.9:1 以上，保持现状）。用上面的令牌实算器断言浅深两套都 ≥ 4.5:1；
 * 深色段与基础规则特异性相同，要写在后面才生效。
 */
const TONED_CHIPS: Record<string, string> = {
  ".ps-chip--leaf": "var(--c-leaf)",
  ".ps-chip--sun": "var(--c-sun)",
  ".ps-chip--coral": "var(--c-coral)",
  ".ps-chip--sky": "var(--c-sea)",
  ".ps-chip--danger": "var(--c-danger)",
};
const THEME_SURFACES = ["var(--c-bg)", "var(--c-bg-soft)", "var(--c-surface)", "var(--c-surface-2)"];

describe("第四轮：带色调标签与“演示数据”，浅深两套都不低于 4.5:1", () => {
  for (const selector of Object.keys(TONED_CHIPS)) {
    it(`${selector}：浅色（基础规则）与深色（深色段）的字，在标签自己的底上`, () => {
      const bg = valueOf(UI_CSS, selector, "background");
      expect(ratioOf(valueOf(UI_CSS, selector, "color"), bg, "light"), "浅色").toBeGreaterThanOrEqual(4.5);
      expect(ratioOf(valueOf(UI_CSS, selector, "color", DARK), bg, "dark"), "深色").toBeGreaterThanOrEqual(4.5);
    });
  }

  it(".ps-origin：浅色与深色的字，在页面底、次底、卡面、次卡面四种主题底色上", () => {
    for (const bg of THEME_SURFACES) {
      expect(ratioOf(valueOf(UI_CSS, ".ps-origin", "color"), bg, "light"), `浅色 ${bg}`).toBeGreaterThanOrEqual(4.5);
      expect(ratioOf(valueOf(UI_CSS, ".ps-origin", "color", DARK), bg, "dark"), `深色 ${bg}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("深色保持现状：深色段里标签是各自的色调令牌、演示标记是 --c-sun，并且写在基础规则之后", () => {
    const rules = parseRules(UI_CSS);
    for (const [selector, token] of Object.entries({ ...TONED_CHIPS, ".ps-origin": "var(--c-sun)" })) {
      expect(valueOf(UI_CSS, selector, "color", DARK), selector).toBe(token);
      const base = rules.findIndex((r) => r.selector === selector && r.context === "");
      const dark = rules.findIndex((r) => r.selector === selector && r.context === DARK);
      expect(dark, `${selector} 深色段要在基础规则之后`).toBeGreaterThan(base);
    }
  });
});

/* ---------------- 第五轮（2026-09-24）：危险按钮、技术信息小字、出错兜底框、未开放状态图标 ----------------
 * 危险按钮与出错兜底框的字、未开放图标：浅色下掺 --c-ink 加深，深色段恢复原令牌（深色本来达标，保持现状）。
 * 技术信息小字（.ps-state__meta / .ps-state__tech）两种模式都改用 --c-ink-2，没有深色段。
 * 文字要求 4.5:1；未开放图标是图形，要求 3:1（仍比文字浅，保留“未开放”的样子）。
 */
function colorIn(selector: string, scheme: Scheme): string {
  if (scheme === "dark" && findRules(UI_CSS, selector, DARK).length) return valueOf(UI_CSS, selector, "color", DARK);
  return valueOf(UI_CSS, selector, "color");
}
const SCHEMES: Scheme[] = ["light", "dark"];

describe("第五轮：危险按钮、技术信息小字、出错兜底框（文字 4.5:1）与未开放图标（图形 3:1），浅深两套", () => {
  it(".ps-btn--danger：字在自己的浅红底上", () => {
    for (const scheme of SCHEMES) expect(ratioOf(colorIn(".ps-btn--danger", scheme), valueOf(UI_CSS, ".ps-btn--danger", "background"), scheme), scheme).toBeGreaterThanOrEqual(4.5);
  });

  for (const selector of [".ps-state__meta", ".ps-state__tech", ".ps-error-boundary"]) {
    it(`${selector}：字在页面底、次底、卡面、次卡面四种主题底色上`, () => {
      for (const scheme of SCHEMES) {
        for (const bg of THEME_SURFACES) expect(ratioOf(colorIn(selector, scheme), bg, scheme), `${scheme} ${bg}`).toBeGreaterThanOrEqual(4.5);
      }
    });
  }

  it(".ps-state--disabled .ps-state__icon：图标在自己的浅暖底上不低于 3:1", () => {
    const selector = ".ps-state--disabled .ps-state__icon";
    for (const scheme of SCHEMES) expect(ratioOf(colorIn(selector, scheme), valueOf(UI_CSS, selector, "background"), scheme), scheme).toBeGreaterThanOrEqual(3);
  });

  it("第六轮：禁用的主按钮（含 aria-disabled）是不透明的浅底配次要字色，浅深两套字对底不低于 3:1（禁用控件的要求）", () => {
    const selector = '.ps-btn.ps-btn--primary:disabled, .ps-btn.ps-btn--primary[aria-disabled="true"]';
    const bg = valueOf(UI_CSS, selector, "background");
    for (const scheme of SCHEMES) expect(ratioOf(valueOf(UI_CSS, selector, "color"), bg, scheme), scheme).toBeGreaterThanOrEqual(3);
    // 不再靠整体半透明表达禁用：opacity 必须回到 1，否则上面的实算不代表实际显示（.ps-btn:disabled 的 0.45 会把字和底一起压淡）
    expect(valueOf(UI_CSS, selector, "opacity")).toBe("1");
  });

  it("第六轮追加：共享顶栏底色至少 96% 不透明（浅深两套都能按令牌算出颜色），底边留一条细线或阴影", () => {
    const d = declarations(uiRule(".ps-topbar").body);
    const fill = (d.get("background-color") ?? d.get("background") ?? "").trim();
    const mix = /^color-mix\(\s*in srgb\s*,\s*(.+?)\s+(\d+(?:\.\d+)?)%\s*,\s*transparent\s*\)$/.exec(fill);
    expect(mix ? Number(mix[2]) / 100 : 1, `顶栏底色 ${fill} 的不透明度`).toBeGreaterThanOrEqual(0.96);
    // 能算出颜色 = 只用了令牌 / 十六进制 / 不带透明的 color-mix；rgba()、transparent 这类写法会直接报错
    for (const scheme of SCHEMES) expect(() => resolveColor(mix ? mix[1] : fill, tokenTable(scheme)), scheme).not.toThrow();
    const line = [d.get("background-image"), d.get("box-shadow"), d.get("border-bottom")].filter((v) => v && v !== "none");
    expect(line.length, "底边细线或阴影").toBeGreaterThan(0);
  });

  it("第七轮：禁用的次要 / 透明按钮不透明，字对底不低于 3:1（次要按钮在自己的卡面底上，透明按钮在四种主题底色上），浅深两套", () => {
    const selector = '.ps-btn.ps-btn--secondary:disabled, .ps-btn.ps-btn--secondary[aria-disabled="true"], .ps-btn.ps-btn--ghost:disabled, .ps-btn.ps-btn--ghost[aria-disabled="true"]';
    const fg = valueOf(UI_CSS, selector, "color");
    for (const scheme of SCHEMES) {
      expect(ratioOf(fg, valueOf(UI_CSS, ".ps-btn--secondary", "background"), scheme), `${scheme} 次要按钮`).toBeGreaterThanOrEqual(3);
      for (const bg of THEME_SURFACES) expect(ratioOf(fg, bg, scheme), `${scheme} 透明按钮 ${bg}`).toBeGreaterThanOrEqual(3);
    }
    expect(valueOf(UI_CSS, selector, "opacity"), "不再靠整体半透明").toBe("1");
  });

  it("第七轮：“技术信息”入口点按区不小于 40px，上下负外边距抵消多出的高度（版面不动）", () => {
    const d = declarations(uiRule(".ps-state__tech summary").body);
    const h = parseInt(d.get("min-height") ?? "0", 10);
    expect(h, "min-height").toBeGreaterThanOrEqual(40);
    const m = /^(-?\d+)px 0$/.exec(d.get("margin") ?? "");
    expect(m, "margin 写成“-Npx 0”").not.toBeNull();
    expect(h + 2 * Number(m![1]), "占位高度仍是原来的 32px").toBe(32);
  });

  it("深色保持现状：危险按钮、兜底框用 --c-danger，未开放图标用 --c-sun，深色段写在基础规则之后", () => {
    const rules = parseRules(UI_CSS);
    const expected: Record<string, string> = { ".ps-btn--danger": "var(--c-danger)", ".ps-error-boundary": "var(--c-danger)", ".ps-state--disabled .ps-state__icon": "var(--c-sun)" };
    for (const [selector, token] of Object.entries(expected)) {
      expect(valueOf(UI_CSS, selector, "color", DARK), selector).toBe(token);
      const base = rules.findIndex((r) => r.selector === selector && r.context === "");
      const dark = rules.findIndex((r) => r.selector === selector && r.context === DARK);
      expect(dark, `${selector} 深色段要在基础规则之后`).toBeGreaterThan(base);
    }
  });
});

/* ---------------- 驾校终检（2026-09-24 晚）：深色主按钮、红线说明、科目行焦点框、出错红字、领证完成页底栏 ----------------
 * 深色主按钮（ui.css 源头）：原来深色下仍是近乎纯黑的深墨底，和深色页面 / 卡面只差 1.1～1.3:1；深色下改成奶白底深墨字，
 *   按钮底对四种深色主题底色都要 ≥ 3:1（图形要求）、字对按钮底 ≥ 4.5:1。纸卡昼夜都是浅色纸面，纸卡里的主按钮深色下仍用深墨底。
 * 红线说明（school.css“通用”段）：浅色掺 --c-ink 到 4.5:1 以上，深色保持 --c-danger。
 * 科目行（“总览 / 科目”段）：卡片 overflow:hidden，焦点框必须画在行内（负的 outline-offset）才不被裁。
 * 出错红字（“通用”段）：浅色掺 --c-ink，深色保持 --c-danger；纸卡里的出错字不论明暗都用纸面的深红。
 * 领证完成页底栏（“领证仪式”段）：贴底的操作栏必须是实底，滚动时下面的字不能从按钮之间透出来。
 */
const SCHOOL_CSS = "driving_school/school.css";
/** 某条规则在浅 / 深色下实际生效的字色：深色有深色段就用深色段，否则用基础规则。 */
function colorInFile(file: string, selector: string, scheme: Scheme): string {
  if (scheme === "dark" && findRules(file, selector, DARK).length) return valueOf(file, selector, "color", DARK);
  return valueOf(file, selector, "color");
}

describe("驾校终检：深色主按钮、红线说明、科目行焦点框、出错红字、领证完成页底栏", () => {
  it("深色主按钮（源头 .ps-btn--primary）：按钮底对四种深色主题底色不低于 3:1、字对按钮底不低于 4.5:1，深色段写在基础规则之后", () => {
    const fill = valueOf(UI_CSS, ".ps-btn--primary", "background", DARK);
    for (const bg of THEME_SURFACES) expect(ratioOf(fill, bg, "dark"), `按钮形状 对 ${bg}`).toBeGreaterThanOrEqual(3);
    expect(ratioOf(valueOf(UI_CSS, ".ps-btn--primary", "color", DARK), fill, "dark"), "字对按钮底").toBeGreaterThanOrEqual(4.5);
    const rules = parseRules(UI_CSS);
    const base = rules.findIndex((r) => r.selector === ".ps-btn--primary" && r.context === "");
    const dark = rules.findIndex((r) => r.selector === ".ps-btn--primary" && r.context === DARK);
    expect(dark, "深色段要在基础规则之后").toBeGreaterThan(base);
  });

  it("纸卡里的主按钮：深色下纸面仍是浅色，按钮底对纸面不低于 3:1、字对按钮底不低于 4.5:1", () => {
    const fill = valueOf(UI_CSS, ".ps-card--paper .ps-btn--primary", "background", DARK);
    const paper = valueOf(UI_CSS, ".ps-card--paper", "background");
    expect(ratioOf(fill, paper, "dark"), "按钮形状 对纸面").toBeGreaterThanOrEqual(3);
    expect(ratioOf(valueOf(UI_CSS, ".ps-card--paper .ps-btn--primary", "color", DARK), fill, "dark"), "字对按钮底").toBeGreaterThanOrEqual(4.5);
  });

  it("红线说明 .ds-redlines：浅深两套字在自己的浅红 / 深红底上都不低于 4.5:1，深色段写在基础规则之后", () => {
    const bg = valueOf(SCHOOL_CSS, ".ds-redlines", "background");
    expect(ratioOf(valueOf(SCHOOL_CSS, ".ds-redlines", "color"), bg, "light"), "浅色").toBeGreaterThanOrEqual(4.5);
    expect(ratioOf(valueOf(SCHOOL_CSS, ".ds-redlines", "color", DARK), bg, "dark"), "深色").toBeGreaterThanOrEqual(4.5);
    const rules = parseRules(SCHOOL_CSS);
    const base = rules.findIndex((r) => r.selector === ".ds-redlines" && r.context === "");
    const dark = rules.findIndex((r) => r.selector === ".ds-redlines" && r.context === DARK);
    expect(dark, "深色段要在基础规则之后").toBeGreaterThan(base);
  });

  it("科目行 .ds-subject-row：键盘焦点框画在行内（outline-offset 为负），不被 overflow:hidden 的卡片裁掉", () => {
    const offset = parseFloat(valueOf(SCHOOL_CSS, ".ds-subject-row:focus-visible", "outline-offset"));
    expect(offset, "outline-offset").toBeLessThan(0);
  });

  it("出错红字 .ds-error：浅深两套在四种主题底色上、纸卡里的出错字在纸面上（明暗都一样），都不低于 4.5:1", () => {
    for (const scheme of SCHEMES) {
      for (const bg of THEME_SURFACES) expect(ratioOf(colorInFile(SCHOOL_CSS, ".ds-error", scheme), bg, scheme), `${scheme} ${bg}`).toBeGreaterThanOrEqual(4.5);
      expect(ratioOf(valueOf(SCHOOL_CSS, ".ps-card--paper .ds-error", "color"), valueOf(UI_CSS, ".ps-card--paper", "background"), scheme), `${scheme} 纸卡`).toBeGreaterThanOrEqual(4.5);
    }
    const rules = parseRules(SCHOOL_CSS);
    const base = rules.findIndex((r) => r.selector === ".ds-error" && r.context === "");
    const dark = rules.findIndex((r) => r.selector === ".ds-error" && r.context === DARK);
    expect(dark, "深色段要在基础规则之后").toBeGreaterThan(base);
  });

  it("领证完成页底栏 .ds-ceremony__actions：实底（浅深两套都能按令牌算出颜色，不掺 transparent）", () => {
    const fill = valueOf(SCHOOL_CSS, ".ds-ceremony__actions", "background");
    expect(fill).not.toMatch(/transparent/);
    for (const scheme of SCHEMES) expect(() => resolveColor(fill, tokenTable(scheme)), scheme).not.toThrow();
  });
});
