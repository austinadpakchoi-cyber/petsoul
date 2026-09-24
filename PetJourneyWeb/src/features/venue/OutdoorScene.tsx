import type { PetPrivateSummary, Visit } from "@/shared/contracts";
import { VisitPet } from "./VisitPet";

/**
 * 户外（家附近的小路、公园；见 visitKind.ts 的 outdoor）：不画店内、不写“到店”。
 * 只用设计令牌画一小片天、远坡、草地和一条小路（跟着深浅色走），宠物站在路上；
 * “找块地方躺一会儿”做完后挪到草地上歇着，“和路过的居民打招呼”做完后冒一句“你好呀”——都只看这次到访的动作状态。
 */
export function OutdoorScene({ visit, pet, resting }: { visit: Visit; pet: PetPrivateSummary | null; resting: boolean }) {
  const greeted = visit.activities.some((activity) => activity.kind === "greet_resident" && activity.state === "done");
  const sceneLabel = pet ? `${pet.name} 在${visit.place.name}${resting ? "，找了块地方躺下歇着" : ""}` : visit.place.name;
  return (
    <section className={`ps-outdoor${resting ? " is-resting" : ""}`} aria-label={sceneLabel}>
      <svg className="ps-outdoor__drawing" viewBox="0 0 360 150" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <rect className="ps-outdoor__sky" width="360" height="150" />
        <circle className="ps-outdoor__sun" cx="302" cy="34" r="15" />
        <path className="ps-outdoor__cloud" d="M40 40h46a10 10 0 0 0-14-11a13 13 0 0 0-24 3a8 8 0 0 0-8 8Z" />
        <path className="ps-outdoor__hill" d="M0 90C44 66 92 62 140 78C186 94 232 62 282 66C318 69 342 78 360 86V150H0Z" />
        <path className="ps-outdoor__grass" d="M0 108C62 97 120 100 180 106C244 112 300 101 360 104V150H0Z" />
        <path className="ps-outdoor__path" d="M126 150C146 133 178 125 214 119C244 114 272 111 298 107L316 109C288 115 262 121 238 129C210 138 190 145 182 150Z" />
        <g className="ps-outdoor__tree">
          <rect x="50" y="80" width="6" height="26" rx="3" />
          <circle cx="53" cy="72" r="16" />
          <circle cx="330" cy="92" r="11" />
          <rect x="327" y="98" width="5" height="14" rx="2.5" />
        </g>
        <g className="ps-outdoor__flower">
          <circle cx="96" cy="124" r="3" />
          <circle cx="252" cy="136" r="3" />
          <circle cx="286" cy="124" r="2.5" />
        </g>
      </svg>

      {pet ? (
        <div className="ps-outdoor__pet" aria-label={`${pet.name} ${resting ? "躺在草地上歇着" : "在这儿走走"}`}>
          <span className="ps-outdoor__pet-shadow" aria-hidden="true" />
          <VisitPet pet={pet} portraitClass="ps-outdoor__pet-portrait" />
          <span className="ps-outdoor__pet-name">{pet.name}</span>
        </div>
      ) : null}
      {greeted ? <span className="ps-outdoor__hello" aria-label="已完成打招呼">你好呀</span> : null}
    </section>
  );
}
