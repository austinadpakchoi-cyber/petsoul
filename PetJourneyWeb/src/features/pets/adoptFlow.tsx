/**
 * 共用的“迎接 TA”：领养页（/adopt）与居民主页（/world/residents/:petId）都用它。点一下只打开确认，确认之后才领养，不会自动领养。
 * 按这个人此刻的家决定怎么迎（后端 POST /adoption/adopt：带 household_id 迎进那个家，要求是它的管理员；不带就新建家庭）：
 * - 未登录（live）：去注册，沿用原来的入口 /register?entry=adopt&pet_id=…（注册后由你确认才领养）；
 * - 还没有任何家（或演示模式）：新建家庭，照原来的流程；
 * - 只管理一个家：按钮写“迎接 TA 到{家名}”，确认后带上这个家；
 * - 管理不止一个家：确认框里先选迎进哪个家，只列出你是管理员的家；
 * - 在家里但不是任何一个家的管理员：说清楚要家里的管理员来迎接，不给按钮。
 * 家名与切换栏同一套说法（householdLabels：没起名叫“{第一只已入住宠物}的家”，撞名带序号）。
 * 成功后照原流程去入住准备（接待 → 入住 → 到家）；失败按原因说人话，原始错误码不出现在正文里。
 */
import { useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import type { HouseholdBrief } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { householdLabels } from "@/shared/session/householdContext";
import { useSessionState } from "@/shared/session/onboarding";
import { Button } from "@/shared/ui";

export type AdoptFlowProps = {
  /** 领养候选编号：领养页用 AdoptionCandidate.candidate_id，居民主页用 PublicPetView.resident.candidate_id。 */
  candidateId: string;
  /** 居民的 pet_id：未登录去注册时带上（entry=adopt&pet_id=…），注册后回到这位居民；没有就走普通注册。 */
  petId?: string | null;
  /** 居民名字：确认框与读屏名里用。 */
  name: string;
  /** 此刻能不能被领养（AdoptionCandidate.availability === "available" / PublicPetView.adoptable）；不能时按钮是灰的、点不开。 */
  adoptable: boolean;
  /** 放在“迎接 TA”旁边、打开确认时收起的动作（例如领养页的“认识 TA”）。 */
  beside?: ReactNode;
  /** 按钮占满一行（居民主页贴底的行动区）。 */
  block?: boolean;
};

/** 失败说人话：按错误码与原因码给一句话；认不出的只说没成功，不把后端原话或错误码摆进正文。 */
export function adoptFailureText(error: unknown): string {
  const err = toApiError(error);
  const reason = typeof err.details?.reason === "string" ? err.details.reason : null;
  if (err.code === "ADOPTION_TAKEN") return "TA 刚刚有了自己的家。每一位居民只属于一个家庭。";
  if (err.code === "ALREADY_HAS_COMPANION") return "每个账号先陪伴一只专属伙伴。";
  if (reason === "household_exists") return "你已经建立过一个家，新的伙伴可以迎进那个家。";
  if (err.code === "FORBIDDEN" || err.status === 403) return "需要家里的管理员来迎接 TA。";
  if (err.code === "NOT_FOUND" || err.status === 404) return "没有找到这位伙伴，TA 可能已经不在等一个家了。";
  if (err.isAuth) return "登录状态过期了，重新登录后再来迎接 TA。";
  if (err.kind === "network" || err.kind === "timeout") return "网络不太稳，这次没有迎接成功，可以再试一次。";
  return "这次没有迎接成功，请稍后再试。";
}

type Plan =
  | { kind: "pending" }
  | { kind: "error"; retry: () => void }
  | { kind: "visitor" }
  | { kind: "new" }
  | { kind: "one"; household: HouseholdBrief; label: string }
  | { kind: "choose"; options: Array<{ household: HouseholdBrief; label: string }> }
  | { kind: "not_admin" };

export function AdoptFlow({ candidateId, petId, name, adoptable, beside, block = false }: AdoptFlowProps) {
  const services = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const session = useSessionState();
  const live = env.dataMode === "live";
  const userId = session.data?.authenticated ? session.data.user?.user_id ?? null : null;
  // 与切换栏同一个缓存键；领养页、居民主页都不在 HouseholdProvider 里，这里自己读。
  const households = useQuery({ queryKey: queryKeys.households(userId ?? "-"), queryFn: () => services.households.list(), enabled: live && Boolean(userId), staleTime: 15_000 });
  const [confirming, setConfirming] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);
  const keyRef = useRef(newIdempotencyKey("adopt"));

  let plan: Plan;
  if (!live) plan = { kind: "new" }; // 演示模式：演示领养，不读账号与家庭
  else if (session.isPending) plan = { kind: "pending" };
  else if (!session.data?.authenticated) plan = { kind: "visitor" };
  else if (households.isPending) plan = { kind: "pending" };
  else if (households.isError) plan = { kind: "error", retry: () => void households.refetch() };
  else {
    const list = households.data ?? [];
    const labels = householdLabels(list);
    const admin = list.filter((household) => household.role === "admin").map((household) => ({ household, label: labels.get(household.household_id) ?? "" }));
    if (!list.length) plan = { kind: "new" };
    else if (!admin.length) plan = { kind: "not_admin" };
    else if (admin.length === 1) plan = { kind: "one", household: admin[0].household, label: admin[0].label };
    else plan = { kind: "choose", options: admin };
  }
  const target = plan.kind === "one" ? plan.household.household_id : plan.kind === "choose" ? chosen : null;

  const adopt = useMutation({
    mutationFn: () => services.pets.adopt(candidateId, keyRef.current, target),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.session }),
        queryClient.invalidateQueries({ queryKey: ["households"] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.adoption }),
        queryClient.invalidateQueries({ queryKey: ["public"] }),
      ]);
      navigate("/onboarding/reception?branch=adopted");
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.adoption });
      void queryClient.invalidateQueries({ queryKey: ["public"] });
    },
  });

  const blockClass = block ? " ps-btn--block" : "";
  if (plan.kind === "visitor") {
    return <div className="ps-adopt-flow__actions">
      {beside}
      <Link className={`ps-btn ps-btn--primary${blockClass}`} to={petId ? `/register?entry=adopt&pet_id=${encodeURIComponent(petId)}` : "/register"} aria-label={`迎接 TA：${name}`}>迎接 TA</Link>
    </div>;
  }
  if (plan.kind === "not_admin") {
    return <div className="ps-adopt-flow__actions">
      {beside}
      <p className="ps-adopt-flow__note" role="note">要把 {name} 迎进家里，需要家里的管理员来迎接。</p>
    </div>;
  }
  if (plan.kind === "error") {
    return <div className="ps-adopt-flow__actions">
      {beside}
      <div className="ps-adopt-flow__note" role="alert">暂时确认不了你的家。<Button variant="secondary" onClick={plan.retry}>再试一次</Button></div>
    </div>;
  }

  const buttonText = plan.kind === "one" ? `迎接 TA 到${plan.label}` : "迎接 TA";
  if (!confirming || plan.kind === "pending") {
    return <div className="ps-adopt-flow__actions">
      {beside}
      <Button variant="primary" block={block} disabled={!adoptable || plan.kind === "pending"} loading={plan.kind === "pending"} aria-label={`${buttonText}：${name}`} onClick={() => setConfirming(true)}>
        {buttonText}
      </Button>
    </div>;
  }

  const where = plan.kind === "one" ? `到${plan.label}` : "";
  return (
    <div className="ps-adopt-confirm" role="group" aria-label={`确认领养 ${name}`}>
      <strong>确定迎接 {name} {where}吗？</strong>
      {plan.kind === "choose" ? (
        <fieldset className="ps-adopt-flow__homes">
          <legend>迎进哪个家</legend>
          {plan.options.map(({ household, label }) => (
            <label key={household.household_id}>
              <input type="radio" name={`adopt-home-${candidateId}`} value={household.household_id} checked={chosen === household.household_id} disabled={adopt.isPending}
                onChange={() => {
                  setChosen(household.household_id);
                  // 迎进的家变了，请求就不是同一个了：换一把幂等键，不沿用上一次的。
                  keyRef.current = newIdempotencyKey("adopt");
                  adopt.reset();
                }} />
              <span>{label}</span>
            </label>
          ))}
        </fieldset>
      ) : null}
      <p>{plan.kind === "new" ? "领养后 TA 会加入你的家，下一步可以先和接待员说说想交代的事。" : plan.kind === "one" ? `领养后 TA 会住进${plan.label}，下一步可以先和接待员说说想交代的事。` : "领养后 TA 会住进你选的家，下一步可以先和接待员说说想交代的事。"}</p>
      <div className="ps-adopt-confirm__actions">
        <Button variant="secondary" onClick={() => { setConfirming(false); adopt.reset(); }} disabled={adopt.isPending}>再看看</Button>
        <Button variant="primary" loading={adopt.isPending} disabled={plan.kind === "choose" && !chosen} onClick={() => adopt.mutate()}>确认领养</Button>
      </div>
      {adopt.isError ? <p className="ps-form-error" role="alert">{adoptFailureText(adopt.error)}</p> : null}
    </div>
  );
}
