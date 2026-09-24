import type { MouseEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import type { PetSpecies } from "@/shared/contracts";
import { Icon } from "@/shared/ui";
import { BrandLogo } from "@/shared/ui/BrandLogo";
import { PlanetScene } from "./PlanetMap";

/**
 * 访客星球与居民主页共用的头图：小星球插画 + 左上返回 + 品牌字。
 * historyBack：站内点进来的（不是直接打开链接），普通左键点返回就退回上一页（例如回到星球页原来滚到的位置），
 * 和全站顶栏的“从哪来回哪去”一致；直接打开的、带修饰键的，照常去 back。
 */
export function WorldHero({ back, species, historyBack = false }: { back: string; species: PetSpecies[]; historyBack?: boolean }) {
  const navigate = useNavigate();
  const location = useLocation();
  const onBack = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!historyBack || location.key === "default" || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(-1);
  };
  return (
    <header className="ps-world-hero">
      <PlanetScene species={species} />
      <div className="ps-world-hero__bar">
        <Link to={back} className="ps-world-hero__back" aria-label="返回" onClick={onBack}>
          <Icon name="back" size={20} />
        </Link>
        <BrandLogo size="compact" />
      </div>
    </header>
  );
}
