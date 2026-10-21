# Live Demo 验收报告

## 验收结论

**北京亲子历史舒缓四日 Live 链路已完整通过。** 调研 Agent 调用了本地案例库、经验库与
Tavily，规划 Agent 生成四日行程，Python 校验器通过，审核 Agent 批准，未触发返工。

验收环境：

- Python 3.11
- PyTorch `2.8.0+cu126`
- NVIDIA GeForce RTX 4060
- Embedding 与 Reranker 均为 `cuda:0`
- CrewAI `1.15.5`
- DeepSeek V4 Flash / Pro API
- Tavily Search API

## 结果指标

| 指标 | 结果 |
|---|---:|
| 运行模式 | Live |
| 目的地 | 北京 |
| 行程天数 | 4 |
| 用户预算 | 6000 元 |
| 预计行程成本 | 1570 元 |
| 总引用数 | 15 |
| 历史案例引用 | 3 |
| 经验卡引用 | 4 |
| 实时来源引用 | 8 |
| 实时 URL 有效性检查 | 通过 |
| Python 规则校验 | 通过 |
| 审核 Agent | 通过 |
| 返工次数 | 0 |
| 总耗时 | 约 218 秒 |

四日主题为：

1. 皇城根下中轴线探秘
2. 巨龙长城缆车之旅
3. 科技探索与奥体夜色
4. 皇家园林泛舟赏景

## 路由验证

**稳定路线经验留在本地，时效事实进入实时检索。** 案例与经验检索最高重排置信度约为
0.73，高于 0.55 阈值，因此用于路线结构、亲子节奏和体力控制；门票、预约、缆车价格、
天气、住宿价格等被标记为实时问题，交由 Tavily 查询。其他城市案例在 Chroma 查询阶段被
目的地元数据过滤排除。

## 结构化输出兼容性

**DeepSeek V4 接受 `json_object`，但不接受 CrewAI 转换器触发的 OpenAI
`json_schema/parse`。** 项目不降低 Schema 要求：关闭 `output_pydantic` 的二次模型转换，使用
DeepSeek 原生 JSON 模式生成结果，再由 Python 本地提取 JSON 边界并执行 Pydantic 校验；同时
显式关闭 thinking，防止 reasoning token 占满输出预算。非法 JSON 或字段错误直接失败并写日志，
不产生额外的“格式修复”模型调用。

## 成本与性能观察

2026-08-04 修复后的完整 Live 验收日志汇总：

- Prompt tokens：20,929
- Completion tokens：3,911
- Total tokens：24,840
- Cached prompt tokens：9,728
- Reasoning tokens：0（结构化交接显式使用 non-thinking）
- 工作流耗时：57.5 秒
- 最终结果：规则校验通过、审核通过、未触发返工

**当前效果已经可验证，但调研阶段 Token 与延迟仍有优化空间。** 下一阶段应重点合并相近的
实时查询、限制 Tavily 返回正文长度、压缩工具结果、缓存相同目的地的稳定调研证据，并评估将
多个实时事实查询合并为一次批量研究工具调用。优化必须通过对照测试验证，不通过替换低能力模型
或关闭证据链实现。
