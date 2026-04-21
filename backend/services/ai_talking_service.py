from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib import error, request

from configs.ai_cfg import AiConfig

logger = logging.getLogger(__name__)


class AiTalkingService:
    """Generate counselor talking draft from student context."""

    def __init__(self) -> None:
        cfg = AiConfig.from_env()
        self.api_key = cfg.api_key
        self.api_base = cfg.base_url
        self.model = cfg.model

    def generate_talking_draft(self, context: dict[str, Any]) -> list[str]:
        # If no API key configured, gracefully fallback to rule-based lines.
        if not self.api_key:
            logger.warning("AiTalkingService non-stream fallback: empty API key")
            return self._fallback_draft(context)

        try:
            content = self._chat_complete(
                system_prompt=(
                    "你是高校辅导员谈话助手。请基于学生画像生成5条中文谈话提纲，"
                    "每条一句话，务必克制、共情、可执行，避免贴标签与过度推断。"
                ),
                context=context,
                temperature=0.4,
            )
            lines = [x.strip("- ").strip() for x in str(content).splitlines() if x.strip()]
            lines = [x for x in lines if x]
            if lines:
                logger.info("AiTalkingService non-stream success with %d lines", len(lines[:5]))
                return lines[:5]
            logger.warning("AiTalkingService non-stream fallback: empty model content")
            return self._fallback_draft(context)
        except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
            self._log_stream_exception(exc)
            return self._fallback_draft(context)

    def generate_content_suggestions(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.api_key:
            logger.warning("AiTalkingService content fallback: empty API key")
            return self._fallback_content_suggestions(context)

        try:
            content = self._chat_complete(
                system_prompt=(
                    "你是高校辅导员内容助手。请基于热点与群体画像，生成工作台可用的内容建议。"
                    "输出必须是 JSON 数组，每个元素字段固定为"
                    "id, updatedAt, audienceHint, title, outline, tone, disclaimers。"
                    "outline 必须是 3-5 条中文句子数组，禁止输出学生个人身份信息。"
                ),
                context=context,
                temperature=0.6,
            )
            parsed = self._parse_json_array(content)
            if parsed:
                return parsed[:3]
            logger.warning("AiTalkingService content fallback: invalid model JSON")
            return self._fallback_content_suggestions(context)
        except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
            self._log_stream_exception(exc)
            return self._fallback_content_suggestions(context)

    def stream_content_text(self, *, kind: str, context: dict[str, Any]):
        """
        Stream long-form content via SSE.
        kind:
          - article:公众号/班会长文（markdown）
          - video:短视频脚本与分镜（纯文本）
        """
        kind = (kind or "").strip().lower()
        if kind not in {"article", "video", "video_prompt"}:
            kind = "article"

        if not self.api_key:
            text = self._fallback_content_text(kind=kind, context=context)
            yield self._sse({"type": "done", "kind": kind, "text": text})
            return

        if kind == "video_prompt":
            system_prompt = (
                "你是视频生成模型的提示词工程师。基于给定热点与群体画像，生成一段可直接喂给“文生视频/图生视频”模型的中文提示词。"
                "输出纯文本，必须包含：画面风格、镜头语言、场景、人物（只允许泛化身份，如“大学生/辅导员”）、情绪氛围、字幕/标注建议、"
                "时长、分辨率、画幅、负面提示词（避免出现学生隐私/暴力/血腥）。"
                "禁止输出任何学生个人身份信息。"
            )
        elif kind == "video":
            system_prompt = (
                "你是高校辅导员内容助手。基于给定热点与群体画像，生成一份可直接发布的中文短视频脚本。"
                "输出纯文本，包含：标题、时长建议、分镜（镜头/画面/口播/字幕/时长）、结尾引导与免责声明。"
                "禁止输出任何学生个人身份信息。"
            )
        else:
            system_prompt = (
                "你是高校辅导员内容助手。基于给定热点与群体画像，生成一篇可直接发布的中文推文/班会长文草稿。"
                "输出 Markdown，排版要适合公众号："
                "1）标题 + 导语（含1句金句/引言）；"
                "2）至少5个小节（每节小标题+解释+示例话术/可执行建议）；"
                "3）给出“班会流程建议（10-15分钟）”；"
                "4）给出“辅导员可复制的通知/群公告”模板；"
                "5）结尾：资源引导 + 免责声明 + 3-5个话题标签。"
                "整体不少于 1200 字，务必具体可用；禁止输出任何学生个人身份信息。"
            )

        prompt = self._build_prompt(context)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.6,
            "stream": True,
        }

        try:
            req = request.Request(
                url=f"{self.api_base}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            chunks: list[str] = []
            with request.urlopen(req, timeout=90) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    try:
                        item = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        item.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if not delta:
                        delta = (
                            item.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("reasoning_content", "")
                        )
                    if not delta:
                        continue
                    chunks.append(str(delta))
                    yield self._sse({"type": "delta", "kind": kind, "content": str(delta)})

            text = "".join(chunks).strip()
            if not text:
                text = self._fallback_content_text(kind=kind, context=context)
            yield self._sse({"type": "done", "kind": kind, "text": text})
        except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
            self._log_stream_exception(exc)
            text = self._fallback_content_text(kind=kind, context=context)
            yield self._sse({"type": "error", "kind": kind, "message": self._format_error_message(exc)})
            yield self._sse({"type": "done", "kind": kind, "text": text})

    def stream_talking_draft(self, context: dict[str, Any]):
        """
        Yield SSE events for streaming talking draft.
        Events:
          - data: {"type":"delta","content":"..."}
          - data: {"type":"done","lines":[...]}
        """
        if not self.api_key:
            logger.warning("AiTalkingService stream fallback: empty API key")
            lines = self._fallback_draft(context)
            yield self._sse({"type": "done", "lines": lines})
            return

        prompt = self._build_prompt(context)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是高校辅导员谈话助手。请基于学生画像生成5条中文谈话提纲，"
                        "每条一句话，务必克制、共情、可执行，避免贴标签与过度推断。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "stream": True,
        }

        try:
            req = request.Request(
                url=f"{self.api_base}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            chunks: list[str] = []
            with request.urlopen(req, timeout=60) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    try:
                        item = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        item.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if not delta:
                        delta = (
                            item.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("reasoning_content", "")
                        )
                    if not delta:
                        continue
                    chunks.append(str(delta))
                    yield self._sse({"type": "delta", "content": str(delta)})

            merged = "".join(chunks).strip()
            lines = [x.strip("- ").strip() for x in merged.splitlines() if x.strip()]
            lines = [x for x in lines if x]
            if not lines:
                logger.warning("AiTalkingService stream fallback: empty merged content")
                lines = self._fallback_draft(context)
            yield self._sse({"type": "done", "lines": lines[:5]})
        except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
            self._log_stream_exception(exc)
            lines = self._fallback_draft(context)
            yield self._sse({"type": "error", "message": self._format_error_message(exc)})
            yield self._sse({"type": "done", "lines": lines})

    @staticmethod
    def _build_prompt(context: dict[str, Any]) -> str:
        return json.dumps(context, ensure_ascii=False, indent=2)

    def _chat_complete(self, *, system_prompt: str, context: dict[str, Any], temperature: float) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._build_prompt(context)},
            ],
            "temperature": temperature,
        }
        req = request.Request(
            url=f"{self.api_base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=25) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        return str(data.get("choices", [{}])[0].get("message", {}).get("content", ""))

    @staticmethod
    def _fallback_draft(context: dict[str, Any]) -> list[str]:
        behavior_hint = "、".join(context.get("behavior_tags", [])[:3]) or "近期行为线索待补充"
        cognitive_hint = "、".join(context.get("cognitive_tags", [])[:3]) or "认知情绪线索待补充"
        keyword_hint = "、".join(context.get("content_keywords", [])[:4]) or "近期文本关键词较少"
        action_hint = context.get("intervention_action") or "建议从学习节奏与支持资源连接开始。"
        gpa_hint = context.get("gpa")
        gpa_text = f"{gpa_hint}" if gpa_hint is not None else "暂无"

        return [
            f"开场：先确认近况与课程负荷（当前绩点 {gpa_text}），避免直接使用“风险”措辞。",
            f"可核实的行为线索：{behavior_hint}；建议用“最近有没有这种情况”方式确认。",
            f"可关注的认知/情绪线索：{cognitive_hint}；先共情再讨论可执行调整。",
            f"近期文本关键词参考：{keyword_hint}，用于准备更贴近学生语境的问题。",
            f"收尾行动建议：{action_hint}",
        ]

    @staticmethod
    def _fallback_content_suggestions(context: dict[str, Any]) -> list[dict[str, Any]]:
        hot = context.get("hot_keywords", []) if isinstance(context.get("hot_keywords"), list) else []
        groups = context.get("group_labels", []) if isinstance(context.get("group_labels"), list) else []
        hot_hint = "、".join([str(x) for x in hot[:3]]) or "近期校园热点"
        group_hint = "、".join([str(x) for x in groups[:2]]) or "重点群体"
        return [
            {
                "id": "article-1",
                "updatedAt": context.get("updated_at") or "",
                "audienceHint": f"面向 {group_hint} 的班会/推文参考",
                "title": f"围绕「{hot_hint}」的支持性沟通建议",
                "outline": [
                    "开篇先共情学生现实压力，避免标签化判断。",
                    "结合近期热点给出3条可执行的小行动建议。",
                    "补充可获得的校内资源与求助路径，强调可持续跟进。",
                ],
                "tone": "克制、共情、可执行",
                "disclaimers": ["仅供辅导员工作台参考，发布前请人工审核。"],
            },
            {
                "id": "video-script-1",
                "updatedAt": context.get("updated_at") or "",
                "audienceHint": "面向班级短视频/口播场景",
                "title": "短视频脚本与分镜建议",
                "outline": [
                    "开场15-20秒：借热点切入，说明本期目标是稳节奏而非灌鸡汤。",
                    "中段40-60秒：给出3个可立即执行的学习/作息微习惯。",
                    "结尾15秒：引导到学院官方渠道与支持资源。",
                ],
                "tone": "同伴化、鼓励式",
                "disclaimers": ["禁止包含任何学生学号、姓名等个人信息。"],
            },
        ]

    @staticmethod
    def _fallback_content_text(*, kind: str, context: dict[str, Any]) -> str:
        hot = context.get("hot_keywords", []) if isinstance(context.get("hot_keywords"), list) else []
        groups = context.get("group_labels", []) if isinstance(context.get("group_labels"), list) else []
        hot_hint = "、".join([str(x) for x in hot[:3]]) or "近期热点"
        group_hint = "、".join([str(x) for x in groups[:2]]) or "学生群体"
        if kind == "video":
            return (
                f"【短视频标题】围绕「{hot_hint}」的节奏建议\n"
                f"【受众】{group_hint}\n"
                "【时长】60-90 秒\n"
                "【分镜】\n"
                "1）开场共情（10-15s）：承认压力与节奏被打乱很常见。\n"
                "2）建议1（15s）：把任务拆成3个最小步骤，今天只做第一步。\n"
                "3）建议2（15s）：设置一个固定作息锚点（起床/上床/学习开始三选一）。\n"
                "4）建议3（15s）：遇到卡点就求助同伴/辅导员/校内资源。\n"
                "5）结尾引导（10s）：强调可持续跟进，附资源入口。\n"
                "【免责声明】工作台生成内容仅供参考，发布前请人工审核。\n"
            )
        return (
            f"# 围绕「{hot_hint}」的支持性沟通与行动建议\n\n"
            f"面向：{group_hint}\n\n"
            "## 导语\n"
            "最近不少同学在学习节奏、情绪波动与信息轰炸之间来回拉扯。我们更想做的不是贴标签，而是提供可执行的支持。\n\n"
            "## 1. 先共情，再聚焦可控部分\n"
            "- 承认压力真实存在\n"
            "- 把目标从“必须立刻变好”改为“今天走一小步”\n\n"
            "## 2. 三个可执行的小行动\n"
            "1）任务拆解：把今天最重要的事拆成 3 个最小步骤\n"
            "2）节奏锚点：固定一个时间点（起床/学习开始/上床）\n"
            "3）反馈闭环：每天 3 分钟复盘：做了什么、卡在哪里、下一步是什么\n\n"
            "## 3. 资源与求助路径\n"
            "- 学业支持：学习方法与课程答疑渠道\n"
            "- 心理支持：校内咨询与预约流程\n"
            "- 同伴支持：同学互助与班级学习小组\n\n"
            "## 结尾\n"
            "如果你愿意，我们可以把问题拆小，一起把节奏找回来。\n\n"
            "> 免责声明：本内容为工作台生成建议，仅供辅导员参考，发布前请人工审核。\n"
        )

    @staticmethod
    def _parse_json_array(raw: str) -> list[dict[str, Any]]:
        text = (raw or "").strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\[[\s\S]*\]", text)
            if not m:
                return []
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                return []
        if not isinstance(data, list):
            return []
        result: list[dict[str, Any]] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            outline_raw = item.get("outline")
            outline = [str(x).strip() for x in outline_raw] if isinstance(outline_raw, list) else []
            outline = [x for x in outline if x]
            if not outline:
                continue
            result.append(
                {
                    "id": str(item.get("id") or f"ai-{i+1}"),
                    "updatedAt": str(item.get("updatedAt") or ""),
                    "audienceHint": str(item.get("audienceHint") or ""),
                    "title": str(item.get("title") or f"内容建议 {i+1}"),
                    "outline": outline[:6],
                    "tone": str(item.get("tone") or "支持性"),
                    "disclaimers": [str(x) for x in item.get("disclaimers", []) if isinstance(x, str)],
                }
            )
        return result

    @staticmethod
    def _sse(payload: dict[str, Any]) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @staticmethod
    def _format_error_message(exc: Exception) -> str:
        if isinstance(exc, error.HTTPError):
            return f"AI HTTP error: {exc.code}"
        if isinstance(exc, error.URLError):
            return f"AI URL error: {exc.reason}"
        if isinstance(exc, TimeoutError):
            return "AI request timeout"
        return f"AI stream parse error: {exc.__class__.__name__}"

    @staticmethod
    def _log_stream_exception(exc: Exception) -> None:
        if isinstance(exc, error.HTTPError):
            try:
                body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            logger.warning(
                "AiTalkingService stream HTTPError code=%s reason=%s body=%s",
                exc.code,
                getattr(exc, "reason", ""),
                body[:500],
            )
            return
        logger.warning("AiTalkingService stream failed: %s", repr(exc))

