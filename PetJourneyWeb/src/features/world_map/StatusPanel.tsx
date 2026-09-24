/**
 * 首屏唯一的主状态面板：TA 此刻在哪、在做什么、还要多久；事件提醒也合进这里，不再叠第二张卡。
 * 主按钮随状态变：在家“进小窝看看”；在店里“进店看看”（去 /visits/:id）——W1 phase = there 且有 visit_id，
 * 并且这次到访的场景模板确实是店（./visitPlace：按数据判断，小路、公园、打工的地方都不是店，不按名字猜）；
 * 其余“看看 TA”（只把镜头对准 TA，不弹面板）。“捎句话”一直在。
 * 行程快照对齐时多一行“这趟旅途”按钮（打开 ?sheet=trip），不占主按钮的位置。
 * 提醒（来源与先后见 ./panelNotes）收起时只显示最重要的一条，后面跟“还有 N 条”；点开看全部，再点收起。
 * 这里的去处（带宠物的提醒、进小窝看看、进店看看、捎句话）都属于面板上这只：点下去先交给 onEnter 把当前宠物换成它（见 MapHomePage），再跳；
 * 在地图上打开的提醒（onMap，例如一起听）不换当前宠物。
 */
import { useId, useState } from "react";
import { Link } from "react-router";
import { Icon } from "@/shared/ui";
import { PetMoodAvatar } from "@/features/pets/PetMoodAvatar";
import { panelCopy } from "./copy";
import { SHEET_FROM_MAP } from "./mapSheet";
import { ModeBadge, modeBadgeOf } from "./markers";
import { legProgress, type WorldPet } from "./model";
import type { PanelNote } from "./panelNotes";

/** 读屏先读到一共几条（分组名），收起时列表里只有第一条，“还有 N 条”按钮带展开状态。 */
function PanelNotes({ notes, onEnter }: { notes: PanelNote[]; onEnter?: (petId: string) => void }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const more = notes.length - 1;
  const expanded = open && more > 0;
  const shown = expanded ? notes : notes.slice(0, 1);
  return (
    <div className={`ps-wmap-panel__notes${more > 0 ? " has-more" : ""}${expanded ? " is-expanded" : ""}`} role="group" aria-label={`提醒，共 ${notes.length} 条`}>
      <ul id={listId} className="ps-wmap-panel__note-list">
        {shown.map(({ id, text, to, petId, onMap }) => (
          <li key={id}>
            {to ? (
              <Link to={to} state={onMap ? SHEET_FROM_MAP : undefined} onClick={petId && !onMap ? () => onEnter?.(petId) : undefined}>
                {text}
              </Link>
            ) : (
              text
            )}
          </li>
        ))}
      </ul>
      {more > 0 ? (
        <button type="button" className="ps-wmap-panel__more" aria-expanded={expanded} aria-controls={listId} onClick={() => setOpen(!expanded)}>
          {expanded ? "收起" : `还有 ${more} 条`}
        </button>
      ) : null}
    </div>
  );
}

export function StatusPanel({
  pet,
  nowMs,
  notes,
  onLocate,
  onEnter,
  trip,
  storeVisitId = null,
}: {
  pet: WorldPet;
  nowMs: number;
  notes: PanelNote[];
  onLocate: () => void;
  /** 进按宠物区分的页面之前调用（把当前宠物换成面板上这只）；不给就只跳转。 */
  onEnter?: (petId: string) => void;
  /** 行程快照对齐时才给：“这趟旅途”按钮的说明和打开方式。 */
  trip?: { subtitle: string | null; onOpen: () => void } | null;
  /** 在店里时这次到访的 id（./visitPlace.useStoreVisitId：W1 在那里、有 visit_id、场景模板是店）；其余情况 null。 */
  storeVisitId?: string | null;
}) {
  const moving = pet.activity.phase === "going" || pet.activity.phase === "returning";
  const progress = moving && pet.leg ? legProgress(pet.leg, nowMs) : null;
  const copy = panelCopy(pet, nowMs, progress);
  const mode = modeBadgeOf(pet);
  const atHome = pet.activity.phase === "home";
  // 在店里：W1 phase = there 且这次到访就是面板上这只此刻的这一次（到店前的计划 visit_id 不算），并且上层确认过是店。
  const visitId = pet.activity.phase === "there" && storeVisitId && storeVisitId === pet.activity.visitId ? storeVisitId : null;
  return (
    <section className={`ps-wmap-panel is-${pet.activity.phase}`} aria-label={`${pet.name}此刻`}>
      <div className="ps-wmap-panel__row">
        {/* 在路上坐车船飞机时，头像右下角和地图标记一样换成交通方式角标（./markers）。 */}
        <span className="ps-wmap-panel__avatar">
          <PetMoodAvatar name={pet.name} photoUrl={pet.photoUrl} mood={pet.activity.pose} size={44} compact badge={!mode} />
          {mode ? <ModeBadge mode={mode} /> : null}
        </span>
        <div className="ps-wmap-panel__text" aria-live="polite">
          <h2 key={copy.headline}>{copy.headline}</h2>
          {copy.detail ? <p>{copy.detail}</p> : null}
        </div>
      </div>
      {copy.progress != null ? (
        <div className="ps-wmap-panel__progress" role="progressbar" aria-label="这段路走了多少" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(copy.progress * 100)}>
          <i style={{ width: `${Math.round(copy.progress * 100)}%` }} />
        </div>
      ) : null}
      {trip ? (
        <button type="button" className="ps-wmap-panel__trip" onClick={trip.onOpen}>
          <Icon name="journey" size={16} />
          <span className="ps-wmap-panel__trip-text">
            <strong>这趟旅途</strong>
            {trip.subtitle ? <span>{trip.subtitle}</span> : null}
          </span>
          <Icon name="chevron" size={16} />
        </button>
      ) : null}
      {notes.length ? <PanelNotes notes={notes} onEnter={onEnter} /> : null}
      <div className="ps-wmap-panel__actions">
        {atHome ? (
          <Link className="ps-btn ps-btn--leaf" to="/home?from=map" onClick={() => onEnter?.(pet.petId)}>
            <Icon name="home" size={16} /> 进小窝看看
          </Link>
        ) : visitId ? (
          <Link className="ps-btn ps-btn--leaf" to={`/visits/${encodeURIComponent(visitId)}`} onClick={() => onEnter?.(pet.petId)}>
            <Icon name="cup" size={16} /> 进店看看
          </Link>
        ) : (
          <button type="button" className="ps-btn ps-btn--leaf" onClick={onLocate}>
            <Icon name="locate" size={16} /> 看看 TA
          </button>
        )}
        <Link className="ps-btn ps-btn--ghost" to="/communicator" onClick={() => onEnter?.(pet.petId)}>
          <Icon name="chat" size={16} /> 捎句话
        </Link>
      </div>
    </section>
  );
}
