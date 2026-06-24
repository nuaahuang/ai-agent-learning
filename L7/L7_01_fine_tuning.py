"""
L7-01: Fine-tuning（模型微调）—— 全流程模拟 Demo

不依赖 GPU 和重型训练框架，用纯 Python 模拟微调的完整工程流程：
  ① 数据准备与清洗（质量 > 数量）
  ② 数据格式化（对话格式 + 训练样本构建）
  ③ LoRA 配置（低秩适配，大幅减少可训练参数）
  ④ 训练循环（模拟 loss 下降、学习率调度）
  ⑤ 评估（训练指标 + 任务指标 + 过拟合检测）

目标：理解微调的工程流程与关键决策点，而非真实训练数学。
面向 Agent 场景：以"工具调用格式化输出"为微调任务示例。
"""
import json
import math
import random
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


# ============================================================
# ① 数据准备与清洗
# ============================================================
@dataclass
class TrainingSample:
    messages: List[Dict[str, str]]
    source: str = "manual"

    def is_valid(self) -> Tuple[bool, str]:
        if not self.messages or len(self.messages) < 2:
            return False, "对话轮次不足"
        roles = [m["role"] for m in self.messages]
        if "user" not in roles or "assistant" not in roles:
            return False, "缺少 user 或 assistant 角色"
        for m in self.messages:
            if not m.get("content", "").strip():
                return False, "存在空内容"
        return True, "ok"


class DataPreparer:
    """数据准备与清洗：质量 > 数量"""

    def __init__(self):
        self.raw_samples: List[TrainingSample] = []
        self.clean_samples: List[TrainingSample] = []
        self.stats = {"raw": 0, "invalid": 0, "duplicate": 0, "clean": 0}

    def load_samples(self, samples: List[TrainingSample]):
        self.raw_samples = samples
        self.stats["raw"] = len(samples)

    def clean(self) -> List[TrainingSample]:
        seen_hashes = set()
        for sample in self.raw_samples:
            valid, reason = sample.is_valid()
            if not valid:
                self.stats["invalid"] += 1
                continue

            content_hash = self._hash(sample)
            if content_hash in seen_hashes:
                self.stats["duplicate"] += 1
                continue

            seen_hashes.add(content_hash)
            self.clean_samples.append(sample)

        self.stats["clean"] = len(self.clean_samples)
        return self.clean_samples

    @staticmethod
    def _hash(sample: TrainingSample) -> str:
        text = "".join(m["content"] for m in sample.messages)
        return str(hash(text))

    def split(self, train_ratio: float = 0.8) -> Tuple[List, List]:
        random.seed(42)
        shuffled = self.clean_samples[:]
        random.shuffle(shuffled)
        split_idx = int(len(shuffled) * train_ratio)
        return shuffled[:split_idx], shuffled[split_idx:]


# ============================================================
# ② 数据格式化
# ============================================================
class DataFormatter:
    """将对话样本格式化为训练所需的 token 序列（模拟）"""

    @staticmethod
    def to_chat_format(sample: TrainingSample) -> str:
        parts = []
        for m in sample.messages:
            parts.append(f"<|{m['role']}|>\n{m['content']}\n")
        return "".join(parts) + "<|end|>"

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return len(text) // 2  # 中文粗略估算

    @classmethod
    def build_dataset(cls, samples: List[TrainingSample]) -> List[Dict[str, Any]]:
        dataset = []
        for s in samples:
            formatted = cls.to_chat_format(s)
            dataset.append({
                "text": formatted,
                "tokens": cls.estimate_tokens(formatted)
            })
        return dataset


# ============================================================
# ③ LoRA 配置
# ============================================================
@dataclass
class LoRAConfig:
    rank: int = 8
    alpha: int = 16
    dropout: float = 0.05
    target_modules: List[str] = field(default_factory=lambda: ["q_proj", "v_proj"])

    def compute_trainable_params(self, base_params: int, hidden_dim: int = 4096) -> Dict[str, Any]:
        # LoRA 可训练参数 = 2 * rank * hidden_dim * 模块数
        lora_params = 2 * self.rank * hidden_dim * len(self.target_modules)
        reduction = (1 - lora_params / base_params) * 100
        return {
            "base_params": base_params,
            "lora_params": lora_params,
            "trainable_ratio": lora_params / base_params * 100,
            "reduction": reduction
        }


@dataclass
class TrainingConfig:
    learning_rate: float = 1e-4
    epochs: int = 3
    batch_size: int = 4
    warmup_ratio: float = 0.1
    lora: LoRAConfig = field(default_factory=LoRAConfig)


