"""
L7-03: 垂直领域 Agent（Domain-Specific Agent）—— 金融分析 Agent Demo

以"金融投研分析"为例，综合演示垂直领域 Agent 的五大构建要素：
  ① 领域知识库（财务指标知识 + RAG式检索）
  ② 专业工具集（行情查询、财务指标计算、风险评估）
  ③ 领域提示词（金融分析师角色设定）
  ④ 合规护栏（免责声明、不构成投资建议、风险提示）
  ⑤ 评估体系（数据溯源、置信度）

这是 L1-L7 能力的综合应用：ReAct推理 + 工具调用 + 护栏 + 领域知识。
不依赖真实金融API，用模拟数据演示工程流程。
"""
import asyncio
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field


# ============================================================
# ① 领域知识库
# ============================================================
DOMAIN_KNOWLEDGE = {
    "市盈率": "市盈率(PE)=股价/每股收益。反映投资回本年限，行业不同合理区间不同。一般15-25为合理。",
    "市净率": "市净率(PB)=股价/每股净资产。低于1可能被低估，但需结合行业。",
    "ROE": "净资产收益率(ROE)=净利润/净资产。衡量股东回报，>15%为优秀。",
    "毛利率": "毛利率=(营收-成本)/营收。反映产品竞争力，越高越好。",
    "负债率": "资产负债率=总负债/总资产。>70%偿债压力大，需警惕。",
}


class DomainKnowledgeBase:
    """领域知识库：模拟 RAG 检索"""

    def __init__(self, knowledge: Dict[str, str]):
        self.knowledge = knowledge

    def retrieve(self, query: str) -> List[Dict[str, str]]:
        results = []
        for term, explanation in self.knowledge.items():
            if term in query:
                results.append({"term": term, "content": explanation, "source": "金融指标知识库"})
        return results


# ============================================================
# ② 专业工具集
# ============================================================
@dataclass
class StockData:
    code: str
    name: str
    price: float
    eps: float           # 每股收益
    bps: float           # 每股净资产
    net_profit: float    # 净利润(亿)
    net_assets: float    # 净资产(亿)
    revenue: float       # 营收(亿)
    cost: float          # 成本(亿)
    total_debt: float    # 总负债(亿)
    total_assets: float  # 总资产(亿)


# 模拟行情数据库
MOCK_MARKET = {
    "600519": StockData("600519", "贵州茅台", 1680.0, 59.5, 180.2, 747.0, 2100.0, 1500.0, 220.0, 300.0, 2500.0),
    "000001": StockData("000001", "平安银行", 11.2, 2.3, 18.5, 460.0, 5000.0, 1300.0, 800.0, 52000.0, 55000.0),
}


class FinancialTools:
    """专业金融工具集"""

    @staticmethod
    async def get_quote(code: str) -> Optional[StockData]:
        await asyncio.sleep(0.02)
        return MOCK_MARKET.get(code)

    @staticmethod
    def calc_pe(data: StockData) -> float:
        return round(data.price / data.eps, 2) if data.eps else 0.0

    @staticmethod
    def calc_pb(data: StockData) -> float:
        return round(data.price / data.bps, 2) if data.bps else 0.0

    @staticmethod
    def calc_roe(data: StockData) -> float:
        return round(data.net_profit / data.net_assets * 100, 2) if data.net_assets else 0.0

    @staticmethod
    def calc_gross_margin(data: StockData) -> float:
        return round((data.revenue - data.cost) / data.revenue * 100, 2) if data.revenue else 0.0

    @staticmethod
    def calc_debt_ratio(data: StockData) -> float:
        return round(data.total_debt / data.total_assets * 100, 2) if data.total_assets else 0.0

    @classmethod
    def assess_risk(cls, data: StockData) -> Dict[str, Any]:
        debt_ratio = cls.calc_debt_ratio(data)
        roe = cls.calc_roe(data)
        risks = []
        if debt_ratio > 70:
            risks.append(f"负债率偏高({debt_ratio}%)")
        if roe < 10:
            risks.append(f"ROE偏低({roe}%)")
        level = "高" if len(risks) >= 2 else "中" if risks else "低"
        return {"level": level, "risks": risks}


# ============================================================
# ③ 领域提示词
# ============================================================
DOMAIN_SYSTEM_PROMPT = """你是一名专业的金融投研分析师，具备以下特点：
- 基于财务数据客观分析，引用具体指标
- 使用专业术语但保持通俗易懂
- 指出潜在风险，不回避问题
- 严格遵守合规要求"""


# ============================================================
# ④ 合规护栏
# ============================================================
class ComplianceGuard:
    """金融合规护栏"""

    DISCLAIMER = "⚠️ 风险提示：以上分析仅供参考，不构成任何投资建议。市场有风险，投资需谨慎。"

    SENSITIVE_PATTERNS = ["稳赚", "保证收益", "必涨", "内幕", "包赚不赔"]

    @classmethod
    def check_output(cls, text: str) -> Dict[str, Any]:
        violations = [p for p in cls.SENSITIVE_PATTERNS if p in text]
        return {"passed": len(violations) == 0, "violations": violations}

    @classmethod
    def add_disclaimer(cls, text: str) -> str:
        return f"{text}\n\n{cls.DISCLAIMER}"


