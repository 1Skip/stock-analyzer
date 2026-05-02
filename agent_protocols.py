"""
Agent 协作协议
定义多Agent分析的数据结构和共享上下文
"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentConfig:
    """单个 Agent 的配置"""
    name: str
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 512
    timeout: int = 30

    def clone(self, **overrides) -> "AgentConfig":
        kwargs = {
            "name": self.name, "model": self.model,
            "temperature": self.temperature, "max_tokens": self.max_tokens,
            "timeout": self.timeout,
        }
        kwargs.update(overrides)
        return AgentConfig(**kwargs)


@dataclass
class AgentResult:
    """单个 Agent 的产出"""
    agent: str
    content: str
    success: bool
    structured: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class AgentContext:
    """多Agent分析共享上下文"""

    def __init__(
        self,
        snapshot: dict[str, Any],
        api_key: str,
        base_url: str = "",
        model: str = "deepseek/deepseek-chat",
    ):
        self.snapshot = snapshot
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def config_for(self, name: str, **overrides) -> AgentConfig:
        return AgentConfig(
            name=name,
            model=self.model,
            **overrides,
        )
