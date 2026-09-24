import type { PublicResident } from "@/shared/contracts";
import { homeParts } from "./residentView";

/**
 * 住在哪：“星球居民驿站·西贡海边（香港）”。括号连同城市放进不断行的一段，320 宽时不会拆成“（香”“港）”两行。
 * 只用括号不用分隔点：驿站名自己就带“·”，同一行里不再出现第二种点（2026-09-24 主窗口验收提出）。
 */
export function ResidentHome({ resident }: { resident: Pick<PublicResident, "residence" | "city"> }) {
  const { residence, city } = homeParts(resident);
  return (
    <>
      {residence}
      {city ? <span className="ps-world-nowrap">（{city}）</span> : null}
    </>
  );
}
