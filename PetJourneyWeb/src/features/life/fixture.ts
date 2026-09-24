/**
 * 演示数据，只在 fixture 模式使用，对应演示世界的样板宠物，不代表任何真实账号。
 *
 * - 由 claude-6c2b 分身于 2026-09-24 手写；形状、标签、获得条件、字段名照抄后端证件服务（app/web_credentials、routers/web/credentials.py），
 *   这样演示看到的排版就是 live 会看到的排版。
 * - 编号统一用 DEMO 结尾（后端编号字母表不含 O、0、1，不可能和真实编号撞上）；地名、行程都带“（示意）/（演示）”。
 * - 承运人沿用演示世界的原创动物世界身份（喵航、海獭轮渡），不对应任何真实航空公司、船公司或班次。
 * - 时间相对演示时钟（fixtures/world 的 atMin），银行卡余额直接读演示家园的钱包（余额就是钱包）。
 * - 驾照跟着驾校演示的阶段走，规则和后端卡包一样（想学 / 已报名时“办理中”，领证后有驾照）；
 *   阶段用驾校演示服务同一个开关——整页打开时的 ?school_demo=（driving_school/service.ts 的 fixtureStageFromUrl），只在建服务时读一次。
 *   演示里在驾校页当场报名、领证，卡包不会跟着变（两份演示数据各管各的）。
 * live 模式绝不使用这里的任何数据。
 */
import type { CredentialDetail, CredentialLink, CredentialSummary, JobRecord, LedgerEntry, PassportStamp, PetSpecies } from "@/shared/contracts";
import type { LifeService } from "@/shared/services/types";
import { ApiError } from "@/shared/api/errors";
import { fixtureStageFromUrl } from "@/features/driving_school/service";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { atMin, delay, fixturePet } from "@/fixtures/world";

const SPECIES: Record<PetSpecies, string> = { dog: "狗", cat: "猫", parrot: "鹦鹉", rabbit: "兔子", hamster: "仓鼠", bird: "小鸟", other: "小动物" };
const DAY_MIN = 60 * 24;

type SchoolDemoStage = ReturnType<typeof fixtureStageFromUrl>;

/** 演示时钟上的几个时刻（每次调用按当前演示时钟重新算，跟得上 resetFixtureEpoch）。 */
function moments() {
  const movedIn = atMin(-40 * DAY_MIN);
  const hkDepart = atMin(-21 * DAY_MIN);
  const hkArrive = atMin(-21 * DAY_MIN + 95);
  const macauDepart = atMin(-19 * DAY_MIN);
  const macauArrive = atMin(-19 * DAY_MIN + 60);
  const licensed = atMin(-3 * DAY_MIN);
  return { movedIn, hkDepart, hkArrive, macauDepart, macauArrive, licensed };
}

const pad = (value: number) => String(value).padStart(2, "0");
/** 演示卡面上的日期按本地日期写（YYYY-MM-DD），和页面其余地方按本地时区显示的日期一致。 */
const day = (iso: string) => {
  const date = new Date(iso);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
};
const year = (iso: string) => new Date(iso).getFullYear();

const BOARDING_TITLE = "喵航 Cat105 演示小镇机场（示意） → 香港机场（示意）";
const FERRY_TITLE = "海獭轮渡 Otter08 中环码头（示意） → 澳门码头（示意）";
const LICENSE_CONDITION = "在爪爪驾校通过四科考试后签发（科目一到科目四）";

/** 驾照条目：领证了（licensed）是一张证；想学 / 已报名是“办理中”（后端 summaries 的同一条规则）；其余还没有。 */
function license(stage: SchoolDemoStage, t: ReturnType<typeof moments>): CredentialSummary {
  if (stage === "licensed") {
    return {
      credential_id: "fx-cr-license",
      kind: "driver_license",
      label: "爪爪驾驶证",
      status: "active",
      number: `PAW-DL-${year(t.licensed)}-DEMO07`,
      issued_at: t.licensed,
      title: "PetSoul · 爪爪驾驶证 · 小型车（C）",
      condition: LICENSE_CONDITION,
      private: false,
      links: [{ kind: "exam", ref_id: "fx-license-1", title: "爪爪驾校四科全部通过", at: t.licensed }],
    };
  }
  const learning = stage === "wish" || stage === "enrolled";
  return { credential_id: null, kind: "driver_license", label: "爪爪驾驶证", status: learning ? "in_progress" : "not_obtained", number: null, issued_at: null, title: null, condition: LICENSE_CONDITION, private: false, links: [] };
}

