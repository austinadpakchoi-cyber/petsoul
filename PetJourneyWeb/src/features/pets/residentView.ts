/**
 * 访客星球（/world）与居民公开主页共用的展示规则。只把后端给的公开事实换成人话，不猜、不补：
 * - 此刻在做什么只用服务端的 `doing`；在哪只用 `place_name`、`residence`、`city`；
 * - 公开接口没有任何坐标，这里也不产生坐标（不按城市名查、不按驿站名配）；
 * - 头像：有公开照片用照片；没有时用同物种的插画。演示小灰猫只在演示模式、只给猫用，
 *   绝不拿别的物种的照片顶替，也不冒充 live 里的真实居民。
 */
import type { PetOrigin, PetPresence, PetSpecies, Post, PublicResident } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { petPortraitUrl } from "@/shared/ui";

const SPECIES_NAMES: Record<PetSpecies, string> = { cat: "猫", dog: "狗", rabbit: "兔子", hamster: "仓鼠", bird: "小鸟", parrot: "鹦鹉", other: "小动物" };

export function speciesName(species: PetSpecies): string {
  return SPECIES_NAMES[species] ?? "小动物";
}

export type PresenceGroup = "home" | "out" | "road" | "unknown";

/** 只按服务端给的 presence 分组，不从 doing 文字里猜。 */
export function presenceGroup(presence: PetPresence): PresenceGroup {
  switch (presence) {
    case "at_home":
      return "home";
    case "visiting":
    case "at_destination":
      return "out";
    case "in_transit":
    case "returning":
      return "road";
    default:
      return "unknown";
  }
}

const GROUP_LABEL: Record<PresenceGroup, string> = { home: "在驿站", out: "在外面", road: "在路上", unknown: "暂时不知道在哪" };

/** “3 位在驿站 · 4 位在外面 · 1 位在路上”：只数后端给的状态，没有的分组不写。 */
export function presenceSummary(residents: PublicResident[]): Array<{ group: PresenceGroup; text: string }> {
  const counts = new Map<PresenceGroup, number>();
  for (const resident of residents) {
    const group = presenceGroup(resident.presence);
    counts.set(group, (counts.get(group) ?? 0) + 1);
  }
  return (["home", "out", "road", "unknown"] as const).filter((group) => counts.get(group)).map((group) => ({ group, text: `${counts.get(group)} 位${GROUP_LABEL[group]}` }));
}

/**
 * 此刻那一行：服务端的 doing；到访的地点名已经写在 doing 里就不再重复，没写到才用括号补上。
 * 不用分隔点拼接：服务端的名字里自己就带“·”（如“星球居民驿站·中环”），再拼一个会在同一行里出现两种样子的点。
 */
export function nowLine(resident: Pick<PublicResident, "doing" | "place_name">): string {
  const doing = resident.doing.trim();
  const place = resident.place_name?.trim();
  return place && !doing.includes(place) ? `${doing}（${place}）` : doing;
}

/**
 * 住在哪的两段：驿站名，和要补在括号里的城市（城市为空或已写在驿站名里就是 null）。
 * 显示成“星球居民驿站·西贡海边（香港）”，由 ResidentHome 排版（“（城市）”整体不断行）。
 */
export function homeParts(resident: Pick<PublicResident, "residence" | "city">): { residence: string; city: string | null } {
  const residence = resident.residence.trim();
  const city = resident.city.trim();
  return { residence, city: city && !residence.includes(city) ? city : null };
}

/** 相对时间，以服务器时间为准（访客手机的时钟可能不准）。 */
export function agoText(iso: string, nowMs: number): string {
  const then = Date.parse(iso);
  if (!Number.isFinite(then) || !Number.isFinite(nowMs)) return "";
  const minutes = Math.floor((nowMs - then) / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  const date = new Date(then);
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}

/**
 * 星球上最近的小事：去掉已经在居民卡上出现过的，免得同一句话出现两次。
 * 同一位作者、一字不差的同一句话也算出现过（后台会在不同时间记下同样的一句），列表里也只留最新的一条。
 */
export function extraPosts(posts: Post[], residents: PublicResident[]): Post[] {
  const line = (post: Post) => `${post.author.actor_id}\n${post.text.trim()}`;
  const shownIds = new Set<string>();
  const seen = new Set<string>();
  for (const resident of residents) {
    const post = resident.recent_posts[0];
    if (post) {
      shownIds.add(post.post_id);
      seen.add(line(post));
    }
  }
  const out: Post[] = [];
  for (const post of posts) {
    if (shownIds.has(post.post_id) || seen.has(line(post))) continue;
    seen.add(line(post));
    out.push(post);
  }
  return out;
}

/**
 * 读屏怎么说这张照片：原创居民（origin = adopted_original）的形象是生成的原创设计，不是照片
 * （契约 PublicResident.avatar_url 的说明），读作“{名字}的形象（AI 生成）”；其余读作“{名字}的照片”；
 * 演示小灰猫读作“（演示照片）”。只改读屏，画面上不加角标（2026-09-24 主窗口定）。
 */
export function portraitPhotoLabel(name: string, origin: PetOrigin | null | undefined, demo: boolean): string {
  if (demo) return `${name}（演示照片）`;
  return origin === "adopted_original" ? `${name}的形象（AI 生成）` : `${name}的照片`;
}

export type PortraitSource = { kind: "photo"; src: string; demo: boolean } | { kind: "species"; species: PetSpecies };

/**
 * 居民头像来源：公开照片 → 照片；演示模式里的猫 → 授权的演示小灰猫；其余 → 同物种插画。
 * 演示小灰猫的地址仍由全站唯一规则 petPortraitUrl 给出（live 模式它返回 null）。
 */
export function residentPortrait(species: PetSpecies, photoUrl: string | null | undefined): PortraitSource {
  if (photoUrl) return { kind: "photo", src: photoUrl, demo: false };
  if (env.dataMode === "fixture" && species === "cat") {
    const demo = petPortraitUrl(null);
    if (demo) return { kind: "photo", src: demo, demo: true };
  }
  return { kind: "species", species };
}
