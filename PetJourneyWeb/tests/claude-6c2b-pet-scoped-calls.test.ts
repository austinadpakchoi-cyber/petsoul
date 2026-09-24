/**
 * 静态守卫：服务接口（src/shared/services/types.ts）里凡是带“可选 petId”参数的方法，src 里每一处调用都必须显式传宠物。
 *
 * 为什么（2026-09-24）：家里宠物多于一只时，后端按宠物的接口不带 pet_id 会 409 pet_required（或更糟：设置 GET 默默给第一只）。
 * 这批签名为了不一次打爆别处测试，petId 先做成可选；可选参数漏传时编译器不会响，所以用这条测试按类型解析调用点来挡——
 * 按类型、不按方法名：`session` / `submit` / `updateSettings` 在别的服务里也有同名方法，只有解析到的声明才算数。
 * 字面量 null / undefined 当作没传。改成必填（触发条件：本批 UI 分身全部验收后，由 6c2b 改）以后，这条测试仍然成立、可以留着。
 *
 * 覆盖不到的（别当成“全部调用都被守住了”）：
 * - 只看 src/，不看 tests/ 里的调用；
 * - 只看“有没有传”，不看传进去的表达式运行时是不是 undefined（例如 `pet?.pet_id` 在没有宠物时）；
 * - 不经过我们代码里的调用表达式的用法：把方法本身交出去让别人调（如 `queryFn: services.driving.history`——
 *   react-query 会用它自己的上下文对象当第一个参数去调），这类用法这里看不到；
 * - 调用方类型是 any、解析不出签名的调用；
 * - 用展开参数（`...args`）转发的调用会被当成“没传”（宁可误报）。
 *
 * 变异自检用 PET_CALLS_OVERRIDES 指向一个 JSON（{ 绝对路径: 替换后的全文 }），只在内存里替换读到的文件，不写盘；
 * 从别处跑这份测试时用 PET_CALLS_ROOT 指明项目根。
 */
import { readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { beforeAll, describe, expect, it } from "vitest";

const ROOT = (process.env.PET_CALLS_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), ".."));
const TYPES_FILE = resolve(ROOT, "src/shared/services/types.ts");

function norm(file: string): string {
  return resolve(file).replace(/\\/g, "/").toLowerCase();
}

function buildProgram(): ts.Program {
  const overrides: Record<string, string> = process.env.PET_CALLS_OVERRIDES
    ? Object.fromEntries(Object.entries(JSON.parse(readFileSync(process.env.PET_CALLS_OVERRIDES, "utf8")) as Record<string, string>).map(([k, v]) => [norm(k), v]))
    : {};
  const parsed = ts.getParsedCommandLineOfConfigFile(resolve(ROOT, "tsconfig.app.json"), {}, {
    ...ts.sys,
    onUnRecoverableConfigFileDiagnostic: (d) => {
      throw new Error(ts.flattenDiagnosticMessageText(d.messageText, "\n"));
    },
  });
  if (!parsed) throw new Error("读不到 tsconfig.app.json");
  const host = ts.createCompilerHost(parsed.options, true);
  const readFile = host.readFile.bind(host);
  host.readFile = (file) => overrides[norm(file)] ?? readFile(file);
  const getSourceFile = host.getSourceFile.bind(host);
  host.getSourceFile = (file, lang, onError, fresh) => {
    const text = overrides[norm(file)];
    return text === undefined ? getSourceFile(file, lang, onError, fresh) : ts.createSourceFile(file, text, lang, true);
  };
  return ts.createProgram({ rootNames: parsed.fileNames, options: parsed.options, host });
}

interface Target {
  label: string;
  index: number;
}

/** types.ts 里每个接口方法：参数里有名为 petId 且可选（?）的，记下它在第几个位置。 */
function optionalPetIdMethods(program: ts.Program): Map<ts.Node, Target> {
  const source = program.getSourceFile(TYPES_FILE);
  if (!source) throw new Error("程序里没有 types.ts");
  const targets = new Map<ts.Node, Target>();
  source.forEachChild((node) => {
    if (!ts.isInterfaceDeclaration(node)) return;
    for (const member of node.members) {
      if (!ts.isMethodSignature(member) || !member.name) continue;
      member.parameters.forEach((param, index) => {
        if (ts.isIdentifier(param.name) && param.name.text === "petId" && param.questionToken) {
          targets.set(member, { label: `${node.name.text}.${member.name.getText(source)}`, index });
        }
      });
    }
  });
  return targets;
}

interface Scan {
  checked: string[];
  missing: string[];
}

function scanCalls(program: ts.Program, targets: Map<ts.Node, Target>): Scan {
  const checker = program.getTypeChecker();
  const srcRoot = norm(resolve(ROOT, "src")) + "/";
  const checked: string[] = [];
  const missing: string[] = [];
  for (const file of program.getSourceFiles()) {
    const path = norm(file.fileName);
    if (!path.startsWith(srcRoot) || path === norm(TYPES_FILE) || file.isDeclarationFile) continue;
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node)) {
        const declaration = checker.getResolvedSignature(node)?.getDeclaration();
        const target = declaration ? targets.get(declaration) : undefined;
        if (target) {
          const { line } = file.getLineAndCharacterOfPosition(node.getStart(file));
          const where = `${relative(ROOT, file.fileName).replace(/\\/g, "/")}:${line + 1} ${target.label}`;
          checked.push(where);
          const arg = node.arguments[target.index];
          const literalNothing = arg && (arg.kind === ts.SyntaxKind.NullKeyword || (ts.isIdentifier(arg) && arg.text === "undefined"));
          if (!arg || literalNothing) missing.push(where);
        }
      }
      node.forEachChild(visit);
    };
    visit(file);
  }
  return { checked, missing };
}

describe("按宠物的服务调用都显式带宠物", () => {
  let targets: Map<ts.Node, Target>;
  let scan: Scan;

  beforeAll(() => {
    const program = buildProgram();
    targets = optionalPetIdMethods(program);
    scan = scanCalls(program, targets);
  }, 120_000);

  it("前提：认出了带可选 petId 的方法（本批放行的那些都在），也确实检查到了调用点", () => {
    const labels = [...targets.values()].map((t) => t.label);
    for (const expected of [
      "SessionService.settings",
      "SessionService.updateSettings",
      "WorldService.state",
      "EconomyService.market",
      "EconomyService.sell",
      "EconomyService.fulfill",
      "DrivingSchoolService.enroll",
      "DrivingSchoolService.createSession",
      "DrivingSchoolService.history",
      "DrivingSchoolService.ceremony",
    ]) {
      expect(labels).toContain(expected);
    }
    // 同名但无关的方法不算：陪伴媒体的 session、家庭的 updateSettings 没有 petId 参数。
    expect(labels).not.toContain("CompanionMediaService.session");
    expect(labels).not.toContain("HouseholdService.updateSettings");
    expect(scan.checked.length).toBeGreaterThan(15);
  });

  it("src 里每一处调用都显式传了 petId（不许省略，不许写字面量 null / undefined）", () => {
    expect(scan.missing).toEqual([]);
  });
});
