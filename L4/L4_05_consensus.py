import asyncio
from typing import Dict, List, Optional, Any, Callable
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

class VoteStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"

class VotingStrategy(Enum):
    MAJORITY = "majority"
    UNANIMOUS = "unanimous"
    SUPERMAJORITY = "supermajority"
    RANKED = "ranked"

@dataclass
class Vote:
    agent_id: str
    option: str
    confidence: float
    rationale: str
    status: VoteStatus
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    
    def to_dict(self):
        return {
            "agent_id": self.agent_id,
            "option": self.option,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "status": self.status.value,
            "timestamp": self.timestamp
        }

@dataclass
class Poll:
    id: str
    question: str
    options: List[str]
    votes: List[Vote] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    closed: bool = False

@dataclass
class ConsensusResult:
    question: str
    options: List[str]
    votes: List[Vote]
    winning_option: str
    consensus_reached: bool
    confidence: float
    summary: str
    
    def to_dict(self):
        return {
            "question": self.question,
            "options": self.options,
            "votes": [v.to_dict() for v in self.votes],
            "winning_option": self.winning_option,
            "consensus_reached": self.consensus_reached,
            "confidence": self.confidence,
            "summary": self.summary
        }

class VotingAgent:
    def __init__(self, agent_id: str, name: str, expertise_domain: str, 
                 track_record: List[Dict] = None, credibility: float = 0.5):
        self.agent_id = agent_id
        self.name = name
        self.expertise_domain = expertise_domain
        self.track_record = track_record if track_record else []
        self._credibility = credibility
        self.client = httpx.AsyncClient(timeout=30)
    
    def get_credibility(self) -> float:
        if not self.track_record:
            return self._credibility
        
        correct_count = sum(1 for r in self.track_record if r.get("correct", False))
        accuracy = correct_count / len(self.track_record)
        
        return min(accuracy * 0.8 + self._credibility * 0.2, 1.0)
    
    async def vote(self, question: str, options: List[str]) -> Vote:
        system_prompt = f"""你是一位{self.expertise_domain}领域的专家。请根据你的专业知识对以下问题进行分析并投票。

分析步骤：
1. 仔细分析问题和所有选项
2. 评估每个选项的优缺点
3. 选择你认为最合适的选项
4. 给出你的置信度（0-1）和理由

输出格式：
选项: [选项内容]
置信度: [0-1之间的数字]
理由: [详细说明你的选择理由]
"""
        
        prompt = f"""问题: {question}

选项:
{chr(10).join([f"{i+1}. {opt}" for i, opt in enumerate(options)])}

请根据以上格式输出你的投票。
"""
        
        response = await self._call_ai(prompt, system_prompt)
        
        try:
            lines = response.strip().split('\n')
            option = ""
            confidence = 0.5
            rationale = ""
            
            for line in lines:
                if line.startswith("选项:"):
                    option = line.replace("选项:", "").strip()
                elif line.startswith("置信度:"):
                    confidence = float(line.replace("置信度:", "").strip())
                elif line.startswith("理由:"):
                    rationale = line.replace("理由:", "").strip()
            
            if not option:
                option = options[0]
            
            return Vote(
                agent_id=self.agent_id,
                option=option,
                confidence=min(max(confidence, 0.0), 1.0),
                rationale=rationale,
                status=VoteStatus.SUBMITTED
            )
        except Exception as e:
            print(f"⚠️ [{self.name}] 解析投票失败: {e}")
            return Vote(
                agent_id=self.agent_id,
                option=options[0],
                confidence=0.5,
                rationale="解析失败，使用默认选项",
                status=VoteStatus.SUBMITTED
            )
    
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
            return "选项: 默认选项\n置信度: 0.5\n理由: AI服务不可用"
    
    async def close(self):
        await self.client.aclose()

