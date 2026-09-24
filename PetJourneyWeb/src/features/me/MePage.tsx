/**
 * 我的（/me）：从地图右上角头像进来的全屏页；左上角回地图，不挂底栏（方案第 2.2、9 节）。
 * - 顶部是当前这只宠物，头像一律是 TA 自己的样子（PetPortrait：有照片用照片，演示模式用演示小灰猫，live 没照片是爪印），
 *   不写名字首字；会话里有主人的显示名时一起写上。
 * - 入口只放现在就有页面和接口的：我们的家、给这个家添伙伴（只对这个家的管理员出现）、TA 的档案（/me/dna）、入住叮嘱、
 *   TA 的形象（/me/look）、我的举报（/me/reports）、账号与设置（第二组按方案第 9 节的顺序）。
 *   隐私的接口还没接进前端服务，这里不出现，也不放占位。
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import type { HouseholdBrief } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { ErrorState, Icon, LoadingState, Page, type IconName } from "@/shared/ui";
import { PetPortrait } from "@/features/pets/PetPortrait";
import { WorldGate } from "@/features/world_map/WorldGate";
import { useCurrentPet, type CurrentPet } from "@/features/memories/currentPet";
import "./me.css";

type Tone = "leaf" | "sun" | "coral" | "sky";

export function MePage() {
  return (
    <WorldGate>
      <MeBody />
    </WorldGate>
  );
}

function MeBody() {
  const current = useCurrentPet();
  const ownerName = useOwnerDisplayName();
  return (
    <Page bare className="ps-me">
      <header className="ps-me-top">
        <Link className="ps-me-back" to="/map" aria-label="返回地图">
          <Icon name="back" size={20} />
        </Link>
        <h1>我的</h1>
      </header>
      {current.status === "pending" ? (
        <LoadingState lines={2} label="正在找到 TA…" />
      ) : current.status === "error" ? (
        <ErrorState error={current.error} onRetry={current.retry} />
      ) : (
        <MeContent pet={current.pet} household={current.household} ownerName={ownerName} />
      )}
    </Page>
  );
}

/** 主人的显示名：只认会话里的 user.display_name（live 下 WorldGate 已取过会话，这里读缓存）；演示模式没有账号。 */
function useOwnerDisplayName(): string | null {
  const services = useServices();
  const live = env.dataMode === "live";
  const session = useQuery({ queryKey: queryKeys.session, queryFn: () => services.session.current(), enabled: live, staleTime: 30_000 });
  const name = live && session.data?.authenticated ? session.data.user?.display_name?.trim() : "";
  return name || null;
}

/** “我们的家”那一行的小字：有家庭资料就写家名与成员数，没有就只说里面有什么。 */
function householdLine(household: HouseholdBrief | null): string {
  if (!household) return "家人、伙伴与邀请";
  const name = household.name?.trim();
  const members = `${household.member_count} 位成员`;
  return name ? `${name} · ${members}` : members;
}

function MeContent({ pet, household, ownerName }: { pet: CurrentPet | null; household: HouseholdBrief | null; ownerName: string | null }) {
  // 与“添一位伙伴”页同一条规则：只有这个家的管理员能把新伙伴带进来。
  const isAdmin = household?.role === "admin";
  return (
    <>
      <section className="ps-me-hero" aria-label="当前的伙伴">
        {pet ? <PetPortrait petId={pet.petId} name={pet.name} species={pet.species} photoUrl={pet.photoUrl} size={68} /> : null}
        <div className="ps-me-hero__text">
          <h2>{pet?.name ?? "TA"}</h2>
          {ownerName ? <p>{ownerName}的伙伴</p> : null}
        </div>
      </section>

      <ul className="ps-me-group" aria-label="家">
        <MeRow to="/households/manage" icon="home" tone="leaf" title="我们的家" meta={householdLine(household)} />
        {isAdmin ? <MeRow to="/pets/new" icon="plus" tone="sun" title="给这个家添伙伴" meta="带一位新伙伴住进这个家" /> : null}
        <MeRow to="/me/dna" icon="bookmark" tone="sky" title="TA 的档案" meta="性格、习惯和你们之间的小事" />
        <MeRow to="/onboarding/reception?mode=supplement" icon="heart" tone="coral" title="入住叮嘱" meta="想起 TA 的小事，随时补上" />
      </ul>

      {/* 第二组的读屏名要名副其实：里面是 TA 的形象、我的举报、账号与设置（隐私接上后也放这里），不只是“账号”。 */}
      <ul className="ps-me-group" aria-label="形象与账号">
        <MeRow to="/me/look" icon="sparkle" tone="leaf" title="TA 的形象" meta="星球上的样子和证件照" />
        <MeRow to="/me/reports" icon="mail" tone="sun" title="我的举报" meta="举报过的内容和处理结果" />
        <MeRow to="/settings" icon="settings" tone="sky" title="账号与设置" meta="账号、公开范围、TA 的简介" />
      </ul>
    </>
  );
}

function MeRow({ to, icon, tone, title, meta }: { to: string; icon: IconName; tone: Tone; title: string; meta: string }) {
  return (
    <li>
      <Link to={to} className="ps-me-row" data-tone={tone}>
        <span className="ps-me-row__icon" aria-hidden="true">
          <Icon name={icon} size={20} />
        </span>
        <span className="ps-me-row__text">
          <span className="ps-me-row__title">{title}</span>
          <span className="ps-me-row__meta">{meta}</span>
        </span>
        <Icon name="chevron" size={16} className="ps-me-row__go" />
      </Link>
    </li>
  );
}
