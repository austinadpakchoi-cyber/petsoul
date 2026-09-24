/**
 * 卡包里的驾照换用 UI-ASSET-009 第 11 项正反底图（claude-6c2b 答题分身，2026-09-24）：
 * - 驾照正面、背面、卡包小卡面带 data-license-art，并把这一面的 --cred-art-front / --cred-art-back 换成 SCHOOL_ART.license 的网址；
 * - 图片加载失败：去掉属性与网址，退回 life.css 里原来的样子（UI-ASSET-005 底图、照片框、横线）；
 * - 别的证件（星球居民证、银行卡……）不带这个属性、不带内联底图，外观不变；
 * - 名字、号码、照片、日期仍由代码按真实数据叠上去；
 * - 样式表：新增规则一律限定在 .ps-cred--driver_license[data-license-art] 下；不改卡片比例；深色遮罩比原来重、字下面有衬底。
 * 变异自检：LICENSE_CSS 可指向 life.css 的一份副本（只读），默认读 src/features/life/life.css。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import type { CredentialDetail, CredentialKind } from "@/shared/contracts";
import { SCHOOL_ART } from "@/features/driving_school/assets";
import { CredentialBack, CredentialFront, MiniCard } from "@/features/life/faces";
import type { WalletPet } from "@/features/life/data";

const HERE = dirname(fileURLToPath(import.meta.url));
const CSS_PATH = process.env.LICENSE_CSS ?? resolve(HERE, "..", "src", "features", "life", "life.css");

/** 假的 Image：按用例指定让图片“加载成功”或“加载失败”（jsdom 本身不加载图片，两个事件都不会来）。 */
let loads: "ok" | "fail" = "ok";
const requested: string[] = [];
class FakeImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  set src(value: string) {
    requested.push(value);
    queueMicrotask(() => (loads === "ok" ? this.onload?.() : this.onerror?.()));
  }
}
const RealImage = globalThis.Image;
beforeEach(() => {
  loads = "ok";
  requested.length = 0;
  globalThis.Image = FakeImage as unknown as typeof Image;
});
afterEach(() => {
  cleanup();
  globalThis.Image = RealImage;
});

const pet: WalletPet = { name: "小满", species: "dog", photoUrl: null, photoGenerated: false, idPhoto: null, ready: true };

function detail(kind: CredentialKind, fields: [string, string][]): CredentialDetail {
  return {
    summary: {
      credential_id: `cred-${kind}`,
      kind,
      label: kind === "driver_license" ? "爪爪驾驶证" : kind === "identity_card" ? "星球居民证" : "星球银行卡",
      status: "active",
      number: kind === "driver_license" ? "PAW-C-000123" : "PS-ID-0001",
      issued_at: "2026-09-24T03:00:00Z",
      title: null,
      condition: "",
      private: false,
      links: [],
    },
    fields: fields.map(([label, value]) => ({ label, value })),
    balance: kind === "bank_card" ? 120 : null,
    ledger: [],
    stamps: [],
    care_notes: [],
  };
}

