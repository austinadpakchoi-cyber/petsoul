/**
 * 科一 / 科四的答题界面：看场景选择、拖放标志（也可以点选再点位置）、排先后；科四按情境成组。
 * - 每题作答立即保存到服务端（回来可以接着答，不会重新抽题）；
 * - 练习模式答完马上讲解；正式考试交卷前不给任何对错提示，TA 也不会暗示答案。
 */
import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { AnswerRequest, AnswerResult, QuizAnswer, QuizFeedback, QuizQuestionView, SchoolSession } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { Button, Chip, Icon } from "@/shared/ui";
import { Scene } from "./Scene";

const EMPTY: QuizAnswer = { choice: null, order: null, matches: null };

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

function OrderEditor({ question, value, onChange }: { question: QuizQuestionView; value: string[]; onChange: (order: string[]) => void }) {
  const label = (id: string) => question.options.find((o) => o.option_id === id)?.label ?? id;
  const move = (from: number, to: number) => {
    if (to < 0 || to >= value.length) return;
    const next = [...value];
    const [picked] = next.splice(from, 1);
    next.splice(to, 0, picked);
    onChange(next);
  };
  return (
    <ol className="ds-order" aria-label="排列顺序">
      {value.map((id, i) => (
        <li key={id} className="ds-order__item">
          <span className="ds-order__no">{i + 1}</span>
          <span className="ds-order__text">{label(id)}</span>
          <button type="button" className="ds-mini" aria-label={`把“${label(id)}”往前移`} disabled={i === 0} onClick={() => move(i, i - 1)}>
            ↑
          </button>
          <button type="button" className="ds-mini" aria-label={`把“${label(id)}”往后移`} disabled={i === value.length - 1} onClick={() => move(i, i + 1)}>
            ↓
          </button>
        </li>
      ))}
    </ol>
  );
}

/** 拖放标志：按住标志拖到位置上；也可以先点标志、再点位置（键盘与读屏同样可用）。 */
function MatchEditor({ question, value, onChange }: { question: QuizQuestionView; value: Record<string, string>; onChange: (matches: Record<string, string>) => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [ghost, setGhost] = useState<{ id: string; x: number; y: number } | null>(null);
  const drag = useRef<{ id: string; x0: number; y0: number; moved: boolean } | null>(null);
  const placed = new Set(Object.values(value));
  const label = (id: string) => question.options.find((o) => o.option_id === id)?.label ?? id;
  const place = (optionId: string, targetId: string) => {
    const next: Record<string, string> = {};
    for (const [t, o] of Object.entries(value)) if (o !== optionId && t !== targetId) next[t] = o;
    next[targetId] = optionId;
    onChange(next);
    setSelected(null);
  };
  const unplace = (targetId: string) => {
    const next = { ...value };
    delete next[targetId];
    onChange(next);
  };
  const down = (id: string) => (e: ReactPointerEvent<HTMLButtonElement>) => {
    drag.current = { id, x0: e.clientX, y0: e.clientY, moved: false };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const moveTo = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    if (!d) return;
    if (!d.moved && Math.hypot(e.clientX - d.x0, e.clientY - d.y0) > 6) d.moved = true;
    if (d.moved) setGhost({ id: d.id, x: e.clientX, y: e.clientY });
  };
  const up = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    drag.current = null;
    setGhost(null);
    if (!d) return;
    if (!d.moved) {
      setSelected((s) => (s === d.id ? null : d.id));
      return;
    }
    const el = document.elementFromPoint?.(e.clientX, e.clientY)?.closest("[data-target-id]");
    const targetId = el?.getAttribute("data-target-id");
    if (targetId) place(d.id, targetId);
  };
  return (
    <div className="ds-match">
      <p className="ps-muted">{selected ? `已选“${label(selected)}”，再点它该放的位置。` : "按住标志拖到位置上，或者先点标志、再点位置。"}</p>
      <div className="ds-match__pool" role="group" aria-label="标志">
        {question.options.map((o) => (
          <button
            key={o.option_id}
            type="button"
            className="ds-sign-chip"
            aria-pressed={selected === o.option_id}
            data-placed={placed.has(o.option_id) || undefined}
            onPointerDown={down(o.option_id)}
            onPointerMove={moveTo}
            onPointerUp={up}
            onPointerCancel={() => {
              drag.current = null;
              setGhost(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setSelected((s) => (s === o.option_id ? null : o.option_id));
              }
            }}
          >
            {o.label}
          </button>
        ))}
      </div>
      <div className="ds-match__targets">
        {question.targets.map((t) => {
          const current = value[t.target_id];
          return (
            <div key={t.target_id} className="ds-target" data-target-id={t.target_id}>
              <span className="ds-target__label">{t.label}</span>
              {current ? (
                <button type="button" className="ds-sign-chip ds-sign-chip--placed" aria-label={`${t.label}：${label(current)}（点一下拿走）`} onClick={() => unplace(t.target_id)}>
                  {label(current)} ×
                </button>
              ) : (
                <button type="button" className="ds-target__slot" disabled={!selected} onClick={() => selected && place(selected, t.target_id)}>
                  {selected ? "放到这里" : "空位"}
                </button>
              )}
            </div>
          );
        })}
      </div>
      {ghost ? (
        <div className="ds-sign-ghost" style={{ left: ghost.x, top: ghost.y }} aria-hidden="true">
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
    } catch (e) {
      setError(toApiError(e).message);
    } finally {
      setSaving(false);
    }
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit();
    } catch (e) {
      setError(toApiError(e).message);
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

      <nav className="ds-dots" aria-label="题目进度">
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

      <section className="ds-question" aria-labelledby="ds-question-prompt">
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
          <div className="ds-options" role="radiogroup" aria-label="选项">
            {question.options.map((o) => {
              const chosen = current.choice === o.option_id;
              const verdict = fb ? (fb.correct_answer.choice === o.option_id ? "right" : chosen ? "wrong" : undefined) : undefined;
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
                  {o.label}
                </button>
              );
            })}
          </div>
        ) : null}
        {question.kind === "order" ? (
          <>
            <OrderEditor question={question} value={orderValue} onChange={(order) => !locked && setDraft((d) => ({ ...d, [question.question_id]: { choice: null, order, matches: null } }))} />
            {!locked ? (
              <Button variant="primary" block loading={saving} onClick={() => void save({ choice: null, order: orderValue, matches: null })} disabled={!dirty && answered(saved)}>
                {answered(saved) && !dirty ? "顺序已保存" : "确定这个顺序"}
              </Button>
            ) : null}
          </>
        ) : null}
        {question.kind === "match" ? (
          <>
            <MatchEditor question={question} value={matchValue} onChange={(matches) => !locked && setDraft((d) => ({ ...d, [question.question_id]: { choice: null, order: null, matches } }))} />
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
          <p className="ps-muted" role="status">
            <Icon name="check" size={14} /> 已保存。交卷前可以随时改。
          </p>
        ) : null}
        {fb ? (
          <div className={`ds-feedback ${fb.correct ? "is-right" : "is-wrong"}`} role="status">
            <strong>{fb.correct ? "答对了" : "这题再想想"}</strong>
            {!fb.correct ? <p>正确答案：{describeAnswer(question, fb.correct_answer)}</p> : null}
            <p>{fb.explanation}</p>
            <p className="ds-pet-line">TA：{fb.pet_line}</p>
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
