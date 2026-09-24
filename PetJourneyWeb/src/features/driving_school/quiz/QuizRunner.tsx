/**
 * 科一 / 科四的答题界面：看场景选择、拖放标志（也可以点选再点位置）、排先后；科四按情境成组。
 * - 每题作答立即保存到服务端（回来可以接着答，不会重新抽题）；
 * - 练习模式答完马上讲解；正式考试交卷前不给任何对错提示，TA 也不会暗示答案。
 * - 状态不只靠颜色：选项前有单选圈，讲解后在选项上写明“正确答案 / 你选的”，拖放和排序的每一格标出对错。
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import type { AnswerRequest, AnswerResult, QuizAnswer, QuizFeedback, QuizQuestionView, SchoolSession } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { Button, Chip, Icon } from "@/shared/ui";
import { usePet } from "../hooks";
import { Scene } from "./Scene";

const EMPTY: QuizAnswer = { choice: null, order: null, matches: null };

/** 标志名自己带引号（如 “停”字牌）时不再套一层，免得读成 ““停”字牌”。 */
function quoted(text: string): string {
  return /[“”"]/.test(text) ? text : `“${text}”`;
}

/** 每个题号点按区的边长（与 school.css 的 .ds-dot 一致）。 */
const DOT = 40;

/**
 * 题号每行放几个：一行放得下（每个 40px）就一行；放不下就平均折成几行，每行不超过放得下的个数
 * （10 题：320 宽可用约 296px、390 宽约 366px，都是 5 + 5；宽度未知时按一行算）。
 */
export function dotColumns(total: number, available: number): number {
  if (total <= 1) return 1;
  if (!(available > 0)) return total;
  const fit = Math.max(1, Math.floor(available / DOT));
  if (total <= fit) return total;
  const rows = Math.ceil(total / fit);
  return Math.ceil(total / rows);
}

/** 对错小标：图标＋字，不只靠颜色区分。 */
function VerdictTag({ right, text }: { right: boolean; text: string }) {
  return (
    <span className="ds-answer-tag" data-verdict={right ? "right" : "wrong"}>
      <Icon name={right ? "check" : "close"} size={14} />
      {text}
    </span>
  );
}

function answered(answer: QuizAnswer | undefined): boolean {
  return !!answer && (!!answer.choice || !!answer.order?.length || !!(answer.matches && Object.keys(answer.matches).length));
}

export function describeAnswer(question: Pick<QuizQuestionView, "options" | "targets">, answer: QuizAnswer | null | undefined): string {
  if (!answer) return "没有作答";
  const label = (id: string) => question.options.find((o) => o.option_id === id)?.label ?? id;
  if (answer.choice) return label(answer.choice);
  if (answer.order?.length) return answer.order.map(label).join(" → ");
  if (answer.matches) {
    return question.targets
      .filter((t) => answer.matches![t.target_id])
      .map((t) => `${t.label}：${label(answer.matches![t.target_id])}`)
      .join("；");
  }
  return "没有作答";
}

/**
 * 排先后：点两项交换位置（先点一项、再点另一项；再点一次同一项取消，Esc 也取消）；也保留 ↑ ↓ 一步一步挪。
 * 点选走按钮的 click，键盘回车 / 空格、读屏的“双击激活”都能用；每次变动在读屏播报区说出现在是第几步。
 */
function OrderEditor({
  question,
  value,
  onChange,
  locked,
  verdicts,
}: {
  question: QuizQuestionView;
  value: string[];
  onChange: (order: string[]) => void;
  locked: boolean;
  verdicts?: boolean[];
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const [said, setSaid] = useState("");
  const label = (id: string) => question.options.find((o) => o.option_id === id)?.label ?? id;
  const move = (from: number, to: number) => {
    if (locked || to < 0 || to >= value.length) return;
    const next = [...value];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
    setPicked(null);
    setSaid(`${quoted(label(item))}移到了第 ${to + 1} 步。`);
  };
  const pick = (id: string) => {
    if (locked) return;
    if (picked === null) {
      setPicked(id);
      setSaid(`已选${quoted(label(id))}（第 ${value.indexOf(id) + 1} 步），再点要和它交换的那一项。`);
      return;
    }
    if (picked === id) {
      setPicked(null);
      setSaid("已取消选择。");
      return;
    }
    const a = value.indexOf(picked);
    const b = value.indexOf(id);
    const next = [...value];
    [next[a], next[b]] = [next[b], next[a]];
    onChange(next);
    setPicked(null);
    setSaid(`${quoted(label(picked))}和${quoted(label(id))}换了位置：${quoted(label(id))}现在是第 ${a + 1} 步，${quoted(label(picked))}是第 ${b + 1} 步。`);
  };
  return (
    <div
      className="ds-order-edit"
      onKeyDown={(e) => {
        if (e.key === "Escape" && picked) {
          e.stopPropagation();
          pick(picked);
        }
      }}
    >
      {!verdicts ? (
        <p className="ps-muted ds-order__hint">{picked ? `已选${quoted(label(picked))}，再点另一项和它交换位置。` : "点两项就能交换位置；也可以用 ↑ ↓ 一步一步挪。"}</p>
      ) : null}
      <ol className="ds-order" aria-label="排列顺序" data-picking={picked ? "" : undefined}>
        {value.map((id, i) => (
          <li key={id} className="ds-order__item" data-picked={picked === id || undefined} data-verdict={verdicts ? (verdicts[i] ? "right" : "wrong") : undefined}>
            <span className="ds-order__no" aria-hidden="true">
              {i + 1}
            </span>
            <button
              type="button"
              className="ds-order__pick"
              aria-pressed={picked === id}
              aria-label={picked && picked !== id ? `第 ${i + 1} 步：${label(id)}。和${quoted(label(picked))}交换` : `第 ${i + 1} 步：${label(id)}`}
              disabled={locked}
              onClick={() => pick(id)}
            >
              {label(id)}
            </button>
            {verdicts ? (
              <VerdictTag right={verdicts[i]} text={verdicts[i] ? "位置对" : "位置不对"} />
            ) : (
              <>
                <button type="button" className="ds-mini" aria-label={`把“${label(id)}”往前移`} disabled={locked || i === 0} onClick={() => move(i, i - 1)}>
                  ↑
                </button>
                <button type="button" className="ds-mini" aria-label={`把“${label(id)}”往后移`} disabled={locked || i === value.length - 1} onClick={() => move(i, i + 1)}>
                  ↓
                </button>
              </>
            )}
          </li>
        ))}
      </ol>
      <p className="visually-hidden" aria-live="polite">
        {said}
      </p>
    </div>
  );
}

type Drag = { id: string; x0: number; y0: number; x: number; y: number; moved: boolean };

/**
 * 拖放标志：手指按住标志拖到位置上，拖动中高亮松手会放进的那一格；拖到题目区上下边缘会自动滚动。
 * 不用拖也能做：先点标志、再点位置（点选走 onClick，所以读屏的“双击激活”、键盘回车 / 空格一样能用；Esc 取消已选）。
 * 放错可以撤回：点已经放好的标志把它拿回来；手里选着别的标志时点它，就换成新选的。
 * 每一步都在读屏播报区说一句“放到了哪里”。
 */
function MatchEditor({
  question,
  value,
  onChange,
  locked,
  verdicts,
}: {
  question: QuizQuestionView;
  value: Record<string, string>;
  onChange: (matches: Record<string, string>) => void;
  locked: boolean;
  verdicts?: Record<string, boolean>;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [ghost, setGhost] = useState<{ id: string; x: number; y: number } | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [said, setSaid] = useState("");
  const drag = useRef<Drag | null>(null);
  // 拖完松手后浏览器可能补发一个 click：这段时间内的 click 不当成“点选”。
  const clickMutedUntil = useRef(0);
  const edge = useRef<{ dir: number; frame: number }>({ dir: 0, frame: 0 });
  const root = useRef<HTMLDivElement>(null);
  const label = (id: string) => question.options.find((o) => o.option_id === id)?.label ?? id;
  const targetLabel = (id: string) => question.targets.find((t) => t.target_id === id)?.label ?? id;
  const whereIs = (optionId: string) => Object.entries(value).find(([, o]) => o === optionId)?.[0] ?? null;

  useEffect(() => () => cancelAnimationFrame(edge.current.frame), []);

  const place = (optionId: string, targetId: string) => {
    if (locked) return;
    const next: Record<string, string> = {};
    for (const [t, o] of Object.entries(value)) if (o !== optionId && t !== targetId) next[t] = o;
    next[targetId] = optionId;
    onChange(next);
    setSelected(null);
    const replaced = value[targetId] && value[targetId] !== optionId ? `，换下了${quoted(label(value[targetId]))}` : "";
    setSaid(`${quoted(label(optionId))}放到了${quoted(targetLabel(targetId))}${replaced}。`);
  };
  const unplace = (targetId: string) => {
    if (locked) return;
    const optionId = value[targetId];
    const next = { ...value };
    delete next[targetId];
    onChange(next);
    setSaid(`已把${quoted(label(optionId))}从${quoted(targetLabel(targetId))}拿回来。`);
  };
  const toggle = (id: string) => {
    if (locked) return;
    const next = selected === id ? null : id;
    setSelected(next);
    setSaid(next ? `已选${quoted(label(next))}，再点它该放的位置。` : "已取消选择。");
  };
  const targetAt = (x: number, y: number) => document.elementFromPoint?.(x, y)?.closest("[data-target-id]")?.getAttribute("data-target-id") ?? null;
  const scrollBox = () => root.current?.closest(".ds-question") ?? null;
  // 拖到题目区上下边缘：按住不动也继续滚，滚动后重新判断手指下面是哪一格。
  const autoScroll = () => {
    const d = drag.current;
    const box = scrollBox();
    if (!d || !d.moved || !box || edge.current.dir === 0) {
      edge.current.frame = 0;
      return;
    }
    box.scrollTop += edge.current.dir * 8;
    setOver(targetAt(d.x, d.y));
    edge.current.frame = requestAnimationFrame(autoScroll);
  };
  const down = (id: string) => (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (locked || (e.pointerType === "mouse" && e.button !== 0)) return;
    drag.current = { id, x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY, moved: false };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const moveTo = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    if (!d) return;
    d.x = e.clientX;
    d.y = e.clientY;
    if (!d.moved && Math.hypot(e.clientX - d.x0, e.clientY - d.y0) > 6) {
      d.moved = true;
      setSelected(null);
      setSaid(`正在拖${quoted(label(d.id))}，拖到位置上再松手。`);
    }
    if (!d.moved) return;
    setGhost({ id: d.id, x: e.clientX, y: e.clientY });
    setOver(targetAt(e.clientX, e.clientY));
    const rect = scrollBox()?.getBoundingClientRect();
    edge.current.dir = rect && rect.height > 0 ? (e.clientY > rect.bottom - 48 ? 1 : e.clientY < rect.top + 48 ? -1 : 0) : 0;
    if (edge.current.dir !== 0 && !edge.current.frame) edge.current.frame = requestAnimationFrame(autoScroll);
  };
  const stopDrag = () => {
    drag.current = null;
    edge.current.dir = 0;
    setGhost(null);
    setOver(null);
  };
  const up = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    stopDrag();
    // 没拖动就是一次点按：交给 onClick 当成点选（读屏、键盘也走那里）。
    if (!d || !d.moved) return;
    clickMutedUntil.current = performance.now() + 400;
    const targetId = targetAt(e.clientX, e.clientY);
    if (targetId) place(d.id, targetId);
    else setSaid(`没有放进任何位置，${quoted(label(d.id))}还在上面。`);
  };
  const clickChip = (id: string) => () => {
    if (performance.now() < clickMutedUntil.current) return;
    toggle(id);
  };
  const dragging = ghost !== null;
  const hint = dragging
    ? over
      ? `松手放到${quoted(targetLabel(over))}`
      : "拖到下面的位置上再松手"
    : selected
      ? `已选${quoted(label(selected))}，再点它该放的位置。`
      : "按住标志拖到位置上；也可以先点标志、再点位置。放错了，点一下放好的标志就能拿回来。";
  return (
    <div
      ref={root}
      className="ds-match"
      data-dragging={dragging || undefined}
      data-picking={(!!selected && !locked) || undefined}
      onKeyDown={(e) => {
        if (e.key === "Escape" && selected) {
          e.stopPropagation();
          toggle(selected);
        }
      }}
    >
      {!locked ? <p className="ps-muted ds-match__hint">{hint}</p> : null}
      <div className="ds-match__pool" role="group" aria-label="标志：先选一个，再选位置" hidden={locked}>
        {question.options.map((o) => {
          const at = whereIs(o.option_id);
          return (
            <button
              key={o.option_id}
              type="button"
              className="ds-sign-chip"
              aria-pressed={selected === o.option_id}
              aria-label={at ? `${o.label}（已放在${quoted(targetLabel(at))}）` : undefined}
              data-placed={at ? "" : undefined}
              data-dragging={ghost?.id === o.option_id || undefined}
              disabled={locked}
              onPointerDown={down(o.option_id)}
              onPointerMove={moveTo}
              onPointerUp={up}
              onPointerCancel={stopDrag}
              onClick={clickChip(o.option_id)}
            >
              {o.label}
              {at ? (
                <span className="ds-sign-chip__where" aria-hidden="true">
                  已放
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      <ul className="ds-match__targets" aria-label="位置">
        {question.targets.map((t) => {
          const current = value[t.target_id];
          const verdict = verdicts ? verdicts[t.target_id] : undefined;
          const swap = !!selected && !!current && selected !== current;
          return (
            <li
              key={t.target_id}
              className="ds-target"
              data-target-id={t.target_id}
              data-over={over === t.target_id || undefined}
              data-verdict={verdict === undefined ? undefined : verdict ? "right" : "wrong"}
              onClick={(e) => {
                // 整行都能点：手里选着标志时点这一行的空白处也算放到这里（行里的按钮自己处理）。
                if (!selected || locked || (e.target as HTMLElement).closest("button")) return;
                place(selected, t.target_id);
              }}
            >
              <span className="ds-target__label">{t.label}</span>
              {current ? (
                <button
                  type="button"
                  className="ds-sign-chip ds-sign-chip--placed"
                  disabled={locked}
                  aria-label={swap ? `把${quoted(label(selected!))}放到${quoted(t.label)}，换下${quoted(label(current))}` : `${t.label}：${label(current)}。点一下拿回来`}
                  onClick={() => (swap ? place(selected!, t.target_id) : unplace(t.target_id))}
                >
                  {label(current)}
                  {locked ? null : (
                    <span className="ds-sign-chip__x" aria-hidden="true">
                      {swap ? "换" : "×"}
                    </span>
                  )}
                </button>
              ) : (
                <button
                  type="button"
                  className="ds-target__slot"
                  aria-disabled={!selected || locked || undefined}
                  aria-label={selected ? `把${quoted(label(selected))}放到${quoted(t.label)}` : `${t.label}：还空着，先选一个标志`}
                  onClick={() => {
                    if (locked) return;
                    if (selected) place(selected, t.target_id);
                    else setSaid("先点一个标志，再点这里。");
                  }}
                >
                  {over === t.target_id ? "松手放这里" : selected ? "放到这里" : "空位"}
                </button>
              )}
              {verdict === undefined ? null : <VerdictTag right={verdict} text={verdict ? "放对了" : "放错了"} />}
            </li>
          );
        })}
      </ul>
      <p className="visually-hidden" aria-live="polite">
        {said}
      </p>
      {ghost ? (
        <div className="ds-sign-ghost" data-over={over !== null || undefined} style={{ left: ghost.x, top: ghost.y }} aria-hidden="true">
          {label(ghost.id)}
        </div>
      ) : null}
    </div>
  );
}

export function QuizRunner({
  session,
  practice,
  onAnswer,
  onSubmit,
  onExit,
  exitLabel,
}: {
  session: SchoolSession;
  practice: boolean;
  onAnswer: (body: AnswerRequest) => Promise<AnswerResult>;
  onSubmit: () => Promise<void>;
  onExit: () => void;
  exitLabel: string;
}) {
  const quiz = session.quiz!;
  const questions = quiz.questions;
  const [answers, setAnswers] = useState<Record<string, QuizAnswer>>(quiz.answers ?? {});
  const [feedback, setFeedback] = useState<Record<string, QuizFeedback>>(quiz.feedback ?? {});
  const [index, setIndex] = useState(() => {
    const first = questions.findIndex((q) => !answered(quiz.answers?.[q.question_id]));
    return first < 0 ? questions.length - 1 : first;
  });
  const [draft, setDraft] = useState<Record<string, QuizAnswer>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // 刚拿到讲解的那一题：把讲解卡滚进视野（窄屏上它常在屏幕下面）；回看旧题不滚。
  const [reveal, setReveal] = useState<string | null>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  // 正式考试的“已保存”那一行：窄屏上它在选项下面、常在屏幕外，保存后也滚进视野。
  const savedRef = useRef<HTMLParagraphElement>(null);
  const questionRef = useRef<HTMLElement>(null);
  const dotsRef = useRef<HTMLElement>(null);
  // 讲解里 TA 的话用宠物的名字署名（和成绩单一致）；取不到名字时是“TA”。
  const { name: petName } = usePet();
  const question = questions[index];
  const saved = answers[question.question_id];
  const current = draft[question.question_id] ?? saved ?? EMPTY;
  const fb = practice ? feedback[question.question_id] : undefined;
  const done = questions.filter((q) => answered(answers[q.question_id])).length;
  const orderValue = useMemo(() => current.order ?? question.options.map((o) => o.option_id), [current.order, question]);
  const matchValue = current.matches ?? {};
  const dirty = !!draft[question.question_id];

  const save = async (answer: QuizAnswer) => {
    setSaving(true);
    setError(null);
    try {
      const result = await onAnswer({ question_id: question.question_id, answer });
      setAnswers((a) => ({ ...a, [question.question_id]: answer }));
      setDraft((d) => {
        const next = { ...d };
        delete next[question.question_id];
        return next;
      });
      if (result.feedback) setFeedback((f) => ({ ...f, [question.question_id]: result.feedback! }));
      // 练习：讲解卡；正式：“已保存”那一行——保存成功后都滚进视野
      setReveal(question.question_id);
    } catch (e) {
      setError(toApiError(e).playerMessage);
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    if (!reveal) return;
    // 保存回来之前已经换到别的题：不再滚动，免得回头看这题时突然跳一下
    if (reveal !== question.question_id) {
      setReveal(null);
      return;
    }
    const still = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    (feedbackRef.current ?? savedRef.current)?.scrollIntoView?.({ block: "nearest", behavior: still ? "auto" : "smooth" });
    setReveal(null);
  }, [reveal, question.question_id]);

  // 换题后题目区回到顶部：先看到情境、插画和题干，而不是停在上一题讲解卡的滚动位置。
  useEffect(() => {
    if (questionRef.current) questionRef.current.scrollTop = 0;
  }, [index]);

  // 题号每行放几个：按这一行的实际宽度算（原来放不下时横向滑动，玩家看不出后面还有题）。
  // 放得下就一行；放不下就平均折成几行（10 题在 320、390 宽都是 5 + 5），每个点仍是 40px，所有题号都在屏幕里。
  const [dotCols, setDotCols] = useState(questions.length);
  useLayoutEffect(() => {
    const strip = dotsRef.current;
    if (!strip) return;
    const measure = () => {
      const style = getComputedStyle(strip);
      const available = strip.clientWidth - (parseFloat(style.paddingLeft) || 0) - (parseFloat(style.paddingRight) || 0);
      setDotCols(dotColumns(questions.length, available));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [questions.length]);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit();
    } catch (e) {
      setError(toApiError(e).playerMessage);
      setSubmitting(false);
      setConfirming(false);
    }
  };

  const locked = practice && !!fb;
  const last = index === questions.length - 1;
  const groupIndex = question.group ? [...new Set(questions.map((q) => q.group))].indexOf(question.group) : -1;

  return (
    <div className="ds-quiz">
      <header className="ds-exam__top">
        <div className="ds-exam__title">
          <strong>{session.title}</strong>
          <span>{practice ? "练习 · 不计成绩" : `正式考试 · 已答 ${done}/${questions.length}`}</span>
        </div>
        <div className="ds-exam__stat">
          <span>第</span>
          <strong>
            {index + 1}/{questions.length}
          </strong>
        </div>
        <Button variant="ghost" size="sm" onClick={onExit}>
          {exitLabel}
        </Button>
      </header>

      <nav className="ds-dots" aria-label="题目进度" ref={dotsRef} data-cols={dotCols} style={{ "--dot-cols": dotCols } as CSSProperties}>
        {questions.map((q, i) => (
          <button
            key={q.question_id}
            type="button"
            className="ds-dot"
            aria-current={i === index ? "step" : undefined}
            data-answered={answered(answers[q.question_id]) || undefined}
            aria-label={`第 ${i + 1} 题${answered(answers[q.question_id]) ? "（已答）" : ""}`}
            onClick={() => setIndex(i)}
          />
        ))}
      </nav>

      <section className="ds-question" aria-labelledby="ds-question-prompt" ref={questionRef}>
        {question.group ? (
          <div className="ds-story">
            <Chip tone="sky">
              情境 {groupIndex + 1} · {question.group_title}
            </Chip>
            {question.story.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        ) : (
          <Chip>{question.topic_title}</Chip>
        )}
        <Scene scene={question.scene} />
        <h2 id="ds-question-prompt" className="ps-h2">
          {question.prompt}
        </h2>

        {question.kind === "choice" ? (
          <div className="ds-options" role="radiogroup" aria-label="选项" data-locked={locked || undefined}>
            {question.options.map((o) => {
              const chosen = current.choice === o.option_id;
              const right = !!fb && fb.correct_answer.choice === o.option_id;
              const verdict = fb ? (right ? "right" : chosen ? "wrong" : undefined) : undefined;
              return (
                <button
                  key={o.option_id}
                  type="button"
                  role="radio"
                  aria-checked={chosen}
                  className="ds-option"
                  data-verdict={verdict}
                  disabled={saving || locked}
                  onClick={() => void save({ choice: o.option_id, order: null, matches: null })}
                >
                  <span className="ds-option__mark" aria-hidden="true" />
                  <span className="ds-option__text">{o.label}</span>
                  {verdict ? <VerdictTag right={right} text={right ? (chosen ? "你选对了" : "正确答案") : "你选的"} /> : null}
                </button>
              );
            })}
          </div>
        ) : null}
        {question.kind === "order" ? (
          <>
            <OrderEditor
              key={question.question_id}
              question={question}
              value={orderValue}
              locked={locked}
              verdicts={fb ? orderValue.map((id, i) => fb.correct_answer.order?.[i] === id) : undefined}
              onChange={(order) => !locked && setDraft((d) => ({ ...d, [question.question_id]: { choice: null, order, matches: null } }))}
            />
            {!locked ? (
              <Button variant="primary" block loading={saving} onClick={() => void save({ choice: null, order: orderValue, matches: null })} disabled={!dirty && answered(saved)}>
                {answered(saved) && !dirty ? "顺序已保存" : "确定这个顺序"}
              </Button>
            ) : null}
          </>
        ) : null}
        {question.kind === "match" ? (
          <>
            <MatchEditor
              key={question.question_id}
              question={question}
              value={matchValue}
              locked={locked}
              verdicts={fb ? Object.fromEntries(question.targets.map((t) => [t.target_id, !!matchValue[t.target_id] && fb.correct_answer.matches?.[t.target_id] === matchValue[t.target_id]])) : undefined}
              onChange={(matches) => !locked && setDraft((d) => ({ ...d, [question.question_id]: { choice: null, order: null, matches } }))}
            />
            {!locked ? (
              <Button
                variant="primary"
                block
                loading={saving}
                disabled={Object.keys(matchValue).length !== question.targets.length || (!dirty && answered(saved))}
                onClick={() => void save({ choice: null, order: null, matches: matchValue })}
              >
                {answered(saved) && !dirty ? "已保存" : Object.keys(matchValue).length === question.targets.length ? "确定摆放" : "把每个位置都放上标志"}
              </Button>
            ) : null}
          </>
        ) : null}

        {!practice && answered(saved) ? (
          <p className="ps-muted ds-saved" role="status" ref={savedRef}>
            <Icon name="check" size={14} /> 已保存。交卷前可以随时改。
          </p>
        ) : null}
        {fb ? (
          <div ref={feedbackRef} className={`ds-feedback ${fb.correct ? "is-right" : "is-wrong"}`} role="status">
            <strong className="ds-feedback__title">
              <Icon name={fb.correct ? "check" : "alert"} size={18} /> {fb.correct ? "答对了" : "这题再想想"}
            </strong>
            {!fb.correct ? <p>正确答案：{describeAnswer(question, fb.correct_answer)}</p> : null}
            <p>{fb.explanation}</p>
            <p className="ds-pet-line">
              {petName}：{fb.pet_line}
            </p>
          </div>
        ) : null}
        {error ? (
          <p className="ds-error" role="alert">
            {error}
          </p>
        ) : null}
      </section>

      <footer className="ds-quiz__nav">
        <Button disabled={index === 0} onClick={() => setIndex(index - 1)}>
          上一题
        </Button>
        {last ? (
          <Button variant="primary" loading={submitting} onClick={() => (done < questions.length ? setConfirming(true) : void submit())}>
            {practice ? "看练习结果" : "交卷"}
          </Button>
        ) : (
          <Button variant="primary" onClick={() => setIndex(index + 1)}>
            下一题
          </Button>
        )}
      </footer>

      {confirming ? (
        <div className="ds-overlay">
          <div className="ds-overlay__card" role="alertdialog" aria-label="确认交卷">
            <strong className="ps-h2">还有 {questions.length - done} 题没答</strong>
            <p className="ps-muted">交卷后没答的题算错{practice ? "（练习不计成绩）" : "，成绩只结算一次"}。确定现在交卷吗？</p>
            <Button variant="primary" block loading={submitting} onClick={() => void submit()}>
              确定交卷
            </Button>
            <Button variant="ghost" block onClick={() => setConfirming(false)}>
              回去接着答
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