const LICENSE = detail("driver_license", [
  ["姓名", "小满"],
  ["准驾车型", "C 照"],
  ["发证日期", "2026-09-24"],
  ["有效期", "长期"],
  ["签发机构", "爪爪驾校"],
  ["编号", "PAW-C-000123"],
]);
const IDENTITY = detail("identity_card", [
  ["姓名", "小满"],
  ["入住日期", "2026-09-22"],
]);
const BANK = detail("bank_card", [["户名", "小满"]]);

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("驾照：用 UI-ASSET-009 的正反底图", () => {
  it("正面、背面、卡包小卡面都换成 SCHOOL_ART.license 的网址，并带 data-license-art", async () => {
    const { container } = render(
      <>
        <CredentialFront detail={LICENSE} pet={pet} />
        <CredentialBack detail={LICENSE} pet={pet} />
        <MiniCard summary={LICENSE.summary} pet={pet} />
      </>,
    );
    await settle();
    const front = container.querySelector('[data-testid="cred-front"]') as HTMLElement;
    const back = container.querySelector('[data-testid="cred-back"]') as HTMLElement;
    const mini = container.querySelector('[data-testid="wallet-card"]') as HTMLElement;
    for (const el of [front, back, mini]) expect(el.getAttribute("data-license-art")).toBe("009");
    expect(front.style.getPropertyValue("--cred-art-front")).toBe(`url("${SCHOOL_ART.license.front}")`);
    expect(mini.style.getPropertyValue("--cred-art-front")).toBe(`url("${SCHOOL_ART.license.front}")`);
    expect(back.style.getPropertyValue("--cred-art-back")).toBe(`url("${SCHOOL_ART.license.back}")`);
    expect(new Set(requested)).toEqual(new Set([SCHOOL_ART.license.front, SCHOOL_ART.license.back]));
  });

  it("名字、号码、照片、日期仍由代码按真实数据叠上去（图上没有字）", async () => {
    const { container } = render(
      <>
        <CredentialFront detail={LICENSE} pet={pet} />
        <CredentialBack detail={LICENSE} pet={pet} />
      </>,
    );
    await settle();
    const front = container.querySelector('[data-testid="cred-front"]')!;
    const back = container.querySelector('[data-testid="cred-back"]')!;
    expect(front.textContent).toContain("爪爪驾驶证");
    expect(front.textContent).toContain("小满");
    expect(front.textContent).toContain("C 照");
    expect(front.querySelector('[data-testid="id-photo"]')!.getAttribute("aria-label")).toContain("小满");
    // 正面放前 4 个，其余排到背面的横线上
    expect(back.textContent).toContain("签发机构");
    expect(back.textContent).toContain("PAW-C-000123");
  });

  it("底图加载失败：去掉 data-license-art 和新图网址，退回 life.css 里原来的样子", async () => {
    loads = "fail";
    const { container } = render(
      <>
        <CredentialFront detail={LICENSE} pet={pet} />
        <CredentialBack detail={LICENSE} pet={pet} />
        <MiniCard summary={LICENSE.summary} pet={pet} />
      </>,
    );
    await settle();
    for (const id of ["cred-front", "cred-back", "wallet-card"]) {
      const el = container.querySelector(`[data-testid="${id}"]`) as HTMLElement;
      expect(el.hasAttribute("data-license-art"), id).toBe(false);
      expect(el.style.getPropertyValue("--cred-art-front"), id).toBe("");
      expect(el.style.getPropertyValue("--cred-art-back"), id).toBe("");
      expect(el.className, id).toContain("ps-cred--driver_license");
    }
  });

  it("别的证件（星球居民证正反、银行卡、它们的小卡面）不带这个属性、不带内联底图，也不去加载驾照底图", async () => {
    const { container } = render(
      <>
        <CredentialFront detail={IDENTITY} pet={pet} />
        <CredentialBack detail={IDENTITY} pet={pet} />
        <MiniCard summary={IDENTITY.summary} pet={pet} />
        <CredentialFront detail={BANK} pet={pet} />
        <MiniCard summary={BANK.summary} pet={pet} />
      </>,
    );
    await settle();
    const cards = container.querySelectorAll(".ps-cred");
    expect(cards.length).toBeGreaterThanOrEqual(5);
    for (const el of cards) {
      expect(el.hasAttribute("data-license-art"), el.className).toBe(false);
      expect((el as HTMLElement).getAttribute("style"), el.className).toBeNull();
    }
    expect(requested).toEqual([]);
  });
});

describe("驾照背面“成绩”一行：每一科作为一个整体不在中间折行", () => {
  // 服务端原文（18779 实取）：科与科之间是全角空格 U+3000，科内是普通空格
  const SCORES = "科一 100 分\u3000科二 100 分\u3000科三 90 分\u3000科四 100 分";
  const WITH_SCORES = detail("driver_license", [
    ["名字", "团团"],
    ["准驾车型", "C（星球小型车）"],
    ["证号", "PAW-DL-2026-T49GTW"],
    ["初次领取", "2026-09-24"],
    ["成绩", SCORES],
    ["签发机构", "爪爪驾校（PetSoul 星球交通局）"],
  ]);
  const scoreValue = (root: ParentNode) => [...root.querySelectorAll('[data-testid="field-value"]')].find((dd) => dd.textContent?.includes("四"))!;

  it("每一科包在一个不换行的 span 里；科与科之间的全角空格在 span 外面，照旧可以折行", async () => {
    const { container } = render(<CredentialBack detail={WITH_SCORES} pet={pet} />);
    await settle();
    const dd = scoreValue(container);
    expect([...dd.querySelectorAll("span.ps-score-item")].map((s) => s.textContent)).toEqual(["科一 100 分", "科二 100 分", "科三 90 分", "科四 100 分"]);
    const between = [...dd.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE && n.textContent).map((n) => n.textContent);
    expect(between).toEqual(["\u3000", "\u3000", "\u3000"]);
  });

  it("文字一个字符都不改：textContent 与服务端原文逐字相同，没有插任何隐形字符", async () => {
    const { container } = render(<CredentialBack detail={WITH_SCORES} pet={pet} />);
    await settle();
    expect(scoreValue(container).textContent).toBe(SCORES);
    expect(container.textContent).not.toMatch(/[\u2060\u00a0\u200b\ufeff]/);
    // 别的字段原样（例如签发机构里的普通空格照旧）
    expect(container.textContent).toContain("爪爪驾校（PetSoul 星球交通局）");
  });

  it("样式：驾照里的 .ps-score-item 不换行（新图、退回旧图时都生效，不挂在 data-license-art 上）", () => {
    const found = rules().filter((r) => r.selector === ".ps-cred--driver_license .ps-score-item" && r.context === "");
    expect(found.length).toBe(1);
    expect(found[0].body).toMatch(/(?:^|;)\s*white-space\s*:\s*nowrap/);
  });

  it("只有驾照这样处理：星球居民证里就算出现同样写法也原样显示、不包 span", async () => {
    const odd = detail("identity_card", [["备注", "科一 100 分"]]);
    const { container } = render(<CredentialFront detail={odd} pet={pet} />);
    await settle();
    expect(container.textContent).toContain("科一 100 分");
    expect(container.querySelector(".ps-score-item")).toBeNull();
  });
});

