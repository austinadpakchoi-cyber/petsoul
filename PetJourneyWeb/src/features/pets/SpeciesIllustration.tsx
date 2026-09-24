import type { PetSpecies } from "@/shared/contracts";

/**
 * 物种类别小图（UI-ASSET-002 v1，r7k 交付：192×192 透明 WebP，指纹见
 * docs/coordination/ui-assets/deliveries/UI-ASSET-002-v1.md）。只表示可选类别，从不当作某只宠物的肖像。
 */
export function SpeciesIllustration({ species }: { species: PetSpecies }) {
  return <img className="ps-species-art" src={`/ui-assets/UI-ASSET-002/v1/species-${species}.webp`} alt="" aria-hidden="true" width={192} height={192} decoding="async" />;
}
