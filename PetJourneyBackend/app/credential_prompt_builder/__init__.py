"""证件提示词构建器包。

架构审计 P1-2：原 app/credential_prompt_builder.py 411 行（> 400 行阈值）拆包。
历史导入面不变：from app.credential_prompt_builder import PetCredentialPromptBuilder。
"""

from .engine import PetCredentialPromptBuilder

__all__ = ["PetCredentialPromptBuilder"]
