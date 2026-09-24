import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate } from "react-router";
import type { AdoptionCandidate, PetSpecies } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { onboardingRoute, useSessionState } from "@/shared/session/onboarding";
import { useCurrentHousehold } from "@/shared/session/householdContext";
import { Button, Card, Chip, DataOriginBadge, DisabledState, ErrorState, Icon, Page, PetAvatar, QueryView, TopBar } from "@/shared/ui";
import { EntryHeading } from "@/features/identity/EntryHeading";
import { SpeciesIllustration } from "./SpeciesIllustration";
import "./pets.css";

const SPECIES: Array<{ id: PetSpecies; label: string }> = [
  { id: "cat", label: "猫" },
  { id: "dog", label: "狗" },
  { id: "rabbit", label: "兔子" },
  { id: "hamster", label: "仓鼠" },
  { id: "bird", label: "鸟" },
  { id: "parrot", label: "鹦鹉" },
  { id: "other", label: "其他" },
];
const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

/** 首次入住入口：已有家庭的管理员从独立的添伙伴页面进入。 */
function useOnboardingRedirect(): string | null {
  const session = useSessionState();
  if (env.dataMode !== "live" || !session.data) return null;
  if (!session.data.authenticated) return "/welcome";
  const step = session.data.onboarding?.step;
  return step && step !== "needs_companion" ? onboardingRoute(session.data.onboarding) : null;
}

