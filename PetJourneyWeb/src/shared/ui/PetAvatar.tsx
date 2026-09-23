import type { PetSpecies } from "@/shared/contracts";

const PALETTE = ["#efe4d4", "#e7e9df", "#e8e5ed", "#e3ebe9"];

function hash(value: string): number {
  let h = 0;
  for (let i = 0; i < value.length; i += 1) h = (h * 31 + value.charCodeAt(i)) >>> 0;
  return h;
}

/**
 * 当前宠物头像：有照片只用实际照片；缺照片用姓名首字占位，绝不把通用品种图当成 TA。
 * species 保留在统一组件签名中，供调用方保持生成契约；占位不猜测形象。
 */
export function PetAvatar({ petId, name, species, photoUrl, size = 40 }: { petId: string; name: string; species: PetSpecies; photoUrl?: string | null; size?: number }) {
  const color = PALETTE[hash(petId) % PALETTE.length];
  void species;
  return (
    <span className="ps-avatar" style={{ width: size, height: size, background: color, fontSize: Math.max(12, Math.round(size * 0.42)) }} role="img" aria-label={photoUrl ? name : `${name}，暂无照片`}>
      {photoUrl ? (
        <img src={photoUrl} alt="" loading="lazy" />
      ) : (
        <span className="ps-avatar__initial" aria-hidden="true">{name.trim().slice(0, 1) || "·"}</span>
      )}
    </span>
  );
}
