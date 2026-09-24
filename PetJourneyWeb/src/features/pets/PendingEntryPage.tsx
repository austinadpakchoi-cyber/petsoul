import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { onboardingRoute, useSessionState } from "@/shared/session/onboarding";
import { Button, ErrorState, LoadingState, Page, TopBar } from "@/shared/ui";
import publicWorldScene from "./assets/public-world-v1.webp";
import "./pets.css";

/** 领养选择属于“待确认”，注册只保存意向；这里的点击才执行原子领养。 */
export function PendingEntryPage() {
  const { pets } = useServices();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useSessionState();
  const [params] = useSearchParams();
  const pending = session.data?.onboarding?.entry?.pending_adoption;
  const petId = params.get("pet_id") ?? pending?.pet_id ?? null;
  const [confirming, setConfirming] = useState(false);
  const keyRef = useRef(newIdempotencyKey("entry-adopt"));
  const pet = useQuery({ queryKey: queryKeys.publicPet(petId ?? "-"), queryFn: () => pets.publicPet(petId!), enabled: Boolean(petId && session.data?.authenticated), staleTime: 15_000 });
  const adopt = useMutation({
    mutationFn: () => pets.adopt(pet.data!.resident!.candidate_id, keyRef.current, null), // 入住流程：还没有家，新建家庭
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.session }),
        queryClient.invalidateQueries({ queryKey: queryKeys.publicWorld }),
        queryClient.invalidateQueries({ queryKey: queryKeys.adoption }),
      ]);
      navigate("/onboarding/reception?branch=adopted", { replace: true });
    },
    onError: () => {
      keyRef.current = newIdempotencyKey("entry-adopt");
      void pet.refetch();
    },
  });

  if (session.isPending) return <Page bare><LoadingState lines={2} label="正在找回你的选择…" /></Page>;
  if (session.isError) return <Page bare><ErrorState error={session.error} onRetry={() => void session.refetch()} /></Page>;
  if (!session.data.authenticated) return <Navigate to={`/login${petId ? `?entry=adopt&pet_id=${encodeURIComponent(petId)}` : ""}`} replace />;
  // 已经不在“挑伙伴”这一步：按入住阶段去该去的地方（已入住 → 地图首页，接待 / 入住没完成 → 对应那一步）。
  if (session.data.onboarding?.step !== "needs_companion") return <Navigate to={onboardingRoute(session.data.onboarding)} replace />;
  if (!petId) return <Navigate to="/onboarding" replace />;
  const selected = pet.data;
  const canAdopt = Boolean(selected?.adoptable && selected.resident?.candidate_id && (pending?.pet_id !== petId || pending.available !== false));
  return (
    <Page bare className="ps-entry-page ps-public-page">
      <TopBar title="你之前认识的伙伴" subtitle="继续之前，请你自己决定" back="/world" />
      {pet.isPending ? <LoadingState lines={2} label="正在核对 TA 现在的状态…" /> : pet.isError ? <ErrorState error={pet.error} onRetry={() => void pet.refetch()} /> : selected ? (
        <div className="ps-pending-choice">
          <div className="ps-pending-choice__image"><img src={publicWorldScene} alt="" /><span>还在星球上的 TA</span></div>
          <span className="ps-public-kicker">你选中的居民 · 登录后已找回</span>
          <h1>{selected.profile.display_name}</h1>
          {selected.resident ? <p>{selected.resident.doing} · {selected.resident.residence}</p> : null}
          {selected.resident?.dream ? <div className="ps-public-profile__dream"><span>TA 想做的事</span><strong>{selected.resident.dream}</strong></div> : null}
          {!canAdopt ? <p className="ps-public-profile__quiet">TA 现在不能被领养了。不会替你换成另一位，也不会自动建立新伙伴。</p> : confirming ? (
            <div className="ps-pending-choice__confirm" role="group" aria-label={`确认迎接 ${selected.profile.display_name}`}>
              <strong>确定迎接 {selected.profile.display_name} 吗？</strong>
              <p>确认后，TA 才会加入你的家。TA 在星球上的身份和经历会继续保留。</p>
              <div>
                <Button variant="secondary" disabled={adopt.isPending} onClick={() => setConfirming(false)}>再想想</Button>
                <Button variant="primary" loading={adopt.isPending} onClick={() => adopt.mutate()}>确认迎接 TA</Button>
              </div>
            </div>
          ) : <Button variant="primary" block onClick={() => setConfirming(true)}>我想迎接 {selected.profile.display_name}</Button>}
          {adopt.isError ? <ErrorState error={toApiError(adopt.error)} onRetry={() => void pet.refetch()} /> : null}
          <div className="ps-pending-choice__alternatives">
            <Link to="/world">再看看其他居民</Link>
            <Link to="/onboarding">带自己的宠物来</Link>
          </div>
        </div>
      ) : null}
    </Page>
  );
}
