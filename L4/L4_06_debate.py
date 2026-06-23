import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import uuid
import httpx
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("MODEL", "deepseek-chat")

class DebateRole(Enum):
    PRO = "pro"
    CON = "con"
    MODERATOR = "moderator"
    JUDGE = "judge"

class DebatePhase(Enum):
    OPENING = "opening"
    ARGUMENT = "argument"
    COUNTER = "counter"
    REBUTTAL = "rebuttal"
    CLOSING = "closing"
    JUDGMENT = "judgment"

@dataclass
class Argument:
    agent_id: str
    role: DebateRole
    content: str
    evidence: str
    confidence: float
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    
    def to_dict(self):
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "content": self.content,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "timestamp": self.timestamp
        }

@dataclass
class DebateTopic:
    id: str
    question: str
    pro_position: str
    con_position: str
    arguments: List[Argument] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())

@dataclass
class DebateResult:
    topic_id: str
    winner: Optional[DebateRole]
    resolved: bool
    confidence: float
    summary: str
    arguments_summary: str
    
    def to_dict(self):
        return {
            "topic_id": self.topic_id,
            "winner": self.winner.value if self.winner else None,
            "resolved": self.resolved,
            "confidence": self.confidence,
            "summary": self.summary,
            "arguments_summary": self.arguments_summary
        }

class DebatingAgent:
    def __init__(self, agent_id: str, name: str, role: DebateRole):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.client = httpx.AsyncClient(timeout=30)
    
    async def present_argument(self, topic: DebateTopic) -> Argument:
        system_prompt = f"""你是一位资深辩论专家，当前立场是{'正方' if self.role == DebateRole.PRO else '反方'}。
        
请针对以下辩论主题提出有力的论点：
- 辩论问题: {topic.question}
- 你的立场: {topic.pro_position if self.role == DebateRole.PRO else topic.con_position}

要求：
1. 论点要清晰、有逻辑性
2. 提供充分的论据支持
3. 保持专业、理性的语气

输出格式：
论点: [简洁明确的论点陈述]
论据: [支持论点的详细理由或证据]
置信度: [0-1之间的数字，表示你对论点的信心程度]
"""
        
        response = await self._call_ai(system_prompt, "")
        parsed = self._parse_argument(response)
        
        return Argument(
            agent_id=self.agent_id,
            role=self.role,
            content=parsed["论点"],
            evidence=parsed["论据"],
            confidence=parsed["置信度"]
        )
    
    async def counter_argument(self, opponent_argument: Argument) -> Argument:
        system_prompt = """你是一位辩论专家。请针对对方的论点提出有力的反驳。
        
分析步骤：
1. 仔细分析对方论点的核心观点
2. 找出论点中的漏洞、缺陷或不合理之处
3. 提出相反的证据或理由
4. 保持逻辑严谨、论点清晰

输出格式：
反驳论点: [你的反驳观点]
反驳论据: [支持反驳的详细理由或证据]
置信度: [0-1]
"""
        
        prompt = f"""对方论点: {opponent_argument.content}
对方论据: {opponent_argument.evidence}
对方置信度: {opponent_argument.confidence}

请针对以上论点提出有力的反驳。
"""
        
        response = await self._call_ai(prompt, system_prompt)
        parsed = self._parse_counter(response)
        
        return Argument(
            agent_id=self.agent_id,
            role=self.role,
            content=parsed["反驳论点"],
            evidence=parsed["反驳论据"],
            confidence=parsed["置信度"]
        )
    
    async def closing_statement(self, topic: DebateTopic) -> str:
        system_prompt = f"""你是一位辩论专家，当前立场是{'正方' if self.role == DebateRole.PRO else '反方'}。
        
请针对以下辩论主题进行总结陈词：
- 辩论问题: {topic.question}
- 你的立场: {topic.pro_position if self.role == DebateRole.PRO else topic.con_position}

要求：
1. 总结己方的主要论点
2. 强调对方论点的不足
3. 用有力的语言结束陈述

输出格式：
总结陈词: [你的总结陈述]
"""
        
        response = await self._call_ai(system_prompt, "")
        
        if "总结陈词:" in response:
            return response.replace("总结陈词:", "").strip()
        return response.strip()
    
    def _parse_argument(self, response: str) -> Dict[str, Any]:
        lines = response.strip().split('\n')
        result = {"论点": "未解析", "论据": "无", "置信度": 0.5}
        
        for line in lines:
            if line.startswith("论点:"):
                result["论点"] = line.replace("论点:", "").strip()
            elif line.startswith("论据:"):
                result["论据"] = line.replace("论据:", "").strip()
            elif line.startswith("置信度:"):
                try:
                    result["置信度"] = float(line.replace("置信度:", "").strip())
                except:
                    result["置信度"] = 0.5
        
        return result
    
    def _parse_counter(self, response: str) -> Dict[str, Any]:
        lines = response.strip().split('\n')
        result = {"反驳论点": "未解析", "反驳论据": "无", "置信度": 0.5}
        
        for line in lines:
            if line.startswith("反驳论点:"):
                result["反驳论点"] = line.replace("反驳论点:", "").strip()
            elif line.startswith("反驳论据:"):
                result["反驳论据"] = line.replace("反驳论据:", "").strip()
            elif line.startswith("置信度:"):
                try:
                    result["置信度"] = float(line.replace("置信度:", "").strip())
                except:
                    result["置信度"] = 0.5
        
        return result
    
    async def _call_ai(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = await self.client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODEL,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 800
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"⚠️ [{self.name}] AI调用失败: {e}")
            return "论点: AI服务不可用\n论据: 无\n置信度: 0.5"
    
    async def close(self):
        await self.client.aclose()

