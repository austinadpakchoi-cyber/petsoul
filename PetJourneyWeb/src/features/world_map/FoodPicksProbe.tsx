/**
 * 寻味推荐现在能不能用：交给 food_discovery 自己的 useFoodPicksAvailable 判断（/meta 的 food.recommendations 为 available 才算；
 * 和 queryKeys.meta 共用缓存），结果报给地图页，由它决定“这趟旅途”里那条寻味提醒出不出（./journeyNotes）。
 * 只在对齐后的快照带到达上下文时才挂上这个不画东西的小组件——别的时候地图用不着问（也就不去碰平台服务）。
 * 卸载时报一次“不能用”，下次挂上再重新问。
 */
import { useEffect } from "react";
import { useFoodPicksAvailable } from "@/features/food_discovery/availability";

export function FoodPicksProbe({ onChange }: { onChange: (available: boolean) => void }) {
  const available = useFoodPicksAvailable();
  useEffect(() => {
    onChange(available);
  }, [available, onChange]);
  useEffect(() => () => onChange(false), [onChange]);
  return null;
}
