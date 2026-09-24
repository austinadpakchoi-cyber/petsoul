/**
 * 朋友圈的前端兜底（2026-09-24 巡检 P1）：老数据里同一位作者会一连发好几条一字不差的话（例如“在家附近的星球小路待了一会儿……”）。
 * 后端已经从源头挡住新的重复（同一作者 3 天内一字不差且没照片就不发），这里只收拾还留着的老数据：
 * 同一位作者、文字一字不差（去掉首尾空白后比）、都没带照片的几条，只留最新的一条；带照片的一律照留（照片各不相同）。
 * 别的作者说了同一句不算重复。留下来的几条保持原来的先后。
 * （写法参考了星球页 /world 的做法，但不引用它的文件——那边的分身正在改。）
 */
import type { Post } from "@/shared/contracts";

const keyOf = (post: Post) => `${post.author.actor_kind}\u0000${post.author.actor_id}\u0000${post.text.trim()}`;

export function collapseRepeats(posts: readonly Post[]): Post[] {
  const newest = new Map<string, Post>();
  for (const post of posts) {
    if (post.media.length > 0) continue;
    const key = keyOf(post);
    const kept = newest.get(key);
    if (!kept || Date.parse(post.created_at) > Date.parse(kept.created_at)) newest.set(key, post);
  }
  return posts.filter((post) => post.media.length > 0 || newest.get(keyOf(post)) === post);
}