class ConsensusManager:
    def __init__(self, strategy: VotingStrategy = VotingStrategy.MAJORITY, 
                 threshold: float = 0.6, max_rounds: int = 3):
        self.polls: Dict[str, Poll] = {}
        self.strategy = strategy
        self.consensus_threshold = threshold
        self.max_rounds = max_rounds
    
    def create_poll(self, question: str, options: List[str]) -> str:
        poll_id = str(uuid.uuid4())[:8]
        self.polls[poll_id] = Poll(
            id=poll_id,
            question=question,
            options=options
        )
        print(f"\n📋 创建投票: {poll_id} - {question}")
        return poll_id
    
    async def collect_votes(self, poll_id: str, agents: List[VotingAgent]) -> List[Vote]:
        if poll_id not in self.polls:
            print(f"⚠️ 投票不存在: {poll_id}")
            return []
        
        poll = self.polls[poll_id]
        if poll.closed:
            print(f"⚠️ 投票已关闭: {poll_id}")
            return []
        
        print(f"\n🗳️ 正在收集投票...")
        tasks = [agent.vote(poll.question, poll.options) for agent in agents]
        votes = await asyncio.gather(*tasks)
        
        for vote in votes:
            poll.votes.append(vote)
            print(f"  ✓ [{vote.agent_id}] 投票: {vote.option} (置信度: {vote.confidence:.2f})")
        
        return votes
    
    async def aggregate_results(self, poll_id: str) -> Optional[ConsensusResult]:
        if poll_id not in self.polls:
            return None
        
        poll = self.polls[poll_id]
        if not poll.votes:
            return None
        
        vote_counts: Dict[str, float] = {}
        total_weight = 0.0
        
        for vote in poll.votes:
            agent = next((a for a in [] if a.agent_id == vote.agent_id), None)
            credibility = agent.get_credibility() if agent else 0.5
            weight = credibility * vote.confidence
            
            if vote.option not in vote_counts:
                vote_counts[vote.option] = 0.0
            vote_counts[vote.option] += weight
            total_weight += weight
        
        if not vote_counts:
            return None
        
        winning_option = max(vote_counts, key=vote_counts.get)
        winning_weight = vote_counts[winning_option]
        confidence = winning_weight / total_weight if total_weight > 0 else 0.0
        
        consensus_reached = self._check_consensus(vote_counts, total_weight)
        
        summary = await self._generate_summary(poll, vote_counts, confidence)
        
        return ConsensusResult(
            question=poll.question,
            options=poll.options,
            votes=poll.votes,
            winning_option=winning_option,
            consensus_reached=consensus_reached,
            confidence=confidence,
            summary=summary
        )
    
    def _check_consensus(self, vote_counts: Dict[str, float], total_weight: float) -> bool:
        if not vote_counts or total_weight == 0:
            return False
        
        if self.strategy == VotingStrategy.UNANIMOUS:
            return len(vote_counts) == 1
        
        elif self.strategy == VotingStrategy.SUPERMAJORITY:
            max_weight = max(vote_counts.values())
            return max_weight / total_weight >= 0.67
        
        else:
            max_weight = max(vote_counts.values())
            return max_weight / total_weight >= self.consensus_threshold
    
    async def _generate_summary(self, poll: Poll, vote_counts: Dict[str, float], 
                                confidence: float) -> str:
        system_prompt = "你是一位决策分析专家。请根据投票结果生成一份清晰的总结报告。"
        
        votes_text = "\n".join([
            f"- {vote.agent_id}: {vote.option} (置信度: {vote.confidence:.2f}, 理由: {vote.rationale})"
            for vote in poll.votes
        ])
        
        prompt = f"""投票问题: {poll.question}

投票选项: {poll.options}

投票详情:
{votes_text}

投票统计: {vote_counts}

共识置信度: {confidence:.2f}

请生成一份简明扼要的总结报告。
"""
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 500
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"共识结果: {max(vote_counts, key=vote_counts.get)}，置信度: {confidence:.2f}"
    
    async def multi_round_consensus(self, question: str, options: List[str], 
                                   agents: List[VotingAgent]) -> ConsensusResult:
        print(f"\n🔄 开始多轮共识协商 (最多 {self.max_rounds} 轮)")
        
        for round_num in range(self.max_rounds):
            print(f"\n{'='*60}")
            print(f"第 {round_num + 1} 轮协商")
            print('='*60)
            
            poll_id = self.create_poll(question, options)
            await self.collect_votes(poll_id, agents)
            result = await self.aggregate_results(poll_id)
            
            if result:
                print(f"\n📊 本轮结果:")
                print(f"   获胜选项: {result.winning_option}")
                print(f"   共识达成: {'✅ 是' if result.consensus_reached else '❌ 否'}")
                print(f"   置信度: {result.confidence:.2f}")
                
                if result.consensus_reached:
                    print(f"\n🎉 第 {round_num + 1} 轮达成共识!")
                    return result
                
                if round_num < self.max_rounds - 1:
                    print(f"\n💬 未达成共识，进行下一轮讨论...")
                    question = await self._refine_question(question, options, result.votes)
        
        print(f"\n⏰ 已达到最大轮数，返回最终结果")
        return result
    
    async def _refine_question(self, question: str, options: List[str], 
                               votes: List[Vote]) -> str:
        system_prompt = "你是一位会议主持人。请根据投票结果，帮助重新表述问题以促进进一步讨论。"
        
        votes_text = "\n".join([
            f"- {vote.agent_id}: {vote.option} (理由: {vote.rationale})"
            for vote in votes
        ])
        
        prompt = f"""原问题: {question}

原选项: {options}

上一轮投票情况:
{votes_text}

请重新表述问题，突出争议点，帮助达成共识。
"""
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.5,
                        "max_tokens": 300
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return question
    
    def visualize_results(self, result: ConsensusResult):
        print("\n" + "="*60)
        print("📊 投票结果可视化")
        print("="*60)
        
        vote_counts = {}
        for vote in result.votes:
            if vote.option not in vote_counts:
                vote_counts[vote.option] = []
            vote_counts[vote.option].append(vote.confidence)
        
        print(f"\n问题: {result.question}")
        print(f"共识达成: {'✅' if result.consensus_reached else '❌'}")
        print(f"获胜选项: {result.winning_option}")
        print(f"置信度: {result.confidence:.2f}")
        
        print("\n详细投票情况:")
        for option, confidences in vote_counts.items():
            avg_confidence = sum(confidences) / len(confidences)
            bar_length = int(avg_confidence * 30)
            print(f"\n{option}:")
            print(f"  投票数: {len(confidences)} 票")
            print(f"  平均置信度: {'█' * bar_length} ({avg_confidence:.2f})")
            
            for vote in result.votes:
                if vote.option == option:
                    print(f"    - [{vote.agent_id}]: {vote.confidence:.2f} - {vote.rationale[:30]}...")
        
        print(f"\n📝 总结: {result.summary}")

