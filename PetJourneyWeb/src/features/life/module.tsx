/**
 * 证件卡包模块（回忆 → 证件卡包）：/life 卡包（证件 | 打工记录）、/credentials/:credentialId 单张证件。
 * 按方案 2.2，二级 / 三级页全屏、不显示底部标签栏，所以挂 bareRoutes；登录与入住守卫沿用新版一级页共用的 WorldGate。
 * 卡面信息全部来自服务端，前端只排版；fixture 只返回演示世界的数据（fixture.ts），live 只请求真实接口。
 */
import type { CredentialDetail, CredentialSummary, JobRecord } from "@/shared/contracts";
import { defineModule } from "@/shared/modules/types";
import { WorldGate } from "@/features/world_map/WorldGate";
import { CredentialPage } from "./CredentialPage";
import { fixtureLifeService } from "./fixture";
import { WalletPage } from "./WalletPage";

export default defineModule({
  id: "life",
  bareRoutes: [
    {
      path: "life",
      element: (
        <WorldGate>
          <WalletPage />
        </WorldGate>
      ),
    },
    {
      path: "credentials/:credentialId",
      element: (
        <WorldGate>
          <CredentialPage />
        </WorldGate>
      ),
    },
  ],
  services: {
    life: {
      live: ({ api }) => ({
        jobs: (petId, signal) => api.request<JobRecord[]>("/jobs", { query: { pet_id: petId }, signal }),
        credentials: (petId, signal) => api.request<CredentialSummary[]>("/credentials", { query: { pet_id: petId }, signal }),
        credential: (credentialId, signal) => api.request<CredentialDetail>(`/credentials/${encodeURIComponent(credentialId)}`, { signal }),
      }),
      fixture: () => fixtureLifeService(),
    },
  },
});
