import { produceVisual } from "./cropVisual";

/**
 * 篮子、种子袋来自用户提供的 V4 原型包（只取无宠物的物件，按连通区域抠出；来源 docs/coordination/ui-assets/imports/USER-V4-v1.md）；
 * 摘菜爪来自 UI-ASSET-003 v1（r7k）。
 */
export const FARM_ART = {
  basket: "/ui-assets/USER-V4/v1/farm-basket.webp",
  seedBag: "/ui-assets/USER-V4/v1/farm-seed-bag.webp",
  pickPaw: "/ui-assets/UI-ASSET-003/v1/pick-paw.webp",
} as const;

/**
 * 收成落进篮子：作物从上方落下、篮子一沉、数量浮起。只在服务端确认成功后渲染。
 * 篮子是一整张不透明的图，所以作物画在篮子前面，再用下边缘对齐“前篮沿”的裁切框（__mouth）截掉下半截，
 * 看起来就是装进了篮子里。`delayed`：场景里先有一颗菜从地里飞过来，落篮等它到了再开始。
 */
export function BasketCatch({ cropKey, units = null, delayed = false }: { cropKey: string | null; units?: number | null; delayed?: boolean }) {
  return (
    <span className={`ps-basket-catch${delayed ? " is-delayed" : ""}`} aria-hidden="true" data-testid="basket-catch">
      <img className="ps-basket-catch__basket" src={FARM_ART.basket} alt="" />
      <span className="ps-basket-catch__mouth">
        <img className="ps-basket-catch__drop" src={produceVisual(cropKey)} alt="" />
      </span>
      {units ? <b className="ps-basket-catch__count">+{units}</b> : null}
    </span>
  );
}

/** 种子袋一歪、几粒种子落进土里。只在服务端确认种下后渲染。 */
export function SeedPour() {
  return (
    <span className="ps-seed-pour" aria-hidden="true" data-testid="seed-pour">
      <img className="ps-seed-pour__bag" src={FARM_ART.seedBag} alt="" />
      <i /><i /><i /><i />
    </span>
  );
}
