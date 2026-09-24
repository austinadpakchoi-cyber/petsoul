/**
 * claude-6c2b · 证件卡包（/life、/credentials/:id）。
 * 已获得的画成卡面、未获得的只是虚线空卡位（写怎样获得，不写号码、不画卡面）；驾照没有时才给“陪 TA 去驾校”；
 * 详情原样显示服务端字段；翻到背面：银行卡收支、护照印章、照护档案的私密提示；打工记录 going ≠ working；
 * fixture 只在演示模式给演示数据；live 请求的路径与参数。照片位永远是 TA 自己的样子，不用名字首字。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { ReactNode } from "react";
import type {
  CharacterIdPhoto,
  CharacterState,
  CredentialDetail,
  CredentialSummary,
  DrivingSchoolStatus,
  HomeSnapshot,
  HouseholdBrief,
  HouseholdPetBrief,
  JobRecord,
  PassportStamp,
  SubjectStatus,
} from "@/shared/contracts";
import { useSchoolStatus } from "@/features/driving_school/hooks";
import type { ApiClient } from "@/shared/api/client";
import { ApiError } from "@/shared/api/errors";
import { createQueryClient, queryKeys } from "@/shared/query/queryClient";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { petPortraitUrl } from "@/features/pets/PetPortrait";
import lifeModule from "@/features/life/module";
import { WalletPage } from "@/features/life/WalletPage";
import { CredentialPage } from "@/features/life/CredentialPage";
import { coverAvatarIsAi, coverAvatarUrl, credentialPhotoIsAi, credentialPhotoUrl } from "@/features/life/parts";

const mode = vi.hoisted(() => ({ value: "live" as "live" | "fixture" }));
vi.mock("@/shared/config/env", () => ({
  env: {
    get dataMode() {
      return mode.value;
    },
    isDev: false,
    apiBase: "/api/v1/web",
  },
}));

afterEach(() => {
  cleanup();
  mode.value = "live";
});

const PHOTO = "/api/v1/web/media/pets/pet-1/photo";

function petBrief(over: Partial<HouseholdPetBrief> = {}): HouseholdPetBrief {
  return { pet_id: "pet-1", name: "栗子", species: "dog", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-08-01T04:00:00Z", added_by_you: true, ...over };
}

function households(pet: HouseholdPetBrief): HouseholdBrief[] {
  return [{ household_id: "hh-1", name: "我们的家", home_id: "home-1", role: "admin", home_activated: true, member_count: 1, pets: [pet] }];
}

function homeFor(pet: HouseholdPetBrief, generated = false): HomeSnapshot {
  const base = fixtureHomeSnapshot();
  return { ...base, pet: { ...base.pet, pet_id: pet.pet_id, name: pet.name, species: pet.species, photo_url: pet.photo_url, photo_generated: generated }, data_origin: "live" };
}

const summary = (over: Partial<CredentialSummary>): CredentialSummary => ({
  credential_id: null,
  kind: "identity_card",
  label: "星球居民证",
  status: "active",
  number: null,
  issued_at: null,
  title: null,
  condition: "入住星球时签发",
  private: false,
  links: [],
  ...over,
});

const ID_CARD = summary({ credential_id: "cr-id", kind: "identity_card", label: "星球居民证", number: "PS-ID-2026-ABCDEF", issued_at: "2026-08-01T04:00:00Z", title: "星球居民证" });
const BANK = summary({ credential_id: "cr-bank", kind: "bank_card", label: "星球银行卡", number: "PSB-2026-GHJKLM", issued_at: "2026-08-01T04:00:00Z", title: "星球银行卡", condition: "入住时开户；就是 TA 的钱包账户，工资和旅费都记在这里" });
const HOTEL_MISSING = summary({ kind: "hotel_key", label: "酒店房卡", status: "not_obtained", condition: "在外过夜入住时发放；目前的旅程都是当天往返，暂未开放" });
const LICENSE_MISSING = summary({ kind: "driver_license", label: "爪爪驾驶证", status: "not_obtained", condition: "在爪爪驾校通过四科考试后签发（科目一到科目四）" });

function detailOf(over: Partial<CredentialDetail> & { summary: CredentialSummary }): CredentialDetail {
  return { fields: [], balance: null, ledger: [], stamps: [], care_notes: [], ...over };
}

type Life = ServiceMap["life"];

function strictServices(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

const ID_PHOTO = "/api/v1/web/media/pets/pet-1/id-photo?rev=3";

function characterState(idPhoto: Partial<CharacterIdPhoto> | null): CharacterState {
  return {
    pet_id: "pet-1",
    status: "absent",
    active: null,
    candidate: null,
    can_regenerate: false,
    blocked_reason: null,
    id_photo: idPhoto
      ? { status: "absent", source: null, url: null, avatar_url: null, width: null, height: null, content_sha256: null, reference_version: null, revision: null, reason: null, task_id: null, ...idPhoto }
      : null,
  };
}

type CharacterFn = (petId: string, signal?: AbortSignal) => Promise<CharacterState>;
/** meta 里 character.state 的能力状态；"missing" 表示 meta 里根本没有这一项。 */
type CharacterCapability = "available" | "not_implemented" | "missing";

function metaWith(capability: CharacterCapability) {
  return {
    api_prefix: "/api/v1/web",
    contract_version: "test",
    server_time: "2026-09-24T04:00:00Z",
    backend_version: "test",
    data_origin: "live",
    auth_methods_available: [],
    applied_migrations: [],
    capabilities: capability === "missing" ? [] : [{ key: "character.state", status: capability, module: "character", note: null }],
  };
}

type SchoolStatusFn = (petId?: string | null, signal?: AbortSignal) => Promise<DrivingSchoolStatus>;

