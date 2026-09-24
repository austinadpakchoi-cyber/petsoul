/**
 * 领证合影的纸质纪念卡（没有写实照片时，它本身就是那张纪念）：画出内容，不再是“缺图”的空框。
 * - 画面：TA 的头像（@/shared/ui 的 PetAvatar：有照片用照片，live 没照片是爪印，演示是授权的演示小灰猫）＋ 龟教练·慢慢；
 *   龟教练用 UI-ASSET-009 的头像素材（SCHOOL_ART.coach.portrait，和领证仪式那张同一张图；网址只从驾校的 assets.ts 取，不另写路径），
 *   图片加载失败就退回下面这个代码画的线稿（CoachTurtle）。
 * - 下面：TA 领证时说的话（服务端 note 原文，加引号）、领证日期（收藏的 obtained_at，按看的人所在时区）、爪印章。
 * - 纸色底、深墨字、爪印章都用固定的纸墨色（--paper 系昼夜一样，像一张实物卡片）：
 *   --paper-ink 在 --paper 上约 11:1，--paper-secondary-ink 约 4.6:1（tests/claude-6c2b-ds-touchpoints 实算）。
 * - 照片还在冲洗 / 没生成成功 / 状态待确认时，卡片照样画出来，底下多一行说明；照片画好了由收藏页换成照片，不用这张卡。
 * 领证仪式页的同款卡片由驾校页面分身在 CeremonyPage.tsx 里按同一设计自己画，两边不互相引用。
 */
import { useState } from "react";
import type { CollectionItem, PetSpecies, PhotoStatus } from "@/shared/contracts";
import { PetAvatar } from "@/shared/ui";
import { SCHOOL_ART } from "@/features/driving_school/assets";

export interface MementoPet {
  petId: string | null;
  name: string;
  species: PetSpecies;
  photoUrl: string | null;
}

const DAY = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" });

function dayOf(iso: string): string | null {
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? DAY.format(ms) : null;
}

/** 照片没有换上来时底下那一行；没有开生成照片（状态为空）时不写——纸质卡本身就是这张纪念，不是缺图。 */
const PHOTO_NOTE: Partial<Record<PhotoStatus, string>> = {
  processing: "合影照片还在冲洗，洗好了会换上",
  failed: "合影照片没有生成成功，留下这张纸质纪念卡",
  unknown: "合影照片的状态还没确认",
};

export function PaperMemento({ item, pet }: { item: CollectionItem; pet: MementoPet }) {
  const note = item.note?.trim();
  const day = dayOf(item.obtained_at);
  const status = item.image_status ? PHOTO_NOTE[item.image_status] ?? null : null;
  return (
    <figure className="ps-memento" data-testid="license-memento" aria-label={`${pet.name}和龟教练·慢慢的领证纪念卡`}>
      <div className="ps-memento__scene">
        <span className="ps-memento__who" data-testid="memento-pet">
          <PetAvatar petId={pet.petId ?? "-"} name={pet.name} species={pet.species} photoUrl={pet.photoUrl} size={64} />
          <span className="ps-memento__name">{pet.name}</span>
        </span>
        <span className="ps-memento__who" data-testid="memento-coach">
          <span className="ps-memento__coach">
            <CoachPortrait />
          </span>
          <span className="ps-memento__name">龟教练·慢慢</span>
        </span>
      </div>
      {note ? <blockquote className="ps-memento__quote">“{note}”</blockquote> : null}
      <figcaption className="ps-memento__foot">
        {/* 日期与“在爪爪驾校领证”各自不拆行，窄屏时整段换到下一行（不在词中间断开） */}
        <span className="ps-memento__day">
          {day ? <span>{day}</span> : null}
          <span>{day ? " · 在爪爪驾校领证" : "在爪爪驾校领证"}</span>
        </span>
        <PawStamp />
      </figcaption>
      {status ? (
        <p className="ps-memento__status" data-testid="memento-status">
          {status}
        </p>
      ) : null}
    </figure>
  );
}

/** 龟教练的头像素材；加载失败（网络、文件缺失）就换成线稿。名字写在下面那行字里，图本身是装饰（alt 为空）。 */
function CoachPortrait() {
  const [failed, setFailed] = useState(false);
  if (failed) return <CoachTurtle />;
  return <img className="ps-memento__coach-art" src={SCHOOL_ART.coach.portrait} alt="" width={60} height={60} draggable={false} onError={() => setFailed(true)} data-testid="memento-coach-art" />;
}

/** 龟教练·慢慢的线稿（素材加载失败时的退路）：侧面的小乌龟，龟壳上一块六边形纹，描边随文字色。 */
function CoachTurtle() {
  return (
    <svg className="ps-memento__turtle" viewBox="0 0 48 36" width={46} height={34} fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path className="ps-memento__shell" d="M9 25C9 15 16.5 9 25 9s16 6 16 16z" />
      <path d="M20 15.5l5-2.5 5 2.5v5l-5 2.5-5-2.5zM25 9v4M20 15.5l-6-2M30 15.5l6-2M20 20.5l-7.5 4.5M30 20.5l7.5 4.5" />
      <path d="M6.5 25h37M9 25l-4.5 2M13 25.5v4.5h4v-4.5M33 25.5v4.5h4v-4.5" />
      <circle cx="44" cy="20" r="3.6" />
      <path d="M41 23.2c1.2 1 2.4 1.6 3.6 1.6" />
      <circle cx="45.2" cy="19.2" r=".5" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** 爪印章：双圈加一枚爪印，印泥色（纸上的 --paper-accent），略微歪一点，像盖上去的。只是装饰。到站明信片的邮票位也用它。 */
export function PawStamp({ testId = "memento-stamp" }: { testId?: string } = {}) {
  return (
    <svg className="ps-memento__stamp" data-testid={testId} viewBox="0 0 48 48" width={44} height={44} aria-hidden="true" focusable="false">
      <circle cx="24" cy="24" r="21.5" fill="none" stroke="currentColor" strokeWidth={2} />
      <circle cx="24" cy="24" r="17.5" fill="none" stroke="currentColor" strokeWidth={1} strokeDasharray="2.5 2" />
      <g fill="currentColor" transform="translate(12 11)">
        <circle cx="5.3" cy="9" r="2.1" />
        <circle cx="9.7" cy="5" r="2.2" />
        <circle cx="14.3" cy="5" r="2.2" />
        <circle cx="18.7" cy="9" r="2.1" />
        <path d="M12 10.8c-2.9 0-5.6 3-5.6 5.4 0 1.7 1.3 2.8 2.9 2.8 1.1 0 1.8-.5 2.7-.5s1.6.5 2.7.5c1.6 0 2.9-1.1 2.9-2.8 0-2.4-2.7-5.4-5.6-5.4z" />
      </g>
    </svg>
  );
}