class JudgeAgent(DebatingAgent):
    def __init__(self, agent_id: str, name: str):
        super().__init__(agent_id, name, DebateRole.JUDGE)
    
    async def judge_debate(self, topic: DebateTopic, pro_agent: DebatingAgent, 
                          con_agent: DebatingAgent) -> DebateResult:
        system_prompt = """你是一位资深辩论评委。请根据双方的论点和论据做出公正裁决。
        
评分标准：
1. 论点的逻辑性和合理性
2. 论据的充分性和可信度
3. 反驳的力度和针对性
4. 整体论证的完整性

输出格式：
获胜方: 正方/反方/平局
置信度: [0-1之间的数字]
理由: [详细说明裁决理由]
总结: [辩论总结报告]
"""
        
        arguments_text = "\n".join([
            f"{arg.role.value}: {arg.content} (论据: {arg.evidence[:50]}...)"
            for arg in topic.arguments
        ])
        
        prompt = f"""辩论主题: {topic.question}
正方立场: {topic.pro_position}
反方立场: {topic.con_position}

辩论记录:
{arguments_text}

请根据以上内容做出裁决。
"""
        
        response = await self._call_ai(prompt, system_prompt)
        result = self._parse_judgment(response)
        
        return DebateResult(
            topic_id=topic.id,
            winner=result["获胜方"],
            resolved=result["获胜方"] != DebateRole.JUDGE,
            confidence=result["置信度"],
            summary=result["总结"],
            arguments_summary=self._generate_arguments_summary(topic)
        )
    
    def _parse_judgment(self, response: str) -> Dict[str, Any]:
        result = {"获胜方": DebateRole.JUDGE, "置信度": 0.5, "总结": "未解析"}
        
        lines = response.strip().split('\n')
        for line in lines:
            if line.startswith("获胜方:"):
                winner_str = line.replace("获胜方:", "").strip()
                if winner_str == "正方":
                    result["获胜方"] = DebateRole.PRO
                elif winner_str == "反方":
                    result["获胜方"] = DebateRole.CON
                else:
                    result["获胜方"] = DebateRole.JUDGE
            elif line.startswith("置信度:"):
                try:
                    result["置信度"] = float(line.replace("置信度:", "").strip())
                except:
                    result["置信度"] = 0.5
            elif line.startswith("总结:"):
                result["总结"] = line.replace("总结:", "").strip()
        
        if result["总结"] == "未解析":
            result["总结"] = response
        
        return result
    
    def _generate_arguments_summary(self, topic: DebateTopic) -> str:
        pro_args = [a for a in topic.arguments if a.role == DebateRole.PRO]
        con_args = [a for a in topic.arguments if a.role == DebateRole.CON]
        
        summary = f"正方提出了 {len(pro_args)} 个论点，反方提出了 {len(con_args)} 个论点。"
        return summary

