/**
 * TA 的档案 · 编辑态的表单（受控）：栏目按 DNA_GROUPS 分组，文字栏是输入框，列表栏是可增删的小标签。
 * - 输入框限长与后端一致；列表满了就收起输入框并说明“去掉一条才能再添”。
 * - 标签输入按回车添上：中文输入法组字时的回车（isComposing / keyCode 229）不算，免得把没选完的拼音添进去。
 * - “只属于你”“只在私信里用”按服务端给的 personal_fields / private_fields 标，不写死。
 * 320 宽手机上：标签、说明都能换行，输入框占满一行，按钮至少 36px 高。
 */
import { useId, type KeyboardEvent } from "react";
import { Button, Icon } from "@/shared/ui";
import { charCount, cleanItem, DNA_GROUPS, type DnaForm, type ListFieldSpec, type ListKey, type PendingItems, type TextFieldSpec, type TextKey } from "./dnaModel";

export interface FieldMarks {
  personal: ReadonlySet<string>;
  privateOnly: ReadonlySet<string>;
}

export function FieldBadges({ fieldKey, marks }: { fieldKey: string; marks: FieldMarks }) {
  const personal = marks.personal.has(fieldKey);
  const privateOnly = marks.privateOnly.has(fieldKey);
  if (!personal && !privateOnly) return null;
  return (
    <span className="ps-dna-badges">
      {personal ? <span className="ps-dna-badge" data-tone="sky">只属于你</span> : null}
      {privateOnly ? <span className="ps-dna-badge" data-tone="leaf">只在私信里用</span> : null}
    </span>
  );
}

/** 个人 / 私信栏目在编辑时多说一句它的去处。 */
function markHint(fieldKey: string, marks: FieldMarks): string | null {
  const parts: string[] = [];
  if (marks.personal.has(fieldKey)) parts.push("每位家人各写各的，别的家人看不到");
  if (marks.privateOnly.has(fieldKey)) parts.push("只在你和 TA 的私聊里用");
  return parts.length ? `${parts.join("；")}。` : null;
}

/** 栏目下的小字：栏目自己的说明在前，去处在后，每句都以句号收尾。 */
function hintOf(field: { key: string; hint?: string }, marks: FieldMarks): string {
  return [field.hint ? `${field.hint}。` : "", markHint(field.key, marks) ?? ""].join("");
}

export function DnaEditor({
  form,
  pending,
  marks,
  disabled,
  onText,
  onList,
  onPending,
}: {
  form: DnaForm;
  pending: PendingItems;
  marks: FieldMarks;
  disabled: boolean;
  onText: (key: TextKey, value: string) => void;
  onList: (key: ListKey, items: string[]) => void;
  onPending: (key: ListKey, value: string) => void;
}) {
  return (
    <>
      {DNA_GROUPS.map((group) => (
        <section className="ps-dna-card ps-dna-edit" key={group.id} aria-labelledby={`ps-dna-edit-${group.id}`}>
          <h3 id={`ps-dna-edit-${group.id}`}>{group.title}</h3>
          {group.fields.map((field) =>
            field.kind === "text" ? (
              <TextInput key={field.key} field={field} value={form[field.key]} marks={marks} disabled={disabled} onChange={(value) => onText(field.key, value)} />
            ) : (
              <TagInput
                key={field.key}
                field={field}
                items={form[field.key]}
                draft={pending[field.key] ?? ""}
                marks={marks}
                disabled={disabled}
                onItems={(items) => onList(field.key, items)}
                onDraft={(value) => onPending(field.key, value)}
              />
            ),
          )}
        </section>
      ))}
    </>
  );
}

/**
 * 栏目标题行：标题与标记在左边一起换行，计数固定在右上角（320 宽时“小暗号和趣事”带两个标记也不会把计数挤到单独一行）。
 * htmlFor 为空时（列表满了、输入框收起）标题只是标题，不指向不存在的输入框。
 */