function renderLive(
  entry: string,
  life: Partial<Life>,
  options: {
    pet?: HouseholdPetBrief;
    generated?: boolean;
    character?: CharacterFn;
    capability?: CharacterCapability;
    school?: SchoolStatusFn;
    extra?: ReactNode;
    client?: QueryClient;
  } = {},
) {
  const pet = options.pet ?? petBrief();
  const client = options.client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const services = strictServices({
    households: { list: async () => households(pet) },
    world: { home: async () => homeFor(pet, options.generated) },
    platform: { meta: async () => metaWith(options.capability ?? "available") },
    pets: { character: options.character ?? (async () => characterState(null)) },
    // 默认驾校服务读不到：驾照空卡位照原来的样子
    driving: {
      status:
        options.school ??
        (async () => {
          throw new ApiError({ kind: "http", status: 503, code: "UPSTREAM_UNAVAILABLE", message: "驾校暂时读不到" });
        }),
    },
    life: {
      credentials: async () => [],
      jobs: async () => [],
      credential: async () => {
        throw new Error("no detail");
      },
      ...life,
    },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <MemoryRouter initialEntries={[entry]}>
          <HouseholdProvider userId="u-1">
            <Routes>
              <Route path="/life" element={<WalletPage />} />
              <Route path="/credentials/:credentialId" element={<CredentialPage />} />
              <Route path="/school" element={<p>驾校首页</p>} />
            </Routes>
            {options.extra}
          </HouseholdProvider>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { ...view, client };
}

const NUMBER_LIKE = /PS-ID|PSB-|PSP-|PAW-DL|\b(?:BP|TK|RK)-\d{4}|-20\d\d-/;

describe("卡包：已获得画成卡面，未获得只是虚线空卡位", () => {
  it("已获得的是能点开的小卡面（带编号）；未获得的排在最后，只写怎样获得，没有号码、没有卡面、没有照片", async () => {
    // 服务端把一个未获得的放在了中间：前端也要把它挪到最后
    renderLive("/life", { credentials: async () => [ID_CARD, HOTEL_MISSING, BANK, LICENSE_MISSING] });
    const cards = await screen.findAllByTestId("wallet-card");
    expect(cards).toHaveLength(2);
    const idLink = cards[0].closest("a");
    expect(idLink?.getAttribute("href")).toBe("/credentials/cr-id");
    expect(cards[0].textContent).toContain("星球居民证");
    expect(cards[0].textContent).toContain("PS-ID-2026-ABCDEF");
    expect(cards[1].closest("a")?.getAttribute("href")).toBe("/credentials/cr-bank");

    const slots = screen.getAllByTestId("wallet-slot");
    expect(slots.map((slot) => slot.getAttribute("data-kind"))).toEqual(["hotel_key", "driver_license"]);
    for (const slot of slots) {
      expect(slot.textContent).not.toMatch(NUMBER_LIKE);
      expect(slot.querySelector(".ps-mini, .ps-idcard, [data-testid='id-photo'], [data-testid='wallet-card']")).toBeNull();
      expect(slot.querySelector("a[href^='/credentials/']")).toBeNull();
      expect(slot.textContent).toContain("还没有");
    }
    expect(slots[0].textContent).toContain(HOTEL_MISSING.condition);
    expect(slots[1].textContent).toContain(LICENSE_MISSING.condition);
    // 所有卡面都在所有空卡位之前
    expect(cards[1].compareDocumentPosition(slots[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // 卡包封面：宠物名 + 已有几张
    expect(screen.getByTestId("wallet-cover").textContent).toContain("栗子");
    expect(screen.getByTestId("wallet-cover").textContent).toContain("2 张证件");
    // live 不挂演示标记
    expect(screen.queryByText("演示数据")).toBeNull();
  });

  it("只有驾照还没有时，驾照空卡位里才有“陪 TA 去驾校”，点进去是 /school", async () => {
    renderLive("/life", { credentials: async () => [ID_CARD, LICENSE_MISSING, HOTEL_MISSING] });
    const slots = await screen.findAllByTestId("wallet-slot");
    const license = slots.find((slot) => slot.getAttribute("data-kind") === "driver_license")!;
    const hotel = slots.find((slot) => slot.getAttribute("data-kind") === "hotel_key")!;
    const go = within(license).getByRole("link", { name: "陪 TA 去驾校" });
    expect(go.getAttribute("href")).toBe("/school");
    expect(within(hotel).queryByRole("link")).toBeNull();
    expect(screen.getAllByText("陪 TA 去驾校")).toHaveLength(1);
    fireEvent.click(go);
    expect(await screen.findByText("驾校首页")).toBeTruthy();
  });

  it("驾照已经有了：没有“陪 TA 去驾校”；只有房卡没有时也没有", async () => {
    const license = summary({ credential_id: "cr-dl", kind: "driver_license", label: "爪爪驾驶证", number: "PAW-DL-2026-QRSTUV", issued_at: "2026-09-01T04:00:00Z", title: "PetSoul · 爪爪驾驶证 · 小型车（C）" });
    renderLive("/life", { credentials: async () => [ID_CARD, license, HOTEL_MISSING] });
    expect(await screen.findAllByTestId("wallet-card")).toHaveLength(2);
    expect(screen.getAllByTestId("wallet-slot")).toHaveLength(1);
    expect(screen.queryByText("陪 TA 去驾校")).toBeNull();
    expect(screen.queryByText("去驾校看看")).toBeNull();
  });

  it("驾校那边已经在办（in_progress、还没有证件号）：是“去驾校看看”，不是“陪 TA 去驾校”", async () => {
    renderLive("/life", { credentials: async () => [ID_CARD, { ...LICENSE_MISSING, status: "in_progress" }] });
    const slot = await screen.findByTestId("wallet-slot");
    expect(within(slot).getByRole("link", { name: "去驾校看看" }).getAttribute("href")).toBe("/school");
    expect(screen.queryByText("陪 TA 去驾校")).toBeNull();
    expect(slot.textContent).toContain("办理中");
    expect(slot.textContent).not.toMatch(NUMBER_LIKE);
  });
});

describe("单张证件：原样显示服务端字段，照片位是 TA 自己的样子", () => {
  const FIELDS = [
    { label: "名字", value: "栗子" },
    { label: "物种", value: "狗" },
    { label: "星球编号", value: "PS-ID-2026-ABCDEF" },
    { label: "住在", value: "香港 · 深水埗" },
    { label: "入住日期", value: "2026-08-01" },
  ];

  it("字段的标签与内容按服务端顺序原样排上卡面；编号、日期已在字段里时不再重复写", async () => {
    renderLive("/credentials/cr-id", { credentials: async () => [ID_CARD, BANK], credential: async () => detailOf({ summary: ID_CARD, fields: FIELDS }) }, { pet: petBrief({ photo_url: PHOTO }) });
    const front = await screen.findByTestId("cred-front");
    const shown = within(front)
      .getAllByTestId("cred-field")
      .map((field) => [within(field).getByTestId("field-label").textContent, within(field).getByTestId("field-value").textContent]);
    expect(shown).toEqual(FIELDS.map((field) => [field.label, field.value]));
    expect(within(front).getAllByText("PS-ID-2026-ABCDEF")).toHaveLength(1);
    expect(within(front).queryByTestId("face-extras")).toBeNull();
    const photo = within(front).getByTestId("id-photo");
    expect(photo.querySelector("img")?.getAttribute("src")).toBe(PHOTO);
    expect(front.textContent).not.toMatch(/二维码|条码|机读/);
    // 和护照同一家族：左上角虚构声明框、PETSOUL REPUBLIC、中英证件名与双语字段标签
    expect(within(front).getByTestId("fiction-box").textContent).toBe("纪念用 · 非真实证件");
    expect(front.textContent).toContain("PETSOUL REPUBLIC");
    expect(front.textContent).toContain("PLANET RESIDENT CARD");
    expect(within(front).getAllByTestId("cred-field")[0].querySelector("dt small")?.textContent).toBe("Name");
    expect(screen.getByRole("button", { name: /翻到背面/ })).toBeTruthy();
  });

  it("护照资料页：抬头条与声明框；护照号挪进抬头（标签用服务端原文）；只显示服务端给的字段；签名栏空着；代号行只由真实数据拼成", async () => {
    const passport = summary({ credential_id: "cr-pp", kind: "passport", label: "护照", number: "PSP-2026-NPQRST", issued_at: "2026-09-03T04:00:00Z", title: "PetSoul 星球护照" });
    const fields = [
      { label: "名字", value: "栗子" },
      { label: "物种", value: "狗" },
      { label: "护照号", value: "PSP-2026-NPQRST" },
      { label: "签发日期", value: "2026-09-03" },
      { label: "签发地", value: "香港" },
      { label: "爱好", value: "追泡泡" },
    ];
    renderLive("/credentials/cr-pp", { credentials: async () => [passport], credential: async () => detailOf({ summary: passport, fields }) });
    const front = await screen.findByTestId("cred-front");
    expect(within(front).getByTestId("fiction-box").textContent).toBe("纪念用 · 非真实证件");
    for (const text of ["宠物灵魂护照", "PETSOUL PASSPORT", "PETSOUL REPUBLIC", "PETS", "PSR"]) expect(front.textContent).toContain(text);
    const number = within(front).getByTestId("passport-number");
    expect(number.querySelector("dt")?.textContent).toContain("护照号");
    expect(number.querySelector("dd")?.textContent).toBe("PSP-2026-NPQRST");
    // 正文：护照号之外的字段按服务端顺序原样排；认得的标签才有英文，认不出的不猜
    const body = within(front).getAllByTestId("cred-field");
    expect(body.map((field) => within(field).getByTestId("field-label").textContent)).toEqual(["名字", "物种", "签发日期", "签发地", "爱好"]);
    expect(body.map((field) => field.querySelector("dt small")?.textContent ?? null)).toEqual(["Name", "Species", "Date of issue", "Place of issue", null]);
    // 参考样式里的典型字段，服务端没给就不出现
    expect(front.textContent).not.toMatch(/出生日期|出生地|国籍|性别|有效期至|品种/);
    // 主人签名：服务端没给签名，只有栏位没有名字
    expect(within(front).getByTestId("owner-signature").textContent).toBe("主人签名 Owner's signature");
    // 代号行：护照号去掉连字符 + 本地签发日期 YYMMDD + 物种代码，PSR 为虚构代号，每行 30 个字符
    const d = new Date("2026-09-03T04:00:00Z");
    const yymmdd = `${String(d.getFullYear()).slice(2)}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
    const lines = [...within(front).getByTestId("passport-mrz").querySelectorAll("span")].map((line) => line.textContent ?? "");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toBe("P<PSR<DOG<<PETSOUL".padEnd(30, "<"));
    expect(lines[1]).toBe(`PSP2026NPQRST<${yymmdd}`.padEnd(30, "<"));
    // 照片上压的圆章：签发地 + 签发日期（都来自服务端）
    expect(front.querySelector(".ps-passport-data__seal")?.textContent).toContain("香港");
  });

  it("证件照统一由 credentialPhotoUrl 取：没有可用的证件照时有照片用照片，live 没有照片为空（爪印占位），不回退到名字首字", () => {
    const base = { photoGenerated: false, idPhoto: null };
    expect(credentialPhotoUrl({ ...base, photoUrl: PHOTO })).toBe(PHOTO);
    expect(credentialPhotoUrl({ ...base, photoUrl: null })).toBeNull();
    mode.value = "fixture";
    expect(credentialPhotoUrl({ ...base, photoUrl: null })).toBe(petPortraitUrl(null));
    expect(credentialPhotoUrl({ ...base, photoUrl: null })).toBeTruthy();
  });

  it("证件照规则：id_photo 是 ready 且有 url 才用它（优先于 photo_url）；queued / running / failed / unknown / absent，或 ready 但 url 为空，都退回 photo_url", () => {
    const id = (over: Partial<CharacterIdPhoto>) => characterState(over).id_photo ?? null;
    const pet = (idPhoto: CharacterIdPhoto | null, photoGenerated = false) => ({ photoUrl: PHOTO, photoGenerated, idPhoto });
    expect(credentialPhotoUrl(pet(id({ status: "ready", source: "generated", url: ID_PHOTO })))).toBe(ID_PHOTO);
    expect(credentialPhotoUrl(pet(id({ status: "ready", source: "companion_portrait", url: ID_PHOTO })))).toBe(ID_PHOTO);
    for (const status of ["queued", "running", "failed", "unknown", "absent"] as const) {
      expect(credentialPhotoUrl(pet(id({ status, url: null }))), status).toBe(PHOTO);
      // 不是 ready 时，即使意外带了地址也不用
      expect(credentialPhotoUrl(pet(id({ status, url: ID_PHOTO }))), `${status}+url`).toBe(PHOTO);
    }
    expect(credentialPhotoUrl(pet(id({ status: "ready", url: null })))).toBe(PHOTO);
    expect(credentialPhotoUrl(pet(null))).toBe(PHOTO);
    // “AI 生成”角标：用上证件照一律标；没用上时，照片是生成的形象才标
    expect(credentialPhotoIsAi(pet(id({ status: "ready", source: "generated", url: ID_PHOTO }), false))).toBe(true);
    expect(credentialPhotoIsAi(pet(id({ status: "ready", url: null }), false))).toBe(false);
    expect(credentialPhotoIsAi(pet(id({ status: "failed", url: null }), true))).toBe(true);
    expect(credentialPhotoIsAi(pet(null, false))).toBe(false);
    expect(credentialPhotoIsAi({ photoUrl: null, photoGenerated: true, idPhoto: null })).toBe(false);
  });

  it("页面上：证件照 ready 时照片位用证件照并标“AI 生成”；读的是 pets.character（和小窝同一个查询键）", async () => {
    const character = vi.fn<CharacterFn>(async () => characterState({ status: "ready", source: "generated", url: ID_PHOTO, width: 600, height: 800 }));
    const { client } = renderLive(
      "/credentials/cr-id",
      { credentials: async () => [ID_CARD], credential: async () => detailOf({ summary: ID_CARD, fields: FIELDS }) },
      { pet: petBrief({ photo_url: PHOTO }), character },
    );
    const front = await screen.findByTestId("cred-front");
    const photo = within(front).getByTestId("id-photo");
    await within(photo).findByText("AI 生成");
    expect(photo.querySelector("img")?.getAttribute("src")).toBe(ID_PHOTO);
    expect(character).toHaveBeenCalledWith("pet-1", expect.anything());
    expect(client.getQueryData<CharacterState>(queryKeys.characterFor("u-1", "pet-1"))?.id_photo?.url).toBe(ID_PHOTO);
  });

  it("页面上：证件照还在画（queued、url 为空）时退回 photo_url，不标 AI；读角色状态出错时照常显示、同样退回", async () => {
    renderLive(
      "/credentials/cr-id",
      { credentials: async () => [ID_CARD], credential: async () => detailOf({ summary: ID_CARD, fields: FIELDS }) },
      { pet: petBrief({ photo_url: PHOTO }), character: async () => characterState({ status: "queued", url: null }) },
    );
    let photo = within(await screen.findByTestId("cred-front")).getByTestId("id-photo");
    expect(photo.querySelector("img")?.getAttribute("src")).toBe(PHOTO);
    expect(photo.textContent).toBe("");
    cleanup();

    renderLive(
      "/credentials/cr-id",
      { credentials: async () => [ID_CARD], credential: async () => detailOf({ summary: ID_CARD, fields: FIELDS }) },
      {
        pet: petBrief({ photo_url: PHOTO }),
        character: async () => {
          throw new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "读不到" });
        },
      },
    );
    photo = within(await screen.findByTestId("cred-front")).getByTestId("id-photo");
    expect(photo.querySelector("img")?.getAttribute("src")).toBe(PHOTO);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("字段里没有的编号与签发日期补在卡面上（票据）", async () => {
    const ticket = summary({ credential_id: "cr-bp", kind: "boarding_pass", label: "登机牌", status: "used", number: "BP-2026-WXYZ23", issued_at: "2026-09-03T04:00:00Z", title: "动物世界交通 喵航 香港 → 东京" });
    const fields = [{ label: "承运", value: "喵航" }, { label: "班次", value: "Cat105" }, { label: "日期", value: "2026-09-02" }, { label: "状态", value: "已使用" }];
    renderLive("/credentials/cr-bp", { credentials: async () => [ticket], credential: async () => detailOf({ summary: ticket, fields }) });
    const front = await screen.findByTestId("cred-front");
    const extras = within(front).getByTestId("face-extras");
    expect(extras.textContent).toContain("BP-2026-WXYZ23");
    expect(extras.textContent).toContain("签发");
    fireEvent.click(screen.getByRole("button", { name: /翻到背面/ }));
    const back = screen.getByTestId("cred-back");
    const stub = within(back).getByTestId("ticket-stub");
    expect(stub.textContent).toContain("BP-2026-WXYZ23");
    expect(stub.textContent).toContain("已使用");
    expect(back.textContent).toContain(ticket.title);
  });

  it("没有照片：live 下是中性爪印占位，不写名字首字；生成的形象标“AI 生成”", async () => {
    renderLive("/credentials/cr-id", { credentials: async () => [ID_CARD], credential: async () => detailOf({ summary: ID_CARD, fields: FIELDS }) });
    const photo = within(await screen.findByTestId("cred-front")).getByTestId("id-photo");
    expect(photo.querySelector("img")).toBeNull();
    expect(photo.querySelector("svg")).toBeTruthy();
    expect(photo.textContent).toBe("");
    cleanup();

    renderLive("/credentials/cr-id", { credentials: async () => [ID_CARD], credential: async () => detailOf({ summary: ID_CARD, fields: FIELDS }) }, { pet: petBrief({ photo_url: PHOTO }), generated: true });
    const generated = within(await screen.findByTestId("cred-front")).getByTestId("id-photo");
    expect(generated.querySelector("img")?.getAttribute("src")).toBe(PHOTO);
    expect(await within(generated).findByText("AI 生成")).toBeTruthy();
  });

  it("不在当前宠物卡包里的证件：不把当前宠物的照片放上去", async () => {
    const credential = vi.fn(async () => detailOf({ summary: { ...ID_CARD, credential_id: "cr-other" }, fields: FIELDS }));
    renderLive("/credentials/cr-other", { credentials: async () => [ID_CARD], credential });
    expect(await screen.findByText("这张证件不在栗子的卡包里")).toBeTruthy();
    expect(screen.queryByTestId("cred-front")).toBeNull();
    expect(screen.getByRole("link", { name: "回到卡包" }).getAttribute("href")).toBe("/life");
  });

  it("相关经历：能确定页面的才是链接（驾校 → /school，到访 → /visits/…），其余只写文字", async () => {
    const withLinks = {
      ...ID_CARD,
      links: [
        { kind: "exam", ref_id: "sess-9", title: "爪爪驾校四科全部通过", at: "2026-09-01T04:00:00Z" },
        { kind: "visit", ref_id: "v 1", title: "在咖啡店坐了一会儿", at: "2026-09-02T04:00:00Z" },
        { kind: "journey", ref_id: "j-1", title: "去澳门看看", at: "2026-09-03T04:00:00Z" },
      ],
    };
    renderLive("/credentials/cr-id", { credentials: async () => [withLinks], credential: async () => detailOf({ summary: withLinks, fields: FIELDS }) });
    const items = await screen.findAllByTestId("cred-link");
    expect(items.map((item) => item.querySelector("a")?.getAttribute("href") ?? null)).toEqual(["/school", "/visits/v%201", null]);
    expect(items[2].textContent).toContain("去澳门看看");
    expect(items[2].textContent).toContain("旅程");
    expect(screen.getByRole("heading", { name: "相关经历" })).toBeTruthy();
    // 不出现原始代码
    expect(items.map((item) => item.textContent).join("")).not.toMatch(/exam|visit|journey|sess-9|j-1/);
  });
});

describe("翻到背面：银行卡、护照、照护档案", () => {
  it("银行卡：余额与收支记录（收入 +、支出 −），不露内部的类型与关联编号；能翻回正面", async () => {
    const detail = detailOf({
      summary: BANK,
      fields: [{ label: "户名", value: "栗子 的星球账户" }, { label: "卡号", value: "PSB-2026-GHJKLM" }],
      balance: 88,
      ledger: [
        { tx_id: "t1", type: "web_travel_fee", delta: -40, reason: "「去澳门看看」的旅费", created_at: "2026-09-01T04:00:00Z", ref_kind: "journey", ref_id: "j-secret-1" },
        { tx_id: "t2", type: "web_job_income", delta: 30, reason: "咖啡店帮工的工钱", created_at: "2026-09-02T04:00:00Z", ref_kind: "journey", ref_id: "j-secret-2" },
      ],
    });
    renderLive("/credentials/cr-bank", { credentials: async () => [ID_CARD, BANK], credential: async () => detail });
    await screen.findByTestId("cred-front");
    expect(screen.queryByTestId("cred-back")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "翻到背面" }));
    const back = screen.getByTestId("cred-back");
    expect(within(back).getByTestId("bank-balance").textContent).toBe("88");
    const rows = within(back).getAllByTestId("ledger-row");
    expect(rows.map((row) => row.textContent)).toEqual([expect.stringMatching(/咖啡店帮工的工钱.*\+30$/), expect.stringMatching(/「去澳门看看」的旅费.*−40$/)]);
    expect(back.textContent).not.toMatch(/j-secret|web_job_income|web_travel_fee|journey/);
    expect(screen.queryByTestId("cred-front")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "翻回正面" }));
    expect(screen.getByTestId("cred-front")).toBeTruthy();
  });

  it("护照：可翻页的小本，章上沿圆弧写城市与盖章日期（SVG textPath），按时间从早到晚", async () => {
    const at = (day: number) => `2026-09-${String(day).padStart(2, "0")}T04:00:00Z`;
    const stamps: PassportStamp[] = [
      { city: "东京", stamped_at: at(9), journey_id: "j-5", title: "去东京" },
      { city: "澳门", stamped_at: at(3), journey_id: "j-1", title: "去澳门看看" },
      { city: "香港", stamped_at: at(4), journey_id: "j-2", title: "进城" },
      { city: "台北", stamped_at: at(6), journey_id: "j-3", title: "去台北" },
      { city: "首尔", stamped_at: at(7), journey_id: "j-4", title: "去首尔" },
    ];
    const passport = summary({ credential_id: "cr-pp", kind: "passport", label: "护照", number: "PSP-2026-NPQRST", issued_at: at(3), title: "PetSoul 星球护照" });
    renderLive("/credentials/cr-pp", { credentials: async () => [passport], credential: async () => detailOf({ summary: passport, fields: [{ label: "护照号", value: "PSP-2026-NPQRST" }], stamps }) });
    await screen.findByTestId("cred-front");
    fireEvent.click(screen.getByRole("button", { name: "翻到背面" }));
    expect(screen.getByText("封面")).toBeTruthy();
    expect(screen.getByText("已盖 5 枚纪念章，翻开看看")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "翻开" }));
    const local = (iso: string) => {
      const d = new Date(iso);
      return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
    };
    let shown = screen.getAllByTestId("passport-stamp");
    expect(shown.map((stamp) => within(stamp).getByTestId("stamp-city").textContent)).toEqual(["澳门", "香港", "台北", "首尔"]);
    expect(shown.map((stamp) => within(stamp).getByTestId("stamp-date").textContent)).toEqual([at(3), at(4), at(6), at(7)].map(local));
    for (const stamp of shown) {
      expect(stamp.querySelectorAll("textPath")).toHaveLength(2);
      expect(stamp.textContent).not.toMatch(/二维码|条码/);
    }
    expect(screen.getByText("纪念章 1 / 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    shown = screen.getAllByTestId("passport-stamp");
    expect(shown.map((stamp) => within(stamp).getByTestId("stamp-city").textContent)).toEqual(["东京"]);
    expect((screen.getByRole("button", { name: "下一页" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("照护档案：私密提示 + 原样的叮嘱", async () => {
    const care = summary({ credential_id: "cr-care", kind: "care_profile", label: "照护档案", number: "PS-CARE-2026-ABCDEF", issued_at: "2026-08-01T04:00:00Z", title: "照护档案", private: true });
    const notes = ["习惯：打雷时躲进衣柜", "叮嘱：出门前摸摸头"];
    renderLive("/credentials/cr-care", { credentials: async () => [care], credential: async () => detailOf({ summary: care, fields: [{ label: "名字", value: "栗子" }], care_notes: notes }) });
    expect((await screen.findByTestId("cred-front")).textContent).toContain("私密");
    fireEvent.click(screen.getByRole("button", { name: "翻到背面" }));
    expect(screen.getByTestId("care-private").textContent).toContain("只有你能看到");
    expect(screen.getAllByTestId("care-note").map((note) => note.textContent)).toEqual(notes);
  });
});

describe("打工记录：只按服务端状态说话", () => {
  const job = (over: Partial<JobRecord>): JobRecord => ({ journey_id: "j", job_key: "cafe", title: "咖啡店帮工", place: "街角咖啡店", starts_at: "2026-09-24T06:00:00Z", ends_at: "2026-09-24T09:00:00Z", status: "done", pay: 30, paid: true, ...over });

  it("/life?tab=jobs 直达；去上班的路上 ≠ 在干活；到账写“已进银行卡”，没到账写“收工后到账”", async () => {
    renderLive("/life?tab=jobs", {
      credentials: async () => [ID_CARD, BANK],
      jobs: async () => [
        job({ journey_id: "j1", status: "going", paid: false, title: "书店整理书架" }),
        job({ journey_id: "j2", status: "working", paid: false, title: "面包店帮忙" }),
        job({ journey_id: "j3", status: "done", paid: true }),
      ],
    });
    const rows = await screen.findAllByTestId("job-row");
    expect(screen.getByRole("tab", { name: "打工记录" }).getAttribute("aria-selected")).toBe("true");
    const status = rows.map((row) => within(row).getByTestId("job-status").textContent);
    expect(status).toEqual(["去上班的路上", "正在干活", "干完了"]);
    expect(rows[0].textContent).not.toMatch(/在打工|正在干活|在干活/);
    expect(rows.map((row) => within(row).getByTestId("job-pay").textContent)).toEqual(["收工后到账", "收工后到账", "已进银行卡"]);
    expect(screen.getByRole("link", { name: "看银行卡" }).getAttribute("href")).toBe("/credentials/cr-bank");
    expect(screen.queryByTestId("wallet-card")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "证件" }));
    expect(await screen.findAllByTestId("wallet-card")).toHaveLength(2);
    expect(screen.queryByTestId("job-row")).toBeNull();
  });
});

describe("服务：fixture 只在演示模式给演示数据；live 只请求真实接口", () => {
  const signal = new AbortController().signal;

  it("fixture：8 种证件（6 张演示卡、驾照与房卡未获得）、护照两个章、两份演示工作；不碰网络", async () => {
    const request = vi.fn(async () => {
      throw new Error("fixture 不应请求网络");
    });
    const services = buildServices([lifeModule], { mode: "fixture", api: { request, base: "/api/v1/web" } as unknown as ApiClient });
    const list = await services.life.credentials("whatever");
    expect(list.map((item) => item.kind)).toEqual(["identity_card", "bank_card", "care_profile", "passport", "boarding_pass", "transport_ticket", "driver_license", "hotel_key"]);
    // 证件名跟后端 CATALOG：“星球居民证”（kind 与 PS-ID 编号前缀不变）
    expect(list[0]).toMatchObject({ kind: "identity_card", label: "星球居民证", title: "星球居民证" });
    expect(list[0].number).toMatch(/^PS-ID-/);
    const obtained = list.filter((item) => item.credential_id);
    expect(obtained).toHaveLength(6);
    for (const item of obtained) expect(item.number).toMatch(/-DEMO0\d$/);
    expect(list.filter((item) => !item.credential_id).map((item) => [item.kind, item.status, item.number])).toEqual([
      ["driver_license", "not_obtained", null],
      ["hotel_key", "not_obtained", null],
    ]);
    expect(list.find((item) => item.kind === "care_profile")?.private).toBe(true);
    const passport = await services.life.credential("fx-cr-passport");
    expect(passport.stamps.map((stamp) => stamp.city)).toEqual(["香港", "澳门"]);
    const bank = await services.life.credential("fx-cr-bank");
    expect(bank.ledger).toHaveLength(3);
    expect(typeof bank.balance).toBe("number");
    const care = await services.life.credential("fx-cr-care");
    expect(care.care_notes).toHaveLength(2);
    const jobs = await services.life.jobs("whatever");
    expect(jobs.map((item) => [item.status, item.paid])).toEqual([
      ["working", false],
      ["done", true],
    ]);
    await expect(services.life.credential("cr-not-there")).rejects.toMatchObject({ code: "NOT_FOUND" });
    expect(request).not.toHaveBeenCalled();
  });

  it("live：请求 /credentials、/jobs（带 pet_id）与 /credentials/{id}（编码），返回什么就是什么，失败也不退回演示数据", async () => {
    const request = vi.fn(async () => [] as unknown);
    const services = buildServices([lifeModule], { mode: "live", api: { request, base: "/api/v1/web" } as unknown as ApiClient });
    expect(await services.life.credentials("pet-1", signal)).toEqual([]);
    expect(request).toHaveBeenLastCalledWith("/credentials", { query: { pet_id: "pet-1" }, signal });
    expect(await services.life.jobs("pet-1", signal)).toEqual([]);
    expect(request).toHaveBeenLastCalledWith("/jobs", { query: { pet_id: "pet-1" }, signal });
    await services.life.credential("cr/1?x", signal);
    expect(request).toHaveBeenLastCalledWith("/credentials/cr%2F1%3Fx", { signal });

    const failing = buildServices([lifeModule], {
      mode: "live",
      api: {
        request: async () => {
          throw new Error("offline");
        },
        base: "/api/v1/web",
      } as unknown as ApiClient,
    });
    await expect(failing.life.credentials("pet-1")).rejects.toThrow("offline");
  });

  it("fixture 页面：演示宠物、演示标记、演示卡面与空卡位；演示模式不查能力、不读角色状态，照片位和封面头像都是演示小灰猫（不是首字）", async () => {
    mode.value = "fixture";
    const fixtureLife = buildServices([lifeModule], { mode: "fixture", api: { request: vi.fn(), base: "" } as unknown as ApiClient }).life;
    const character = vi.fn(async () => {
      throw ApiError.capability("character.state", "演示模式没有专属世界形象。");
    });
    const meta = vi.fn(async () => metaWith("available"));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={strictServices({ households: {}, life: fixtureLife, platform: { meta }, pets: { character }, world: { home: async () => fixtureHomeSnapshot() } })}>
          <MemoryRouter initialEntries={["/life"]}>
            <HouseholdProvider userId={null}>
              <Routes>
                <Route path="/life" element={<WalletPage />} />
              </Routes>
            </HouseholdProvider>
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findAllByTestId("wallet-card", {}, { timeout: 3000 })).toHaveLength(6);
    expect(screen.getAllByTestId("wallet-slot")).toHaveLength(2);
    expect(screen.getByText("演示数据")).toBeTruthy();
    expect(screen.getByTestId("wallet-cover").textContent).toContain(fixtureHomeSnapshot().pet.name);
    const demoCat = petPortraitUrl(null);
    expect(demoCat).toBeTruthy();
    const photo = screen.getAllByTestId("id-photo")[0];
    expect(photo.querySelector("img")?.getAttribute("src")).toBe(demoCat);
    expect(screen.getByText("陪 TA 去驾校")).toBeTruthy();
    // 封面头像：没有证件照头像，照旧 PetPortrait（演示模式没照片时是小灰猫），不标 AI
    const cover = screen.getByTestId("cover-avatar");
    expect(cover.getAttribute("data-source")).toBe("photo");
    expect(cover.querySelector("img")?.getAttribute("src")).toBe(demoCat);
    expect(within(cover).queryByText("AI 生成")).toBeNull();
    // 能力开关只在 live 下查：演示模式既不读 meta，也不读角色状态；卡包照常显示
    expect(meta).not.toHaveBeenCalled();
    expect(character).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getAllByTestId("wallet-card")).toHaveLength(6);
  });
});

describe("证件照的能力开关与封面头像", () => {
  const FIELDS = [
    { label: "名字", value: "栗子" },
    { label: "星球编号", value: "PS-ID-2026-ABCDEF" },
  ];

  it("meta 里 character.state 没开（not_implemented）或根本没有：不发角色状态的读取，照片位退回 photo_url；开着时才读", async () => {
    for (const capability of ["not_implemented", "missing"] as const) {
      const character = vi.fn<CharacterFn>(async () => characterState({ status: "ready", source: "generated", url: ID_PHOTO }));
      renderLive(
        "/credentials/cr-id",
        { credentials: async () => [ID_CARD], credential: async () => detailOf({ summary: ID_CARD, fields: FIELDS }) },
        { pet: petBrief({ photo_url: PHOTO }), character, capability },
      );
      const photo = within(await screen.findByTestId("cred-front")).getByTestId("id-photo");
      // 等 meta 读完、页面稳定后再看：始终没有去读角色状态
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(character, capability).not.toHaveBeenCalled();
      expect(photo.querySelector("img")?.getAttribute("src"), capability).toBe(PHOTO);
      expect(within(photo).queryByText("AI 生成"), capability).toBeNull();
      cleanup();
    }
    // 对照：开着时才读，并用上证件照
    const character = vi.fn<CharacterFn>(async () => characterState({ status: "ready", source: "generated", url: ID_PHOTO }));
    renderLive(
      "/credentials/cr-id",
      { credentials: async () => [ID_CARD], credential: async () => detailOf({ summary: ID_CARD, fields: FIELDS }) },
      { pet: petBrief({ photo_url: PHOTO }), character, capability: "available" },
    );
    const photo = within(await screen.findByTestId("cred-front")).getByTestId("id-photo");
    await waitFor(() => expect(photo.querySelector("img")?.getAttribute("src")).toBe(ID_PHOTO));
    expect(character).toHaveBeenCalledTimes(1);
  });

  it("封面头像：有 id_photo.avatar_url（ready）就用它并标 AI；只有证件照没有裁好的头像（companion_portrait）或能力没开时，照旧 PetPortrait(photo_url)", async () => {
    const AVATAR = "/api/v1/web/media/pets/pet-1/id-photo/avatar?rev=3";
    const cases: Array<{ label: string; character: CharacterFn; capability?: CharacterCapability; src: string; source: string; ai: boolean }> = [
      { label: "ready + avatar_url", character: async () => characterState({ status: "ready", source: "generated", url: ID_PHOTO, avatar_url: AVATAR }), src: AVATAR, source: "id-photo-avatar", ai: true },
      { label: "companion_portrait 没有头像", character: async () => characterState({ status: "ready", source: "companion_portrait", url: PHOTO, avatar_url: null }), src: PHOTO, source: "photo", ai: false },
      { label: "能力没开", character: async () => characterState({ status: "ready", source: "generated", url: ID_PHOTO, avatar_url: AVATAR }), capability: "not_implemented", src: PHOTO, source: "photo", ai: false },
    ];
    for (const item of cases) {
      renderLive("/life", { credentials: async () => [ID_CARD] }, { pet: petBrief({ photo_url: PHOTO }), character: item.character, capability: item.capability });
      await screen.findAllByTestId("wallet-card");
      const cover = screen.getByTestId("cover-avatar");
      await waitFor(() => expect(cover.getAttribute("data-source"), item.label).toBe(item.source));
      if (item.source === "photo") await new Promise((resolve) => setTimeout(resolve, 50));
      expect(cover.getAttribute("data-source"), item.label).toBe(item.source);
      expect(cover.querySelector("img")?.getAttribute("src"), item.label).toBe(item.src);
      expect(Boolean(within(cover).queryByText("AI 生成")), item.label).toBe(item.ai);
      cleanup();
    }
  });

  it("封面头像的 AI 规则照旧：没用上证件照头像时，photo_url 是服务端生成的形象才标", async () => {
    renderLive("/life", { credentials: async () => [ID_CARD] }, { pet: petBrief({ photo_url: PHOTO }), generated: true });
    await screen.findAllByTestId("wallet-card");
    const cover = screen.getByTestId("cover-avatar");
    expect(cover.getAttribute("data-source")).toBe("photo");
    expect(await within(cover).findByText("AI 生成")).toBeTruthy();
    const base = { photoUrl: PHOTO, photoGenerated: false };
    expect(coverAvatarUrl({ idPhoto: characterState({ status: "queued", avatar_url: "/x" }).id_photo ?? null })).toBeNull();
    expect(coverAvatarIsAi({ ...base, idPhoto: null })).toBe(false);
    expect(coverAvatarIsAi({ ...base, idPhoto: characterState({ status: "ready", url: ID_PHOTO, avatar_url: "/a" }).id_photo ?? null })).toBe(true);
  });
});

describe("领证后刷新、同一家族卡面分字段、银行卡照片位", () => {
  it("卡包列表挂在 queryKeys.credentials 前缀下：驾校领证时失效这个前缀，卡包会重新请求", async () => {
    expect(queryKeys.credentials).toEqual(["credentials", "list"]);
    const credentials = vi.fn(async () => [ID_CARD, LICENSE_MISSING]);
    const { client } = renderLive("/life", { credentials });
    await screen.findAllByTestId("wallet-card");
    expect(credentials).toHaveBeenCalledTimes(1);
    expect(client.getQueryData([...queryKeys.credentials, "u-1", "pet-1"])).toBeTruthy();
    // 驾校领证后的失效（driving_school/hooks.ts 的 useInvalidateSchool 用的就是这个键）
    await client.invalidateQueries({ queryKey: queryKeys.credentials });
    await waitFor(() => expect(credentials).toHaveBeenCalledTimes(2));
  });

  it("驾驶证 7 个字段：正面放前 4 个，其余 3 个按原顺序写在背面横线上；一个不少、原样显示", async () => {
    const license = summary({ credential_id: "cr-dl", kind: "driver_license", label: "爪爪驾驶证", number: "PAW-DL-2026-QRSTUV", issued_at: "2026-09-01T04:00:00Z", title: "PetSoul · 爪爪驾驶证 · 小型车（C）" });
    const fields = [
      { label: "名字", value: "栗子" },
      { label: "准驾车型", value: "C（星球小型车）" },
      { label: "证号", value: "PAW-DL-2026-QRSTUV" },
      { label: "初次领取", value: "2026-09-01" },
      { label: "成绩", value: "科一 95 分　科二 90 分　科三 88 分　科四 92 分" },
      { label: "签发机构", value: "爪爪驾校（PetSoul 星球交通局）" },
      { label: "说明", value: "PetSoul 世界的证件，不代表现实驾驶资格；不能交易或转赠" },
    ];
    renderLive("/credentials/cr-dl", { credentials: async () => [license], credential: async () => detailOf({ summary: license, fields }) });
    const pairs = (root: HTMLElement) =>
      within(root)
        .getAllByTestId("cred-field")
        .map((field) => [within(field).getByTestId("field-label").textContent, within(field).getByTestId("field-value").textContent]);
    const front = await screen.findByTestId("cred-front");
    expect(pairs(front)).toEqual(fields.slice(0, 4).map((field) => [field.label, field.value]));
    fireEvent.click(screen.getByRole("button", { name: "翻到背面" }));
    const back = screen.getByTestId("cred-back");
    expect(back.className).toContain("ps-idcard--ruled");
    expect(pairs(back)).toEqual(fields.slice(4).map((field) => [field.label, field.value]));
    // 没有接口数据的准驾类别（陆地 / 水上 / 空中 / 特殊）不画
    expect(back.textContent).not.toMatch(/陆地|水上|空中|特殊/);
  });

  it("星球居民证字段不超过 5 个时全在正面，背面只写编号与签发日期", async () => {
    const fields = [
      { label: "名字", value: "栗子" },
      { label: "物种", value: "狗" },
      { label: "星球编号", value: "PS-ID-2026-ABCDEF" },
      { label: "住在", value: "香港 · 深水埗" },
      { label: "入住日期", value: "2026-08-01" },
    ];
    renderLive("/credentials/cr-id", { credentials: async () => [ID_CARD], credential: async () => detailOf({ summary: ID_CARD, fields }) });
    expect(within(await screen.findByTestId("cred-front")).getAllByTestId("cred-field")).toHaveLength(5);
    fireEvent.click(screen.getByRole("button", { name: "翻到背面" }));
    const back = screen.getByTestId("cred-back");
    expect(within(back).queryAllByTestId("cred-field")).toHaveLength(0);
    expect(within(back).getByTestId("back-info").textContent).toContain("PS-ID-2026-ABCDEF");
  });

  it("银行卡底图左侧是芯片：证件照放在标题条的小圆框里，正文里没有照片框；小卡面也不放照片", async () => {
    const fields = [
      { label: "户名", value: "栗子 的星球账户" },
      { label: "卡号", value: "PSB-2026-GHJKLM" },
    ];
    renderLive("/credentials/cr-bank", { credentials: async () => [BANK], credential: async () => detailOf({ summary: BANK, fields, balance: 1 }) }, { pet: petBrief({ photo_url: PHOTO }) });
    const front = await screen.findByTestId("cred-front");
    const photos = within(front).getAllByTestId("id-photo");
    expect(photos).toHaveLength(1);
    expect(photos[0].className).toContain("ps-idcard__bandphoto");
    expect(photos[0].closest(".ps-idcard__band")).toBeTruthy();
    cleanup();

    renderLive("/life", { credentials: async () => [BANK] });
    const mini = await screen.findByTestId("wallet-card");
    expect(within(mini).queryByTestId("id-photo")).toBeNull();
  });
});

describe("驾照学车中：空卡位里的四科进度（方案 8.2）", () => {
  const LICENSE_LEARNING = summary({ kind: "driver_license", label: "爪爪驾驶证", status: "in_progress", condition: "在爪爪驾校通过四科考试后签发（科目一到科目四）" });
  const TITLES = { s1: "科目一：交规小课堂", s2: "科目二：把小车开稳", s3: "科目三：上路走一走", s4: "科目四：安全文明" } as const;
  const UNTIL = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });

  function subjectRow(subject: keyof typeof TITLES, over: Partial<SubjectStatus>): SubjectStatus {
    return {
      subject,
      title: TITLES[subject],
      theme: "",
      kind: subject === "s1" || subject === "s4" ? "quiz" : "drive",
      state: "available",
      passed_at: null,
      passed_score: null,
      legacy: false,
      round_no: 1,
      attempts_used: 0,
      attempts_left: 2,
      next_attempt: "first",
      cooldown_until: null,
      unlock_hint: null,
      open_session_id: null,
      last_result: null,
      practice_count: 0,
      ...over,
    };
  }

  function schoolStatus(over: Partial<DrivingSchoolStatus>): DrivingSchoolStatus {
    return {
      stage: "enrolled",
      wish_text: null,
      enrolled_at: "2026-09-20T04:00:00Z",
      coach: { name: "龟教练·慢慢", line: "", intro: "" },
      subjects: [],
      open_session: null,
      license: null,
      voucher_available: false,
      ceremony_done: false,
      temperament: "steady",
      rules_version: "test",
      server_time: "2026-09-24T04:00:00Z",
      ...over,
    };
  }

  const tagsOf = async () => (await screen.findAllByTestId("school-subject")).map((tag) => tag.textContent);

  it("四科各一个小标签，说法只按服务端状态：已通过 / 可以约补考 / 冷却到某时 / 未解锁照 unlock_hint 原文；整块点进 /school", async () => {
    const cooldown = "2026-09-30T06:00:00Z";
    const school = vi.fn<SchoolStatusFn>(async () =>
      schoolStatus({
        subjects: [
          subjectRow("s1", { state: "passed", passed_at: "2026-09-21T04:00:00Z", next_attempt: null }),
          subjectRow("s2", { state: "cooldown", cooldown_until: cooldown, next_attempt: null, attempts_left: 0 }),
          subjectRow("s3", { state: "available", next_attempt: "retake", attempts_used: 1, attempts_left: 1 }),
          subjectRow("s4", { state: "locked", unlock_hint: "先通过科目三" }),
        ],
      }),
    );
    renderLive("/life", { credentials: async () => [ID_CARD, LICENSE_LEARNING] }, { school });
    expect(await tagsOf()).toEqual(["科目一：已通过", `科目二：冷却到 ${UNTIL.format(Date.parse(cooldown))}`, "科目三：可以约补考", "科目四：先通过科目三"]);
    const block = screen.getByTestId("school-progress");
    expect(block.tagName).toBe("A");
    expect(block.getAttribute("href")).toBe("/school");
    expect(block.textContent).toContain("去驾校看看");
    // 整块就是入口：里面没有另外的按钮，也没有“陪 TA 去驾校”
    expect(block.querySelector(".ps-wallet-slot__go, a")).toBeNull();
    expect(screen.queryByText("陪 TA 去驾校")).toBeNull();
    fireEvent.click(block);
    expect(await screen.findByText("驾校首页")).toBeTruthy();
  });

  it("可以约考（首次）与在考", async () => {
    renderLive(
      "/life",
      { credentials: async () => [LICENSE_LEARNING] },
      {
        school: async () =>
          schoolStatus({
            subjects: [
              subjectRow("s1", { state: "passed", next_attempt: null }),
              subjectRow("s2", { state: "in_exam", open_session_id: "sess-1" }),
              subjectRow("s3", { state: "available", next_attempt: "first" }),
              subjectRow("s4", { state: "available", next_attempt: null }),
            ],
          }),
      },
    );
    expect(await tagsOf()).toEqual(["科目一：已通过", "科目二：在考", "科目三：可以约考", "科目四：可以约考"]);
  });

  it("license_pending：写“四科都过了，驾照正在签发”，不再列四科", async () => {
    renderLive(
      "/life",
      { credentials: async () => [LICENSE_LEARNING] },
      { school: async () => schoolStatus({ stage: "license_pending", subjects: (["s1", "s2", "s3", "s4"] as const).map((s) => subjectRow(s, { state: "passed", next_attempt: null })) }) },
    );
    expect((await screen.findByTestId("school-line")).textContent).toBe("四科都过了，驾照正在签发");
    expect(screen.queryAllByTestId("school-subject")).toHaveLength(0);
    expect(screen.getByTestId("school-progress").getAttribute("href")).toBe("/school");
  });

  it("想学（wish）还没报名：只写 TA 想学的那句话（wish_text 原文），入口是“陪 TA 去驾校”，不写“可以约考”", async () => {
    renderLive(
      "/life",
      { credentials: async () => [LICENSE_LEARNING] },
      {
        school: async () =>
          schoolStatus({
            stage: "wish",
            wish_text: "我想学会开车，以后换我载你出去玩。",
            enrolled_at: null,
            // 后端报名前也照常算四科（科目一 available），但没报名约不了考试
            subjects: [subjectRow("s1", {}), subjectRow("s2", { state: "locked", unlock_hint: "先通过科目一" })],
          }),
      },
    );
    expect((await screen.findByTestId("school-line")).textContent).toBe("TA 说想学开车：“我想学会开车，以后换我载你出去玩。”");
    const block = screen.getByTestId("school-progress");
    expect(block.textContent).toContain("陪 TA 去驾校");
    expect(block.textContent).not.toContain("可以约考");
    expect(screen.queryAllByTestId("school-subject")).toHaveLength(0);
  });

  it("和驾校用的是同一个查询键：驾校自己的 useSchoolStatus 同时在读，缓存里也只有一条驾校状态查询、只请求一次", async () => {
    function SchoolProbe() {
      useSchoolStatus();
      return null;
    }
    const school = vi.fn<SchoolStatusFn>(async () => schoolStatus({ subjects: [subjectRow("s1", {}), subjectRow("s2", { state: "locked", unlock_hint: "先通过科目一" })] }));
    // 用应用自己的 QueryClient（默认 15 秒内不重读）：驾校先读到的结果，卡包后挂上时直接用缓存
    const { client } = renderLive("/life", { credentials: async () => [LICENSE_LEARNING] }, { school, extra: <SchoolProbe />, client: createQueryClient() });
    await tagsOf();
    const queries = client.getQueryCache().findAll({ queryKey: ["driving"] });
    expect(queries).toHaveLength(1);
    expect(queries[0].queryKey).toEqual(queryKeys.drivingStatusFor("u-1", "pet-1"));
    expect(school).toHaveBeenCalledTimes(1);
  });

  it("驾校服务出错：驾照空卡位照原来的样子（办理中 + 获得条件 + “去驾校看看”），页面不报错", async () => {
    const school = vi.fn<SchoolStatusFn>(async () => {
      throw new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "读不到" });
    });
    renderLive("/life", { credentials: async () => [ID_CARD, LICENSE_LEARNING] }, { school });
    const slot = await screen.findByTestId("wallet-slot");
    await waitFor(() => expect(school).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(slot.textContent).toContain("办理中");
    expect(slot.textContent).toContain(LICENSE_LEARNING.condition);
    expect(within(slot).getByRole("link", { name: "去驾校看看" }).getAttribute("href")).toBe("/school");
    expect(screen.queryByTestId("school-progress")).toBeNull();
    expect(screen.queryAllByTestId("school-subject")).toHaveLength(0);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("字段不够（锁定没给解锁提示、冷却没给截止时间）：不编进度，空卡位照原来的样子", async () => {
    for (const broken of [subjectRow("s2", { state: "locked", unlock_hint: null }), subjectRow("s2", { state: "cooldown", cooldown_until: null, next_attempt: null })]) {
      const school = vi.fn<SchoolStatusFn>(async () => schoolStatus({ subjects: [subjectRow("s1", { state: "passed", next_attempt: null }), broken] }));
      renderLive("/life", { credentials: async () => [LICENSE_LEARNING] }, { school });
      const slot = await screen.findByTestId("wallet-slot");
      await waitFor(() => expect(school).toHaveBeenCalled());
      await new Promise((resolve) => setTimeout(resolve, 30));
      expect(screen.queryByTestId("school-progress"), broken.state).toBeNull();
      expect(within(slot).getByRole("link", { name: "去驾校看看" })).toBeTruthy();
      cleanup();
    }
  });

  it("驾照不在办（还没有 / 已经有了）时不读驾校状态", async () => {
    const school = vi.fn<SchoolStatusFn>(async () => schoolStatus({}));
    renderLive("/life", { credentials: async () => [ID_CARD, LICENSE_MISSING] }, { school });
    await screen.findByTestId("wallet-slot");
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(school).not.toHaveBeenCalled();
  });

  it("演示数据跟着驾校演示阶段走（?school_demo=，整页打开时读一次）：想学 / 已报名是“办理中”，领证后有驾照；不带参数还是“还没有”", async () => {
    const at = (search: string) => {
      window.history.replaceState(null, "", `/life${search}`);
      return buildServices([lifeModule], { mode: "fixture", api: { request: vi.fn(), base: "" } as unknown as ApiClient }).life;
    };
    try {
      for (const stage of ["enrolled", "wish"] as const) {
        const list = await at(`?school_demo=${stage}`).credentials("x");
        const license = list.find((item) => item.kind === "driver_license");
        expect([license?.status, license?.credential_id], stage).toEqual(["in_progress", null]);
      }
      const licensed = at("?school_demo=licensed");
      const list = await licensed.credentials("x");
      const license = list.find((item) => item.kind === "driver_license");
      expect(license?.credential_id).toBe("fx-cr-license");
      expect(license?.number).toMatch(/-DEMO07$/);
      // 顺序照后端：驾照排在护照后、登机牌前；没有的只剩房卡
      expect(list.map((item) => item.kind)).toEqual(["identity_card", "bank_card", "care_profile", "passport", "driver_license", "boarding_pass", "transport_ticket", "hotel_key"]);
      const detail = await licensed.credential("fx-cr-license");
      expect(detail.fields.map((field) => field.label)).toEqual(["名字", "准驾车型", "证号", "初次领取", "成绩", "签发机构", "说明"]);
      const none = await at("").credentials("x");
      expect(none.find((item) => item.kind === "driver_license")?.status).toBe("not_obtained");
    } finally {
      window.history.replaceState(null, "", "/");
    }
  });
});