async def main():
    print("="*80)
    print("🏫 L4-05: Consensus（共识机制）")
    print("="*80)
    
    tech_agents = [
        VotingAgent(
            "agent_arch",
            "架构专家",
            "系统架构",
            track_record=[{"correct": True}, {"correct": True}, {"correct": False}],
            credibility=0.85
        ),
        VotingAgent(
            "agent_perf",
            "性能专家",
            "性能优化",
            track_record=[{"correct": True}, {"correct": True}, {"correct": True}],
            credibility=0.90
        ),
        VotingAgent(
            "agent_sec",
            "安全专家",
            "网络安全",
            track_record=[{"correct": True}, {"correct": False}, {"correct": True}],
            credibility=0.80
        ),
        VotingAgent(
            "agent_cost",
            "成本专家",
            "成本评估",
            track_record=[{"correct": False}, {"correct": True}, {"correct": True}],
            credibility=0.75
        )
    ]
    
    print(f"\n🤖 参与共识的专家:")
    for agent in tech_agents:
        print(f"  - {agent.name} ({agent.expertise_domain}) - 可信度: {agent.get_credibility():.2f}")
    
    print("\n" + "="*80)
    print("📌 演示1: 单轮共识投票")
    print("="*80)
    
    question = "推荐哪种技术方案作为新项目的架构选型？"
    options = [
        "方案A: 微服务架构 - 高可扩展性，适合复杂系统",
        "方案B: 单体架构 - 简单高效，适合中小型项目",
        "方案C: 混合架构 - 核心模块单体，外围服务微服务"
    ]
    
    consensus_manager = ConsensusManager(strategy=VotingStrategy.MAJORITY, threshold=0.5)
    poll_id = consensus_manager.create_poll(question, options)
    await consensus_manager.collect_votes(poll_id, tech_agents)
    result = await consensus_manager.aggregate_results(poll_id)
    
    if result:
        consensus_manager.visualize_results(result)
    
    print("\n" + "="*80)
    print("🔄 演示2: 多轮共识协商")
    print("="*80)
    
    question2 = "是否应该采用微服务架构？"
    options2 = ["是，采用微服务架构", "否，采用单体架构", "折中方案，混合架构"]
    
    consensus_manager2 = ConsensusManager(strategy=VotingStrategy.MAJORITY, threshold=0.6, max_rounds=2)
    result2 = await consensus_manager2.multi_round_consensus(question2, options2, tech_agents)
    
    if result2:
        consensus_manager2.visualize_results(result2)
    
    print("\n" + "="*80)
    print("✅ Consensus 机制演示完成")
    print("="*80)
    
    for agent in tech_agents:
        await agent.close()

if __name__ == "__main__":
    asyncio.run(main())