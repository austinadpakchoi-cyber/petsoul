"""1800：首批 6 位原创居民住进星球（用户 2026-09-24 指示上传；1800–1899 段归「可领养居民」，I 分配）。

内容来源：c84a 整理的《可领养居民首批内容准备包》图文待审稿 v0.2（RES-DRAFT-001～006），
用户 2026-09-24 亲自下令上传——**这一步就是那份资料的发布决定**。

**与 0240 同一种建档方式**（候选 → 宠物 → 公开档案 → 驿站名单），所以领养、公开页、自主生活这些
现成的路径对它们一视同仁；pet_id 用 0240 的 `resident_pet_id`，同一个候选编号永远是同一只。

和前 8 位不同、这一批**多带了两样**：

- **各自的 DNA**（`web_pet_dna`）：性格、说话的样子、口头禅、习惯、喜欢的事、怕的事、偏爱的地方——
  生活引擎与之后的大脑读的就是这一份，**每只一份、互不相同**。前 8 位至今没有 DNA。
  只写 `PetDNA` 已有的字段（它 `extra="forbid"`，多一个键整份读不出来）；**爱吃的**资料里没写，**留空不编**。
- **形象照**：资料包附带的原创形象草稿，随仓打包在 `web_pets/platform_photos/`，
  `photo_ref` 记成 `platform:<文件名>`，由 `PetService.photo_path` 只在那个目录里解析。
  **`photo_generated = 1`**：这是生成的原创形象，**不是主人上传的真实照片**——
  形象链 `request_in` 拒绝把 `photo_generated` 当身份源，这道保护照旧生效（要给它们做透明世界角色，
  得走 A 的平台居民导入入口，本批没有）。

**不做、也不许做的**（需求 §4／§5，资料包「统一初始化边界」）：
- 钱包为 0（不写任何流水；无钱包行即读作 0）。
- 经历为空：背景是**原创设定**，写进简介，**不转成到访、工资、好友或回忆**。
- 住处从**现有驿站**里选，规则与 0240 相同（梦想里有海／灯塔／船／日出 → 西贡海边，其余 → 中环），不虚构驿站。
- 初始活动不写死，由当下时间与合法机会决定。
- 资料里「备注（仅运营可见）」**不进任何玩家可见字段、也不进宠物记忆**——只留在本文件注释里。
- 工作偏好／探索偏好／储蓄倾向资料里标着「待 B 映射」，现有 DNA 没有对应字段，**不硬塞**；
  `favorite_places` 只取探索偏好里明确说出的地点类型。

**大脑与心跳**：居民本来就在 `living_pets` 里，心跳照常为它们跑规则生活（散步、打工、攒钱、出门）。
**模型大脑不开**：无主居民启用模型要 B 的「平台居民策略」与独立额度池（需求 §3），本批没有；
开它就是给没有家庭授权的宠物花真钱。DNA 已经备好，策略一到位就能直接读。
"""

from __future__ import annotations

import json
import sqlite3

from . import WebMigration
from .m0240_residents import SEASIDE_WORDS, SYSTEM_USER, resident_pet_id

SOURCE_NOTE = "原创星球居民"  # 资料包「玩家可见来源说明」

