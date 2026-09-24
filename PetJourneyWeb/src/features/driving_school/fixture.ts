/**
 * 爪爪驾校 fixture 服务的实现（按需加载，不进主包）：在内存里按服务端同一套规则运行，明确是演示数据，刷新页面即重置。
 * - 规则：报名 → 科目一至科目四依次解锁；每轮首次＋一次补考；两次不过冷却 7×24 小时；只结算一次；四科齐全签发驾照与借车券；
 * - 驾驶：用同一个确定性复算（sim/replay.ts）按上传的操作片段复算，片段必须连续，完全相同的重发原样返回；
 * - 题目：只有几道演示题（正式题库只在服务端），按题数折算满分与及格线，和后端的练习卷一致。
 */
import type {
  AnswerRequest,
  CollectionItem,
  CredentialSummary,
  Deduction,
  DrivingSchoolStatus,
  InputChunk,
  InputResult,
  NextStep,
  QuizAnswer,
  QuizFeedback,
  SchoolSession,
  SchoolSubject,
  SessionBrief,
  SessionCreateRequest,
  SessionResult,
  SimEvent,
  SubjectStatus,
} from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import type { DrivingSchoolService } from "@/shared/services/types";
import { DEMO_CURRICULUM, DEMO_QUESTIONS, type DemoQuestion, demoCourse } from "@/fixtures/driving";
import { delay } from "@/fixtures/world";
import type { FixtureDrivingOptions } from "./service";
import { Replay } from "./sim/replay";
import type { Course, InputEventT, Snapshot } from "./sim/types";

const SUBJECTS: SchoolSubject[] = ["s1", "s2", "s3", "s4"];
const PREREQ: Record<SchoolSubject, SchoolSubject | null> = { s1: null, s2: "s1", s3: "s2", s4: "s3" };
const FORMAL_ITEMS: Record<string, string[]> = { s2: ["reverse_park", "side_park", "curve"], s3: ["route"] };
const COOLDOWN_MS = DEMO_CURRICULUM.cooldown_hours * 3600 * 1000;
const PREPARING_TTL_MS = 3600 * 1000;
const TEMPERAMENT = "lively";

interface SubjectRow {
  round_no: number;
  fails: number;
  cooldown_until: number | null;
  passed_at: number | null;
  passed_score: number | null;
  practice_count: number;
}

interface DriveItemState {
  item: string;
  course: Course;
  status: string;
  events: InputEventT[];
  chunks: { from: number; upto: number; digest: string }[];
  snapshot: Snapshot;
}

interface FixtureSession {
  session_id: string;
  subject: SchoolSubject;
  mode: "practice" | "formal";
  item: string | null;
  attempt_kind: "first" | "retake" | null;
  round_no: number | null;
  state: "preparing" | "running" | "settled" | "void";
  created_at: number;
  begun_at: number | null;
  paused_at: number | null;
  settled_at: number | null;
  void_reason: string | null;
  questions: DemoQuestion[] | null;
  answers: Record<string, QuizAnswer>;
  feedback: Record<string, QuizFeedback>;
  items: DriveItemState[] | null;
  item_index: number;
  result: SessionResult | null;
}

const iso = (ms: number) => new Date(ms).toISOString();
const meta = (subject: SchoolSubject) => DEMO_CURRICULUM.subjects.find((s) => s.subject === subject)!;
const shortName = (subject: SchoolSubject) => meta(subject).title.split("：")[0];
const itemTitle = (item: string) => DEMO_CURRICULUM.subjects.flatMap((s) => [...s.items, ...s.practice_items]).find((i) => i.item === item)?.title ?? item;
const line = (kind: string) => DEMO_CURRICULUM.pet_lines[TEMPERAMENT][kind];
const reason = (kind: string) => DEMO_CURRICULUM.reasons[kind] ?? kind;

function conflict(reasonKey: string, message: string, details: Record<string, unknown> = {}): ApiError {
  return new ApiError({ kind: "http", status: 409, code: "CONFLICT", message, details: { reason: reasonKey, ...details } });
}

function invalid(reasonKey: string, message: string): ApiError {
  return new ApiError({ kind: "http", status: 422, code: "VALIDATION_FAILED", message, details: { reason: reasonKey } });
}

