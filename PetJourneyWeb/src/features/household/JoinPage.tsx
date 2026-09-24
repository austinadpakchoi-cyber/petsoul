import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import type { InvitePreview } from "@/shared/contracts";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useSessionState } from "@/shared/session/onboarding";
import { Button, ErrorState, LoadingState, Page, TopBar } from "@/shared/ui";
import { BrandLogo } from "@/shared/ui/BrandLogo";
import invitationLetter from "@/features/pets/assets/entry-invitation-letter-v1.webp";
import "./household.css";

function InviteCard({ invite }: { invite: InvitePreview }) {
  return <div className="ps-join-card">
    <span className="ps-join-card__kicker">来自 {invite.inviter_name} 的邀请</span>
    <h2>{invite.household_name || "一个正在生活的家"}</h2>
    <p>{invite.pet_names.length ? `家里的伙伴：${invite.pet_names.join("、")}` : "这个家暂时没有公开的宠物名字。"}</p>
    <span className="ps-join-card__role">邀请角色：{invite.role === "admin" ? "管理员" : "共同照顾者"}</span>
    {invite.relation_hint ? <small>称呼提示：{invite.relation_hint}（不改变权限）</small> : null}
  </div>;
}

/** 邀请直达：预览不加入，登录不加入，只有二次确认调用接受接口。 */
export function JoinPage() {
  const { households } = useServices();
  const session = useSessionState();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("invite")?.trim() ?? "";
  const [confirming, setConfirming] = useState(false);
  const saved = session.data?.onboarding?.entry?.pending_invite ?? null;
  const preview = useQuery({ queryKey: queryKeys.invitePreview(token), queryFn: () => households.previewInvite(token), enabled: Boolean(token), retry: false, staleTime: 0 });
  const accept = useMutation({
    mutationFn: () => households.acceptInvite(token),
    onSuccess: () => {
      queryClient.clear();
      navigate("/map", { replace: true });
    },
  });
  const invite = token ? preview.data : saved;
  const valid = invite?.status === "pending" && !invite.already_member;
  const authQuery = `entry=invite&invite=${encodeURIComponent(token)}`;
  return <Page bare className="ps-join-page">
    <TopBar title="家人邀请" subtitle="先看清楚，再决定要不要加入" back="/world" />
    <div className="ps-join-hero">
      <img src={invitationLetter} alt="" />
      <BrandLogo size="compact" />
      <h1>有一封信，<br />写给你。</h1>
      <p>加入家庭是你的决定。打开邀请、注册或登录，都不会自动加入。</p>
    </div>
    {token && preview.isPending ? <LoadingState lines={2} label="正在核对这封邀请…" /> : token && preview.isError ? <ErrorState error={preview.error} onRetry={() => void preview.refetch()} /> : invite ? <>
      <InviteCard invite={invite} />
      {!valid ? <p className="ps-join-notice">{invite.already_member ? "你已经是这个家的成员，可以回家看看。" : "邀请已不可用或已过期。请联系邀请你的家人获取新链接。"}</p> : !token ? <p className="ps-join-notice">你的邀请选择已找回。出于安全考虑，这里不会再显示原来的邀请链接；请重新打开家人发来的链接，核对后确认加入。</p> : session.isPending ? <LoadingState lines={1} label="正在确认你是否登录…" /> : session.isError ? <ErrorState error={session.error} onRetry={() => void session.refetch()} /> : !session.data?.authenticated ? <div className="ps-join-actions">
        <Link className="ps-btn ps-btn--primary ps-btn--block" to={`/register?${authQuery}`}>注册后再确认</Link>
        <Link className="ps-join-login" to={`/login?${authQuery}`}>已有账号？登录后继续</Link>
      </div> : confirming ? <div className="ps-join-confirm" role="group" aria-label="确认加入家庭">
        <strong>确定加入这个家吗？</strong>
        <p>加入后，你能看到的宠物和家庭内容由上面的角色决定。</p>
        <div><Button variant="secondary" disabled={accept.isPending} onClick={() => setConfirming(false)}>再想想</Button><Button variant="primary" loading={accept.isPending} onClick={() => accept.mutate()}>确认加入</Button></div>
      </div> : <Button variant="primary" block onClick={() => setConfirming(true)}>我想加入这个家</Button>}
      {accept.isError ? <ErrorState error={accept.error} onRetry={() => void preview.refetch()} /> : null}
    </> : !token ? <p className="ps-join-notice">这里还没有邀请。请从家人分享的专属链接进入，或先去认识星球居民。</p> : null}
    <Link className="ps-join-back" to="/world">先看看星球 →</Link>
  </Page>;
}