class DebateManager:
    def __init__(self):
        self.topics: Dict[str, DebateTopic] = {}
    
    def create_topic(self, question: str, pro_position: str, con_position: str) -> DebateTopic:
        topic_id = str(uuid.uuid4())[:8]
        topic = DebateTopic(
            id=topic_id,
            question=question,
            pro_position=pro_position,
            con_position=con_position
        )
        self.topics[topic_id] = topic
        print(f"\n📋 创建辩论主题: {topic_id} - {question}")
        return topic
    
    async def start_debate(self, topic_id: str, pro_agent: DebatingAgent, 
                          con_agent: DebatingAgent, judge_agent: JudgeAgent,
                          max_rounds: int = 2) -> DebateResult:
        topic = self.topics.get(topic_id)
        if not topic:
            print(f"⚠️ 辩论主题不存在: {topic_id}")
            return None
        
        print(f"\n{'='*80}")
        print(f"🎤 开始辩论: {topic.question}")
        print(f"正方立场: {topic.pro_position}")
        print(f"反方立场: {topic.con_position}")
        print(f"预计轮数: {max_rounds}")
        print('='*80)
        
        print(f"\n🎬 【开场陈述】")
        print(f"📢 正方 ({pro_agent.name}):")
        opening_pro = await pro_agent.present_argument(topic)
        topic.arguments.append(opening_pro)
        print(f"论点: {opening_pro.content}")
        print(f"论据: {opening_pro.evidence[:100]}...")
        
        print(f"\n🔊 反方 ({con_agent.name}):")
        opening_con = await con_agent.present_argument(topic)
        topic.arguments.append(opening_con)
        print(f"论点: {opening_con.content}")
        print(f"论据: {opening_con.evidence[:100]}...")
        
        for round_num in range(max_rounds):
            print(f"\n{'='*80}")
            print(f"⚔️ 第 {round_num + 1} 轮辩论")
            print('='*80)
            
            print(f"\n📢 正方 ({pro_agent.name}) 提出论点:")
            pro_arg = await pro_agent.present_argument(topic)
            topic.arguments.append(pro_arg)
            print(f"论点: {pro_arg.content}")
            print(f"论据: {pro_arg.evidence[:100]}...")
            print(f"置信度: {pro_arg.confidence:.2f}")
            
            print(f"\n🔊 反方 ({con_agent.name}) 反驳:")
            con_counter = await con_agent.counter_argument(pro_arg)
            topic.arguments.append(con_counter)
            print(f"反驳论点: {con_counter.content}")
            print(f"反驳论据: {con_counter.evidence[:100]}...")
            print(f"置信度: {con_counter.confidence:.2f}")
            
            print(f"\n📢 正方 ({pro_agent.name}) 再反驳:")
            pro_rebuttal = await pro_agent.counter_argument(con_counter)
            topic.arguments.append(pro_rebuttal)
            print(f"再反驳: {pro_rebuttal.content}")
            print(f"论据: {pro_rebuttal.evidence[:100]}...")
            print(f"置信度: {pro_rebuttal.confidence:.2f}")
        
        print(f"\n{'='*80}")
        print(f"🎯 【总结陈词】")
        print('='*80)
        
        print(f"\n📢 正方 ({pro_agent.name}) 总结:")
        pro_closing = await pro_agent.closing_statement(topic)
        print(pro_closing[:200] + "..." if len(pro_closing) > 200 else pro_closing)
        
        print(f"\n🔊 反方 ({con_agent.name}) 总结:")
        con_closing = await con_agent.closing_statement(topic)
        print(con_closing[:200] + "..." if len(con_closing) > 200 else con_closing)
        
        print(f"\n{'='*80}")
        print(f"⚖️ 【评委裁决】")
        print('='*80)
        
        result = await judge_agent.judge_debate(topic, pro_agent, con_agent)
        
        print(f"\n🏆 获胜方: {'正方' if result.winner == DebateRole.PRO else '反方' if result.winner == DebateRole.CON else '平局'}")
        print(f"置信度: {result.confidence:.2f}")
        print(f"\n📝 辩论总结:")
        print(result.summary)
        
        return result
    
    def visualize_debate(self, result: DebateResult):
        topic = self.topics.get(result.topic_id)
        if not topic:
            return
        
        print("\n" + "="*80)
        print("📊 辩论结果可视化")
        print("="*80)
        
        pro_args = [a for a in topic.arguments if a.role == DebateRole.PRO]
        con_args = [a for a in topic.arguments if a.role == DebateRole.CON]
        
        print(f"\n辩论主题: {topic.question}")
        print(f"获胜方: {'✅ 正方' if result.winner == DebateRole.PRO else '✅ 反方' if result.winner == DebateRole.CON else '➡️ 平局'}")
        print(f"置信度: {result.confidence:.2f}")
        print(f"论点总数: 正方 {len(pro_args)} 个 | 反方 {len(con_args)} 个")
        
        print("\n📢 正方论点:")
        for i, arg in enumerate(pro_args, 1):
            bar_length = int(arg.confidence * 20)
            print(f"\n{i}. {arg.content}")
            print(f"   置信度: {'█' * bar_length} ({arg.confidence:.2f})")
            print(f"   论据: {arg.evidence[:50]}...")
        
        print("\n🔊 反方论点:")
        for i, arg in enumerate(con_args, 1):
            bar_length = int(arg.confidence * 20)
            print(f"\n{i}. {arg.content}")
            print(f"   置信度: {'█' * bar_length} ({arg.confidence:.2f})")
            print(f"   论据: {arg.evidence[:50]}...")