function sameAnswer(question: DemoQuestion, answer: QuizAnswer): boolean {
  const right = question.answer;
  if (question.kind === "choice") return answer.choice === right.choice;
  if (question.kind === "order") return JSON.stringify(answer.order ?? []) === JSON.stringify(right.order);
  const mine = answer.matches ?? {};
  const keys = Object.keys(right.matches ?? {});
  return keys.length === Object.keys(mine).length && keys.every((k) => mine[k] === right.matches![k]);
}

function validAnswer(question: DemoQuestion, answer: QuizAnswer): boolean {
  const optionIds = new Set(question.options.map((o) => o.option_id));
  if (question.kind === "choice") return typeof answer.choice === "string" && optionIds.has(answer.choice);
  if (question.kind === "order") {
    const order = answer.order ?? [];
    return order.length === optionIds.size && new Set(order).size === order.length && order.every((id) => optionIds.has(id));
  }
  const matches = answer.matches ?? {};
  const targetIds = new Set(question.targets.map((t) => t.target_id));
  const entries = Object.entries(matches);
  return entries.length > 0 && entries.every(([t, o]) => targetIds.has(t) && optionIds.has(o)) && new Set(entries.map(([, o]) => o)).size === entries.length;
}

function correctAnswer(question: DemoQuestion): QuizAnswer {
  return { choice: question.answer.choice ?? null, order: question.answer.order ?? null, matches: question.answer.matches ?? null };
}

function cleanAnswer(answer: QuizAnswer): QuizAnswer {
  return {
    choice: answer.choice || null,
    order: answer.order && answer.order.length ? [...answer.order] : null,
    matches: answer.matches && Object.keys(answer.matches).length ? { ...answer.matches } : null,
  };
}

const MAX_CHUNK_TICKS = 900;
const MAX_CHUNK_EVENTS = 2000;
const IN_RANGE: Record<string, (v: number, steps: number) => boolean> = {
  s: (v, steps) => v >= -steps && v <= steps,
  t: (v) => v === 0 || v === 1,
  b: (v) => v === 0 || v === 1,
  g: (v) => v === -1 || v === 1,
  k: (v) => v >= -1 && v <= 1,
  c: (v) => v >= 1 && v <= 3,
  v: (v) => v === 0 || v === 1,
};

/** 与服务端 replay.validate 相同的片段校验：最多 30 秒、时间单调且落在片段内、数值在范围内。 */
function validateChunk(events: InputEventT[], from: number, upto: number, steps: number): InputEventT[] {
  if (upto < from || upto - from > MAX_CHUNK_TICKS) throw invalid("invalid_input", "一段操作最多 30 秒");
  if (events.length > MAX_CHUNK_EVENTS) throw invalid("invalid_input", "操作记录过多");
  let last = from;
  return events.map((e) => {
    const ok = Number.isInteger(e.t) && Number.isInteger(e.v) && e.c in IN_RANGE;
    if (!ok) throw invalid("invalid_input", "操作记录格式不对");
    if (e.t < last || e.t >= upto) throw invalid("invalid_input", "操作记录的时间不连续");
    if (!IN_RANGE[e.c](e.v, steps)) throw invalid("invalid_input", "操作的数值超出范围");
    last = e.t;
    return { t: e.t, c: e.c, v: e.v };
  });
}

function hasAnswer(answer: QuizAnswer | undefined): answer is QuizAnswer {
  return !!answer && (!!answer.choice || !!answer.order?.length || !!(answer.matches && Object.keys(answer.matches).length));
}

function quizResult(subject: SchoolSubject, questions: DemoQuestion[], answers: Record<string, QuizAnswer>): SessionResult {
  const deductions: Deduction[] = [];
  let right = 0;
  const review = questions.map((q) => {
    const answer = answers[q.question_id];
    const ok = hasAnswer(answer) && sameAnswer(q, answer);
    if (ok) right += 1;
    else deductions.push({ kind: "wrong_answer", label: `${hasAnswer(answer) ? "答错" : "没有作答"}：${q.topic_title}`, points: 10, item: null, t: null, ref: null, question_id: q.question_id });
    return { question_id: q.question_id, prompt: q.prompt, correct: ok, your_answer: answer ?? null, correct_answer: correctAnswer(q), explanation: q.explanation };
  });
  const maxScore = questions.length * 10;
  const passScore = Math.floor((meta(subject).pass_score * maxScore) / 100);
  const passed = right * 10 >= passScore;
  return { passed, score: right * 10, max_score: maxScore, pass_score: passScore, deductions, fatal: null, review, items: [], pet_says: line(passed ? "pass" : "fail"), next: null };
}

