import type { PetPrivateSummary, Visit, VisitActivityKind } from "@/shared/contracts";
import { Icon, PetAvatar } from "@/shared/ui";
import cafeStorybookArt from "./assets/pet-cafe-storybook.webp";

/** 原创动物世界咖啡馆；角色、饮品和相片只从当前到访动作状态得出。 */
export function CafeScene({ visit, pet, seated }: { visit: Visit; pet: PetPrivateSummary | null; seated: boolean }) {
  const isDone = (kind: VisitActivityKind) => visit.activities.some((activity) => activity.kind === kind && activity.state === "done");
  const drinkReady = isDone("order_drink");
  const photoTaken = isDone("take_photo");
  const greeted = isDone("greet_resident");
  const sceneLabel = pet
    ? `${pet.name} 在动物世界咖啡馆${photoTaken ? "留下纪念卡" : drinkReady ? "正在享用饮品" : seated ? "已经入座" : "刚刚到店"}`
    : "动物世界咖啡馆原创场景";

  return (
    <section className={`ps-cafe${seated ? " is-seated" : ""}${drinkReady ? " has-drink" : ""}${photoTaken ? " has-photo" : ""}`} aria-label={sceneLabel}>
      <img className="ps-cafe__art" src={cafeStorybookArt} alt="" aria-hidden="true" />
      <svg viewBox="0 0 360 224" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <defs>
          <linearGradient id="ps-cafe-wall" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#f9e5bd" />
            <stop offset="1" stopColor="#f3c986" />
          </linearGradient>
          <linearGradient id="ps-cafe-window" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#cce9ee" />
            <stop offset="1" stopColor="#9dced6" />
          </linearGradient>
        </defs>
        <rect width="360" height="224" fill="url(#ps-cafe-wall)" />
        <path d="M0 154H360V224H0Z" fill="#b67b51" />
        <path d="M0 154H360V161H0Z" fill="#e9c490" opacity=".75" />
        <rect x="23" y="23" width="121" height="99" rx="14" fill="#fff6e7" stroke="#b96f48" strokeWidth="5" />
        <rect x="33" y="33" width="101" height="79" rx="8" fill="url(#ps-cafe-window)" />
        <path d="M33 88C56 67 73 101 95 80C110 66 120 78 134 69V112H33Z" fill="#78af8c" opacity=".82" />
        <circle cx="62" cy="57" r="13" fill="#f4b542" opacity=".9" />
        <path d="M48 111L84 73L119 111" fill="none" stroke="#e6f2ee" strokeWidth="4" opacity=".82" />
        <path d="M188 38H332" stroke="#87583e" strokeWidth="8" strokeLinecap="round" />
        <g fill="#c86d50">
          <rect x="200" y="17" width="29" height="21" rx="4" />
          <rect x="244" y="13" width="35" height="25" rx="4" />
          <rect x="294" y="20" width="24" height="18" rx="4" />
        </g>
        <g fill="#f8dc9b" opacity=".85">
          <circle cx="213" cy="28" r="6" />
          <path d="M253 30h17v-10h-17z" />
          <circle cx="306" cy="29" r="6" />
        </g>
        <path d="M259 115c0-14 10-25 23-25s23 11 23 25v8h-46z" fill="#6ba77d" />
        <path d="M270 95l-11-10l4 17M294 95l11-10l-4 17" fill="#6ba77d" />
        <circle cx="278" cy="108" r="2" fill="#314c43" />
        <circle cx="289" cy="108" r="2" fill="#314c43" />
        <path d="M280 116q4 4 8 0" fill="none" stroke="#314c43" strokeWidth="2" strokeLinecap="round" />
        <ellipse cx="161" cy="184" rx="78" ry="17" fill="#7d4c36" opacity=".2" />
        <rect x="91" y="154" width="139" height="16" rx="8" fill="#f4e2b5" />
        <rect x="113" y="170" width="12" height="38" rx="5" fill="#704836" />
        <rect x="195" y="170" width="12" height="38" rx="5" fill="#704836" />
        <path d="M16 197c9-33 31-40 45-25c12 13 3 29-5 36H16z" fill="#6ca66d" />
        <path d="M46 180c-9-17-3-37 16-43c-4 20-6 33-16 43z" fill="#8ac78a" />
      </svg>

      {pet ? (
        <div className="ps-cafe__pet" aria-label={`${pet.name} ${seated ? "已入座" : "在入口处"}`}>
          <span className="ps-cafe__pet-shadow" aria-hidden="true" />
          {pet.photo_url ? <img className="ps-cafe__pet-portrait" src={pet.photo_url} alt="" /> : <PetAvatar petId={pet.pet_id} name={pet.name} species={pet.species} photoUrl={null} size={58} />}
          <span className="ps-cafe__pet-name">{pet.name}</span>
        </div>
      ) : null}
      {drinkReady ? <span className="ps-cafe__drink" aria-label="饮品已送达"><i aria-hidden="true" /><b>今日饮品</b></span> : null}
      {greeted ? <span className="ps-cafe__hello" aria-label="已完成打招呼">你好呀</span> : null}
      {photoTaken && pet ? <span className="ps-cafe__photo" aria-label={`${pet.name} 的留念活动已记录；照片状态以通讯和收藏为准`}><Icon name="camera" size={17} /><b>留念卡</b></span> : null}
      {visit.interior_is_original ? <span className="ps-cafe__tag">动物世界原创内饰</span> : null}
    </section>
  );
}
