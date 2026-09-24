/**
 * claude-6c2b · 可复用的宠物头像与状态表情（live 规则）：
 * 头像永远是 TA 自己的样子——有照片用照片；live 没有照片显示爪印占位，不用名字首字，也不借演示小灰猫冒充；
 * 状态表情只由结构化的 mood 决定（睡觉 zzz、走路爪印、店里热气……），任何宠物都能用。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { PetPortrait, petPortraitUrl } from "@/features/pets/PetPortrait";
import { MOOD_LABEL, PetMoodAvatar, type PetMood } from "@/features/pets/PetMoodAvatar";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => cleanup());

describe("PetPortrait（live）", () => {
  it("有照片用照片", () => {
    const { container } = render(<PetPortrait name="栗子" photoUrl="/media/pets/p1.jpg" size={40} />);
    expect(container.querySelector("img")?.getAttribute("src")).toBe("/media/pets/p1.jpg");
    expect(container.querySelector("[role=img]")?.getAttribute("aria-label")).toBe("栗子");
  });

  it("没有照片：爪印占位，不写名字首字，也不用演示小灰猫", () => {
    const { container } = render(<PetPortrait name="栗子" photoUrl={null} size={40} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".ps-pet-portrait.is-placeholder svg")).toBeTruthy();
    expect(container.textContent).toBe("");
    expect(petPortraitUrl(null)).toBeNull();
  });
});

describe("PetMoodAvatar：结构化状态 → 表情", () => {
  const cases: Array<[PetMood, string | null]> = [
    ["sleeping", ".ps-mood__zzz"],
    ["walking", ".ps-mood__steps"],
    ["riding", ".ps-mood__wind"],
    ["cafe", ".ps-mood__steam"],
    ["working", ".ps-mood__spark"],
    ["exploring", ".ps-mood__spark"],
    ["eating", ".ps-mood__crumbs"],
    ["sunbathing", ".ps-mood__rays"],
    ["idle", null],
    ["unknown", null],
  ];

  it.each(cases)("%s", (mood, fx) => {
    const { container } = render(<PetMoodAvatar name="栗子" photoUrl="/media/pets/p1.jpg" mood={mood} size={44} />);
    const root = container.querySelector(".ps-mood")!;
    expect(root.classList.contains(`is-${mood}`)).toBe(true);
    expect(root.getAttribute("aria-label")).toBe(`栗子，${MOOD_LABEL[mood]}`);
    if (fx) expect(root.querySelector(fx)).toBeTruthy();
    for (const other of [".ps-mood__zzz", ".ps-mood__steps", ".ps-mood__wind", ".ps-mood__steam", ".ps-mood__spark", ".ps-mood__crumbs", ".ps-mood__rays"]) {
      if (other !== fx) expect(root.querySelector(other)).toBeNull();
    }
    // 头像本身不写首字
    expect(root.querySelector(".ps-pet-portrait")?.textContent).toBe("");
  });

  it("只有睡觉才冒 z Z z", () => {
    const { container } = render(<PetMoodAvatar name="栗子" mood="sleeping" />);
    expect(container.querySelector(".ps-mood__zzz")?.textContent).toBe("zzZ");
  });

  it("可以关掉徽标（列表里用）", () => {
    const { container } = render(<PetMoodAvatar name="栗子" mood="walking" badge={false} />);
    expect(container.querySelector(".ps-mood__badge")).toBeNull();
    expect(container.querySelector(".ps-mood__steps")).toBeTruthy();
  });
});
