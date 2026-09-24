import type { PetSpecies } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import demoCatPortrait from "./assets/demo-cat-portrait-v1.webp";

/**
 * 全站头像取图的唯一规则（用户 2026-09-24：头像永远是 TA 自己的样子，不用名字首字）：
 * 有照片就用照片；演示（fixture）模式没有照片时用内部测试小灰猫（用户授权的演示对象，见 assets/demo-cat-portrait-provenance.md）；
 * live 没有照片时返回 null，显示中性爪印——不借演示猫冒充真实宠物。
 */
export function petPortraitUrl(photoUrl: string | null | undefined): string | null {
  if (photoUrl) return photoUrl;
  return env.dataMode === "fixture" ? demoCatPortrait : null;
}

const PAW = "M8.5 13.5c-1.9 0-3.5 1.9-3.5 3.6 0 1.4 1.2 1.9 2.4 1.9 1.1 0 1.9-.5 3.1-.5s2 .5 3.1.5c1.2 0 2.4-.5 2.4-1.9 0-1.7-1.6-3.6-3.5-3.6zM5.5 11.5a1.6 2 0 1 0 0-.01zM9.3 8.6a1.7 2.1 0 1 0 0-.01zM14.7 8.6a1.7 2.1 0 1 0 0-.01zM18.5 11.5a1.6 2 0 1 0 0-.01z";

/** 没有可用图片时的中性爪印：任何地方的头像占位都用它，不写名字首字。 */
export function PawMark({ size = 20 }: { size?: number }) {
  return (
    <svg className="ps-paw-mark" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PAW} />
    </svg>
  );
}

/**
 * 当前宠物头像：有照片只用实际照片；没有照片时按 petPortraitUrl 的规则（演示小灰猫 / 爪印），绝不写名字首字，
 * 也不拿通用品种图当成 TA。petId、species 保留在统一组件签名中，占位不按物种猜形象。
 */
export function PetAvatar({ name, photoUrl, size = 40 }: { petId: string; name: string; species: PetSpecies; photoUrl?: string | null; size?: number }) {
  const src = petPortraitUrl(photoUrl);
  return (
    <span className={`ps-avatar${src ? "" : " is-placeholder"}`} style={{ width: size, height: size }} role="img" aria-label={photoUrl ? name : `${name}，暂无照片`}>
      {src ? <img src={src} alt="" loading="lazy" draggable={false} /> : <PawMark size={Math.round(size * 0.5)} />}
    </span>
  );
}