function FieldHead({ htmlFor, label, fieldKey, marks, count }: { htmlFor?: string; label: string; fieldKey: string; marks: FieldMarks; count: string }) {
  return (
    <div className="ps-dna-input__head">
      <div className="ps-dna-input__title">
        <label htmlFor={htmlFor}>{label}</label>
        <FieldBadges fieldKey={fieldKey} marks={marks} />
      </div>
      <span className="ps-dna-count" aria-hidden="true">
        {count}
      </span>
    </div>
  );
}

/** 输入法组字中的回车是在选字。 */
function composing(event: KeyboardEvent<HTMLInputElement>): boolean {
  return event.nativeEvent.isComposing || event.keyCode === 229;
}

/** 单行栏目里按回车（手机键盘的“完成”）只是写完这一栏：收起键盘，不顺手提交整张表。 */
function finishOnEnter(event: KeyboardEvent<HTMLInputElement>) {
  if (event.key !== "Enter" || composing(event)) return;
  event.preventDefault();
  event.currentTarget.blur();
}

function TextInput({ field, value, marks, disabled, onChange }: { field: TextFieldSpec; value: string; marks: FieldMarks; disabled: boolean; onChange: (value: string) => void }) {
  const id = useId();
  const hint = hintOf(field, marks);
  const common = {
    id,
    value,
    maxLength: field.max,
    placeholder: field.placeholder,
    disabled,
    "aria-describedby": hint ? `${id}-hint` : undefined,
  };
  return (
    <div className="ps-dna-input">
      <FieldHead htmlFor={id} label={field.label} fieldKey={field.key} marks={marks} count={`${charCount(value)}/${field.max}`} />
      {hint ? (
        <p className="ps-dna-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
      {field.multiline ? (
        <textarea {...common} className="ps-textarea" rows={3} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input {...common} className="ps-input" type="text" enterKeyHint="done" onChange={(event) => onChange(event.target.value)} onKeyDown={finishOnEnter} />
      )}
    </div>
  );
}

function TagInput({
  field,
  items,
  draft,
  marks,
  disabled,
  onItems,
  onDraft,
}: {
  field: ListFieldSpec;
  items: string[];
  draft: string;
  marks: FieldMarks;
  disabled: boolean;
  onItems: (items: string[]) => void;
  onDraft: (value: string) => void;
}) {
  const id = useId();
  const hint = hintOf(field, marks);
  const full = items.length >= field.maxItems;
  const add = () => {
    const item = cleanItem(draft);
    if (!item) return;
    if (!items.includes(item) && !full) onItems([...items, item]);
    onDraft("");
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    // 输入法组字中的回车是在选字，不是“添上”；添上时也不顺手提交整张表。
    if (event.key !== "Enter" || composing(event)) return;
    event.preventDefault();
    add();
  };
  return (
    <div className="ps-dna-input">
      <FieldHead htmlFor={full ? undefined : id} label={field.label} fieldKey={field.key} marks={marks} count={`${items.length}/${field.maxItems}`} />
      {hint ? (
        <p className="ps-dna-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
      {items.length ? (
        <ul className="ps-dna-tags" aria-label={`${field.label}：已写下的`}>
          {items.map((item) => (
            <li key={item} className="ps-dna-tag">
              <span>{item}</span>
              <button type="button" aria-label={`去掉「${item}」`} disabled={disabled} onClick={() => onItems(items.filter((other) => other !== item))}>
                <Icon name="close" size={14} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {full ? (
        <p className="ps-dna-hint">最多 {field.maxItems} 条，去掉一条才能再添。</p>
      ) : (
        <div className="ps-dna-add">
          <input
            id={id}
            className="ps-input"
            type="text"
            value={draft}
            maxLength={field.itemMax}
            placeholder={field.placeholder}
            enterKeyHint="done"
            disabled={disabled}
            aria-describedby={hint ? `${id}-hint` : undefined}
            onChange={(event) => onDraft(event.target.value)}
            onKeyDown={onKeyDown}
          />
          <Button size="sm" icon="plus" disabled={disabled || !cleanItem(draft)} onClick={add}>
            添上
          </Button>
        </div>
      )}
    </div>
  );
}