# ============================================================
# 垂直领域 Agent（综合五大要素）
# ============================================================
class FinancialAnalysisAgent:
    def __init__(self):
        self.kb = DomainKnowledgeBase(DOMAIN_KNOWLEDGE)
        self.tools = FinancialTools()
        self.compliance = ComplianceGuard()

    async def analyze(self, code: str, question: str = "") -> Dict[str, Any]:
        print(f"\n📊 金融分析 Agent 启动 | 标的: {code}")
        evidence = []  # 数据溯源

        # ② 调用专业工具获取数据
        data = await self.tools.get_quote(code)
        if not data:
            return {"success": False, "answer": f"未找到标的 {code} 的数据"}
        print(f"   ✓ [工具] 获取行情: {data.name} 现价 {data.price}")

        # 计算财务指标
        pe = self.tools.calc_pe(data)
        pb = self.tools.calc_pb(data)
        roe = self.tools.calc_roe(data)
        gross_margin = self.tools.calc_gross_margin(data)
        debt_ratio = self.tools.calc_debt_ratio(data)
        risk = self.tools.assess_risk(data)
        print(f"   ✓ [工具] 计算指标: PE={pe} PB={pb} ROE={roe}% 毛利率={gross_margin}% 负债率={debt_ratio}%")

        evidence.append({"source": "行情数据", "data": f"{data.name} 现价{data.price}"})
        evidence.append({"source": "财务计算", "data": f"PE={pe}, ROE={roe}%"})

        # ① 检索领域知识
        kb_results = self.kb.retrieve(question or "市盈率 ROE 负债率")
        for kb in kb_results:
            evidence.append({"source": kb["source"], "data": kb["term"]})
        print(f"   ✓ [知识库] 检索到 {len(kb_results)} 条相关知识")

        # ③ 基于领域提示词生成分析（模拟LLM推理）
        analysis = self._generate_analysis(data, pe, pb, roe, gross_margin, debt_ratio, risk)

        # ④ 合规护栏检查
        check = self.compliance.check_output(analysis)
        if not check["passed"]:
            print(f"   ❌ [合规] 命中敏感词: {check['violations']}")
            analysis = "（内容因合规问题已过滤）"
        else:
            print(f"   ✓ [合规] 输出合规检查通过")

        # 添加免责声明
        final_answer = self.compliance.add_disclaimer(analysis)

        # ⑤ 置信度评估
        confidence = self._assess_confidence(data, kb_results)

        return {
            "success": True,
            "stock": data.name,
            "metrics": {"PE": pe, "PB": pb, "ROE": roe, "毛利率": gross_margin, "负债率": debt_ratio},
            "risk_level": risk["level"],
            "answer": final_answer,
            "evidence": evidence,
            "confidence": confidence
        }

    def _generate_analysis(self, data, pe, pb, roe, gross_margin, debt_ratio, risk) -> str:
        lines = [f"【{data.name}({data.code}) 投研分析】", ""]
        lines.append(f"估值水平: PE={pe}倍, PB={pb}倍")
        if pe > 30:
            lines.append("  → 估值偏高，需关注成长性是否匹配")
        elif pe < 15:
            lines.append("  → 估值相对偏低")
        else:
            lines.append("  → 估值处于合理区间")

        lines.append(f"盈利能力: ROE={roe}%, 毛利率={gross_margin}%")
        if roe > 15:
            lines.append("  → 盈利能力优秀")
        elif roe < 10:
            lines.append("  → 盈利能力偏弱")

        lines.append(f"偿债能力: 资产负债率={debt_ratio}%")
        if debt_ratio > 70:
            lines.append("  → 负债率偏高，需警惕偿债压力（银行业属正常）")

        lines.append(f"\n风险评级: {risk['level']}")
        if risk["risks"]:
            lines.append(f"主要风险: {', '.join(risk['risks'])}")

        return "\n".join(lines)

    def _assess_confidence(self, data, kb_results) -> str:
        score = 0.5
        if data:
            score += 0.3
        if kb_results:
            score += 0.2
        if score >= 0.9:
            return "高"
        elif score >= 0.7:
            return "中"
        return "低"


async def test_analysis(agent, code, question):
    result = await agent.analyze(code, question)
    if result["success"]:
        print(f"\n{result['answer']}")
        print(f"\n📌 数据溯源: {len(result['evidence'])}条 | 置信度: {result['confidence']} | 风险: {result['risk_level']}")
    else:
        print(f"\n{result['answer']}")


async def main():
    print("=" * 80)
    print("💰 L7-03: 垂直领域 Agent —— 金融分析 Agent")
    print("=" * 80)

    agent = FinancialAnalysisAgent()

    print("\n" + "=" * 70)
    print("案例一：贵州茅台（消费股）分析")
    print("=" * 70)
    await test_analysis(agent, "600519", "分析市盈率、ROE和负债率")

    print("\n" + "=" * 70)
    print("案例二：平安银行（金融股）分析")
    print("=" * 70)
    await test_analysis(agent, "000001", "分析ROE和负债率")

    print("\n" + "=" * 70)
    print("案例三：不存在的标的（异常处理）")
    print("=" * 70)
    await test_analysis(agent, "999999", "分析这只股票")

    print("\n" + "=" * 80)
    print("✅ 垂直领域 Agent 演示完成")
    print("=" * 80)
    print("""
💡 垂直 Agent 五大要素:
   ① 领域知识库: 金融指标知识 + RAG式检索
   ② 专业工具集: 行情查询、指标计算、风险评估
   ③ 领域提示词: 金融分析师角色设定
   ④ 合规护栏: 敏感词过滤 + 免责声明（金融强制）
   ⑤ 评估体系: 数据溯源 + 置信度评估

🔑 垂直 Agent 是 L1-L7 能力的综合: ReAct推理+工具调用+护栏+领域知识
""")


if __name__ == "__main__":
    asyncio.run(main())