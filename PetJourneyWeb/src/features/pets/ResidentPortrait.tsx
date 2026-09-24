import { useState } from "react";
import type { PetOrigin, PetSpecies } from "@/shared/contracts";
import { type PortraitSource, portraitPhotoLabel, residentPortrait, speciesName } from "./residentView";
import { SpeciesIllustration } from "./SpeciesIllustration";
// 样式在 planet.css（.ps-resident-portrait）；领养页等别处也在用这个组件，这里自己引入，不靠星球页先加载。
import "./planet.css";

/**
 * 居民头像：有公开照片（`PublicResident.avatar_url` / 主页的 `profile.avatar_url`）就用照片；
 * 没有、或者照片打不开，就用同物种的插画，并在角上标“插画”，读屏也说清楚“这是物种插画，不是 TA 本人的照片”。
 * 不说“TA 没有照片”：照片打不开时 TA 其实是有照片的。
 * origin：知道来历时传上（原创居民读作“形象（AI 生成）”）；不知道就按照片读。
 */
export function ResidentPortrait({ name, species, photoUrl, origin, size = 64 }: { name: string; species: PetSpecies; photoUrl?: string | null; origin?: PetOrigin | null; size?: number }) {
  const [broken, setBroken] = useState(false);
  const source: PortraitSource = broken ? { kind: "species", species } : residentPortrait(species, photoUrl);
  if (source.kind === "photo") {
    return (
      <span className="ps-resident-portrait is-photo" style={{ width: size, height: size }} role="img" aria-label={portraitPhotoLabel(name, origin, source.demo)}>
        <img src={source.src} alt="" loading="lazy" draggable={false} onError={() => setBroken(true)} />
      </span>
    );
  }
  return (
    <span className="ps-resident-portrait is-species" style={{ width: size, height: size }} role="img" aria-label={`${speciesName(species)}的插画，不是${name}本人的照片`} data-species={species}>
      <SpeciesIllustration species={species} />
      <small aria-hidden="true">插画</small>
    </span>
  );
}
