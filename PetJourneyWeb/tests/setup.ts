import "@testing-library/dom";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// 每条用例后清空页面。项目没开 vitest 的 globals，@testing-library/react 不会自己注册清理；
// 不清理时上一条用例渲染的页面会留到下一条，按整页查找的断言可能是在旧页面上通过的（2026-09-24 web-041-entry 实证过一次）。
// 各文件里自己写的 afterEach(cleanup) 可以留着，重复清理没有副作用。守卫：tests/claude-6c2b-cleanup-between-tests.test.tsx。
afterEach(() => cleanup());
