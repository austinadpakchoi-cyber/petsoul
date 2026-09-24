/**
 * 静态守卫：src 里不许出现与契约生成类型（src/shared/contracts/generated.ts 的导出）同名的本地类型声明。
 *
 * 为什么（2026-09-24 实证）：journey/travelPlan/model.ts 曾有一份与生成类型同名的本地草案 TravelJourneySummary，
 * 契约改名（fare_paid → fare）后重新生成够不到它；tsc 看到的是自洽的本地类型，fixture 也用旧名，于是 typecheck 与用例全绿，
 * 运行期那个字段却永远是 undefined、被防御分支安静吞掉。同名恰恰让它看起来像已经接上了。
 * 修法是删掉本地声明、改成 import——静默的运行期错误就变成编译错误。这条测试防止同类草案再出现。
 *
 * 危险度不看“同名”本身，看“能不能悄悄互相顶替”：两者没有任何公共成员名时，误用必定编译报错，才允许进白名单；
 * 白名单每一条都带一个会执行的不变量，前提消失（例如给接口加了同名成员）时当场变红，不会在前提消失后继续生效。
 *
 * 变异自检用 CONTRACT_SHADOW_ROOT 指向一份项目副本（只读原仓库，副本里改）。
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const ROOT = process.env.CONTRACT_SHADOW_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), "..");
const GENERATED = join(ROOT, "src", "shared", "contracts", "generated.ts");

interface Allowed {
  file: string;
  name: string;
  /** 为什么允许同名。 */
  reason: string;
  /** 允许的前提；前提不成立时该条目变红（见下面的用例）。 */
  invariant: "disjoint-members";
}

const ALLOWED: ReadonlyArray<Allowed> = [
  {
    file: "src/shared/services/types.ts",
    name: "WorldService",
    reason:
      "前端服务接口（home / state 等方法）与契约的承运身份模型（world_service_id、carrier_name、mode…）同名；两者没有公共成员名，误用必定编译报错。I 2026-09-24 定：不改名（types.ts 的 *Service 命名惯例）。",
    invariant: "disjoint-members",
  },
];

/** 真正的本地类型声明（interface / type / enum / class 后紧跟 { = < extends implements）；import 列表里的 `type X,` 不算。 */
const DECLARATION = /^[ \t]*(?:export[ \t]+)?(?:declare[ \t]+)?(?:interface|type|enum|class)[ \t]+([A-Za-z_$][\w$]*)[ \t]*(?:<|=|\{|extends\b|implements\b)/gm;

function generatedTypeNames(): Set<string> {
  const text = readFileSync(GENERATED, "utf8");
  const names = new Set<string>();
  for (const m of text.matchAll(/^export[ \t]+(?:interface|type|enum)[ \t]+([A-Za-z_$][\w$]*)/gm)) names.add(m[1]);
  return names;
}

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === "node_modules") continue;
      sourceFiles(full, out);
    } else if (/\.(ts|tsx)$/.test(name) && !/\.d\.ts$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

function rel(file: string): string {
  return relative(ROOT, file).replace(/\\/g, "/");
}

/** 与生成类型同名的本地声明，形如 "src/…/file.ts WorldService"（生成物本身不算）。 */
function shadowingDeclarations(): string[] {
  const exported = generatedTypeNames();
  const hits: string[] = [];
  for (const file of sourceFiles(join(ROOT, "src"))) {
    if (rel(file) === "src/shared/contracts/generated.ts") continue;
    const text = readFileSync(file, "utf8");
    for (const m of text.matchAll(DECLARATION)) if (exported.has(m[1])) hits.push(`${rel(file)} ${m[1]}`);
  }
  return hits.sort();
}

/** 接口体里第一层的成员名（去掉注释；嵌套的对象、参数列表、泛型里的名字不算）。 */
function interfaceMembers(text: string, name: string): string[] {
  const clean = text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  const head = new RegExp(`(?:^|\\n)[ \\t]*(?:export[ \\t]+)?interface[ \\t]+${name}\\b[^{]*\\{`).exec(clean);
  if (!head) throw new Error(`找不到 interface ${name}`);
  // 只保留第一层的字符：嵌套的内容换成空格，第一层的括号本身留着（方法名后面要认得出“(”），“=>”里的“>”不算括号。
  let depth = 0;
  let body = "";
  for (let i = head.index + head[0].length; i < clean.length; i++) {
    const ch = clean[i];
    const arrow = ch === ">" && clean[i - 1] === "=";
    if (!arrow && "})]>".includes(ch)) {
      if (depth === 0) {
        if (ch === "}") break;
        continue;
      }
      depth--;
      body += depth === 0 ? ch : " ";
      continue;
    }
    if ("{([<".includes(ch)) {
      body += depth === 0 ? ch : " ";
      depth++;
      continue;
    }
    body += depth === 0 || ch === "\n" ? ch : " ";
  }
  const members = new Set<string>();
  for (const m of body.matchAll(/(?:^|[;\n])[ \t]*(?:readonly[ \t]+)?([A-Za-z_$][\w$]*)[ \t]*\??[ \t]*[:(<]/g)) members.add(m[1]);
  return [...members].sort();
}

describe("契约生成类型不被同名本地声明遮蔽", () => {
  it("声明识别：认得出真正的声明，import 列表里的 type 不算", () => {
    const sample = [
      "export interface Foo {",
      "type Bar = string;",
      "interface Baz<T> extends Qux<T> {",
      "export declare class Kit implements Tool {",
      "import { type Feed, type Source } from \"@/shared/contracts\";",
      "  type Inline,",
    ].join("\n");
    expect([...sample.matchAll(DECLARATION)].map((m) => m[1])).toEqual(["Foo", "Bar", "Baz", "Kit"]);
  });

  it("前提：确实读到了生成物与源码（不是空扫一遍就绿）", () => {
    expect(generatedTypeNames().size).toBeGreaterThan(300);
    expect(sourceFiles(join(ROOT, "src")).length).toBeGreaterThan(100);
  });

  it("src 里与生成类型同名的本地声明，恰好是白名单里的这些（多一个、少一个都红）", () => {
    expect(shadowingDeclarations()).toEqual(ALLOWED.map((a) => `${a.file} ${a.name}`).sort());
  });

  it.each(ALLOWED.filter((a) => a.invariant === "disjoint-members"))("白名单前提仍成立：$file 的 $name 与生成的同名模型没有公共成员名", (allowed) => {
    const local = interfaceMembers(readFileSync(join(ROOT, allowed.file), "utf8"), allowed.name);
    const generated = interfaceMembers(readFileSync(GENERATED, "utf8"), allowed.name);
    // 两边都要真读到成员，否则“交集为空”是空断言。
    expect(local.length).toBeGreaterThan(0);
    expect(generated.length).toBeGreaterThan(0);
    expect(local.filter((m) => generated.includes(m))).toEqual([]);
  });
});
