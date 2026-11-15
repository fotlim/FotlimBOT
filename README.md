# 阿渔 · Ayu

一只**自研的 QQ 智能体**核心：人格、记忆、判断、通道彻底解耦。
嘴（协议端）可以随手换，脑子（人格+记忆）只写一遍。

> 设计信条：`core/` 里不出现任何 `onebot / milky / nonebot` 字样；
> 协议端（NapCat / LLBot / SnowCat …）只是可插拔的一层。

## 架构

```
L4 核心（本仓库重点）  persona · memory · decide · compose · tools · scheduler
L3 桥接               channels/  （协议端 ↔ 核心，唯一翻译层）
L2 协议               OneBot v11（已实现） / Milky（预留）
L1 协议端             NapCat / LLBot / SnowCat（可替换，不属于本仓库）
```

## 现在能做什么

- ✅ QQ 私聊 / 群聊收发（OneBot v11 正向 WS）
- ✅ 接入任意 OpenAI 兼容大模型，多轮对话、人设
- ✅ 短句连发（像真人聊天）、群聊未被 @ 时保持安静
- ⏳ 长期记忆、主动发言、管理面板、双通道热备（见路线图）

## 快速开始

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
copy .env.example .env      # 按需修改
CHANNEL=mock python3 bin/main.py        # 无依赖跑一次内置演示
CHANNEL=onebot11 python3 bin/main.py    # 连接本机 OneBot 协议端
```

`.env` 关键项：

| 变量 | 说明 |
|---|---|
| `LLM_BASE_URL` | OpenAI 兼容端点，如 `http://127.0.0.1:8000/v1` |
| `LLM_API_KEY` | 密钥（本机网关可留任意值） |
| `LLM_MODEL` | 模型 id |
| `CHANNEL` | `mock` / `onebot11` / `milky` |
| `ONEBOT_WS` | 协议端 OneBot v11 正向 WS，如 `ws://127.0.0.1:3001` |

## 路线图

- M0 通血管 ✅（协议端接入、@ 触发闭环）
- M1 会说话 ✅（人设 + 短句连发）
- M2 记得住 ⏳（SQLite 单一真相 + 事实抽取 + 检索）
- M3 有分寸 ⏳（何时说/说几句/主动性 + 速率熔断）
- M4 活得久 ⏳（双通道热备 + 断电补偿 + 多平台同源）

## License

MIT —— 随便改、随便发。
