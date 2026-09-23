"""爪爪驾校接口测试的辅助：按题库作答（可以故意答错几题）、用测试驾驶员生成操作并按每秒一段上传。"""

from __future__ import annotations

from app.web_driving.questions import ALL, correct_answer
from driving_bots import Driver, curve_bot, reverse_park_bot, route_bot, side_park_bot


def bots_for(subject: str, variant: str) -> list:
    sign = 1 if variant == "a" else -1
    if subject == "s2":
        return [reverse_park_bot(2.8, 2.0, sign), side_park_bot(3.8, 0.8, sign), curve_bot(sign)]
    return [route_bot()]


def wrong_answer(question_id: str) -> dict:
    question = ALL[question_id]
    right = correct_answer(question)
    if question.kind == "choice":
        return {"choice": next(oid for oid, _ in question.options if oid != right["choice"])}
    if question.kind == "order":
        return {"order": list(reversed(right["order"]))}
    targets = list(right["matches"])
    values = [right["matches"][t] for t in targets]
    return {"matches": dict(zip(targets, values[1:] + values[:1]))}


class School:
    """一个主人在驾校里的操作（用 WebUser 调接口）。"""

    def __init__(self, case, owner) -> None:
        self.case = case
        self.owner = owner

    def create(self, subject: str, mode: str = "formal", item: str | None = None, key: str | None = None):
        body = {"subject": subject, "mode": mode, **({"item": item} if item else {})}
        return self.owner.post("/driving/sessions", body, key=key)

    def start(self, subject: str, mode: str = "formal", item: str | None = None) -> dict:
        created = self.create(subject, mode, item)
        self.case.assertEqual(created.status_code, 200, created.text)
        begun = self.owner.post(f"/driving/sessions/{created.json()['session_id']}/begin")
        self.case.assertEqual(begun.status_code, 200, begun.text)
        return begun.json()

    def answer_all(self, session: dict, wrong: int = 0) -> None:
        for index, question in enumerate(session["quiz"]["questions"]):
            qid = question["question_id"]
            answer = wrong_answer(qid) if index < wrong else correct_answer(ALL[qid])
            response = self.owner.put(f"/driving/sessions/{session['session_id']}/answers", {"question_id": qid, "answer": answer})
            self.case.assertEqual(response.status_code, 200, response.text)

    def quiz(self, subject: str, wrong: int = 0, mode: str = "formal") -> dict:
        session = self.start(subject, mode)
        self.answer_all(session, wrong)
        submitted = self.owner.post(f"/driving/sessions/{session['session_id']}/submit")
        self.case.assertEqual(submitted.status_code, 200, submitted.text)
        return submitted.json()

    def drive(self, session: dict, bots: list | None = None, chunk: int = 30) -> dict:
        items = session["drive"]["items"]
        bots = bots or bots_for(session["subject"], items[0]["course"]["variant"])
        last = None
        for index, item in enumerate(items):
            driver = Driver(item["course"]).run(bots[index])
            tick = 0
            while tick < driver.tick:
                upto = min(driver.tick, tick + chunk)
                last = self.owner.post(f"/driving/sessions/{session['session_id']}/inputs",
                                       {"item_index": index, "from_tick": tick, "upto_tick": upto, "events": [e for e in driver.events if tick <= e["t"] < upto]})
                self.case.assertEqual(last.status_code, 200, last.text)
                tick = upto
            if last.json()["session_state"] == "settled":
                break
        return self.owner.get(f"/driving/sessions/{session['session_id']}").json()

    def exam(self, subject: str, *, wrong: int = 0, bots: list | None = None) -> dict:
        if subject in ("s1", "s4"):
            return self.quiz(subject, wrong)
        return self.drive(self.start(subject), bots)

    def pass_all(self) -> None:
        for subject in ("s1", "s2", "s3", "s4"):
            session = self.exam(subject)
            self.case.assertTrue(session["result"]["passed"], (subject, session["result"]))
