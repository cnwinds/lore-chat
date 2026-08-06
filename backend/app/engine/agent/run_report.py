"""Agent / Chat 运行结束报告：统一 `agent run end` 日志格式。

stop_reason（agent 层）:
  assistant_reply      — LLM 返回正文，无 tool_calls
  assistant_reply_empty — 无 tool_calls 且正文为空
  awaiting_user        — ask_user / sandbox_confirm，停等用户选择
  tool_call_limit      — 达到 agent_max_tool_calls
  llm_stream_incomplete — 流式 LLM 未产出 ChatWithToolsResult
  cancelled            — asyncio.CancelledError
  consumer_aborted     — SSE 消费者在 done 前断开
  error                — 未预期异常

stop_reason（chat 层）:
  turn_complete           — 收到 done 并 finalize complete
  client_disconnect       — CancelledError（客户端断流等）
  stream_closed_partial   — 连接关闭但有部分助手输出 → interrupted
  stream_closed_empty     — 无任何助手输出即关闭
  agent_exception         — Agent 抛错
  agent_finished_without_done — Agent 生成器结束但未发 done
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field


@dataclass
class AgentRunReport:
    """单次 Agent 工具循环的可观测结束报告（一条日志即可 grep）。"""

    layer: str  # "agent" | "chat"
    stop_reason: str
    conversation_id: str | None = None
    turn_id: str | None = None
    run_id: str | None = None
    llm_rounds: int = 0
    tool_calls_total: int = 0
    tool_limit: int = 0
    last_tool_names: list[str] = field(default_factory=list)
    done_emitted: bool = False
    turn_status: str | None = None  # complete | interrupted（chat 层）
    duration_ms: int = 0
    detail: str | None = None

    def emit(self, logger: logging.Logger, *, level: int = logging.INFO) -> None:
        parts = [
            f"layer={self.layer}",
            f"stop_reason={self.stop_reason}",
        ]
        if self.conversation_id:
            parts.append(f"cid={self.conversation_id}")
        if self.turn_id:
            parts.append(f"turn_id={self.turn_id}")
        if self.run_id:
            parts.append(f"run_id={self.run_id}")
        parts.append(f"llm_rounds={self.llm_rounds}")
        parts.append(f"tool_calls={self.tool_calls_total}")
        if self.tool_limit:
            parts.append(f"tool_limit={self.tool_limit}")
        if self.last_tool_names:
            parts.append(f"last_tools={','.join(self.last_tool_names)}")
        parts.append(f"done_emitted={self.done_emitted}")
        if self.turn_status:
            parts.append(f"turn_status={self.turn_status}")
        parts.append(f"ms={self.duration_ms}")
        if self.detail:
            parts.append(f"detail={self.detail}")
        logger.log(level, "agent run end %s", " ".join(parts))
