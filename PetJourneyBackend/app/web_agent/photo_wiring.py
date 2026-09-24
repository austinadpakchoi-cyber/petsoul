"""照片链路的接线：把世界侧的到店拍照事件，接到 A 的同事务登记口上。

和 `photo_scene.py` 分开：那边是**纯映射**（destination_key → 场景键、地点类目 → 已核验事实），
这边是**接线**（拿着 illustrations 这个服务去登记）。组合根 `web_agent_wiring.py` 已经顶在门禁上限，
而且这两件事本来也该能分别验。
"""

from __future__ import annotations

from .photo_scene import (fact_basis, fact_revision, missing_fact_reason, place_timezone,
                          scene_facts, scene_key_of, verified_facts)

PHOTO_SOURCE_PREFIX = "photo:"  # 与 web_journey/service.py 的 photo_taken 事件键同源


def bind_photo_request(illustrations, households):
    """返回 `journeys.photo_request_in` 要的那个回调（C 的方案 B：在调用方的写事务里登记）。

    活动结果、photo_taken 事件与排队一起提交，版本冲突或租约被接手时一起回滚——
    不会留下"镜头没响、队列里却多一张图"的孤儿任务。
    """

    def photo_request_in(conn, visit, journey, *, captured_at, source_key):
        """`scene_key` 决定这次走不走照片导演：**只看目的地，不看有没有拿到事实**。

        为 None ＝ 本来就不归导演管（散步、进城、明信片自拍、驾校证件照），照旧走模板，这是正常的旧路。
        不为 None 但事实核不齐时，由导演侧 hold，**不回落旧模板**——那种"回落"会把一次没拍成的照片
        伪装成拍成了（COORD-B-INTERFACE）。`hold_reason` 让运维一眼看出是哪一种缺。
        """
        scene_key = scene_key_of(journey.destination_key)
        household_id = households.household_of_pet(journey.pet_id)
        facts = verified_facts(scene_key, visit.place)
        return illustrations.request_photo_in(
            conn, journey.user_id, journey.pet_id, source_key,
            # **这里必须传真店名。** 我一度改成类目（想挡住"地名进提示词→招牌被画出字"），**那是错的**：
            # `place` 在载荷里有**四个读者**，只有一个是提示词——
            #   illustrations.py:339        回落旧模板的提示词（只有这一个希望它不是专名）
            #   photo_director_bridge.py:155 → SceneFacts.place_label → 导演提示词（P 有意要真名：
            #                                 BACKGROUND_RULE「仍认得出是哪里」，compiler.py:262 还断言它出现在提示词里）
            #   routers/web/pets.py:271／:298 → PhotoRequestView／PhotoRequestResult，**给界面看的**
            # 换成类目会同时弄坏后两者。我当时只 grep 了 `illustrations.py` 一个文件就说"只有一个消费者"——
            # **范围缩到一个文件，却把结论说成了全仓**。
            #
            # 提示词那一侧的修法不在这儿，而且**已经落地**：`build_selfie_prompt` 现在只读 `scene`、
            # 不读 `place`／`city`（A 2026-09-24，`photo_prompts.py c4d14ec9…`，并有用例钉着
            # "传真名也进不去"、加回去的变异被杀）。**专名在模板那一层就进不来，不靠每个调用方自觉。**
            place=visit.place["name"], city=journey.city,
            scene="在店里靠窗的位置坐着",  # 旧模板句：scene_key 为 None 时才用得到
            captured_at=captured_at, scene_key=scene_key,
            household_id=household_id,
            place_id=visit.place.get("place_id"),
            # 拍照时刻按**真实地点**换算，不是宿主机时区、也不是家的时区；取不到就如实为 None，不回落默认城市
            place_timezone=place_timezone(visit.place),
            revision=fact_revision(visit.place),  # 只由地点身份与类目决定，见 photo_scene.fact_revision
            # 形状以消费端（A 的桥）为准：SceneFact 的六个键。给 token 元组会被当成"没有事实"而一直 hold。
            scene_facts=scene_facts(scene_key, visit.place, pet_id=journey.pet_id,
                                    household_id=household_id, event_id=source_key) or None,
            fact_basis=fact_basis(scene_key, facts) or None,  # 依据，给诊断用，不进提示词
            # 这是**真的世界事件**（到店拍照）。虚构叙事不得挂 world_event——
            # 否则一张想象出来的照片会被记成"世界上真的发生过"。这条路名副其实。
            event_origin="world_event",
            hold_reason=missing_fact_reason(scene_key, visit.place))

    return photo_request_in


def bind_visit_revision(journeys):
    """执行那一刻**重新读**一次到访事实的代数，交给 `illustrations.visit_revision_of`。

    必须现读：回读 payload 里那个值两边永远相等，那是伪装的围栏，比没有更坏。
    `source_key` 形如 `photo:<visit_id>`（`web_journey/service.py` 里与 photo_taken 的事件键同源）。

    **只接 `visit_revision_of` 这个分支口，不接总入口 `event_revision_of`**——
    总入口在组合根按来路分派（主人主动发起的命令型事件没有后续修订，恒为 1），
    两边各自赋值同一个属性会互相覆盖，后写的那个把另一条路整条打成 hold。
    """

    def visit_revision_of(source_key: str) -> int | None:
        if not isinstance(source_key, str) or not source_key.startswith(PHOTO_SOURCE_PREFIX):
            return None  # 不是到访照片：由组合根的总入口按来路分派，这里不替别的来路编代数
        visit = journeys.repo.visit(source_key[len(PHOTO_SOURCE_PREFIX):])
        return fact_revision(visit.place) if visit is not None else None  # 到访没了就 None，A 据此 hold

    return visit_revision_of
