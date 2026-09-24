/**
 * TA 的档案（/me/dna）：从“我的”进来的全屏页，左上角回 /me，不挂底栏（方案第 9 节）。
 * 档案就是主人交代的 TA 的性格、习惯、共同回忆；TA 在生活和说话时按这份来。
 *
 * - 读：pets.dna。没保存过时是按已有资料整理的草稿（confirmed=false）：提示“待你确认”，一句话按草稿的真实来源写。
 * - 改：点“改一改”进入编辑态，表单是进入那一刻的快照；保存带的是**进入编辑时读到的**共用版本号
 *   （编辑期间后台刷新到新数据也不换，否则会带着新版本号把家人的修改无声盖掉）。
 * - 冲突：保存被拒（409，details.reason = dna_version_conflict），或编辑期间后台已经读到家人改过的新一份，
 *   都提示“家人刚改过，先看看最新的再改”，不当成已保存、不写缓存，保存按钮先停用（旧版本号发出去也只会再被拒）；
 *   “看看最新的”会丢掉本地改动，先让主人确认。
 * - 从没保存过的草稿（读到的没有版本号）第一次保存带 expected_version=0，意思是“我读到的是还没保存过的”：
 *   服务端在同一个写事务（BEGIN IMMEDIATE）里核对，已经有一份（版本从 1 起）就 409——两位家人同时首存，后到的一定冲突，
 *   不会无声覆盖。发之前先重读一眼只是提前发现冲突、少走一趟：家人已经确认过一份就不发，直接按冲突处理。
 * - 每次进页面都重新读（称呼和“我们的家”里的是同一份，那边改了不会让这里的缓存失效），读完之前“改一改”先等一等。
 * - 有没保存的改动时：取消、离开本页（含浏览器返回）、刷新或关页都先确认。
 * - 称呼与小暗号是每位家人自己的一份（personal_fields），只在私信里用的栏目（private_fields）另标，都按服务端给的标。
 * - 演示模式没有档案（服务抛能力未接入）：只说“演示模式没有 TA 的档案”，不编数据，不放“改一改”。
 * - 头像一律用 PetPortrait（不写名字首字）。
 */
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useBlocker } from "react-router";
import type { PetDNA, PetDNAView } from "@/shared/contracts";
import { isApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { Button, ErrorState, Icon, LoadingState, Page, Sheet } from "@/shared/ui";
import { PetPortrait } from "@/features/pets/PetPortrait";
import { WorldGate } from "@/features/world_map/WorldGate";
import { useCurrentPet, type CurrentPet } from "@/features/memories/currentPet";
import { DnaBehavior } from "./DnaBehavior";
import { DnaEditor, FieldBadges, type FieldMarks } from "./DnaEditor";
import {
  bodyFrom,
  DNA_GROUPS,
  draftNote,
  formFrom,
  formProblems,
  isVersionConflict,
  sameBody,
  saveFailureText,
  withPending,
  type DnaForm,
  type PendingItems,
} from "./dnaModel";
import "./me.css";
import "./dna.css";

/**
 * 从没保存过的草稿保存时带的版本号：“我读到的是还没保存过的”。服务端版本从 1 起（迁移 m0230 的默认值也是 1），
 * 在写事务里核对，已经有一份就 409 dna_version_conflict，所以两位家人同时首存时后到的那位一定冲突。
 */
const NEVER_SAVED = 0;

export function DnaPage() {
  return (
    <WorldGate>
      <DnaBody />
    </WorldGate>
  );
}

function DnaTop({ action }: { action?: ReactNode }) {
  return (
    <header className="ps-me-top ps-dna-top">
      <Link className="ps-me-back" to="/me" aria-label="返回我的">
        <Icon name="back" size={20} />
      </Link>
      <h1>TA 的档案</h1>
      {action}
    </header>
  );
}

function DnaBody() {
  const current = useCurrentPet();
  if (current.status === "ready" && current.pet) return <DnaForPet key={current.pet.petId} pet={current.pet} userId={current.userId} />;
  return (
    <Page bare className="ps-dna">
      <DnaTop />
      {current.status === "pending" ? (
        <LoadingState lines={2} label="正在找到 TA…" />
      ) : current.status === "error" ? (
        <ErrorState error={current.error} onRetry={current.retry} />
      ) : (
        <p className="ps-dna-quiet" role="status">
          还没有住进来的伙伴。
        </p>
      )}
    </Page>
  );
}

interface EditSession {
  /** 进入编辑时读到的那一份：保存带它的版本号，“有没有改动”也跟它比 */
  base: PetDNAView;
  form: DnaForm;
  pending: PendingItems;
}
type Discard = "cancel" | "latest";
type Notice = "saved" | "latest";

function DnaForPet({ pet, userId }: { pet: CurrentPet; userId: string | null }) {
  const services = useServices();
  const queryClient = useQueryClient();
  const who = userId ?? "-";
  const key = queryKeys.dnaFor(who, pet.petId);
  // 每次进来都重新读：称呼和“我们的家”里的是同一份，那边改过这里的缓存不会失效；拿旧称呼进编辑再保存会把它悄悄改回去。
  const dna = useQuery({ queryKey: key, queryFn: ({ signal }) => services.pets.dna(pet.petId, signal), staleTime: 0 });
  const view = dna.data;

  const [edit, setEdit] = useState<EditSession | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [discard, setDiscard] = useState<Discard | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [checking, setChecking] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshFailed, setRefreshFailed] = useState(false);

  const save = useMutation({
    mutationFn: ({ body, version }: { body: PetDNA; version: number }) => services.pets.saveDna(pet.petId, body, version),
    onSuccess: (saved) => {
      // 返回的就是最新的一份，直接写回缓存；称呼与家庭关系是同一份，作息与倾向会影响家园、世界状态与通讯器里的状态。
      queryClient.setQueryData(key, saved);
      void queryClient.invalidateQueries({ queryKey: queryKeys.householdRelationship(who, pet.petId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.homeFor(who, pet.petId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.messagesFor(who, pet.petId) });
      if (userId) void queryClient.invalidateQueries({ queryKey: queryKeys.worldStateFor(userId) });
      setEdit(null);
      setProblems([]);
      setNotice("saved");
      toTop();
    },
  });

  const busy = save.isPending || checking || refreshing;
  const dirty = edit ? !sameBody(bodyFrom(withPending(edit.form, edit.pending)), bodyFrom(formFrom(edit.base.dna))) : false;
  // 编辑期间后台已经读到家人改过的新一份：不等保存被拒就提示，也不再让保存按钮发出去。
  const newer = Boolean(edit && view && (view.version ?? null) !== (edit.base.version ?? null));
  const conflict = newer || isVersionConflict(save.error);
  const marks: FieldMarks = useMemo(() => ({ personal: new Set(view?.personal_fields ?? []), privateOnly: new Set(view?.private_fields ?? []) }), [view]);

  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && !save.isPending && currentLocation.pathname !== nextLocation.pathname);
  useLeaveWarning(dirty);

  const noticeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (notice) noticeRef.current?.focus({ preventScroll: true });
  }, [notice]);

  function startEdit(current: PetDNAView) {
    save.reset();
    setNotice(null);
    setProblems([]);
    setRefreshFailed(false);
    setEdit({ base: current, form: formFrom(current.dna), pending: {} });
  }

  function exitEdit() {
    save.reset();
    setDiscard(null);
    setProblems([]);
    setRefreshFailed(false);
    setEdit(null);
  }

  /**
   * 发出保存，带读到的共用版本号；从没保存过（读到的没有版本号）就带 NEVER_SAVED（0），由服务端在写事务里核对。
   * 草稿首存前先重读一眼只是提前发现：家人已经确认过一份就不发，交给冲突提示。
   */
  async function send(body: PetDNA, base: PetDNAView, fromEditor: boolean) {
    save.reset();
    const readVersion = base.version ?? null;
    if (readVersion === null) {
      setChecking(true);
      const latest = await dna.refetch();
      setChecking(false);
      if ((latest.data?.version ?? null) !== null) {
        if (!fromEditor) {
          setNotice("latest");
          toTop();
        }
        return;
      }
    }
    save.mutate({ body, version: readVersion ?? NEVER_SAVED });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    // 已知家人改过（被拒过或后台读到新版本）：只能先看最新的，不再发同一个旧版本号。
    if (!edit || busy || conflict) return;
    // 输入框里还没点“添上”的那条也算进去，并且马上变成标签，保存失败时也还在。
    const form = withPending(edit.form, edit.pending);
    setEdit({ ...edit, form, pending: {} });
    const issues = formProblems(form);
    setProblems(issues);
    if (issues.length) return;
    await send(bodyFrom(form), edit.base, true);
  }

  /** 重新读取最新的一份；读不到就留在原处（改动也还在），读到了才丢掉本地改动回到只读。 */
  async function showLatest() {
    setDiscard(null);
    setRefreshFailed(false);
    setRefreshing(true);
    const latest = await dna.refetch();
    setRefreshing(false);
    if (latest.isError) {
      setRefreshFailed(true);
      return;
    }
    exitEdit();
    setNotice("latest");
    toTop();
  }

  const askLatest = () => (dirty ? setDiscard("latest") : void showLatest());
  const cancel = () => (dirty ? setDiscard("cancel") : exitEdit());

  const conflictNote = (
    <div className="ps-dna-alert is-conflict" role="alert">
      <p>家人刚改过，先看看最新的再改。</p>
      <Button size="sm" variant="secondary" icon="refresh" loading={refreshing} onClick={askLatest}>
        看看最新的
      </Button>
    </div>
  );
  const problem = refreshFailed ? (
    <p className="ps-dna-alert" role="alert">
      没拿到最新的一份，你写的还在，稍后再试。
    </p>
  ) : conflict ? (
    conflictNote
  ) : problems.length ? (
    <p className="ps-dna-alert" role="alert">
      {problems[0]}
    </p>
  ) : save.isError ? (
    <p className="ps-dna-alert" role="alert">
      {saveFailureText(save.error)}
    </p>
  ) : null;

  // 正在重新读的时候先等一等：编辑的底子要是刚读到的那一份。
  const action =
    view && !edit ? (
      <Button variant="secondary" disabled={busy || dna.isFetching} onClick={() => startEdit(view)}>
        改一改
      </Button>
    ) : null;

  return (
    <Page bare className={`ps-dna${edit ? " is-editing" : ""}`}>
      <DnaTop action={action} />
      <Hero pet={pet} view={view} />

      {notice ? (
        <div className="ps-dna-notice" role="status" tabIndex={-1} ref={noticeRef}>
          <Icon name="check" size={18} />
          <p>{notice === "saved" ? "已保存，TA 从现在起按这份来。" : "已换成最新的一份。想改的话，再点“改一改”。"}</p>
        </div>
      ) : null}

      {!view ? (
        dna.isPending ? (
          <LoadingState lines={3} label="正在翻开 TA 的档案…" />
        ) : (
          <LoadFailure error={dna.error} onRetry={() => void dna.refetch()} />
        )
      ) : edit ? (
        <form className="ps-dna-form" onSubmit={(event) => void submit(event)} noValidate aria-label="改一改 TA 的档案">
          <DnaEditor
            form={edit.form}
            pending={edit.pending}
            marks={marks}
            disabled={busy}
            onText={(field, value) => setEdit((open) => (open ? { ...open, form: { ...open.form, [field]: value } } : open))}
            onList={(field, items) => setEdit((open) => (open ? { ...open, form: { ...open.form, [field]: items } } : open))}
            onPending={(field, value) => setEdit((open) => (open ? { ...open, pending: { ...open.pending, [field]: value } } : open))}
          />
          <div className="ps-dna-bar">
            {problem}
            <div className="ps-dna-bar__buttons">
              <Button variant="ghost" disabled={busy} onClick={cancel}>
                取消
              </Button>
              <Button variant="primary" type="submit" icon="check" loading={save.isPending || checking} disabled={refreshing || conflict}>
                {edit.base.confirmed ? "保存" : "确认并保存"}
              </Button>
            </div>
          </div>
        </form>
      ) : (
        <>
          {!view.confirmed ? (
            <div className="ps-dna-draft" role="note">
              <Icon name="sparkle" size={18} />
              <div className="ps-dna-draft__body">
                <p>{draftNote(view.draft_sources)}</p>
                {hasContent(view.dna) ? (
                  <Button variant="primary" size="sm" loading={save.isPending || checking} disabled={refreshing} onClick={() => void send(bodyFrom(formFrom(view.dna)), view, false)}>
                    就按这份
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}
          {problem}
          <DnaFields dna={view.dna} marks={marks} />
          <DnaBehavior behavior={view.behavior} />
        </>
      )}

      {discard ? <DiscardSheet reason={discard} onKeep={() => setDiscard(null)} onDrop={() => (discard === "cancel" ? exitEdit() : void showLatest())} /> : null}
      {blocker.state === "blocked" ? <DiscardSheet reason="leave" onKeep={() => blocker.reset()} onDrop={() => blocker.proceed()} /> : null}
    </Page>
  );
}

function toTop() {
  if (typeof window.scrollTo === "function") window.scrollTo(0, 0);
}

/** 有没保存的改动时，刷新或关掉页面前让浏览器问一句。 */
function useLeaveWarning(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [active]);
}

function hasContent(dna: PetDNA): boolean {
  const body = bodyFrom(formFrom(dna));
  return Object.values(body).some((value) => (Array.isArray(value) ? value.length > 0 : Boolean(value)));
}

function Hero({ pet, view }: { pet: CurrentPet; view: PetDNAView | undefined }) {
  return (
    <section className="ps-me-hero ps-dna-hero" aria-label="当前的伙伴">
      <PetPortrait petId={pet.petId} name={pet.name} species={pet.species} photoUrl={pet.photoUrl} size={56} />
      <div className="ps-me-hero__text">
        <h2>{pet.name}</h2>
        {!view ? null : view.confirmed ? (
          <p>{view.updated_by_you === false ? "家人最近改过这份，TA 正按它来" : "TA 正按这份来"}</p>
        ) : (
          <p>
            <span className="ps-dna-badge" data-tone="sun">
              待你确认
            </span>
          </p>
        )}
      </div>
    </section>
  );
}

/** 读不到档案：演示模式（能力未接入）温和说明，不编数据；其余按统一错误态，可重试。 */
function LoadFailure({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (isApiError(error) && error.isCapabilityUnavailable) {
    const demo = env.dataMode === "fixture";
    return (
      <div className="ps-dna-card ps-dna-demo" role="note">
        <span className="ps-dna-demo__icon" aria-hidden="true">
          <Icon name="bookmark" size={22} />
        </span>
        <h3>{demo ? "演示模式没有 TA 的档案" : "TA 的档案暂时打不开"}</h3>
        <p>{demo ? "住进来以后，你说过的 TA 的性格、习惯，还有你们之间的小事，会整理在这里，等你确认。" : "过一会儿再来看看。"}</p>
      </div>
    );
  }
  return <ErrorState error={error} onRetry={onRetry} />;
}

function DnaFields({ dna, marks }: { dna: PetDNA; marks: FieldMarks }) {
  return (
    <>
      {DNA_GROUPS.map((group) => (
        <section className="ps-dna-card" key={group.id} aria-labelledby={`ps-dna-${group.id}`}>
          <h3 id={`ps-dna-${group.id}`}>{group.title}</h3>
          <dl className="ps-dna-fields">
            {group.fields.map((field) => {
              const text = field.kind === "text" ? (dna[field.key] ?? "").trim() : "";
              const items = field.kind === "list" ? (dna[field.key] ?? []) : [];
              return (
                <div className="ps-dna-field" key={field.key} data-field={field.key}>
                  <dt>
                    {field.label}
                    <FieldBadges fieldKey={field.key} marks={marks} />
                  </dt>
                  <dd>
                    {field.kind === "text" ? (
                      text || <span className="ps-dna-empty">还没写</span>
                    ) : items.length ? (
                      <ul className="ps-dna-chips">
                        {items.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      <span className="ps-dna-empty">还没写</span>
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        </section>
      ))}
    </>
  );
}

const DISCARD_COPY: Record<Discard | "leave", { title: string; text: string; keep: string; drop: string }> = {
  cancel: { title: "不改了？", text: "刚写的还没保存，现在不改，这些就丢掉了。", keep: "接着写", drop: "不改了" },
  latest: { title: "看看最新的？", text: "你这次写的还没保存。换成最新的一份，这些改动会丢掉；想留着的话，可以先抄下来。", keep: "先留着", drop: "丢掉改动，看最新的" },
  leave: { title: "要离开吗？", text: "刚写的还没保存，离开这一页就丢掉了。", keep: "接着写", drop: "离开" },
};

function DiscardSheet({ reason, onKeep, onDrop }: { reason: Discard | "leave"; onKeep: () => void; onDrop: () => void }) {
  const copy = DISCARD_COPY[reason];
  return (
    <Sheet title={copy.title} onClose={onKeep} className="ps-dna-sheet">
      <p className="ps-dna-sheet__text">{copy.text}</p>
      <div className="ps-dna-sheet__actions">
        <Button variant="secondary" onClick={onKeep}>
          {copy.keep}
        </Button>
        <Button variant="danger" onClick={onDrop}>
          {copy.drop}
        </Button>
      </div>
    </Sheet>
  );
}
