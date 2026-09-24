/**
 * 我们的家 · 一起照顾 TA 的人（方案第 9 节：管理员可移除成员、调整角色）。
 * - 只有管理员（your_permissions 含 manage）看得到“移除”和“调整角色”；共同照顾者只看名单。
 * - 不能移除自己（自己那一行没有“移除”；退出家庭不是这里的事）；家里不能没有管理员：你是唯一管理员时，
 *   自己那一行不给“改为共同照顾者”，说明先把另一位家人设为管理员。这些只是先挡明显的情况，以后端的拒绝码为准。
 * - 每个动作都要二次确认，写清后果（移除：对方将看不到这个家和家里的伙伴）。
 * - 后端拒绝按原因码说人话（409 last_admin、403 admin_required、404 member_not_found……），码收进“技术信息”；
 *   403 / 404 说明情况已经变了，顺手刷新家庭详情与家庭列表。
 * - 成功后刷新家庭详情，以及 households 列表（切换宠物栏、“我的”页读的就是它）。
 */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { HouseholdDetail, HouseholdMember } from "@/shared/contracts";
import { isApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { Card } from "@/shared/ui";
import "./members.css";

type MemberAction = "remove" | "admin" | "caregiver";
interface Asked {
  member: HouseholdMember;
  action: MemberAction;
}
interface Failure {
  text: string;
  tech: string;
}

/** 后端拒绝的原因码（details.reason）。 */
function reasonOf(error: unknown): string | null {
  return isApiError(error) && typeof error.details?.reason === "string" ? error.details.reason : null;
}

/** 成员动作没做成时的一句人话：以后端的原因码为准。 */
export function memberActionFailure(error: unknown): string {
  const reason = reasonOf(error);
  if (reason === "last_admin") return "家里至少要有一位管理员。想交出管理员，先把另一位家人设为管理员。";
  if (reason === "admin_required") return "这一步需要家庭管理员来做。你现在可能已经不是管理员了，页面已按最新情况刷新。";
  if (reason === "member_not_found") return "这位家人已经不在这个家里了，页面已按最新情况刷新。";
  if (reason === "household_not_found") return "你已经不在这个家里了。";
  if (!isApiError(error)) return "这一步没做成，请稍后再试。";
  if (error.code === "CSRF_FAILED") return "登录状态有变化，刷新页面后再试。";
  if (error.isAuth) return "登录状态过期了，重新登录后再试。";
  if (error.kind === "network" || error.kind === "timeout") return "信号断了一下，没做成，再试一次。";
  if (error.status === 409) return "家里的情况刚有变化，这一步没做成。刷新看看最新的。";
  if (error.status === 403) return "你现在没有权限做这一步。";
  return "这一步没做成，请稍后再试。";
}

/** 给“技术信息”的一行：错误码 · 原因码 · request_id（平时收起）。 */
function techLine(error: unknown): string {
  if (!isApiError(error)) return error instanceof Error ? error.message : "";
  return [error.code, reasonOf(error), error.requestId ? `request_id ${error.requestId}` : null].filter(Boolean).join(" · ");
}

/** 403 / 404：情况已经变了（不再是管理员、对方已经不在），要按最新的刷新。 */
function staleAfter(error: unknown): boolean {
  return isApiError(error) && (error.status === 403 || error.status === 404) && error.code !== "CSRF_FAILED";
}

const ROLE_LABEL: Record<HouseholdMember["role"], string> = { admin: "家庭管理员", caregiver: "共同照顾者" };

function consequence({ member, action }: Asked): string {
  const who = member.is_you ? "你" : member.display_name;
  // “TA 们”中间是不换行空格（ ）：窄屏上不会把“TA”和“们”拆到两行。
  if (action === "remove") return `移除后，${who}将看不到这个家和家里的伙伴，也不能再照顾 TA 们；想让 TA 回来，需要重新邀请。确定移除吗？`;
  if (action === "admin") return `设为管理员后，${who}可以管理家人、发出邀请、修改家里的约定，也能移除其他家人（包括你）。确定吗？`;
  return member.is_you
    ? "改为共同照顾者后，你就不能再管理家人和家里的约定了，只有其他管理员能把你改回来。确定吗？"
    : `改为共同照顾者后，${who}不能再管理家人和家里的约定，日常照顾不受影响。确定吗？`;
}

const CONFIRM_LABEL: Record<MemberAction, string> = { remove: "确定移除", admin: "确定设为管理员", caregiver: "确定改为共同照顾者" };

function doneText({ member, action }: Asked): string {
  const who = member.is_you ? "你" : member.display_name;
  if (action === "remove") return `已移除${who}。`;
  return action === "admin" ? `已把${who}设为管理员。` : `已把${who}改为共同照顾者。`;
}

export function MembersCard({ detail, userId }: { detail: HouseholdDetail; userId: string | null }) {
  const { households } = useServices();
  const queryClient = useQueryClient();
  const householdId = detail.household.household_id;
  const canManage = detail.your_permissions.includes("manage");
  const admins = detail.members.filter((member) => member.role === "admin");
  const [asked, setAsked] = useState<Asked | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  const detailKey = queryKeys.householdDetail(userId ?? "-", householdId);
  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: detailKey });
    void queryClient.invalidateQueries({ queryKey: queryKeys.households(userId ?? "-") });
  };

  const act = useMutation({
    mutationFn: async ({ member, action }: Asked) => {
      if (action === "remove") {
        await households.removeMember(householdId, member.user_id);
        return null;
      }
      return households.setMemberRole(householdId, member.user_id, action);
    },
    onSuccess: (updated, done) => {
      if (updated) queryClient.setQueryData(detailKey, updated);
      refreshAll();
      setAsked(null);
      setFailure(null);
      setNotice(doneText(done));
    },
    onError: (error) => {
      setFailure({ text: memberActionFailure(error), tech: techLine(error) });
      if (staleAfter(error)) {
        setAsked(null);
        refreshAll();
      }
    },
  });

  const ask = (member: HouseholdMember, action: MemberAction) => {
    setNotice(null);
    setFailure(null);
    setAsked({ member, action });
  };

  /** 这一行能做的角色调整：对方按现角色给相反的；自己只有在还有别的管理员时才能交出管理员。 */
  const roleAction = (member: HouseholdMember): MemberAction | null => {
    if (member.role === "caregiver") return member.is_you ? null : "admin";
    if (member.is_you && admins.length <= 1) return null;
    return "caregiver";
  };
  const soleAdminIsYou = canManage && admins.length === 1 && admins[0].is_you && detail.members.length > 1;

  return (
    <Card paper className="ps-family-card ps-members">
      <h2>一起照顾 TA 的人</h2>
      {detail.members.map((member) => {
        const role = canManage ? roleAction(member) : null;
        const removable = canManage && !member.is_you;
        const open = asked?.member.user_id === member.user_id;
        return (
          <div className="ps-member" key={member.user_id}>
            <div className="ps-family-row ps-member__row">
              <div>
                <strong>
                  {member.display_name}
                  {member.is_you ? " · 你" : ""}
                </strong>
                <small>{ROLE_LABEL[member.role]}</small>
              </div>
              {role || removable ? (
                <div className="ps-member__actions">
                  {role ? (
                    <button type="button" className="is-quiet" disabled={act.isPending} onClick={() => ask(member, role)}>
                      {role === "admin" ? "设为管理员" : "改为共同照顾者"}
                    </button>
                  ) : null}
                  {removable ? (
                    <button type="button" className="is-danger" disabled={act.isPending} onClick={() => ask(member, "remove")}>
                      移除
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
            {open && asked ? (
              <div className="ps-member__confirm" role="group" aria-label={`确认：${member.display_name}`}>
                <p>{consequence(asked)}</p>
                <div className="ps-member__confirm-buttons">
                  <button type="button" className={asked.action === "remove" ? "is-danger-solid" : undefined} disabled={act.isPending} onClick={() => act.mutate(asked)}>
                    {act.isPending ? "正在处理…" : CONFIRM_LABEL[asked.action]}
                  </button>
                  <button type="button" className="is-quiet" disabled={act.isPending} onClick={() => setAsked(null)}>
                    先不
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        );
      })}
      {notice ? <p role="status" className="ps-member__notice">{notice}</p> : null}
      {failure ? (
        <div role="alert" className="ps-member__failure">
          <p>{failure.text}</p>
          {failure.tech ? (
            <details className="ps-member__tech">
              <summary>技术信息</summary>
              <span>{failure.tech}</span>
            </details>
          ) : null}
        </div>
      ) : null}
      {soleAdminIsYou ? <p className="ps-family-fine">你是这个家唯一的管理员；想交出管理员，先把另一位家人设为管理员。</p> : null}
      <p className="ps-family-fine">角色与权限由家庭服务端判定；称呼只属于你与当前宠物，不改变家人权限。</p>
    </Card>
  );
}