function PhotoPicker({ photo, onChange }: { photo: File | null; onChange: (file: File | null, error: string | null) => void }) {
  const [preview, setPreview] = useState<string | null>(null);
  useEffect(() => {
    if (!photo) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(photo);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);
  return (
    <div className="ps-pet-photo">
      <label className={`ps-pet-photo__stage${preview ? " has-photo" : ""}`}>
        {preview ? <img src={preview} alt="TA 的照片预览" /> : <span className="ps-pet-photo__empty" aria-hidden="true"><span className="ps-pet-photo__camera"><Icon name="camera" size={27} /></span></span>}
        <span className="ps-pet-photo__action"><Icon name="camera" size={17} />{photo ? "换一张照片" : "放入 TA 的照片"}</span>
        <input
          type="file"
          accept={PHOTO_TYPES.join(",")}
          className="visually-hidden"
          aria-label="上传 TA 的照片"
          onChange={(e) => {
            const file = e.target.files?.[0] ?? null;
            if (file && !PHOTO_TYPES.includes(file.type)) onChange(null, "只支持 JPEG / PNG / WebP 图片。");
            else if (file && file.size > MAX_PHOTO_BYTES) onChange(null, "图片太大了（上限 5MB）。");
            else onChange(file, null);
            e.target.value = "";
          }}
        />
      </label>
      <span className="ps-pet-photo__note">照片可以以后再补。上传时会去掉位置信息，只有你和获你允许的家人能看到；它也会用来为 TA 画出在星球上的形象。</span>
    </div>
  );
}

function OwnPetForm({ householdId }: { householdId?: string }) {
  const { pets } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [species, setSpecies] = useState<PetSpecies>("cat");
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const keyRef = useRef(newIdempotencyKey("pet-create"));
  const create = useMutation({
    mutationFn: () => pets.createOwn({ name: name.trim(), species, photo, householdId }, keyRef.current),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.session }),
        queryClient.invalidateQueries({ queryKey: ["households"] }),
      ]);
      navigate("/onboarding/reception?branch=own_pet");
    },
  });
  const error = create.error ? toApiError(create.error) : null;
  if (env.dataMode === "fixture") {
    return (
      <>
        <DisabledState title="演示模式不上传照片">上传在 live 模式下私有存储、校验格式并去掉照片里的位置信息。</DisabledState>
        <Link to="/onboarding/reception?branch=own_pet" className="ps-btn ps-btn--secondary ps-btn--block">
          用演示宠物体验接待
        </Link>
      </>
    );
  }
  return (
    <form
      className="ps-own-pet-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim() && !photoError) create.mutate();
      }}
    >
      <div className="ps-own-pet-form__lead">
        <span>01 / 一张照片</span>
        <h2>先让我们看看 TA</h2>
        <p>选一张你喜欢的，或先留下空白，等以后再放。</p>
      </div>
      <PhotoPicker
        photo={photo}
        onChange={(file, err) => {
          setPhoto(file);
          setPhotoError(err);
          keyRef.current = newIdempotencyKey("pet-create");
        }}
      />
      {photoError ? (
        <p role="alert" className="ps-form-error">
          {photoError}
        </p>
      ) : null}
      <div className="ps-own-pet-form__details">
        <div className="ps-field ps-own-pet-name">
          <label htmlFor="pet-name">02 / TA 叫什么名字？</label>
          <input id="pet-name" className="ps-input" maxLength={24} required value={name} onChange={(e) => setName(e.target.value)} placeholder="写下 TA 的名字" />
        </div>
        <fieldset className="ps-pet-species">
          <legend>03 / TA 是哪一位？</legend>
          <div className="ps-pet-species__choices">
            {SPECIES.map((s) => (
              <label key={s.id} className="ps-pet-species__choice">
                <input type="radio" name="pet-species" value={s.id} checked={species === s.id} onChange={() => setSpecies(s.id)} />
                <span><SpeciesIllustration species={s.id} />{s.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </div>
      <div className="ps-own-pet-next">
        <span className="ps-own-pet-next__icon"><Icon name="chat" size={23} /></span>
        <div>
          <small>下一站 · 初次接待</small>
          <strong>聊聊 TA 的习惯和故事</strong>
          <p>你可以慢慢说，也可以先跳过。</p>
        </div>
      </div>
      <Button type="submit" variant="primary" block loading={create.isPending} disabled={!name.trim() || Boolean(photoError)}>
        {householdId ? "把 TA 带进这个家" : "继续，去见接待员"}
      </Button>
      {error ? (
        error.code === "MEDIA_REJECTED" || error.code === "ALREADY_HAS_COMPANION" ? (
          <p role="alert" className="ps-form-error">
            {error.message}
          </p>
        ) : (
          <ErrorState error={error} />
        )
      ) : null}
    </form>
  );
}

export function OnboardingPage() {
  const redirect = useOnboardingRedirect();
  if (redirect) return <Navigate to={redirect} replace />;
  return (
    <Page bare className="ps-entry-page ps-own-pet-page">
      <TopBar title="认识 TA" back={env.dataMode === "fixture" ? "/welcome" : undefined} />
      <EntryHeading step={2} kicker="入住准备 · 02 / 04" title="这是 TA。" description="先用你熟悉的样子和名字，让这里认识 TA。" />
      <div className="ps-own-pet-content">
        <OwnPetForm />
        <div className="ps-own-pet-alternative">
          <span>另一种相遇</span>
          <h2>想先认识星球上的伙伴？</h2>
          <p>也可以看看正在等待一个家的原创居民。选择之前，先了解 TA。</p>
          <Link to="/adopt">去认识他们 <span aria-hidden="true">→</span></Link>
        </div>
      </div>
    </Page>
  );
}

/** Existing-home flow uses the same upload and reception, never creates a second household. */
export function AddCompanionPage() {
  const { household } = useCurrentHousehold();
  if (!household || household.role !== "admin") {
    return <Page><TopBar title="添一位伙伴" back="/me" /><DisabledState title="需要家庭管理员">只有家庭管理员可以把新伙伴带进这个家。</DisabledState></Page>;
  }
  return <Page className="ps-add-companion-page">
    <TopBar title="添一位伙伴" back="/me" />
    <EntryHeading kicker="同一个家 · 新的伙伴" title="这个家，再认识一位 TA" description="新伙伴会先经过接待与入住，再出现在家里的切换栏。照片和名字都来自你刚提交的资料。" />
    <Card className="ps-stack ps-entry-card ps-companion-card">
      <Chip tone="leaf" icon="home">{household.name || "当前家庭"}</Chip>
      <p className="ps-muted">只加入这个家，不会新建家庭。现有伙伴、家园位置和库存保持原样。</p>
      <OwnPetForm householdId={household.household_id} />
    </Card>
  </Page>;
}

function CandidateCard({ candidate }: { candidate: AdoptionCandidate }) {
  const { pets } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  const keyRef = useRef(newIdempotencyKey("adopt"));
  const adopt = useMutation({
    mutationFn: () => pets.adopt(candidate.candidate_id, keyRef.current),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.session });
      navigate("/onboarding/reception?branch=adopted");
    },
    onError: () => void queryClient.invalidateQueries({ queryKey: queryKeys.adoption }),
  });
  const taken = candidate.availability !== "available";
  return (
    <Card className="ps-stack ps-entry-card ps-resident-card">
      <div className="ps-row">
        <PetAvatar petId={candidate.candidate_id} name={candidate.name} species={candidate.species} size={48} />
        <div style={{ flex: 1 }}>
          <strong>{candidate.name}</strong>
          <div className="ps-muted">{candidate.personality}</div>
        </div>
        {taken ? <Chip>{candidate.availability === "adopted" ? "已有家" : "保留中"}</Chip> : null}
      </div>
      <div>
        <Icon name="sparkle" size={14} /> 梦想：{candidate.dream}
      </div>
      <div className="ps-muted">来源：{candidate.source_note ?? "未知"}</div>
      <DataOriginBadge origin={candidate.data_origin} label={candidate.data_origin === "fixture" ? "演示伙伴" : "PetSoul 原创伙伴"} />
      {confirming && !taken ? (
        <div className="ps-adopt-confirm" role="group" aria-label={`确认领养 ${candidate.name}`}>
          <strong>确定迎接 {candidate.name} 吗？</strong>
          <p>领养后 TA 会加入你的家，下一步可以先和接待员说说想交代的事。</p>
          <div className="ps-adopt-confirm__actions">
            <Button variant="secondary" onClick={() => setConfirming(false)} disabled={adopt.isPending}>再看看</Button>
            <Button variant="primary" loading={adopt.isPending} onClick={() => adopt.mutate()}>确认领养</Button>
          </div>
        </div>
      ) : (
        <Button variant="primary" disabled={taken} onClick={() => setConfirming(true)}>
          {taken ? "已经有家了" : `了解并迎接 ${candidate.name}`}
        </Button>
      )}
      {adopt.isError ? <Chip tone="danger">{toApiError(adopt.error).message}</Chip> : null}
    </Card>
  );
}

export function AdoptPage() {
  const redirect = useOnboardingRedirect();
  const { pets } = useServices();
  const query = useQuery({ queryKey: queryKeys.adoption, queryFn: () => pets.adoptionCandidates() });
  if (redirect) return <Navigate to={redirect} replace />;
  return (
    <Page bare className="ps-entry-page">
      <TopBar title="专属领养" subtitle="每一位只属于一个家庭" back="/onboarding" />
      <EntryHeading step={2} kicker="入住准备 · 02 / 04" title="认识一位新伙伴" description="这里的居民有自己的来处与此刻的生活。选中之后还会再让你确认，不会自动领养。" />
      <QueryView query={query} isEmpty={(list) => list.length === 0}>
        {(list) => (
          <div className="ps-stack">
            {list.map((c) => (
              <CandidateCard key={c.candidate_id} candidate={c} />
            ))}
          </div>
        )}
      </QueryView>
    </Page>
  );
}
