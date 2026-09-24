/**
 * claude-6c2b · 用例之间页面要清空（tests/setup.ts 全局注册了 cleanup）。
 * 没有这一条时，上一条用例渲染的页面会留到下一条，按整页查找的断言可能是在旧页面上通过的：
 * 2026-09-24 web-041-entry 的“寻找我的 TA”断言，实际是在上一条用例留下的欢迎页上通过的。
 * 这个文件故意不自己写 afterEach(cleanup)，只靠全局那一条；两条用例按顺序跑。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

describe("用例之间页面清空（全局 cleanup）", () => {
  it("第一条：渲染一段内容", () => {
    render(<p>上一条用例留下的字</p>);
    expect(screen.getByText("上一条用例留下的字")).toBeTruthy();
  });

  it("第二条：开场时页面是空的，上一条渲染的内容已经被清掉", () => {
    expect(document.body.childElementCount).toBe(0);
    expect(screen.queryByText("上一条用例留下的字")).toBeNull();
  });
});
