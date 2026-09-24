"""1701：这趟的旅费到底扣了没有——用驾校借车券抵掉时，账本里没有记录。

`web_journeys.fee` 存的是**这趟的标价**（出发当刻写死），用没用券都一样。
扣钱那次账本里有一笔 `web:travel_fee:{journey_id}`；**用券那次什么都没有**，
而散步、打工这种本来就不花钱的也没有——**两种"查不到"在账本上长得一模一样**，
页面于是把用券那趟显示成「0 星币」，借车券省下的钱就这么消失了。

不靠"账本里没有那一行"去反推：账本是会变的（退款、调账、幂等键改名），
那时"没有那一行"会悄悄变成别的意思，而**页面不会报错，只会显示错**。
出发那一刻就知道的事实，就在出发那一刻记下来。

编号由总集成分配（1700 段，A 的 `m1700_travel_wish` 之后）。加列按幂等写，开发库重复跑也过得去。
"""

from __future__ import annotations

import sqlite3

from . import WebMigration


def _apply(conn: sqlite3.Connection) -> None:
    columns = [row[1] for row in conn.execute("PRAGMA table_info(web_journeys)")]
    if "fare_waived" not in columns:
        conn.execute("ALTER TABLE web_journeys ADD COLUMN fare_waived INTEGER NOT NULL DEFAULT 0")


MIGRATION = WebMigration(
    migration_id="1701_journey_fare_waived",
    module="platform",
    description="record whether a journey's fare was waived by a voucher, so the page can tell 'free trip' from 'voucher saved you N'",
    apply=_apply,
)
