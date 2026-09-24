/**
 * TA 的档案 · 行为倾向（只读，服务端 behavior）：TA 会怎么过日子，每条都附原话出处。
 * - 结论（summary）照原文列出；性子只列“是这样 / 不是这样 / 被别的说法盖过”，说不准的不强行归类，
 *   它们的原话在“还没想明白的”里（服务端 unclassified）。
 * - 出处写成“出自{栏目}：「原话」”：栏目名来自服务端 field_label，原话原样。这里不写“你说的”——
 *   共用那部分可能是别的家人写的、接待叮嘱可能来自别的家人、领养伙伴的草稿来自领养时的介绍，写“你说的”会张冠李戴。
 * - 只说倾向（更愿意 / 不太愿意 / 照常），不露倍数、规则编号这些内部数字。
 */
import type { BehaviorEvidence, PetBehavior } from "@/shared/contracts";
import { leaning, shownPreferences, shownTraits, uniqueEvidence, type LeanTone } from "./dnaModel";

export function DnaBehavior({ behavior }: { behavior: PetBehavior | null | undefined }) {
  if (!behavior) return null;
  const summary = behavior.summary ?? [];
  const traits = shownTraits(behavior);
  const preferences = shownPreferences(behavior);
  const unsure = behavior.unclassified ?? [];
  const nothing = !summary.length && !traits.length && !preferences.length && !unsure.length;
  return (
    <section className="ps-dna-card ps-dna-behavior" aria-labelledby="ps-dna-behavior-title">
      <h3 id="ps-dna-behavior-title">TA 会怎么过日子</h3>
      <p className="ps-dna-lead">从档案里的话看出来的，每条都写着出处；档案改了，这里跟着变。</p>
      {nothing ? <p className="ps-dna-quiet">还看不出 TA 的作息和喜好，先按平常的节奏过。</p> : null}
      {summary.length ? (
        <ul className="ps-dna-summary" aria-label="结论">
          {summary.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      {traits.length ? (
        <div className="ps-dna-sub">
          <h4>性子</h4>
          <ul className="ps-dna-leans">
            {traits.map(({ trait, text, tone }) => (
              <Lean key={trait.key} label={trait.label} tag={text} tone={tone} evidence={trait.evidence} />
            ))}
          </ul>
        </div>
      ) : null}
      {preferences.length ? (
        <div className="ps-dna-sub">
          <h4>想做的事、想去的地方</h4>
          <ul className="ps-dna-leans">
            {preferences.map((preference) => {
              const lean = leaning(preference.weight);
              return <Lean key={preference.key} label={preference.label} tag={lean.text} tone={lean.tone} evidence={preference.evidence} notes={preference.notes} />;
            })}
          </ul>
        </div>
      ) : null}
      {unsure.length ? (
        <div className="ps-dna-sub ps-dna-unsure">
          <h4>还没想明白的</h4>
          <p>这几句说得不太确定，还没算进 TA 的日子里；想让它算数，可以换个更肯定的说法。</p>
          <ul>
            {unsure.map((phrase) => (
              <li key={phrase}>「{phrase}」</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function Lean({ label, tag, tone, evidence, notes }: { label: string; tag: string; tone: LeanTone; evidence: BehaviorEvidence[] | undefined; notes?: string[] }) {
  const lines = uniqueEvidence(evidence);
  return (
    <li className="ps-dna-lean">
      <div className="ps-dna-lean__head">
        <strong>{label}</strong>
        <span className="ps-dna-pill" data-tone={tone}>
          {tag}
        </span>
      </div>
      {lines.length ? (
        <ul className="ps-dna-evidence">
          {lines.map((line) => (
            <li key={`${line.field}|${line.phrase}`} className={line.implied ? "is-implied" : undefined}>
              <span className="ps-dna-evidence__quote">
                出自{line.field_label}：「{line.phrase}」
              </span>
              {line.note ? <span className="ps-dna-why">{line.note}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {(notes ?? []).map((note) => (
        <p key={note} className="ps-dna-why">
          {note}
        </p>
      ))}
    </li>
  );
}