# 顺序即上架先后（public_since 同一时刻，按 pet_id 排）。字段取自资料包逐只档案。
FIRST_RESIDENTS = [
    {
        "candidate_id": "adopt-maisui", "draft": "RES-DRAFT-001", "name": "麦穗", "species": "cat",
        "personality": "认真、慢热、耐心",
        "dream": "亲手照料一小块菜地，看完一个完整的种植季。",
        "bio": ("麦穗对一件事能慢慢变好很有耐心，尤其爱看植物长出新叶。它会蹲下来观察叶子背面，也常把零散的小东西摆得整整齐齐。"
                "它不急着跑遍很多地方，更想先熟悉住处附近的路，再试一份能认真做完的短工。至于将来，它希望有机会照料一小块菜地，看完一个完整的种植季。"),
        "dna": {
            "personality": "认真、慢热、耐心",
            "voice_style": "初见话少，熟悉后会主动分享",
            "catchphrase": "我想种一小块菜地，先从最容易的开始。",
            "hobbies": ["看植物长出新叶", "清晨安静的小路"],
            "habits": ["观察植物时会先看叶子背面", "整理物品时喜欢把边缘摆齐"],
            "fears": ["突然的高声催促", "拥挤、缺少落脚空间的环境"],
            "favorite_places": ["绿地", "安静的步行路线"],
        },
        # 仅运营可见：种菜是兴趣与愿望，不表示已分配菜地、种子或收成。
    },
    {
        "candidate_id": "adopt-modian", "draft": "RES-DRAFT-002", "name": "墨点", "species": "cat",
        "personality": "细致、独立、冷幽默",
        "dream": "慢慢走过不同街区，把沿途的观察整理成一本小册子。",
        "bio": ("墨点喜欢把事情弄清楚，再决定要不要出门。它看见一排小物件，会忍不住按大小重新排一次；到了岔路口，也总要停下来想想。"
                "它不太会热闹地打招呼，却很愿意替别人确认遗漏的小细节。它想靠适合自己的工作攒一点旅费，以后在不同的街区找找安静的窗边，把沿途观察写成一本小册子。"),
        "dna": {
            "personality": "细致、独立、冷幽默",
            "voice_style": "不主动热场，回答简短，偶尔冷幽默",
            "catchphrase": "路线可以慢慢想，东西要先放整齐。",
            "hobbies": ["有秩序的陈列", "安静的窗边"],
            "habits": ["见到小物件会先按大小分类", "走到路口习惯停一下，再选方向"],
            "fears": ["物品被突然打乱", "持续打断或强行追问"],
            "favorite_places": ["安静的小店", "可停留观察的地方"],
        },
        # 仅运营可见：小册子属于长期愿望，不预发书本资产，也不预写到访记录。
    },
    {
        "candidate_id": "adopt-huajuan", "draft": "RES-DRAFT-003", "name": "花卷", "species": "cat",
        "personality": "外向、好奇、容易分心",
        "dream": "慢慢逛过不同地方的小市集，认识各有习惯的邻居。",
        "bio": ("花卷对路边的新鲜事几乎都有兴趣。有人聊起一件小见闻，它会歪着头一直听；出门时原本只想走到路口，也可能因为一块新招牌停下很久。"
                "它想试试需要打招呼的短工，看看自己能认识怎样的邻居。比起一次走得很远，它更想把普通日子过得有点不同，以后慢慢逛遍不同地方的小市集。"),
        "dna": {
            "personality": "外向、好奇、容易分心",
            "voice_style": "很容易开口聊天，打招呼时会歪头",
            "catchphrase": "先走到路口，后面的路到时候再说。",
            "hobbies": ["听别人讲小见闻", "逛有新鲜陈列的小摊"],
            "habits": ["打招呼时会歪头，等对方回应", "听到新鲜动静会先停下脚步看看"],
            "fears": ["被限制只能走同一条路", "拥挤到无法停下观察的场所"],
            "favorite_places": ["就近的新路线", "小市集"],
        },
        # 仅运营可见：社交意愿不是已有好友关系；初始不创建熟人名单或交往事件。
    },
    {
        "candidate_id": "adopt-acheng", "draft": "RES-DRAFT-004", "name": "阿澄", "species": "dog",
        "personality": "热心、爽快、有主见",
        "dream": "整理出几条自己喜欢的散步路线，有机会时邀请朋友同行。",
        "bio": ("阿澄很容易对一条路产生兴趣，尤其喜欢记住转角处特别显眼的东西。它听人说话时会先停下脚步，再认真看看对方。"
                "它想找一份能适量走动、又能帮上忙的短工，把附近的街道一点点认熟。以后有机会，它想整理出几条自己喜欢的散步路线；别人愿意同行就一起走，不愿意也没有关系。"),
        "dna": {
            "personality": "热心、爽快、有主见",
            "voice_style": "主动打招呼，会直接说出不同想法",
            "catchphrase": "这条路我想认熟，下一条再慢慢选。",
            "hobbies": ["有转弯和岔路的街道", "做一件能帮上忙的小事"],
            "habits": ["散步时会记住显眼的路口标志", "听别人说话时会先停下来面对对方"],
            "fears": ["反复无解释地改变安排", "过长且没有休息的连续活动"],
            "favorite_places": ["新路口", "附近的街道"],
        },
        # 仅运营可见：会认路是性格设定，不代表已经具有地图到访记录或导航权限。
    },
    {
        "candidate_id": "adopt-wumi", "draft": "RES-DRAFT-005", "name": "乌米", "species": "dog",
        "personality": "沉稳、体贴、笃定",
        "dream": "慢慢找到几片喜欢的草地，按自己的节奏散步和停留。",
        "bio": ("乌米不着急把每一天排满。它走路时喜欢留意树荫落在哪里，和别人同行也会看看对方是不是跟得舒服。"
                "它想尝试节奏稳定、可以按时休息的小工作，把空下来的时间留给附近的散步。它没有很长的目的地清单，只希望以后慢慢找到几片合意的草地：有地方坐，有风经过，不需要赶着离开。"),
        "dna": {
            "personality": "沉稳、体贴、笃定",
            "voice_style": "不抢话，愿意安静地待在旁边",
            "catchphrase": "有空的时候，我想找片草地坐一会儿。",
            "hobbies": ["树荫下的空地", "节奏稳定的小事情"],
            "habits": ["落座前会在周围慢慢看一圈", "和别人同行时会留意对方的步速"],
            "fears": ["突然的尖锐声响", "需要追赶或高强度负重的安排"],
            "favorite_places": ["绿地", "可休息的路线"],
        },
        # 仅运营可见：偏年长只是原创年龄阶段；不推断疾病，不以衰弱或被抛弃作为卖点。
    },
    {
        "candidate_id": "adopt-xiaoman", "draft": "RES-DRAFT-006", "name": "小满", "species": "dog",
        "personality": "乐观、机灵、略爱逞能",
        "dream": "有机会到一处可达的灯塔附近看海，慢慢过完一个下午。",
        "bio": ("小满常常先对新鲜事说一句“这个我可以试试”，想明白之后才发现还得多学一点。它做成小事时会站得格外精神，但遇到难处也愿意问别人。"
                "它想找一份时长合适的短工，一点点攒出门的旅费。它最想去有灯塔的海边，不用赶很多景点，找个能看见海的地方，把一下午慢慢过完。"),
        "dna": {
            "personality": "乐观、机灵、略爱逞能",
            "voice_style": "容易熟悉，先说得很满，难了也会求助",
            "catchphrase": "先攒一趟看海的路费，耳朵到时候再管。",
            "hobbies": ["窗边的新鲜景色", "有一点挑战的小任务"],
            "habits": ["想事情时会把头轻轻偏向一边", "做成小事后会站直一点，像在等人发现"],
            "fears": ["被持续比较或嘲笑", "没有停顿的高强度活动"],
            "favorite_places": ["窗边", "看得见海的地方"],
        },
        # 仅运营可见：灯塔只是愿望地点类型；未绑定具体城市、景点、船票或出游记录。
    },
]

