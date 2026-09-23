import sprouts from "@/features/home/assets/living/crop-sprouts.webp";
import tomatoes from "@/features/home/assets/living/crop-tomato.webp";
import peas from "@/features/home/assets/living/crop-pea-v1.webp";
import radishes from "@/features/home/assets/living/crop-radish-v1.webp";

/** Visuals describe crop species only; growth and yield always come from the server. */
export function cropVisual(cropKey: string | null, stage: "growing" | "ripe") {
  if (stage === "growing") return sprouts;
  if (cropKey === "star_tomato") return tomatoes;
  if (cropKey === "sun_pea" || cropKey === "sea_salt_pea") return peas;
  if (cropKey === "moon_radish" || cropKey === "sakura_radish") return radishes;
  return sprouts;
}
