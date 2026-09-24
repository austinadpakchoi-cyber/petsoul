import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { CharacterState, HomeSnapshot } from "@/shared/contracts";
import { Icon } from "@/shared/ui";
import { PetPortrait, petPortraitUrl } from "@/features/pets/PetPortrait";
import { sceneAsset } from "./PetFigure";

/**
 * 第一次入住后的“到家”时刻。只用家园快照里的真实事实：名字、TA 的样子（星球形象或 PetPortrait）、住处、
 * 由确认过的入住叮嘱投影出的欢迎语与细节；没有欢迎语时不替 TA 编一句话。
 * 只随入住成功那一次跳转出现（路由状态），关闭后不再重播。
 */
export function ArrivalMoment({ snapshot, character = null, onClose }: { snapshot: HomeSnapshot; character?: CharacterState | null; onClose: () => void }) {
  const primary = useRef<HTMLButtonElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    primary.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);
  const { pet, welcome, place } = snapshot;
  const details = welcome?.details.slice(0, 3) ?? [];
  const figure = sceneAsset(character);
  // 头像永远是 TA 自己的样子（不写名字首字）：有星球形象用形象，否则交给 PetPortrait（照片 / 演示头像 / 爪印占位）。
  const portrait = petPortraitUrl(pet.photo_url);
  return createPortal(
    <div className="ps-arrival" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="ps-arrival__card" role="dialog" aria-modal="true" aria-labelledby="ps-arrival-title" data-testid="home-arrival">
        <span className={`ps-arrival__portrait${figure ? " is-character" : portrait ? " has-photo" : " is-placeholder"}`} aria-hidden="true">
          {figure ? <img src={figure.url} alt="" /> : <PetPortrait name={pet.name} photoUrl={pet.photo_url} size={86} />}
        </span>
        {/* 滚动放在内层：卡片自己不裁切，探出卡片上沿的头像才完整（以前卡片滚动会把头像切掉一半）。 */}
        <div className="ps-arrival__body">
        <span className="ps-arrival__kicker">{place ? `新家 · ${place.display}` : "新家"}</span>
        <h2 id="ps-arrival-title">{pet.name} 到家了</h2>
        {welcome ? (
          <figure className="ps-arrival__greeting">
            <blockquote>“{welcome.greeting}”</blockquote>
            {details.length ? (
              <ul aria-label="家里会记着">
                {details.map((detail) => <li key={detail.note_id}>{detail.text}</li>)}
              </ul>
            ) : null}
            <figcaption>来自你确认过的入住叮嘱</figcaption>
          </figure>
        ) : (
          <p className="ps-arrival__lead">从现在起，家园、信箱和旅途按真实时间慢慢展开。</p>
        )}
        <ul className="ps-arrival__guide" aria-label="新家怎么住">
          <li><Icon name="sprout" size={18} /><span><strong>菜地</strong>种下的菜按真实时间长，成熟后先收进仓库。</span></li>
          <li><Icon name="mail" size={18} /><span><strong>信箱</strong>TA 的来信和照片会寄到这里。</span></li>
          <li><Icon name="journey" size={18} /><span><strong>旅途</strong>TA 会按自己的节奏出门，你可以给建议。</span></li>
        </ul>
        <button ref={primary} type="button" className="ps-btn ps-btn--primary ps-btn--block ps-arrival__go" onClick={onClose}>
          进家看看
        </button>
        </div>
      </section>
    </div>,
    document.body,
  );
}
