# 网页意图判断层离线对照（2026-09-22）

目的：按 INTENT-DECISION-LAYER 的启用条件，先在离线中文样例上对比本地规则基线与“已配置主模型”判断器（configured_llm，DeepSeek）。**这不是启用依据**：意图层仍默认 `mode=off`，Jev 未接入。

读法与局限：
- 20 条人工标注样例（`PetJourneyBackend/tests/web_evals/web_intent_cases.json`），判定只看“应有/不应有的信号种类、是否引用、是否被当作当前命令”，不评估措辞或下游动作；样例少，通过数不能外推为准确率。
- 模型输出的每个信号都必须引用原文片段，找不到片段的信号被丢弃；confidence 不使用。
- 观察到的模型偏差（未被当前标注判为失败，但需要在扩充样例时覆盖）：“谢谢你陪着它。”被标成 share/past；“那家店别去了”同时给出 refuse 与 constraint；这些若在 assist 模式下驱动措辞，需要场景级复核。
- 规则基线失败的 4 类（条件句、撤回、习惯陈述、“以后不要再提”）正是方案里指出的旧关键词规则短板。
- 调用：本次 configured_llm 20 次，全部成功；请求 deepseek-chat，服务端返回 deepseek-flash。复现命令见 `tests/web_evals/run_web_intent_eval.py` 文件头。

## rule

- 判断器：rule（本地规则基线）
- 用例：20 条（tests/web_evals/web_intent_cases.json，人工标注）；通过 16 条
- 耗时：中位 0 ms，最慢 0 ms；模型调用 0 次（失败 0）

| 用例 | 原句 | 输出信号 | 结果 |
|---|---|---|---|
| refuse_photo | 别再给我拍照了。 | refuse/current_command | 通过 |
| missing_only | 好想你呀。 | missing/ongoing | 通过 |
| history_and_constraint | 它以前最喜欢去海边。今天别安排出门。 | share/past, constraint/current_command | 通过 |
| wish_not_history | 希望以后带它去看雪。 | wish/future_wish | 通过 |
| private_part | 我那天没忍住哭了，这件事别告诉它。 | privacy_limit/current_command/限, share/past/限 | 通过 |
| neutral_weather | 今天天气不错。 | unclear/unknown | 通过 |
| quoted_refusal | 它说“别拍啦”，哈哈。 | unclear/unknown | 通过 |
| hypothetical_outing | 如果明天下雨，就别出门了。 | constraint/current_command | 未过：constraint 被当成当前命令 |
| revoke_note | 之前说它怕打雷那条，别记了。 | unclear/unknown | 未过：缺少 revoke |
| childhood_habit | 小时候它总爱钻纸箱。 | share/past | 通过 |
| future_boat | 下次想带它去坐船。 | wish/future_wish | 通过 |
| privacy_blanket | 别告诉它我把它的旧毯子送人了。 | privacy_limit/current_command/限 | 通过 |
| refuse_place | 那家店别去了，太吵。 | refuse/current_command | 通过 |
| stay_home_today | 今天就在家待着吧，别出门。 | constraint/current_command | 通过 |
| thanks | 谢谢你陪着它。 | unclear/unknown | 通过 |
| missing_and_constraint | 我好想它，但是今天还是别出门了。 | missing/ongoing, constraint/current_command | 通过 |
| habit_not_refusal | 它不喜欢被抱，这个要记住。 | unclear/unknown | 未过：缺少 share |
| photos_welcome | 拍照没关系，多拍点！ | unclear/unknown | 通过 |
| dont_mention_lost | 以后不要再提那次走丢的事了。 | wish/future_wish | 未过：不该有 wish；应至少出现 privacy_limit/revoke/constraint |
| negated_missing | 我不是不想你，只是最近太忙了。 | missing/ongoing | 通过 |

## configured_llm

- 判断器：configured_llm（请求模型 deepseek-chat；服务端返回 deepseek-flash；提示版本 intent-llm-q1）
- 用例：20 条（tests/web_evals/web_intent_cases.json，人工标注）；通过 20 条
- 耗时：中位 1751 ms，最慢 2117 ms；模型调用 20 次（失败 0）

| 用例 | 原句 | 输出信号 | 结果 |
|---|---|---|---|
| refuse_photo | 别再给我拍照了。 | refuse/current_command | 通过 |
| missing_only | 好想你呀。 | missing/ongoing | 通过 |
| history_and_constraint | 它以前最喜欢去海边。今天别安排出门。 | share/past, constraint/current_command | 通过 |
| wish_not_history | 希望以后带它去看雪。 | wish/future_wish | 通过 |
| private_part | 我那天没忍住哭了，这件事别告诉它。 | share/past, privacy_limit/current_command/限 | 通过 |
| neutral_weather | 今天天气不错。 | unclear/unknown | 通过 |
| quoted_refusal | 它说“别拍啦”，哈哈。 | refuse/current_command/引 | 通过 |
| hypothetical_outing | 如果明天下雨，就别出门了。 | constraint/hypothetical | 通过 |
| revoke_note | 之前说它怕打雷那条，别记了。 | revoke/past/限 | 通过 |
| childhood_habit | 小时候它总爱钻纸箱。 | share/past | 通过 |
| future_boat | 下次想带它去坐船。 | wish/future_wish | 通过 |
| privacy_blanket | 别告诉它我把它的旧毯子送人了。 | privacy_limit/current_command/限, share/past | 通过 |
| refuse_place | 那家店别去了，太吵。 | refuse/current_command, constraint/current_command | 通过 |
| stay_home_today | 今天就在家待着吧，别出门。 | constraint/current_command | 通过 |
| thanks | 谢谢你陪着它。 | share/past | 通过 |
| missing_and_constraint | 我好想它，但是今天还是别出门了。 | missing/ongoing, constraint/current_command | 通过 |
| habit_not_refusal | 它不喜欢被抱，这个要记住。 | share/ongoing, constraint/current_command | 通过 |
| photos_welcome | 拍照没关系，多拍点！ | request/current_command | 通过 |
| dont_mention_lost | 以后不要再提那次走丢的事了。 | revoke/current_command | 通过 |
| negated_missing | 我不是不想你，只是最近太忙了。 | missing/ongoing, share/ongoing | 通过 |
