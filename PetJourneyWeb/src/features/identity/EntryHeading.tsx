import { BrandLogo } from "@/shared/ui/BrandLogo";
import "./identity.css";

/** 入住准备的四站：账号 → 认识 TA → 接待与叮嘱 → 入住。领养分支同样四站，只是第二站是“迎接 TA”。 */
export const ENTRY_STEP_COUNT = 4;
export type EntryStep = 1 | 2 | 3 | 4;

export function entryStepKicker(step: EntryStep): string {
  return `入住准备 · 0${step} / 0${ENTRY_STEP_COUNT}`;
}

/** 步骤条单独可用：接待页、入住页的场景头图里也放同一条，保证四站在整条流程里读法一致。 */
export function EntrySteps({ step, className = "" }: { step: EntryStep; className?: string }) {
  return (
    <div className={`ps-entry-heading__steps ${className}`} role="img" aria-label={`入住准备第 ${step} 步，共 ${ENTRY_STEP_COUNT} 步`}>
      {Array.from({ length: ENTRY_STEP_COUNT }, (_, index) => <span key={index} className={index < step ? "is-active" : ""} />)}
    </div>
  );
}

/** 第一批入口的同一视觉节奏：开场影片之后，每一步都像翻开同一本生活手册。 */
export function EntryHeading({ step, kicker, title, description }: { step?: EntryStep; kicker: string; title: string; description: string }) {
  return (
    <header className="ps-entry-heading">
      <div className="ps-entry-heading__top">
        <BrandLogo />
        <span className="ps-entry-heading__kicker">{kicker}</span>
      </div>
      <h1>{title}</h1>
      <p>{description}</p>
      {step ? <EntrySteps step={step} /> : null}
    </header>
  );
}
