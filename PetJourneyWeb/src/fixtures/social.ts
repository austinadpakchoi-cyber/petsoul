/**
 * 星球圈 / 通讯 / 收藏 fixture。
 * - 行动者分三类：真实家庭的宠物（is_real_household=true，演示中也是 fixture 账号）、公共 NPC 居民、主人本人；
 * - 计数只来自下面列出的已执行动作，不预填随机点赞；
 * - 通讯是私密的，不出现在星球圈。
 */
import type { ActorRef, CollectionItem, Comment, MessageSummary, MessageThread, PetPublicProfile, Post, PostPage } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { atMin } from "./world";

const ACTORS = {
  me: { actor_kind: "pet", actor_id: "fx-pet-001", display_name: "团子", avatar_url: null, is_real_household: true },
  neighbor: { actor_kind: "pet", actor_id: "fx-pet-002", display_name: "可可", avatar_url: null, is_real_household: true },
  npc: { actor_kind: "npc", actor_id: "fx-npc-pigeon", display_name: "邮差鸽阿咕（星球居民）", avatar_url: null, is_real_household: false },
  owner: { actor_kind: "owner", actor_id: "fx-owner-001", display_name: "团子的主人", avatar_url: null, is_real_household: true },
} satisfies Record<string, ActorRef>;

const posts: Record<string, Post> = {
  "fx-post-1": {
    post_id: "fx-post-1",
    author: ACTORS.me,
    text: "在海边咖啡馆挑了靠窗的位置，云朵奶泡上画的是一条鱼。",
    media: [{ media_id: "fx-img-1", kind: "image", url: null, alt: "咖啡馆窗边（演示，未生成图片）", generated: true }],
    source_event_id: "fx-visit-001:photo",
    visit_id: "fx-visit-001",
    visibility: "public",
    created_at: atMin(-40),
    reaction_count: 2,
    comment_count: 3,
    viewer_reacted: false,
    data_origin: "fixture",
  },
  "fx-post-2": {
    post_id: "fx-post-2",
    author: ACTORS.neighbor,
    text: "今天守菜园，抓到一只来偷番茄的麻雀，放它走了。",
    media: [],
    source_event_id: "fx-farm-guard-7",
    visit_id: null,
    visibility: "public",
    created_at: atMin(-180),
    reaction_count: 1,
    comment_count: 0,
    viewer_reacted: true,
    data_origin: "fixture",
  },
};

const comments: Record<string, Comment[]> = {
  "fx-post-1": [
    { comment_id: "fx-c-1", post_id: "fx-post-1", actor: ACTORS.neighbor, reply_to_comment_id: null, text: "我也想去那家！下次带上我。", created_at: atMin(-35), removed: false },
    { comment_id: "fx-c-2", post_id: "fx-post-1", actor: ACTORS.npc, reply_to_comment_id: null, text: "咕，这封信我记下了，明天送到。", created_at: atMin(-30), removed: false },
    { comment_id: "fx-c-3", post_id: "fx-post-1", actor: ACTORS.owner, reply_to_comment_id: "fx-c-1", text: "你们一起去吧，旅费我来种。", created_at: atMin(-20), removed: false },
  ],
};

const reacted = new Map<string, Post>();

export function fixtureFeed(): PostPage {
  return { items: Object.values(posts).sort((a, b) => b.created_at.localeCompare(a.created_at)), next_cursor: null };
}

export function fixturePetPosts(petId: string): PostPage {
  return { items: Object.values(posts).filter((p) => p.author.actor_id === petId), next_cursor: null };
}

export function fixturePost(postId: string): Post {
  const post = posts[postId];
  if (!post) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "这条动态不存在或已撤下。" });
  return post;
}

export function fixtureComments(postId: string): Comment[] {
  return comments[postId] ?? [];
}

export function fixtureReact(postId: string, key: string): Post {
  const replay = reacted.get(key);
  if (replay) return replay;
  const post = fixturePost(postId);
  const next = post.viewer_reacted ? post : { ...post, viewer_reacted: true, reaction_count: post.reaction_count + 1 };
  posts[postId] = next;
  reacted.set(key, next);
  return next;
}

export function fixturePublicProfile(petId: string): PetPublicProfile | null {
  const actor = Object.values(ACTORS).find((a) => a.actor_id === petId && a.actor_kind === "pet");
  if (!actor) return null;
  return {
    pet_id: petId,
    display_name: actor.display_name,
    species: petId === "fx-pet-002" ? "dog" : "cat",
    avatar_url: null,
    bio: petId === "fx-pet-001" ? "在路上的小猫，喜欢靠窗的位置。" : "守菜园的小狗。",
    origin_label: "自己的宠物",
    visibility: "public",
    follower_count: petId === "fx-pet-001" ? 1 : 2,
    post_count: fixturePetPosts(petId).items.length,
    viewer_follows: petId !== "fx-pet-001",
    is_own: petId === "fx-pet-001",
    data_origin: "fixture",
  };
}

export function fixtureThread(petId: string): MessageThread {
  const items: MessageSummary[] = [
    { message_id: "fx-m-1", client_message_id: null, sender: "pet", text: "登机了，窗外的云像棉花糖。", state: "delivered", created_at: atMin(-58), photo_url: null },
    { message_id: "fx-m-2", client_message_id: "fx-client-1", sender: "owner", text: "路上照顾好自己，到了告诉我。", state: "delivered", created_at: atMin(-50), photo_url: null },
    { message_id: "fx-m-3", client_message_id: null, sender: "pet", text: "在听歌呢，晚点回你～", state: "awaiting_reply", created_at: atMin(-49), photo_url: null },
    { message_id: "fx-m-4", client_message_id: "fx-client-2", sender: "owner", text: "拍张云给我看看？", state: "processing", created_at: atMin(-10), photo_url: null },
  ];
  return { pet_id: petId, items, next_cursor: null, data_origin: "fixture" };
}

export function fixtureCollection(): CollectionItem[] {
  return [
    { item_id: "fx-i-1", kind: "postcard", item_key: null, title: "海边咖啡馆明信片", obtained_at: atMin(-60 * 24), tradable: false, bound_to_pet: true, source_event_id: "fx-visit-001", data_origin: "fixture" },
    { item_id: "fx-i-2", kind: "seed", item_key: "sea_salt_pea", title: "海盐豌豆种子（演示）", obtained_at: atMin(-60 * 30), tradable: true, bound_to_pet: false, source_event_id: "fx-journey-000", data_origin: "fixture" },
    { item_id: "fx-i-3", kind: "badge", item_key: null, title: "第一次坐飞机", obtained_at: atMin(-60), tradable: false, bound_to_pet: true, source_event_id: "fx-leg-flight", data_origin: "fixture" },
  ];
}