function driveResult(subject: SchoolSubject, items: DriveItemState[], abandoned = false): SessionResult {
  const deductions: Deduction[] = [];
  let fatal: Deduction | null = null;
  const results = items.map((it) => {
    let taken = 0;
    for (const e of it.snapshot.events) {
      if (e.p > 0) {
        taken += e.p;
        deductions.push({ kind: e.k, label: reason(e.k), points: e.p, item: it.item, t: e.t, ref: e.ref, question_id: null });
      }
      if (e.f && fatal === null) fatal = { kind: e.k, label: reason(e.k), points: 0, item: it.item, t: e.t, ref: e.ref, question_id: null };
    }
    return { item: it.item, title: itemTitle(it.item), status: it.status, deducted: taken, ticks: it.snapshot.tick };
  });
  if (abandoned && fatal === null) fatal = { kind: "abandoned", label: reason("abandoned"), points: 0, item: null, t: null, ref: null, question_id: null };
  const score = Math.max(0, 100 - deductions.reduce((sum, d) => sum + d.points, 0));
  const passScore = meta(subject).pass_score;
  const passed = items.every((it) => it.status === "done") && fatal === null && score >= passScore;
  return { passed, score, max_score: 100, pass_score: passScore, deductions, fatal, review: [], items: results, pet_says: line(passed ? "pass" : "fail"), next: null };
}

function nextStep(subject: SchoolSubject, mode: string, passed: boolean, fails: number, cooldownUntil: number | null, licensed: boolean): NextStep {
  const name = shortName(subject);
  if (mode === "practice") return { kind: "practice", message: "练习不计成绩，想练多少次都可以。", attempts_left: null, cooldown_until: null };
  if (passed) {
    if (licensed) return { kind: "licensed", message: "四科全部通过！去领爪爪驾照吧。", attempts_left: null, cooldown_until: null };
    return { kind: "passed", message: `${name}通过啦，成绩一直保留。`, attempts_left: null, cooldown_until: null };
  }
  if (cooldownUntil !== null) return { kind: "cooldown", message: "这轮先到这里。我们把需要练的地方记下来了；模拟练习随时开放。", attempts_left: 0, cooldown_until: iso(cooldownUntil) };
  return { kind: "retake", message: "还有一次补考机会。可以先把扣分的地方练一练，再去补考。", attempts_left: 2 - fails, cooldown_until: null };
}