async def main():
    print("="*80)
    print("🏫 L4-06: Debate（辩论机制）")
    print("="*80)
    
    pro_agent = DebatingAgent("agent_pro", "人工智能伦理专家", DebateRole.PRO)
    con_agent = DebatingAgent("agent_con", "法律专家", DebateRole.CON)
    judge_agent = JudgeAgent("agent_judge", "资深辩论评委")
    
    print(f"\n🤖 辩论参与方:")
    print(f"  - 正方: {pro_agent.name}")
    print(f"  - 反方: {con_agent.name}")
    print(f"  - 评委: {judge_agent.name}")
    
    print("\n" + "="*80)
    print("⚔️ 演示: AI法律人格辩论")
    print("="*80)
    
    debate_manager = DebateManager()
    
    topic = debate_manager.create_topic(
        question="人工智能是否应该被赋予法律人格？",
        pro_position="应该赋予人工智能法律人格，因为AI已具备一定的自主决策能力",
        con_position="不应该赋予人工智能法律人格，因为AI缺乏真正的意识和责任能力"
    )
    
    result = await debate_manager.start_debate(
        topic_id=topic.id,
        pro_agent=pro_agent,
        con_agent=con_agent,
        judge_agent=judge_agent,
        max_rounds=2
    )
    
    if result:
        debate_manager.visualize_debate(result)
    
    print("\n" + "="*80)
    print("✅ Debate 机制演示完成")
    print("="*80)
    
    await pro_agent.close()
    await con_agent.close()
    await judge_agent.close()

if __name__ == "__main__":
    asyncio.run(main())