/**
 * 宠物头像（新页面用的轻样式）：永远是 TA 自己的样子，不用名字首字（用户 2026-09-24）。
 * 取图规则和全站共用的 `PetAvatar` 是同一个 `petPortraitUrl`（shared/ui）：
 * - 有照片（主人上传的，或服务端生成的写实证件照）就用照片；
 * - 演示（fixture）模式没有照片时，用内部测试小灰猫的头像（用户授权的演示对象）；
 * - live 模式没有照片时，显示中性的爪印占位——不借演示猫冒充真实宠物，也不写首字。
 * `petPortraitUrl`、`PawMark` 在这里转出，已有的引用不用改。
 */
import type { PetSpecies } from "@/shared/contracts";
import { PawMark, petPortraitUrl } from "@/shared/ui";
import "./pet-portrait.css";

export { PawMark, petPortraitUrl };

export function PetPortrait({ name, photoUrl, size = 40 }: { name: string; photoUrl?: string | null; size?: number; petId?: string; species?: PetSpecies }) {
  const src = petPortraitUrl(photoUrl);
  return (
    <span className={`ps-pet-portrait${src ? "" : " is-placeholder"}`} style={{ width: size, height: size }} role="img" aria-label={name}>
      {src ? <img src={src} alt="" loading="lazy" draggable={false} /> : <PawMark size={Math.round(size * 0.5)} />}
    </span>
  );
}