function summaries(stage: SchoolDemoStage): CredentialSummary[] {
  const t = moments();
  const home: CredentialLink[] = [{ kind: "home", ref_id: "fx-home-001", title: "入住星球", at: t.movedIn }];
  const hkTrip: CredentialLink = { kind: "journey", ref_id: "fx-trip-hk", title: "去香港（演示）", at: t.hkDepart };
  const macauTrip: CredentialLink = { kind: "journey", ref_id: "fx-trip-macau", title: "去澳门（演示）", at: t.macauDepart };
  const driver = license(stage, t);
  const obtainedLicense = driver.credential_id ? [driver] : [];
  const missingLicense = driver.credential_id ? [] : [driver];
  // 顺序照后端：已获得的按证件种类（居民证、银行卡、档案、护照、驾照、登机牌、船票车票），没有的放最后
  return [
    { credential_id: "fx-cr-identity", kind: "identity_card", label: "星球居民证", status: "active", number: `PS-ID-${year(t.movedIn)}-DEMO01`, issued_at: t.movedIn, title: "星球居民证", condition: "入住星球时签发", private: false, links: home },
    { credential_id: "fx-cr-bank", kind: "bank_card", label: "星球银行卡", status: "active", number: `PSB-${year(t.movedIn)}-DEMO02`, issued_at: t.movedIn, title: "星球银行卡", condition: "入住时开户；就是 TA 的钱包账户，工资和旅费都记在这里", private: false, links: home },
    { credential_id: "fx-cr-care", kind: "care_profile", label: "照护档案", status: "active", number: `PS-CARE-${year(t.movedIn)}-DEMO03`, issued_at: t.movedIn, title: "照护档案", condition: "入住时按注册、照片与接待资料建立；主人修改 DNA 后同步", private: true, links: home },
    { credential_id: "fx-cr-passport", kind: "passport", label: "护照", status: "active", number: `PSP-${year(t.hkDepart)}-DEMO04`, issued_at: t.hkDepart, title: "PetSoul 星球护照", condition: "第一次出远门（跨城或跨境）时签发；本地散步不需要", private: false, links: [hkTrip, macauTrip] },
    ...obtainedLicense,
    { credential_id: "fx-cr-boarding", kind: "boarding_pass", label: "登机牌", status: "used", number: `BP-${year(t.hkDepart)}-DEMO05`, issued_at: t.hkDepart, title: BOARDING_TITLE, condition: "坐飞机出行时，按实际成立的航段签发", private: false, links: [hkTrip, { kind: "leg", ref_id: "fx-leg-hk-flight", title: BOARDING_TITLE, at: t.hkDepart }] },
    { credential_id: "fx-cr-ferry", kind: "transport_ticket", label: "船票 / 车票", status: "used", number: `TK-${year(t.macauDepart)}-DEMO06`, issued_at: t.macauDepart, title: FERRY_TITLE, condition: "坐船或火车出行时，按实际成立的行程段签发", private: false, links: [macauTrip, { kind: "leg", ref_id: "fx-leg-macau-ferry", title: FERRY_TITLE, at: t.macauDepart }] },
    ...missingLicense,
    { credential_id: null, kind: "hotel_key", label: "酒店房卡", status: "not_obtained", number: null, issued_at: null, title: null, condition: "在外过夜入住时发放；目前的旅程都是当天往返，暂未开放", private: false, links: [] },
  ];
}

function ledger(): LedgerEntry[] {
  const t = moments();
  return [
    { tx_id: "fx-tx-job-1", type: "web_job_income", delta: 50, reason: "街角咖啡店帮工的工钱", created_at: atMin(-120), ref_kind: "journey", ref_id: "fx-job-journey-1" },
    { tx_id: "fx-tx-fee-hk", type: "web_travel_fee", delta: -30, reason: "「去香港（演示）」的旅费", created_at: t.hkDepart, ref_kind: "journey", ref_id: "fx-trip-hk" },
    { tx_id: "fx-tx-welcome", type: "web_reward", delta: 100, reason: "入住欢迎星币（每个家一次，不可交易）", created_at: t.movedIn, ref_kind: "home", ref_id: "fx-home-001" },
  ];
}

function stamps(): PassportStamp[] {
  const t = moments();
  return [
    { city: "香港", stamped_at: t.hkArrive, journey_id: "fx-trip-hk", title: "去香港（演示）" },
    { city: "澳门", stamped_at: t.macauArrive, journey_id: "fx-trip-macau", title: "去澳门（演示）" },
  ];
}