export function buildFixtureDrivingService(options: FixtureDrivingOptions = {}): DrivingSchoolService {
  const now = options.now ?? (() => Date.now());
  const latency = options.latency ?? 160;
  const reply = <T,>(value: T) => delay(value, latency);
  // 默认“还没开始”：家园、旅途里的驾校卡片不出现，只有星球圈入口；演示其他阶段用网址参数 ?school_demo=
  let stage: "none" | "wish" | "enrolled" | "licensed" = options.stage ?? "none";
  const wishText = "我想学会开车，以后换我载你出去玩。（演示）";
  let enrolledAt: number | null = stage === "enrolled" ? now() : null;
  const rows = new Map<SchoolSubject, SubjectRow>();
  const sessions = new Map<string, FixtureSession>();
  let seq = 0;
  let license: CredentialSummary | null = null;
  let voucher: CollectionItem | null = null;
  let memento: CollectionItem | null = null;
  let ceremonyAt: number | null = null;

  const rowOf = (subject: SchoolSubject): SubjectRow => {
    let row = rows.get(subject);
    if (!row) {
      row = { round_no: 1, fails: 0, cooldown_until: null, passed_at: null, passed_score: null, practice_count: 0 };
      rows.set(subject, row);
    }
    return row;
  };
  const roll = (row: SubjectRow, at: number) => {
    if (row.fails >= 2 && row.cooldown_until !== null && at >= row.cooldown_until) {
      row.round_no += 1;
      row.fails = 0;
      row.cooldown_until = null;
    }
  };
  const voidStale = (at: number) => {
    for (const s of sessions.values()) {
      if (s.state === "preparing" && at - s.created_at > PREPARING_TTL_MS) {
        s.state = "void";
        s.void_reason = "not_started";
      }
    }
  };
  const openFormal = () => [...sessions.values()].find((s) => s.mode === "formal" && (s.state === "preparing" || s.state === "running")) ?? null;
  const brief = (s: FixtureSession | null): SessionBrief | null =>
    s && {
      session_id: s.session_id,
      subject: s.subject,
      mode: s.mode,
      item: s.item,
      attempt_kind: s.attempt_kind,
      state: s.state,
      passed: s.result ? s.result.passed : null,
      score: s.result ? s.result.score : null,
      created_at: iso(s.created_at),
      settled_at: s.settled_at === null ? null : iso(s.settled_at),
    };

  const stateOf = (subject: SchoolSubject, at: number): SubjectStatus => {
    const row = rowOf(subject);
    roll(row, at);
    const open = openFormal();
    const m = meta(subject);
    const base: SubjectStatus = {
      subject,
      title: m.title,
      theme: m.theme,
      kind: m.kind,
      state: "available",
      passed_at: row.passed_at === null ? null : iso(row.passed_at),
      passed_score: row.passed_score,
      legacy: false,
      round_no: row.round_no,
      attempts_used: row.fails,
      attempts_left: 2 - row.fails,
      next_attempt: row.fails === 0 ? "first" : "retake",
      cooldown_until: null,
      unlock_hint: null,
      open_session_id: open && open.subject === subject ? open.session_id : null,
      last_result: brief(
        [...sessions.values()].filter((s) => s.subject === subject && s.mode === "formal" && s.state === "settled").sort((a, b) => (a.settled_at ?? 0) - (b.settled_at ?? 0)).pop() ?? null,
      ),
      practice_count: row.practice_count,
    };
    if (row.passed_at !== null) return { ...base, state: "passed", attempts_left: 0, next_attempt: null };
    if (open && open.subject === subject) return { ...base, state: "in_exam" };
    if (row.cooldown_until !== null && at < row.cooldown_until) return { ...base, state: "cooldown", cooldown_until: iso(row.cooldown_until), attempts_left: 0, next_attempt: null };
    const need = PREREQ[subject];
    if (need && rowOf(need).passed_at === null) return { ...base, state: "locked", unlock_hint: `先通过${shortName(need)}` };
    return base;
  };

  const status = (): DrivingSchoolStatus => {
    const at = now();
    voidStale(at);
    const open = openFormal();
    return {
      stage: stage === "licensed" ? "licensed" : stage,
      wish_text: stage === "none" ? null : wishText,
      enrolled_at: enrolledAt === null ? null : iso(enrolledAt),
      coach: DEMO_CURRICULUM.coach,
      subjects: SUBJECTS.map((s) => stateOf(s, at)),
      open_session: brief(open),
      license,
      voucher_available: voucher !== null,
      ceremony_done: ceremonyAt !== null,
      temperament: TEMPERAMENT,
      rules_version: DEMO_CURRICULUM.rules_version,
      server_time: iso(at),
    };
  };

  const view = (s: FixtureSession): SchoolSession => {
    const title = s.item ? `${meta(s.subject).title} · ${itemTitle(s.item)}` : meta(s.subject).title;
    return structuredClone({
      session_id: s.session_id,
      subject: s.subject,
      title,
      mode: s.mode,
      item: s.item,
      attempt_kind: s.attempt_kind,
      round_no: s.round_no,
      state: s.state,
      pass_score: meta(s.subject).pass_score,
      created_at: iso(s.created_at),
      begun_at: s.begun_at === null ? null : iso(s.begun_at),
      paused_at: s.paused_at === null ? null : iso(s.paused_at),
      settled_at: s.settled_at === null ? null : iso(s.settled_at),
      void_reason: s.void_reason,
      quiz: s.questions
        ? {
            questions: s.questions.map((q) => ({
              question_id: q.question_id,
              kind: q.kind,
              scene: q.scene,
              topic_title: q.topic_title,
              prompt: q.prompt,
              options: q.options,
              targets: q.targets,
              group: q.group,
              group_title: q.group_title,
              story: q.story,
            })),
            answers: s.answers,
            feedback: s.mode === "practice" ? s.feedback : {},
          }
        : null,
      drive: s.items
        ? {
            items: s.items.map((it) => ({
              item: it.item,
              title: itemTitle(it.item),
              course: it.course as unknown as Record<string, unknown>,
              status: it.status,
              committed_tick: it.snapshot.tick,
              events: it.events,
              sim_events: it.snapshot.events,
              snapshot: it.snapshot as unknown as Record<string, unknown>,
            })),
            current_item: s.item_index,
          }
        : null,
      result: s.result,
    });
  };

  const require = (id: string): FixtureSession => {
    const s = sessions.get(id);
    if (!s) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有这场考试或练习。", details: { reason: "session_not_found" } });
    return s;
  };

  const grantLicense = (at: number) => {
    license = {
      credential_id: "fx-license-1",
      kind: "driver_license",
      label: "爪爪驾驶证",
      status: "active",
      number: "PAW-C-000123",
      issued_at: iso(at),
      title: "PetSoul · 爪爪驾驶证（C 照，演示）",
      condition: "四科都通过后由爪爪驾校签发（PetSoul 世界内的证件，不代表现实驾驶资格）",
      private: false,
      links: [],
    };
    voucher = {
      item_id: "fx-voucher-1",
      kind: "car_voucher",
      item_key: null,
      title: "驾校借车券",
      obtained_at: iso(at),
      tradable: false,
      bound_to_pet: true,
      source_event_id: "license:fx-license-1",
      data_origin: "fixture",
      note: "第一次自己开车兜风时，借驾校的车，不用租车费（用一次）",
    };
    stage = "licensed";
  };

  const settle = (s: FixtureSession, result: SessionResult, at: number) => {
    let licensed = false;
    let fails = 0;
    let cooldown: number | null = null;
    if (s.mode === "formal") {
      const row = rowOf(s.subject);
      roll(row, at);
      if (result.passed) {
        row.passed_at = at;
        row.passed_score = result.score;
      } else {
        row.fails += 1;
        if (row.fails >= 2) row.cooldown_until = at + COOLDOWN_MS;
      }
      fails = row.fails;
      cooldown = row.cooldown_until;
      if (result.passed && license === null && SUBJECTS.every((sub) => rowOf(sub).passed_at !== null)) {
        grantLicense(at);
        licensed = true;
      }
    }
    s.result = { ...result, next: nextStep(s.subject, s.mode, result.passed, fails, cooldown, licensed) };
    s.state = "settled";
    s.settled_at = at;
  };

  // 演示“已拿证”：四科都按通过线以上通过，签发驾照与借车券，领证仪式还没做（明确是演示数据）。
  if (options.stage === "licensed") {
    const at = now() - 3600 * 1000;
    enrolledAt = at - 7 * 24 * 3600 * 1000;
    const scores: Record<SchoolSubject, number> = { s1: 100, s2: 90, s3: 85, s4: 100 };
    for (const subject of SUBJECTS) Object.assign(rowOf(subject), { passed_at: at, passed_score: scores[subject] });
    grantLicense(at);
  }

  const inputView = (s: FixtureSession, index: number, fresh: SimEvent[]): InputResult => {
    const it = s.items![index];
    return structuredClone({
      session_id: s.session_id,
      session_state: s.state,
      item_index: index,
      current_item: s.item_index,
      item_status: it.status,
      committed_tick: it.snapshot.tick,
      new_events: fresh,
      deducted: s.items!.reduce((sum, x) => sum + x.snapshot.events.reduce((a, e) => a + e.p, 0), 0),
      snapshot: it.snapshot as unknown as Record<string, unknown>,
      result: s.result,
    });
  };

  return {
    status: () => reply(status()),
    curriculum: () => reply(DEMO_CURRICULUM),
    enroll() {
      if (stage === "none" || stage === "wish") {
        stage = "enrolled";
        enrolledAt = now();
      }
      return reply(status());
    },
    createSession(body: SessionCreateRequest) {
      const at = now();
      voidStale(at);
      const { subject, mode } = body;
      const m = meta(subject);
      const drive = m.kind === "drive";
      if (body.item != null && (!drive || mode === "formal" || !m.practice_items.some((i) => i.item === body.item))) return Promise.reject(invalid("invalid_item", "没有这个练习项目。"));
      if (stage === "none" || stage === "wish") return Promise.reject(conflict("not_enrolled", "先陪 TA 报名爪爪驾校。"));
      const row = rowOf(subject);
      let number: number;
      let attempt: "first" | "retake" | null = null;
      if (mode === "practice") {
        for (const s of sessions.values()) {
          if (s.subject === subject && s.mode === "practice" && (s.state === "preparing" || s.state === "running")) {
            s.state = "void";
            s.void_reason = "replaced";
          }
        }
        number = row.practice_count;
        row.practice_count += 1;
      } else {
        const open = openFormal();
        if (open) {
          if (open.subject === subject) return reply(view(open));
          return Promise.reject(conflict("exam_in_progress", "还有一场正式考试没结束，先回去考完或放弃。", { session_id: open.session_id }));
        }
        const info = stateOf(subject, at);
        if (info.state === "passed") return Promise.reject(conflict("already_passed", "这一科已经通过了，成绩一直保留。"));
        if (info.state === "locked") return Promise.reject(conflict("locked", `${info.unlock_hint}，才能约这一科的正式考试。`));
        if (info.state === "cooldown") return Promise.reject(conflict("cooldown", "这一科两次都没通过，等冷却结束再约考试；练习随时可以。", { cooldown_until: info.cooldown_until }));
        roll(row, at);
        attempt = row.fails === 0 ? "first" : "retake";
        number = (row.round_no - 1) * 2 + row.fails;
      }
      seq += 1;
      const s: FixtureSession = {
        session_id: `fx-ds-${seq}`,
        subject,
        mode,
        item: body.item ?? null,
        attempt_kind: attempt,
        round_no: mode === "formal" ? row.round_no : null,
        state: "preparing",
        created_at: at,
        begun_at: null,
        paused_at: null,
        settled_at: null,
        void_reason: null,
        questions: null,
        answers: {},
        feedback: {},
        items: null,
        item_index: 0,
        result: null,
      };
      if (drive) {
        const variant = number % 2 === 0 ? "a" : "b";
        const names = body.item ? [body.item] : FORMAL_ITEMS[subject];
        s.items = names.map((item, index) => {
          const course = demoCourse(item, variant);
          return { item, course, status: index === 0 ? "running" : "pending", events: [], chunks: [], snapshot: new Replay(course).snapshot() };
        });
      } else {
        s.questions = DEMO_QUESTIONS[subject as "s1" | "s4"];
      }
      sessions.set(s.session_id, s);
      return reply(view(s));
    },
    async session(id) {
      return reply(view(require(id)));
    },
    async begin(id) {
      const s = require(id);
      if (s.state === "preparing") {
        s.state = "running";
        s.begun_at = now();
      }
      return reply(view(s));
    },
    async pause(id) {
      const s = require(id);
      if (s.state === "running") s.paused_at = now();
      return reply(view(s));
    },
    async answer(id, body: AnswerRequest) {
      const s = require(id);
      if (!s.questions || s.state !== "running") throw conflict("not_running", "这场考试还没开始或已经结束。");
      const question = s.questions.find((q) => q.question_id === body.question_id);
      if (!question) throw invalid("question_not_in_paper", "这道题不在这张卷子里。");
      const answer = cleanAnswer(body.answer);
      if (!validAnswer(question, answer)) throw invalid("invalid_answer", "作答的格式和题目对不上。");
      s.answers[question.question_id] = answer;
      s.paused_at = null;
      let feedback: QuizFeedback | null = null;
      if (s.mode === "practice") {
        const ok = sameAnswer(question, answer);
        feedback = { question_id: question.question_id, correct: ok, correct_answer: correctAnswer(question), explanation: question.explanation, pet_line: ok ? question.pet_line : `原来是这样……${question.pet_line}` };
        s.feedback[question.question_id] = feedback;
      }
      return reply({ question_id: question.question_id, saved: true, answered: Object.keys(s.answers).length, total: s.questions.length, feedback });
    },
    async inputs(id, body: InputChunk) {
      const s = require(id);
      if (!s.items) throw conflict("not_running", "这不是驾驶考局。");
      if (s.state === "settled" || (s.state === "running" && body.item_index < s.item_index)) return reply(inputView(s, body.item_index, []));
      if (s.state !== "running") throw conflict("not_running", "这场考试还没开始或已经结束。");
      if (body.item_index !== s.item_index) throw conflict("wrong_item", "这一项还没开始。", { current_item: s.item_index });
      const it = s.items[body.item_index];
      const committed = it.snapshot.tick;
      const events = (body.events ?? []) as InputEventT[];
      const digest = JSON.stringify(events);
      if (body.from_tick < committed) {
        if (it.chunks.some((c) => c.from === body.from_tick && c.upto === body.upto_tick && c.digest === digest)) return reply(inputView(s, body.item_index, []));
        throw conflict("resync", "操作记录和服务器不一致，请按服务器记录重新同步。", { committed_tick: committed });
      }
      if (body.from_tick > committed) throw conflict("gap", "中间缺了一段操作记录，请按服务器记录重新同步。", { committed_tick: committed });
      const clean = validateChunk(events, body.from_tick, body.upto_tick, it.course.car.steer_steps);
      const limit = it.course.time_limit_ticks;
      const replay = new Replay(it.course, it.snapshot);
      const fresh = replay.apply(clean, body.upto_tick < limit ? body.upto_tick : limit);
      it.events = [...it.events, ...clean];
      it.chunks = [...it.chunks, { from: body.from_tick, upto: body.upto_tick, digest }];
      it.snapshot = replay.snapshot();
      s.paused_at = null;
      if (replay.status === "done") {
        it.status = "done";
        if (body.item_index + 1 < s.items.length) {
          s.items[body.item_index + 1].status = "running";
          s.item_index = body.item_index + 1;
        }
      } else if (replay.status === "failed") it.status = "failed";
      if (replay.status === "failed" || s.items.every((x) => x.status === "done")) settle(s, driveResult(s.subject, s.items), now());
      return reply(inputView(s, body.item_index, fresh));
    },
    async submit(id) {
      const s = require(id);
      if (s.state === "settled") return reply(view(s));
      if (s.state !== "running") throw conflict("not_running", "这场考试还没开始或已经结束。");
      if (!s.questions) throw conflict("not_finished", "还没有开完全部项目；开完会自动出成绩。");
      settle(s, quizResult(s.subject, s.questions, s.answers), now());
      return reply(view(s));
    },
    async abandon(id, confirm) {
      if (!confirm) throw invalid("confirm_required", "放弃已经开始的正式考试会计为本次不通过，需要再确认一次。");
      const s = require(id);
      if (s.state === "settled" || s.state === "void") return reply(view(s));
      if (s.mode === "practice" || s.state === "preparing") {
        s.state = "void";
        s.void_reason = "abandoned";
      } else if (s.questions) {
        const result = quizResult(s.subject, s.questions, s.answers);
        settle(s, { ...result, passed: false, fatal: { kind: "abandoned", label: reason("abandoned"), points: 0, item: null, t: null, ref: null, question_id: null }, pet_says: line("fail") }, now());
      } else {
        settle(s, { ...driveResult(s.subject, s.items!, true), passed: false }, now());
      }
      return reply(view(s));
    },
    history: () =>
      reply(
        [...sessions.values()]
          .filter((s) => s.state === "settled" || s.state === "running")
          .sort((a, b) => b.created_at - a.created_at)
          .map((s) => brief(s)!),
      ),
    async ceremony() {
      if (license === null) throw conflict("not_licensed", "四科都通过以后才能领证。");
      const first = ceremonyAt === null;
      if (first) {
        ceremonyAt = now();
        memento = {
          item_id: "fx-memento-1",
          kind: "license_photo",
          item_key: null,
          title: "领证合影",
          obtained_at: iso(ceremonyAt),
          tradable: false,
          bound_to_pet: true,
          source_event_id: "license:fx-license-1",
          data_origin: "fixture",
          note: line("license"),
        };
      }
      return reply({ license, memento, voucher, pet_says: line("license"), first_time: first });
    },
  };
}
