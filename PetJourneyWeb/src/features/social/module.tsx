/**
 * 星球圈模块：动态流、动态详情与评论线程（明确以宠物或主人身份）、宠物公开主页、关注、撤下、屏蔽、举报。
 * 动态只来自真实世界事件（到访）；fixture 模式的互动只在本页内存里演示。
 */
import type { Comment, CommentPage, Post, PostPage } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { defineModule } from "@/shared/modules/types";
import { fixtureComments, fixtureFeed, fixturePetPosts, fixturePost, fixtureReact } from "@/fixtures/social";
import { delay } from "@/fixtures/world";
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
      }),
    },
  },
});