function detailOf(credentialId: string, stage: SchoolDemoStage): CredentialDetail | null {
  const summary = summaries(stage).find((item) => item.credential_id === credentialId);
  if (!summary || !summary.issued_at) return null;
  const name = fixturePet.name;
  const species = SPECIES[fixturePet.species] ?? "小动物";
  const issued = day(summary.issued_at);
  const base: CredentialDetail = { summary, fields: [], balance: null, ledger: [], stamps: [], care_notes: [] };
  const f = (pairs: Array<[string, string]>) => pairs.map(([label, value]) => ({ label, value }));
  switch (summary.kind) {
    case "identity_card":
      return { ...base, fields: f([["名字", name], ["物种", species], ["星球编号", summary.number ?? ""], ["住在", "演示小镇（示意）"], ["入住日期", issued]]) };
    case "bank_card":
      return { ...base, fields: f([["户名", `${name} 的星球账户`], ["卡号", summary.number ?? ""], ["开户日期", issued], ["币种", "星币"]]), balance: fixtureHomeSnapshot().wallet.balance, ledger: ledger() };
    case "care_profile":
      return { ...base, fields: f([["名字", name], ["建档日期", issued]]), care_notes: ["习惯：吃饭前要先闻一闻碗，慢慢来", "叮嘱：打雷时让它先躲一会儿，别硬抱出来"] };
    case "passport":
      return { ...base, fields: f([["名字", name], ["物种", species], ["护照号", summary.number ?? ""], ["签发日期", issued], ["签发地", "演示小镇"]]), stamps: stamps() };
    case "driver_license":
      // 字段照后端 routers/web/credentials.py 的驾驶证写法；成绩是演示值
      return {
        ...base,
        fields: f([
          ["名字", name],
          ["准驾车型", "C（星球小型车）"],
          ["证号", summary.number ?? ""],
          ["初次领取", issued],
          ["成绩", "科一 95 分　科二 90 分　科三 88 分　科四 92 分"],
          ["签发机构", "爪爪驾校（PetSoul 星球交通局）"],
          ["说明", "PetSoul 世界的证件，不代表现实驾驶资格；不能交易或转赠"],
        ]),
      };
    case "boarding_pass":
      return { ...base, fields: f([["承运", "喵航"], ["班次", "Cat105"], ["出发", "演示小镇机场（示意）"], ["到达", "香港机场（示意）"], ["日期", issued], ["座位", "12A"], ["状态", "已使用"]]) };
    case "transport_ticket":
      return { ...base, fields: f([["承运", "海獭轮渡"], ["班次", "Otter08"], ["出发", "中环码头（示意）"], ["到达", "澳门码头（示意）"], ["日期", issued], ["座位", "7C"], ["状态", "已使用"]]) };
    default:
      return base;
  }
}

/** 两份演示工作：一份干完已入账，一份正在干活。状态按演示时钟现算（和后端同一条规则）。 */
function jobs(): JobRecord[] {
  const now = Date.now();
  const status = (starts: string, ends: string) => (now < Date.parse(starts) ? "going" : now < Date.parse(ends) ? "working" : "done");
  const working = { starts: atMin(-40), ends: atMin(180) };
  const done = { starts: atMin(-300), ends: atMin(-120) };
  return [
    { journey_id: "fx-job-journey-2", job_key: "bookstore_helper", title: "旧书店整理书架（演示）", place: "旧书店（示意）", starts_at: working.starts, ends_at: working.ends, status: status(working.starts, working.ends), pay: 40, paid: false },
    { journey_id: "fx-job-journey-1", job_key: "cafe_helper", title: "街角咖啡店帮工（演示）", place: "街角咖啡店（示意）", starts_at: done.starts, ends_at: done.ends, status: status(done.starts, done.ends), pay: 50, paid: true },
  ];
}

export function fixtureLifeService(): LifeService {
  // 和驾校演示服务同一时刻、同一个开关读阶段（建服务时读一次），两边的演示阶段对得上
  const schoolStage = fixtureStageFromUrl();
  return {
    jobs: () => delay(jobs()),
    credentials: () => delay(summaries(schoolStage)),
    credential: (credentialId) => {
      const detail = detailOf(credentialId, schoolStage);
      if (!detail) return Promise.reject(new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这张证件。" }));
      return delay(detail);
    },
  };
}
