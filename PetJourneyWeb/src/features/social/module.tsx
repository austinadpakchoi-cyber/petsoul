/**
 * 星球圈模块：动态流、动态详情与评论线程（明确以宠物或主人身份）、宠物公开主页、关注、撤下、屏蔽、举报。
 * 动态只来自真实世界事件（到访）；fixture 模式的互动只在本页内存里演示。
 */
import type { Comment, CommentPage, FriendSummary, Post, PostPage } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { defineModule } from "@/shared/modules/types";
import { fixtureComments, fixtureFeed, fixturePetPosts, fixturePost, fixtureReact } from "@/fixtures/social";
import { delay } from "@/fixtures/world";
import { parseMyReports } from "@/features/me/myReports";
import { CirclePage, PetProfilePage, PostThreadPage } from "./pages";

export default defineModule({
  id: "social",
  routes: [
    { path: "circle", element: <CirclePage /> },
    { path: "posts/:postId", element: <PostThreadPage /> },
    { path: "pets/:petId", element: <PetProfilePage /> },
  ],
  services: {
    social: {
      fixture: () => ({
        feed: () => delay(fixtureFeed()),
        petPosts: (petId) => delay(fixturePetPosts(petId)),
        post: async (id) => delay(fixturePost(id)),
        comments: async (id) => delay({ items: fixtureComments(id), next_cursor: null }),
        react: async (id, _body, key) => delay(fixtureReact(id, key)),
        comment: async () => {
          throw ApiError.capability("social.reactions", "演示模式不发表评论。");
        },
        removePost: async () => {
          throw ApiError.capability("social.moderation", "演示模式不撤下动态。");
        },
        removeComment: async () => {
          throw ApiError.capability("social.moderation", "演示模式不删除留言。");
        },
        follow: async () => delay(undefined),
        block: async () => delay(undefined),
        report: async () => delay(undefined),
        // 演示世界没有“真实遇见”的记录：不编朋友。
        friends: async () => {
          throw ApiError.capability("social.friends", "演示模式没有朋友记录。");
        },
        // 演示里的“举报”只是本页演示、不记下来，也没有运营后台：没有可查的举报记录，按能力未接入处理，不编记录；
        // 也不回空列表——空列表会被说成“你还没有举报过”，而演示里明明点得了“举报”。
        myReports: async () => {
          throw ApiError.capability("social.report_outcomes", "演示模式没有举报记录。");
        },
      }),
      live: ({ api }) => ({
        feed: (cursor) => api.request<PostPage>("/circle/feed", { query: { cursor } }),
        petPosts: (petId, cursor) => api.request<PostPage>(`/pets/${encodeURIComponent(petId)}/posts`, { query: { cursor } }),
        post: (id) => api.request<Post>(`/posts/${encodeURIComponent(id)}`),
        comments: (id, cursor) => api.request<CommentPage>(`/posts/${encodeURIComponent(id)}/comments`, { query: { cursor } }),
        react: (id, body, key) => api.request<Post>(`/posts/${encodeURIComponent(id)}/reactions`, { method: "POST", body, idempotencyKey: key }),
        comment: (id, body, key) => api.request<Comment>(`/posts/${encodeURIComponent(id)}/comments`, { method: "POST", body, idempotencyKey: key }),
        removePost: (id) => api.request<void>(`/posts/${encodeURIComponent(id)}`, { method: "DELETE" }),
        removeComment: (id) => api.request<void>(`/comments/${encodeURIComponent(id)}`, { method: "DELETE" }),
        follow: (petId, follow) => api.request<void>(`/pets/${encodeURIComponent(petId)}/follow`, { method: "POST", body: { follow } }),
        block: (target) => api.request<void>("/blocks", { method: "POST", body: { post_id: target.post_id ?? null, comment_id: target.comment_id ?? null } }),
        report: (kind, id, reason) => api.request<void>("/reports", { method: "POST", body: { target_kind: kind, target_id: id, reason } }),
        friends: (petId, signal) => api.request<FriendSummary[]>("/friends", { query: { pet_id: petId }, signal }),
        // 契约有 MyReports，但路由还没关联 response_model：先按 unknown 取回，再逐条校验（坏条目丢掉，外层坏了抛可重试的错误）；没装运营后台时后端回能力未接入。
        myReports: async (signal) => parseMyReports(await api.request<unknown>("/reports/mine", { signal })),
      }),
    },
  },
});
