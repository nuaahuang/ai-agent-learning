import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import json
import os
import httpx
from dotenv import load_dotenv

from L5_03_dag_scheduler import DAGBuilder, DAGScheduler, TaskStatus

load_dotenv()
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("MODEL", "deepseek-chat")


class RealLLMAgent:
    """真正调用大模型的Agent"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60)
    
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
                    "max_tokens": 1000
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"⚠️ AI调用失败: {e}")
            return f"错误: {str(e)}"
    
    async def analyze_topic(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析用户问题，提取关键信息"""
        topic = input_data.get("topic", "")
        print(f"🤖 正在分析问题: {topic}")
        
        system_prompt = """你是一位专业的问题分析专家。请分析用户的问题并提取关键信息。
        
输出格式：
主题: [问题主题]
关键词: [关键词1, 关键词2, 关键词3]
问题类型: [事实性问题/分析性问题/建议性问题/创意性问题]
核心需求: [用户的核心需求描述]
"""
        
        prompt = f"请分析以下问题：{topic}"
        response = await self._call_ai(prompt, system_prompt)
        
        result = {
            "topic": topic,
            "keywords": [],
            "question_type": "未知",
            "core_need": ""
        }
        
        lines = response.split('\n')
        for line in lines:
            if line.startswith("主题:"):
                result["topic"] = line.replace("主题:", "").strip()
            elif line.startswith("关键词:"):
                keywords_str = line.replace("关键词:", "").strip()
                result["keywords"] = [k.strip() for k in keywords_str.split("、") if k.strip()]
            elif line.startswith("问题类型:"):
                result["question_type"] = line.replace("问题类型:", "").strip()
            elif line.startswith("核心需求:"):
                result["core_need"] = line.replace("核心需求:", "").strip()
        
        return result
    
    async def search_knowledge(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """基于分析结果搜索知识库（模拟）"""
        print(f"🔍 正在搜索相关知识...")
        
        system_prompt = """你是一位知识库专家。请根据用户的问题和关键词，提供相关的知识信息。
        
输出格式：
相关知识点:
1. [知识点1]
2. [知识点2]
3. [知识点3]

参考资料:
- [资料1]
- [资料2]
"""
        
        prompt = f"问题: {analysis['topic']}\n关键词: {analysis['keywords']}\n请提供相关知识。"
        response = await self._call_ai(prompt, system_prompt)
        
        return {
            "knowledge": response,
            "source_count": 3,
            "keywords": analysis['keywords']
        }
    
    async def generate_answer(self, knowledge: Dict[str, Any]) -> Dict[str, Any]:
        """生成详细回答"""
        print(f"✍️ 正在生成回答...")
        
        system_prompt = """你是一位专业顾问。请根据提供的知识信息，为用户提供详细、专业的回答。
        
要求：
1. 回答要结构清晰，分点说明
2. 使用用户容易理解的语言
3. 引用相关知识
4. 提供实用建议
"""
        
        prompt = f"问题: {knowledge.get('keywords', [])}\n参考知识:\n{knowledge['knowledge']}\n请给出详细回答。"
        response = await self._call_ai(prompt, system_prompt)
        
        return {
            "answer": response,
            "confidence": 0.95,
            "sources": knowledge.get("source_count", 0)
        }
    
    async def review_and_refine(self, answer: Dict[str, Any]) -> Dict[str, Any]:
        """审查并优化回答"""
        print(f"🔎 正在审查回答质量...")
        
        system_prompt = """你是一位内容审查专家。请审查以下回答并提出优化建议。
        
输出格式：
质量评分: [0-100]
问题类型匹配度: [高/中/低]
完整性: [完整/部分完整/不完整]
优化建议:
1. [建议1]
2. [建议2]
3. [建议3]
"""
        
        prompt = f"请审查以下回答:\n{answer['answer']}"
        response = await self._call_ai(prompt, system_prompt)
        
        score = 0
        suggestions = []
        
        lines = response.split('\n')
        for line in lines:
            if line.startswith("质量评分:"):
                try:
                    score = int(line.replace("质量评分:", "").strip())
                except:
                    score = 85
            elif line.startswith("[建议"):
                suggestions.append(line.replace("[建议", "").replace("]", "").strip())
        
        return {
            "original_answer": answer["answer"],
            "quality_score": score,
            "suggestions": suggestions,
            "refined": len(suggestions) == 0
        }
    
    async def format_output(self, review: Dict[str, Any]) -> str:
        """格式化最终输出"""
        print(f"📝 正在格式化输出...")
        
        answer = review["original_answer"]
        score = review["quality_score"]
        
        markdown = f"""# 智能问答结果

## 📋 问题分析

**质量评分**: {score}/100
**回答来源**: AI大模型

---

## 📝 回答内容

{answer}

---

"""
        
        if review["suggestions"]:
            markdown += "## 💡 优化建议\n\n"
            for i, suggestion in enumerate(review["suggestions"], 1):
                markdown += f"{i}. {suggestion}\n"
        
        return markdown
    
    async def close(self):
        await self.client.aclose()


async def main():
    print("="*80)
    print("🏭 L5-03: DAG Agent - 真实大模型调用演示")
    print("="*80)
    
    llm_agent = RealLLMAgent()
    
    user_question = input("\n请输入你的问题: ") or "AI Agent是什么？它有什么应用场景？"
    
    print(f"\n📝 用户问题: {user_question}")
    print("\n" + "-"*60)
    print("构建智能问答DAG流程")
    print("-"*60)
    
    async def init_input():
        return {"topic": user_question}
    
    dag = DAGBuilder("智能问答流程") \
        .add_task("init", "初始化问题", init_input, priority=11) \
        .add_task("analyze", "问题分析", llm_agent.analyze_topic, dependencies=["init"], priority=10) \
        .add_task("search", "知识搜索", llm_agent.search_knowledge, dependencies=["analyze"], priority=9) \
        .add_task("answer", "生成回答", llm_agent.generate_answer, dependencies=["search"], priority=8) \
        .add_task("review", "质量审查", llm_agent.review_and_refine, dependencies=["answer"], priority=7) \
        .add_task("format", "格式输出", llm_agent.format_output, dependencies=["review"], priority=6) \
        .build()
    
    print(f"\n📊 DAG任务流程:")
    for node in dag.get_nodes():
        print(f"  - {node.task_id}: {node.name} (依赖: {node.dependencies})")
    
    print("\n" + "-"*60)
    print("启动DAG调度执行")
    print("-"*60)
    
    scheduler = DAGScheduler(max_concurrent=1)
    results = await scheduler.execute(dag)
    
    print("\n" + "-"*60)
    print("执行结果汇总")
    print("-"*60)
    
    for task_id, result in results.items():
        node = dag.get_node(task_id)
        duration = result.end_time - result.start_time if result.start_time and result.end_time else 0
        status_icon = "✅" if result.status == TaskStatus.COMPLETED else "❌"
        print(f"\n{status_icon} {node.name}:")
        print(f"   状态: {result.status.value}")
        print(f"   耗时: {duration:.2f}秒")
    
    final_output = results.get("format")
    if final_output and final_output.status == TaskStatus.COMPLETED:
        print("\n" + "="*80)
        print("📄 最终输出")
        print("="*80)
        print(final_output.output)
    
    success_count = sum(1 for r in results.values() if r.status == TaskStatus.COMPLETED)
    total_count = len(results)
    print(f"\n📈 执行统计: {success_count}/{total_count} 任务成功完成")
    
    await llm_agent.close()
    
    print("\n" + "="*80)
    print("✅ DAG Agent大模型调用演示完成")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())