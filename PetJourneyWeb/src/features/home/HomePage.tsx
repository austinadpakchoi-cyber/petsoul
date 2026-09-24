import { useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import type { CharacterState, HomeSnapshot } from "@/shared/contracts";
import { useActiveHome, useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import type { SlotPropsMap } from "@/shared/slots/names";
import { Slot, useSlotContributions } from "@/shared/slots/Slot";
import { ErrorBoundary, Page, QueryView } from "@/shared/ui";
import { ArrivalMoment } from "./ArrivalMoment";
import { AdjustCharacter, usePetCharacter } from "./PetFigure";
import { HomeBackLink, HomeScene } from "./HomeScene";
import "./home.css";

/**
 * 小窝（地图下面的二级页）。旧 UI 已退役（用户 2026-09-24“老的 UI 要退役，不要干扰新的 UI/UX”）：
 * - “生活与回忆”那排入口搬去“回忆”“我的”；管理员“给这个家添伙伴”在“我的 · 我们的家”；
 * - “此刻 · 一起生活”面板与地图首页的主状态面板重复，已去掉：菜熟了看院子里发光的菜园门，
 *   未读看院子信箱探出的信封、屋内左侧信箱小图标上的小红点，TA 出门在外就回地图看；
 * - home.panels 在小窝里一张卡都不放（白名单已清空，见 HOME_PANELS_ALLOWED）。
 */
/**
 * home.panels 在小窝里只放白名单里的卡片。旅途状态卡（journey.status）与刚退役的“此刻 · 一起生活”是同一类旧 UI，
 * 它的去向是地图首页的主状态面板；其他模块往 home.panels 新加的卡也不会自动出现在小窝。
 * 已完成（2026-09-24）：驾校提醒按方案第 8.2 节挪到了地图主状态面板（TA 想学开车、学车进度、领证仪式），
 * 白名单清空，home.panels 在小窝不再渲染任何卡片；以后真要在小窝放卡，先在这里登记理由。
 */
const HOME_PANELS_ALLOWED: ReadonlySet<string> = new Set<string>();

function HomePanels({ snapshot }: { snapshot: HomeSnapshot }) {
  const items = useSlotContributions("home.panels").filter((item) => HOME_PANELS_ALLOWED.has(item.id));
  return (
    <>
      {items.map(({ id, Component }) => {
        // 与 Slot 同样的写法：每张卡各有错误边界，一张出错不拖垮小窝。
        const Typed = Component as unknown as (props: SlotPropsMap["home.panels"]) => ReactNode;
        return (
          <ErrorBoundary key={id} scope={`home.panels:${id}`} compact>
            <Typed snapshot={snapshot} />
          </ErrorBoundary>
        );
      })}
    </>
  );
}

export function HomeBody({ snapshot, character = null, introPaused = false }: { snapshot: HomeSnapshot; character?: CharacterState | null; introPaused?: boolean }) {
  return (
    <div className="ps-home-body">
      <HomeScene
        snapshot={snapshot}
        worldCharacter={character}
        petActions={character ? <AdjustCharacter petId={snapshot.pet.pet_id} state={character} /> : null}
        introPaused={introPaused}
      />
      {snapshot.catching_up ? <p className="ps-home-catching-up" role="status">世界正在补记刚发生的小事；位置照常更新，来信、工资与收藏可能稍后出现。</p> : null}
      <div className="ps-home-below">
        <Slot name="home.welcome" props={{ snapshot }} />
        <HomePanels snapshot={snapshot} />
      </div>
    </div>
  );
}

type ArrivalState = { arrival?: unknown } | null;

export function HomePage() {
  const query = useActiveHome({ refetchInterval: 60_000 });
  const currentPetId = useOptionalCurrentHousehold()?.pet?.pet_id ?? null;
  const character = usePetCharacter(query.data?.pet.pet_id);
  const location = useLocation();
  const navigate = useNavigate();
  const arrivalPet = typeof (location.state as ArrivalState)?.arrival === "string" ? ((location.state as ArrivalState)!.arrival as string) : null;
  const [arrivalClosed, setArrivalClosed] = useState(false);
  const closeArrival = () => {
    setArrivalClosed(true);
    // 清掉这次跳转带来的状态：返回、刷新都不会再播放到家时刻。
    navigate({ pathname: location.pathname, search: location.search }, { replace: true, state: null });
  };
  // 左上角始终能回到地图并对准当前宠物（旧链接带的 ?from=map 照样能用，但不再靠它）。场景出来之前（读取中、出错）也给同一个出口。
  return (
    <Page className="ps-home-page">
      {query.isSuccess ? null : <HomeBackLink inline petId={currentPetId} />}
      <QueryView query={query}>
        {(snapshot) => {
          const own = character?.pet_id === snapshot.pet.pet_id ? character : null;
          const arriving = Boolean(arrivalPet && !arrivalClosed && arrivalPet === snapshot.pet.pet_id && snapshot.presence === "at_home");
          return (
            <>
              <HomeBody snapshot={snapshot} character={own} introPaused={arriving} />
              {arriving ? <ArrivalMoment snapshot={snapshot} character={own} onClose={closeArrival} /> : null}
            </>
          );
        }}
      </QueryView>
    </Page>
  );
}
