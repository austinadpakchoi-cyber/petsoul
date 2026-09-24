/**
 * 爪爪驾校的图片素材（UI-ASSET-009 v1，r7k 2026-09-24 交付，见 docs/coordination/ui-assets/deliveries/UI-ASSET-009-v1.md）。
 * 各处都从这里取网址，不在组件里另写路径。素材只是画面：玩家的宠物、驾照上的字、场地线和判定都由代码按真实数据画；
 * 图片加载失败时退回原来的代码画法。
 */
const ART = "/ui-assets/UI-ASSET-009/v1";

export const SCHOOL_ART = {
  coach: {
    /** 512×512 透明，头像在中间约 80% 的圆形安全区里 */
    portrait: `${ART}/coach-turtle-portrait.webp`,
    /** 640×640 透明，讲解的姿势 */
    explain: `${ART}/coach-turtle-explain.webp`,
    /** 640×640 透明，鼓掌的姿势 */
    cheer: `${ART}/coach-turtle-cheer.webp`,
    /** 720×720 透明，领证时举着一张空白卡 */
    ceremony: `${ART}/ceremony-coach.webp`,
  },
  /** 驾校首页横幅：780×320，左边约 40% 是安静的天空和草地，标题用页面文字叠上去；2 倍屏用 1560×640 */
  hero: { src: `${ART}/school-hero.webp`, large: `${ART}/school-hero-large.png`, width: 780, height: 320 },
  /** 驾照正反底图：856×540，四角透明，名字、号码、照片由代码叠上去 */
  license: { front: `${ART}/license-card-front-bg.webp`, back: `${ART}/license-card-back-bg.webp`, width: 856, height: 540 },
  /** 场地（画布用）：车朝右、车顶圆窗约在从车尾算起 40% 处；地面纹理 256×256 可无缝平铺 */
  field: {
    car: `${ART}/car-topdown.webp`,
    carLarge: `${ART}/car-topdown-large.webp`,
    treeA: `${ART}/field-tree-a.webp`,
    treeB: `${ART}/field-tree-b.webp`,
    bush: `${ART}/field-bush.webp`,
    cone: `${ART}/field-cone.webp`,
    flag: `${ART}/field-flag.webp`,
    grass: `${ART}/field-grass-tile.webp`,
    asphalt: `${ART}/field-asphalt-tile.webp`,
  },
} as const;