/** 去掉注释后逐条取规则：选择器（空白归一）、所在 @ 规则、声明体。 */
function rules(): { selector: string; context: string; body: string }[] {
  const src = readFileSync(CSS_PATH, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const out: { selector: string; context: string; body: string }[] = [];
  const stack: string[] = [];
  let buf = "";
  for (const ch of src) {
    if (ch === "{") {
      stack.push(buf.trim().replace(/\s+/g, " "));
      buf = "";
    } else if (ch === "}") {
      const prelude = stack.pop() ?? "";
      if (!prelude.startsWith("@")) out.push({ selector: prelude, context: stack.filter((s) => s.startsWith("@")).join(" "), body: buf.trim() });
      buf = "";
    } else buf += ch;
  }
  return out;
}

describe("驾照新底图的样式：只动驾照这一块", () => {
  const artRules = () => rules().filter((r) => r.selector.includes("data-license-art"));

  it("新增规则的每个选择器都以 .ps-cred--driver_license[data-license-art] 开头（别的证件不受影响）", () => {
    const found = artRules();
    expect(found.length).toBeGreaterThan(5);
    for (const r of found) for (const part of r.selector.split(",").map((s) => s.trim())) expect(part, r.selector).toMatch(/^\.ps-cred--driver_license\[data-license-art\]/);
  });

  it("不改卡片比例与高度（卡高仍是 63.05cqw，不跳版面）", () => {
    // 背面横线是绝对定位的叠层（::before），它的 height 是四条线的范围，不占卡片的高度，单独核
    for (const r of artRules().filter((x) => !x.selector.endsWith("::before"))) expect(r.body, r.selector).not.toMatch(/(?:^|;)\s*(?:aspect-ratio|min-height|height|grid-template-rows|grid-template-columns)\s*:/);
    const ruled = artRules().find((r) => r.selector.endsWith("::before"));
    expect(ruled, "背面横线").toBeTruthy();
    expect(ruled!.body).toMatch(/(?:^|;)\s*height\s*:\s*calc\(3 \* 11\.62cqw \+ 1\.5px\)/);
  });

  it("深色：遮罩比原来的 16% 重（压暗一点），字下面的衬底也跟着压", () => {
    const dark = rules().filter((r) => r.context === "@media (prefers-color-scheme: dark)" && r.selector === ".ps-cred--driver_license[data-license-art]");
    expect(dark.length).toBe(1);
    const dim = Number(dark[0].body.match(/--cred-dim\s*:\s*color-mix\(in srgb, var\(--c-deep-ink\) ([\d.]+)%/)?.[1]);
    expect(dim).toBeGreaterThan(16);
    expect(dark[0].body).toMatch(/--license-veil\s*:/);
  });

  it("字都压在衬底上：标题、字段、页脚、小卡面的标题与标签、背面横线区都用 --license-veil", () => {
    const veiled = new Set(
      artRules()
        .filter((r) => /background\s*:[^;]*var\(--license-veil\)/.test(r.body))
        .flatMap((r) => r.selector.split(",").map((s) => s.trim().replace(".ps-cred--driver_license[data-license-art]", "").trim())),
    );
    for (const part of [".ps-idcard__title", ".ps-mini__titles", ".ps-idcard__fields", ".ps-idcard__foot", ".ps-fiction-box", ".ps-idcard__republic", ".ps-mini__tag", ".ps-mini__issued", ".ps-idcard--ruled::before"]) {
      expect(veiled.has(part), part).toBe(true);
    }
  });
});