# ============================================================
# ④ 训练循环（模拟）
# ============================================================
class FineTuner:
    """模拟微调训练循环：loss 下降 + 学习率调度"""

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.history: List[Dict[str, float]] = []

    def _lr_schedule(self, step: int, total_steps: int) -> float:
        warmup_steps = int(total_steps * self.config.warmup_ratio)
        if step < warmup_steps:
            return self.config.learning_rate * (step + 1) / warmup_steps
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        return self.config.learning_rate * 0.5 * (1 + math.cos(math.pi * progress))

    def _simulate_loss(self, step: int, total_steps: int, base_loss: float = 2.5) -> float:
        # 模拟 loss 指数下降 + 噪声
        progress = step / max(1, total_steps)
        loss = base_loss * math.exp(-2.0 * progress) + 0.3
        noise = random.uniform(-0.05, 0.05)
        return round(loss + noise, 4)

    def train(self, train_set: List[Dict], val_set: List[Dict]) -> List[Dict]:
        steps_per_epoch = max(1, len(train_set) // self.config.batch_size)
        total_steps = steps_per_epoch * self.config.epochs

        print(f"   训练样本: {len(train_set)} | 验证样本: {len(val_set)}")
        print(f"   每轮步数: {steps_per_epoch} | 总步数: {total_steps}")
        print()

        global_step = 0
        for epoch in range(1, self.config.epochs + 1):
            epoch_losses = []
            for _ in range(steps_per_epoch):
                lr = self._lr_schedule(global_step, total_steps)
                loss = self._simulate_loss(global_step, total_steps)
                epoch_losses.append(loss)
                global_step += 1

            train_loss = round(sum(epoch_losses) / len(epoch_losses), 4)
            # 验证 loss 略高于训练 loss（含过拟合检测）
            val_loss = round(train_loss + 0.1 + epoch * 0.02, 4)

            record = {
                "epoch": epoch,
                "train_loss": train_loss,
                "val_loss": val_loss,
                "lr": round(lr, 8)
            }
            self.history.append(record)
            print(f"   Epoch {epoch}/{self.config.epochs} | "
                  f"train_loss={train_loss} | val_loss={val_loss} | lr={lr:.2e}")

        return self.history


# ============================================================
# ⑤ 评估
# ============================================================
class Evaluator:
    """评估：训练指标 + 任务指标 + 过拟合检测"""

    @staticmethod
    def detect_overfitting(history: List[Dict]) -> Tuple[bool, str]:
        if len(history) < 2:
            return False, "数据不足"
        # 训练loss降但验证loss连续升 → 过拟合
        last = history[-1]
        prev = history[-2]
        if last["train_loss"] < prev["train_loss"] and last["val_loss"] > prev["val_loss"]:
            return True, "训练loss下降但验证loss上升，疑似过拟合"
        gap = last["val_loss"] - last["train_loss"]
        if gap > 0.5:
            return True, f"训练/验证loss差距过大({gap:.2f})，疑似过拟合"
        return False, "未检测到明显过拟合"

    @staticmethod
    def task_metrics(predictions: List[str], references: List[str]) -> Dict[str, float]:
        # 模拟任务指标：格式正确率（function calling 场景）
        correct_format = 0
        exact_match = 0
        for pred, ref in zip(predictions, references):
            if pred.strip().startswith("{") and pred.strip().endswith("}"):
                correct_format += 1
            if pred.strip() == ref.strip():
                exact_match += 1
        n = max(1, len(predictions))
        return {
            "format_accuracy": round(correct_format / n * 100, 2),
            "exact_match": round(exact_match / n * 100, 2),
            "samples": n
        }


# ============================================================
# 构建示例数据集（Agent 工具调用场景）
# ============================================================
def build_sample_data() -> List[TrainingSample]:
    system = "你是一个工具调用助手，根据用户请求输出标准JSON格式的工具调用。"
    samples = [
        TrainingSample([
            {"role": "system", "content": system},
            {"role": "user", "content": "查询北京的天气"},
            {"role": "assistant", "content": '{"tool": "get_weather", "args": {"city": "北京"}}'}
        ]),
        TrainingSample([
            {"role": "system", "content": system},
            {"role": "user", "content": "帮我搜索机器学习的资料"},
            {"role": "assistant", "content": '{"tool": "search", "args": {"query": "机器学习"}}'}
        ]),
        TrainingSample([
            {"role": "system", "content": system},
            {"role": "user", "content": "计算 23 乘以 45"},
            {"role": "assistant", "content": '{"tool": "calculator", "args": {"expr": "23*45"}}'}
        ]),
        TrainingSample([
            {"role": "system", "content": system},
            {"role": "user", "content": "发邮件给张三"},
            {"role": "assistant", "content": '{"tool": "send_email", "args": {"to": "张三"}}'}
        ]),
        # 无效样本（缺assistant）
        TrainingSample([
            {"role": "system", "content": system},
            {"role": "user", "content": "无效样本"}
        ]),
        # 空内容样本
        TrainingSample([
            {"role": "user", "content": "  "},
            {"role": "assistant", "content": "x"}
        ]),
    ]
    # 制造重复样本
    samples.append(samples[0])
    # 扩充更多有效样本
    cities = ["上海", "广州", "深圳", "杭州", "成都", "武汉"]
    for city in cities:
        samples.append(TrainingSample([
            {"role": "system", "content": system},
            {"role": "user", "content": f"查询{city}的天气"},
            {"role": "assistant", "content": f'{{"tool": "get_weather", "args": {{"city": "{city}"}}}}'}
        ]))
    return samples


def main():
    print("=" * 80)
    print("🎯 L7-01: Fine-tuning（模型微调）全流程模拟")
    print("=" * 80)

    # ---- ① 数据准备与清洗 ----
    print("\n" + "-" * 60)
    print("① 数据准备与清洗")
    print("-" * 60)
    preparer = DataPreparer()
    preparer.load_samples(build_sample_data())
    preparer.clean()
    print(f"   原始样本: {preparer.stats['raw']}")
    print(f"   无效剔除: {preparer.stats['invalid']}")
    print(f"   去重剔除: {preparer.stats['duplicate']}")
    print(f"   有效样本: {preparer.stats['clean']}")

    train_samples, val_samples = preparer.split(train_ratio=0.8)
    print(f"   训练集: {len(train_samples)} | 验证集: {len(val_samples)}")

    # ---- ② 数据格式化 ----
    print("\n" + "-" * 60)
    print("② 数据格式化")
    print("-" * 60)
    train_set = DataFormatter.build_dataset(train_samples)
    val_set = DataFormatter.build_dataset(val_samples)
    total_tokens = sum(d["tokens"] for d in train_set)
    print(f"   训练集 token 估算: {total_tokens}")
    print(f"   样本格式示例:")
    print("   " + train_set[0]["text"].replace("\n", "\n   ")[:200])

    # ---- ③ LoRA 配置 ----
    print("\n" + "-" * 60)
    print("③ LoRA 配置")
    print("-" * 60)
    lora = LoRAConfig(rank=8, alpha=16, target_modules=["q_proj", "v_proj", "k_proj", "o_proj"])
    base_params = 7_000_000_000  # 假设 7B 模型
    param_info = lora.compute_trainable_params(base_params)
    print(f"   基座参数量: {param_info['base_params']:,}")
    print(f"   LoRA可训练参数: {param_info['lora_params']:,}")
    print(f"   可训练占比: {param_info['trainable_ratio']:.4f}%")
    print(f"   参数减少: {param_info['reduction']:.2f}%")

    # ---- ④ 训练 ----
    print("\n" + "-" * 60)
    print("④ 训练循环")
    print("-" * 60)
    config = TrainingConfig(learning_rate=1e-4, epochs=3, batch_size=2, lora=lora)
    tuner = FineTuner(config)
    history = tuner.train(train_set, val_set)

    # ---- ⑤ 评估 ----
    print("\n" + "-" * 60)
    print("⑤ 评估")
    print("-" * 60)
    overfit, reason = Evaluator.detect_overfitting(history)
    print(f"   过拟合检测: {'⚠️ ' + reason if overfit else '✅ ' + reason}")

    # 模拟微调后的预测结果（工具调用场景）
    predictions = [
        '{"tool": "get_weather", "args": {"city": "南京"}}',
        '{"tool": "search", "args": {"query": "深度学习"}}',
        '我觉得应该调用天气工具',  # 格式错误
    ]
    references = [
        '{"tool": "get_weather", "args": {"city": "南京"}}',
        '{"tool": "search", "args": {"query": "深度学习"}}',
        '{"tool": "get_weather", "args": {"city": "南京"}}',
    ]
    metrics = Evaluator.task_metrics(predictions, references)
    print(f"   格式正确率: {metrics['format_accuracy']}%")
    print(f"   完全匹配率: {metrics['exact_match']}%")
    print(f"   评估样本数: {metrics['samples']}")

    print("\n" + "=" * 80)
    print("✅ Fine-tuning 全流程模拟完成")
    print("=" * 80)
    print("""
💡 核心要点:
   ① 数据质量 > 数量: 清洗剔除无效/重复样本是关键第一步
   ② 数据格式化: 统一对话格式，估算 token 规划成本
   ③ LoRA: 只训练 <0.1% 参数即可微调，大幅降低资源需求
   ④ 训练: 学习率warmup+余弦衰减，监控 train/val loss
   ⑤ 评估: 过拟合检测 + 任务指标（Agent场景关注格式正确率）

🔑 经验法则: 先 Prompt → 再 RAG → 最后才微调
""")


if __name__ == "__main__":
    main()