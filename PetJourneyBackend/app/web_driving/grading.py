"""爪爪驾校的成绩：科一科四按固定题库批改，科二科三汇总服务端复算出的判定事件；只由规则决定，不由模型决定。"""

from __future__ import annotations

from datetime import datetime

from .courses import TITLES
from .curriculum import META, REASONS, pet_line
from .questions import ALL, S1_TOPIC_TITLES, correct, correct_answer

MAX_SCORE = 100


def topic_title(question) -> str:
    return question.group_title or S1_TOPIC_TITLES.get(question.topic, question.topic)


def quiz_result(subject: str, question_ids: list[str], answers: dict, profile) -> dict:
    review, deductions, right = [], [], 0
    for qid in question_ids:
        question = ALL[qid]
        answer = answers.get(qid)
        ok = bool(answer) and correct(question, answer)
        right += 1 if ok else 0
        review.append({"question_id": qid, "prompt": question.prompt, "correct": ok, "your_answer": answer, "correct_answer": correct_answer(question),
                       "explanation": question.explanation})
        if not ok:
            label = f"{'没有作答' if not answer else '答错'}：{topic_title(question)}"
            deductions.append({"kind": "wrong_answer", "label": label, "points": 10, "item": None, "t": None, "ref": None, "question_id": qid})
    score, max_score = right * 10, len(question_ids) * 10  # 正式卷 10 题满分 100；练习卷按实际题数
    pass_score = META[subject]["pass_score"] * max_score // MAX_SCORE
    passed = score >= pass_score
    return {"passed": passed, "score": score, "max_score": max_score, "pass_score": pass_score, "deductions": deductions, "fatal": None,
            "review": review, "items": [], "pet_says": pet_line("pass" if passed else "fail", profile)}


def drive_result(subject: str, items: list[dict], progress_items: list[dict], profile, abandoned: bool = False) -> dict:
    deductions, results, fatal = [], [], None
    for spec, prog in zip(items, progress_items):
        snap = prog["snapshot"]
        taken = 0
        for event in snap["events"]:
            if event["p"] > 0:
                taken += event["p"]
                deductions.append({"kind": event["k"], "label": REASONS.get(event["k"], event["k"]), "points": event["p"], "item": spec["item"], "t": event["t"],
                                   "ref": event["ref"], "question_id": None})
            if event["f"] and fatal is None:
                fatal = {"kind": event["k"], "label": REASONS.get(event["k"], event["k"]), "points": 0, "item": spec["item"], "t": event["t"], "ref": event["ref"],
                         "question_id": None}
        results.append({"item": spec["item"], "title": TITLES[spec["item"]], "status": prog["status"], "deducted": taken, "ticks": snap["tick"]})
    if abandoned and fatal is None:
        fatal = {"kind": "abandoned", "label": REASONS["abandoned"], "points": 0, "item": None, "t": None, "ref": None, "question_id": None}
    score = MAX_SCORE - sum(d["points"] for d in deductions)
    score = score if score > 0 else 0
    complete = all(prog["status"] == "done" for prog in progress_items)
    passed = complete and fatal is None and score >= META[subject]["pass_score"]
    return {"passed": passed, "score": score, "max_score": MAX_SCORE, "pass_score": META[subject]["pass_score"], "deductions": deductions, "fatal": fatal,
            "review": [], "items": results, "pet_says": pet_line("pass" if passed else "fail", profile)}


def next_step(subject: str, mode: str, passed: bool, fails_in_round: int, cooldown_until: datetime | None, licensed: bool) -> dict:
    name = META[subject]["title"].split("：")[0]
    if mode == "practice":
        return {"kind": "practice", "message": "练习不计成绩，想练多少次都可以。", "attempts_left": None, "cooldown_until": None}
    if passed:
        if licensed:
            return {"kind": "licensed", "message": "四科全部通过！去领爪爪驾照吧。", "attempts_left": None, "cooldown_until": None}
        return {"kind": "passed", "message": f"{name}通过啦，成绩一直保留。", "attempts_left": None, "cooldown_until": None}
    if cooldown_until is not None:
        return {"kind": "cooldown", "message": "这轮先到这里。我们把需要练的地方记下来了；模拟练习随时开放。", "attempts_left": 0, "cooldown_until": cooldown_until}
    return {"kind": "retake", "message": "还有一次补考机会。可以先把扣分的地方练一练，再去补考。", "attempts_left": 2 - fails_in_round, "cooldown_until": None}
