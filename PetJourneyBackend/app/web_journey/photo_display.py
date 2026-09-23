"""三个消费者共用的一件事：**挂上任务号的那一刻，这张图可能已经画完了**。

两个执行者之间真实存在一道缝——任务先入队，消费者随后才把任务号写到自己的行上。
中间 worker 跑完时，`UPDATE ... WHERE <任务号列> = ?` 命中 0 行，结果被丢掉；
随后消费者又无条件写下"正在画"，**之后没有任何事件会再来纠正它**，页面就永远停在那里。
（C 在通讯器与收藏两条链上各复现过一次。）

所以挂接/插入时要在**同一个写事务的同一个连接**上读一次终态：
  - 写锁先给 worker：它的回调命中 0 行，我们随后读到终态，写正确的值；
  - 写锁先给我们：先写"正在画"，worker 的回调随后命中这一行。
两种顺序都对，且都不产生额外派发。**读完另开事务再写就还留着那条缝**。
"""

from __future__ import annotations


def settled_photo(conn, task_id: str, outcome_in=None) -> tuple[str, str | None] | None:
    """这张图现在到终态了吗？到了就返回 (展示状态, 图地址)；还在画、或插画记录还没登记就返回 None。

    `conn` 必须是调用方**已经开好的写事务**那个连接；`outcome_in(conn, task_id)` 是同连接的终态口径
    （装配注入 `illustrations.outcome_of`），用来分辨"确定没画成"与"可能已受理、结果没确认"。
    没接 `outcome_in` 时按 `failed` 记——比永远停在"正在画"好，但分不出"还没确认"那一档。
    """
    from .illustrations import IllustrationService  # 局部导入：只为拿图地址的拼法，避免包级耦合

    row = conn.execute("SELECT illustration_id, status FROM web_illustrations WHERE task_id = ?", (task_id,)).fetchone()
    if row is None or row["status"] == "processing":
        return None  # 还在画，或还没登记：维持调用方原本要写的值，不臆断
    if row["status"] == "ready":
        return "ready", IllustrationService.url(row["illustration_id"])
    outcome = outcome_in(conn, task_id) if outcome_in is not None else None
    return outcome or "failed", None
