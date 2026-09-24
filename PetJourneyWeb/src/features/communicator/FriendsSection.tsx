/**
 * 通讯器 · TA 的朋友（玩家端方案 7.1 的新入口）：TA 自己在外面遇见的朋友。数据来自 GET /friends（只给这只宠物的家人）。
 * - 关系不是位置：“最近在某地见过”只说见过，不当成朋友此刻在哪，也不上地图；
 * - 宠物朋友可以点进它的公开主页；星球居民明确标注，只展示信息（没有可去的页面就不做成可点的样子）；
 * - 头像一律是 TA 自己的样子（PetPortrait）：FriendSummary 没有照片字段，live 下是中性爪印，从不写名字首字；
 * - 演示世界没有真实的相遇：服务报“能力未接入”时只给一句说明，不编朋友、不露能力代码。
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import type { FriendSummary } from "@/shared/contracts";
import { isApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useCurrentHousehold } from "@/shared/session/householdContext";
import { Chip, EmptyState, ErrorState, Icon, LoadingState, type ChipTone } from "@/shared/ui";
import { PetPortrait } from "@/features/pets/PetPortrait";
import { closenessOf, friendProfileHref, lastSeenText, meetCountText, sortFriends, speciesLabel, type ClosenessTone } from "./friends";

const CLOSENESS_TONE: Record<ClosenessTone, ChipTone> = { new: "sky", familiar: "leaf", close: "coral", unknown: "neutral" };

function FriendCard({ friend }: { friend: FriendSummary }) {
  const closeness = closenessOf(friend.closeness);
  const resident = friend.kind === "resident";
  const species = speciesLabel(friend.species);
  const facts = [friend.kind === "pet" ? (species ? `宠物 · ${species}` : "宠物") : species, meetCountText(friend.meet_count)].filter(Boolean).join(" · ");
  const seen = lastSeenText(friend.last_place);
  const href = friendProfileHref(friend);
  const content = (
    <>
      <PetPortrait name={friend.name} size={48} />
      <div className="ps-friend__main">
        <div className="ps-friend__title">
          <strong className="ps-friend__name">{friend.name}</strong>
          <Chip tone={CLOSENESS_TONE[closeness.tone]} icon={closeness.tone === "close" ? "heart" : undefined}>
            {closeness.label}
          </Chip>
        </div>
        {resident || facts ? (
          <div className="ps-friend__facts">
            {resident ? (
              <Chip tone="sun" icon="planet">
                星球居民
              </Chip>
            ) : null}
            {facts ? <span>{facts}</span> : null}
          </div>
        ) : null}
        {seen ? <div className="ps-friend__seen">{seen}</div> : null}
      </div>
    </>
  );
  if (!href) {
    return (
      <li className="ps-friend" data-friend-kind={friend.kind}>
        {content}
      </li>
    );
  }
  return (
    <li>
      <Link className="ps-friend ps-friend--link" data-friend-kind={friend.kind} to={href} aria-label={`${friend.name}的主页：${[closeness.label, facts, seen].filter(Boolean).join("，")}`}>
        {content}
        <Icon name="chevron" size={16} className="ps-friend__go" />
      </Link>
    </li>
  );
}

export function FriendsSection({ petId }: { petId: string | null }) {
  const { social } = useServices();
  const { userId } = useCurrentHousehold();
  const friends = useQuery({
    queryKey: queryKeys.friendsFor(userId ?? "-", petId ?? "-"),
    queryFn: ({ signal }) => social.friends(petId!, signal),
    enabled: Boolean(petId),
  });

  if (friends.isError) {
    if (isApiError(friends.error) && friends.error.isCapabilityUnavailable) {
      return env.dataMode === "fixture" ? (
        <EmptyState icon="info" title="演示里还没有朋友记录">
          朋友要 TA 真的在外面遇见，才会记在这里；演示世界里先空着。
        </EmptyState>
      ) : (
        <EmptyState icon="info" title="暂时看不到 TA 的朋友">
          过一会儿再来看看。
        </EmptyState>
      );
    }
    return <ErrorState error={friends.error} onRetry={() => void friends.refetch()} />;
  }
  if (!friends.data) return <LoadingState lines={2} label="翻看 TA 的朋友…" />;
  if (friends.data.length === 0) {
    return (
      <EmptyState icon="heart" title="TA 还没在外面遇到朋友">
        TA 出门时，也许会遇见新朋友。
      </EmptyState>
    );
  }
  const list = sortFriends(friends.data);
  return (
    <div className="ps-friends-section">
      <ul className="ps-friends" aria-label="TA 的朋友">
        {list.map((friend) => (
          <FriendCard key={friend.friend_id} friend={friend} />
        ))}
      </ul>
      {list.some((friend) => friend.kind === "resident") ? <p className="ps-friends__note">标着“星球居民”的，是一直住在这颗星球上的居民，不是别人家的宠物。</p> : null}
    </div>
  );
}
