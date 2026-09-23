/**
 * 幂等键：一次用户动作生成一个键，失败重试复用同一个键（不要每次重试都新建）。
 * 用法：const key = useRef(newIdempotencyKey("farm")); ... 成功后再换新键。
 */
export function newIdempotencyKey(scope: string): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "")
      : Math.random().toString(16).slice(2) + Date.now().toString(16);
  return `${scope}:${random}`.slice(0, 128);
}
