/**
 * 玩家编号 → 名字，并链到用户页。名字由后端随数据一起给（`people`）；查不到名字就照原样显示编号，不猜。
 * 员工号换名字用 labels.tsx 的 `<Staff>`——玩家和员工是两套账号，不混用。
 */
import { Link } from "react-router";
import type { PersonName } from "../api/types";
import { Code } from "../labels";

export function playerName(name: PersonName | null | undefined): string | null {
  if (!name) return null;
  if (name.display_name && name.username && name.display_name !== name.username) return `${name.display_name}（${name.username}）`;
  return name.username ?? name.display_name ?? null;
}

export function Player({ id, name, link = true }: { id: string | null | undefined; name?: PersonName | null; link?: boolean }) {
  if (!id) return <>—</>;
  const text = playerName(name);
  const shown = text ?? <span className="mono" title="查不到这位玩家的名字，照原样显示编号">{id}</span>;
  return (
    <span title={`玩家编号：${id}`}>
      {link ? <Link to={`/users/${id}`}>{shown}</Link> : shown}
      {text && <Code value={id} />}
    </span>
  );
}