PLATFORM_PHOTO_PREFIX = "platform:"  # 与 web_pets.service.PLATFORM_PHOTO_PREFIX 同一个前缀


def _apply(conn: sqlite3.Connection) -> None:
    now = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now') AS t").fetchone()["t"]
    for r in FIRST_RESIDENTS:
        pet_id = resident_pet_id(r["candidate_id"])
        conn.execute(
            "INSERT INTO web_adoption_candidates (candidate_id, name, species, personality, dream, origin, source_note, "
            "background_available, availability, adopted_pet_id, created_at) VALUES (?, ?, ?, ?, ?, 'adopted_original', ?, 0, 'available', ?, ?)",
            (r["candidate_id"], r["name"], r["species"], r["personality"], r["dream"], SOURCE_NOTE, pet_id, now),
        )
        conn.execute("INSERT INTO pets (pet_id, name, pet_type, dna_json, created_at, photo_path, owner_user_id) VALUES (?, ?, ?, '{}', ?, NULL, NULL)",
                     (pet_id, r["name"], r["species"], now))
        conn.execute(
            "INSERT INTO web_pet_profiles (pet_id, user_id, origin, candidate_id, species, photo_ref, photo_content_type, visibility, bio, created_at, "
            "photo_generated) VALUES (?, ?, 'adopted_original', ?, ?, ?, 'image/png', 'public', ?, ?, 1)",
            (pet_id, SYSTEM_USER, r["candidate_id"], r["species"], f"{PLATFORM_PHOTO_PREFIX}{r['candidate_id']}.png", r["bio"], now),
        )
        residence = "res-hk-saikung" if any(word in r["dream"] for word in SEASIDE_WORDS) else "res-hk-central"
        conn.execute("INSERT INTO web_residents (pet_id, candidate_id, residence_id, kind, status, public_since) VALUES (?, ?, ?, 'adoptable', 'resident', ?)",
                     (pet_id, r["candidate_id"], residence, now))
        conn.execute(
            "INSERT INTO web_pet_dna (pet_id, user_id, dna_json, confirmed_at, updated_at, version, updated_by) VALUES (?, ?, ?, ?, ?, 1, ?)",
            (pet_id, SYSTEM_USER, json.dumps(r["dna"], ensure_ascii=False, sort_keys=True), now, now, SYSTEM_USER),
        )


MIGRATION = WebMigration(
    migration_id="1800_first_residents",
    module="pets",
    description="first 6 original planet residents (3 cats, 3 dogs): candidates, stable pet_id, public profile with bundled platform photo, "
                "station, and per-resident DNA; wallet 0, no history; model brain not enabled for ownerless residents",
    apply=_apply,
)
