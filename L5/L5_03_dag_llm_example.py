import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import json

from L5_03_dag_scheduler import DAGBuilder, DAGScheduler, TaskStatus


class MockLLMAgent:
    """模拟大模型调用的Agent"""
    
    def __init__(self, model_name: str = "mock-gpt-4"):
        self.model_name = model_name
        self.initial_topic = None
    
    def set_initial_topic(self, topic: str):
        """设置初始主题"""
        self.initial_topic = topic
    
    async def analyze_topic(self, input_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """分析主题，提取关键词和要点"""
        topic = input_data.get("topic") if input_data else self.initial_topic
        if not topic:
            topic = "AI技术发展趋势"
        
        await asyncio.sleep(1.5)
        print(f"🤖 [{self.model_name}] 正在分析主题: {topic}")
        
        return {
            "topic": topic,
            "keywords": ["AI Agent", "大模型", "自动化", "内容创作"],
            "key_points": [
                "AI Agent的定义和特点",
                "大模型在内容创作中的应用",
                "自动化内容生成的优势",
                "未来发展趋势"
            ],
            "target_audience": "技术爱好者、开发者、内容创作者",
            "content_type": "技术文章"
        }
    
    async def generate_outline(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """根据分析结果生成内容大纲"""
        await asyncio.sleep(1.2)
        print(f"🤖 [{self.model_name}] 正在生成大纲")
        
        return {
            "title": f"{analysis['topic']} - 全面指南",
            "outline": [
                {"section": "一、引言", "word_count": 200},
                {"section": "二、核心概念", "subsections": ["定义", "特点", "应用场景"], "word_count": 500},
                {"section": "三、技术实现", "subsections": ["架构设计", "关键技术", "最佳实践"], "word_count": 800},
                {"section": "四、案例分析", "word_count": 400},
                {"section": "五、总结与展望", "word_count": 200}
            ],
            "estimated_total_words": 2100
        }
    
    async def write_content(self, outline: Dict[str, Any]) -> Dict[str, Any]:
        """根据大纲撰写具体内容"""
        await asyncio.sleep(2.0)
        print(f"🤖 [{self.model_name}] 正在撰写内容")
        
        content = {}
        for item in outline["outline"]:
            section = item["section"]
            content[section] = f"这是关于「{section}」的详细内容。根据大纲要求，本部分预计{item['word_count']}字左右。"
            if "subsections" in item:
                content[section] += "\n\n" + "\n\n".join([
                    f"- **{sub}**: 这是{sub}的详细描述..." 
                    for sub in item["subsections"]
                ])
        
        return {
            "title": outline["title"],
            "content": content,
            "total_sections": len(outline["outline"]),
            "actual_word_count": 2200
        }
    
    async def review_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """审查内容质量和合规性"""
        await asyncio.sleep(0.8)
        print(f"🤖 [{self.model_name}] 正在审查内容")
        
        issues = []
        if content["actual_word_count"] > 2000:
            issues.append("建议精简内容，控制在2000字以内")
        
        return {
            "passed": len(issues) == 0,
            "quality_score": 92,
            "issues": issues,
            "suggestions": ["增加更多实际案例", "添加数据支撑", "优化段落结构"]
        }
    
    async def format_content(self, write: Dict[str, Any], review: Dict[str, Any]) -> str:
        """优化内容格式和排版"""
        content = write
        await asyncio.sleep(0.6)
        print(f"🤖 [{self.model_name}] 正在格式化内容")
        
        markdown = f"# {content['title']}\n\n"
        markdown += f"> 👁️ 质量评分: {review['quality_score']}/100\n\n"
        
        for section, section_content in content["content"].items():
            markdown += f"## {section}\n\n"
            markdown += section_content + "\n\n"
        
        if review["suggestions"]:
            markdown += "---\n\n"
            markdown += "## ✅ 优化建议\n\n"
            for i, suggestion in enumerate(review["suggestions"], 1):
                markdown += f"{i}. {suggestion}\n"
        
        return markdown


async def main():
    print("="*80)
    print("🏭 L5-03: DAG Agent 实战 - 智能内容创作流程")
    print("="*80)
    
    llm_agent = MockLLMAgent()
    
    user_topic = "AI Agent在内容创作中的应用与实践"
    
    async def init_input():
        return {"topic": user_topic}
    
    print(f"\n📝 用户输入主题: {user_topic}")
    print("\n" + "-"*60)
    print("构建内容创作DAG流程")
    print("-"*60)
    
    dag = DAGBuilder("智能内容创作流程") \
        .add_task("init", "初始化输入", init_input, priority=11) \
        .add_task("analyze", "主题分析", llm_agent.analyze_topic, dependencies=["init"], priority=10) \
        .add_task("outline", "大纲生成", llm_agent.generate_outline, dependencies=["analyze"], priority=8) \
        .add_task("write", "内容写作", llm_agent.write_content, dependencies=["outline"], priority=6) \
        .add_task("review", "内容审查", llm_agent.review_content, dependencies=["write"], priority=4) \
        .add_task("format", "格式优化", llm_agent.format_content, dependencies=["write", "review"], priority=2) \
        .build()
    
    print(f"\n📊 DAG任务流程:")
    for node in dag.get_nodes():
        print(f"  - {node.task_id}: {node.name} (依赖: {node.dependencies})")
    
    print("\n" + "-"*60)
    print("启动DAG调度执行")
    print("-"*60)
    
    scheduler = DAGScheduler(max_concurrent=2)
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
        
        if result.output:
            if isinstance(result.output, str):
                preview = result.output[:100] + "..." if len(result.output) > 100 else result.output
                print(f"   输出预览:\n{preview}")
            elif isinstance(result.output, dict):
                keys = list(result.output.keys())[:3]
                print(f"   输出键: {keys}")
    
    final_output = results.get("format")
    if final_output and final_output.status == TaskStatus.COMPLETED:
        print("\n" + "-"*60)
        print("📄 最终生成的内容")
        print("-"*60)
        print(final_output.output)
    
    success_count = sum(1 for r in results.values() if r.status == TaskStatus.COMPLETED)
    total_count = len(results)
    print(f"\n📈 执行统计: {success_count}/{total_count} 任务成功完成")
    
    print("\n" + "="*80)
    print("✅ DAG Agent内容创作演示完成")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())