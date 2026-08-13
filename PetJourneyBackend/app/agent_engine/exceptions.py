"""旅程引擎异常：从 agent_engine.py 抽离，避免 mixin 与门面互相循环引用。"""


class PetNotFoundError(Exception):
    pass


class ThoughtNotFoundError(Exception):
    pass


class TravelQuestNotFoundError(Exception):
    pass
