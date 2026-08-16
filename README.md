# LiteLLM Gateway

统一代理多家人工智能模型的网关。基于 [LiteLLM Proxy](https://docs.litellm.ai/docs/proxy/quick_start)，对外**同时**暴露 OpenAI 兼容协议与 Anthropic 兼容协议，背后自动路由到：

- OpenAI（gpt-4o / gpt-4o-mini / whisper-1 / tts-1）
- **Anthropic（claude-sonnet-4.5 / claude-haiku-4.5 / claude-opus-4.7）**
- **GaogeAI 代理（gpt-5.4 / gpt-5.5 / gpt-5.6-sol / gpt-5.6-terra / gpt-image-2，仅 OpenAI 协议；模型名沿用代理 id，不是 OpenAI 官方命名）**
- DeepSeek（deepseek-v4-flash / deepseek-v4-pro）
- Gemini（gemini-2.5-flash / gemini-2.0-flash）
- MiniMax（**MiniMax-M3** / MiniMax-M2.7-highspeed / speech-2.8-hd）
- 智谱 GLM（glm-asr-2512）
- DashScope（qwen3-flash / qwen3-asr-flash）
- 自托管 pronunciation-service（sensevoice-small）

## 目录结构

```
ai-gateway/
├── config.yaml            # 模型与路由配置
├── docker-compose.yml     # litellm + postgres
├── package.json           # npm 启停脚本
├── .env.example           # 环境变量模板
└── README.md
```

## 快速开始

### 1. 准备环境变量

```bash
cp .env.example .env
# 编辑 .env，填入各 Provider 的真实 API Key，并修改 LITELLM_MASTER_KEY（必须 ≥32 字符、sk- 开头，否则 UI 登录会失败）
```

`.env` 中各 Key 含义：

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `LITELLM_MASTER_KEY` | ✅ | 访问网关的 Bearer Token（同时是 UI 登录密码），格式 `sk-...` 且 ≥32 字符 |
| `DATABASE_URL` | ✅ | Postgres 连接串，默认 `postgresql://litellm:litellm@postgres:5432/litellm` |
| `OPENAI_API_KEY` | 视模型 | 用 `openai/*` 模型时必填 |
| `ANTHROPIC_API_KEY` | 视模型 | 用 `claude-*` 模型时必填，格式 `sk-ant-...` |
| `GAOGEAII_API_KEY` | 视模型 | 用 `gaogeaii-*` 模型时必填，格式 `sk-...` |
| `DEEPSEEK_API_KEY` | 视模型 | 用 `deepseek-*` 模型时必填 |
| `GEMINI_API_KEY` | 视模型 | 用 `gemini-*` 模型时必填 |
| `MINIMAX_API_KEY` | 视模型 | 用 `minimax-*` 模型时必填 |
| `ZHIPU_API_KEY` | 视模型 | 用 GLM ASR 时必填 |
| `DASHSCOPE_API_KEY` | 视模型 | 用 DashScope qwen 模型时必填 |
| `LITELLM_PORT` | ❌ | 网关端口，默认 `4000` |

**只填你要用的 provider 的 key 即可**——没填的 provider 对应的模型启动会报 `AuthenticationError`，不影响其它模型。

### 2. 启动服务

```bash
npm run env:init     # 若 .env 不存在则复制模板（已存在则跳过）
npm run start        # 后台启动 litellm + postgres
npm run status       # 查看容器状态
```

### 3. 验证

```bash
npm run health       # 探活
npm run models       # 列出已注册的模型，应能看到 claude-sonnet-4.5 / qwen3-flash / gpt-4o-mini 等
```

## 协议支持

网关**同时**监听两套协议端点，按客户端用的 SDK / 工具选其中一个即可，**模型名就是路由**，与端点无关：

| 端点 | 协议 | 客户端示例 |
| --- | --- | --- |
| `POST /v1/chat/completions` | OpenAI Chat Completions | Cline、Cursor（OpenAI provider）、Continue、LangChain、OpenAI Python/JS SDK、Aider |
| `POST /v1/messages` | Anthropic Messages | Claude Code（原生 SDK）、Cursor（Anthropic provider）、Anthropic SDK |
| `POST /v1/embeddings` | OpenAI Embeddings | 几乎所有工具 |
| `POST /v1/audio/*` | OpenAI Audio | Whisper / TTS 客户端 |

LiteLLM 在两套协议之间自动转换：

- 任何模型都能用 OpenAI 协议调
- 任何模型都能用 Anthropic 协议调（OpenAI 兼容的上游会被转成 Anthropic 响应，包括 `tool_use`、`thinking` 块、SSE 流事件）
- 调用 Claude 模型时，LiteLLM 走 Anthropic 原生 SDK 转发，无需协议转换

### 调用示例

**OpenAI 协议 —— 调用 OpenAI 上游模型：**

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-flash","messages":[{"role":"user","content":"你好"}]}'
```

**OpenAI 协议 —— 调用 Claude 模型（自动用 Anthropic SDK 上游）：**

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{"model":"claude-sonnet-4.5","messages":[{"role":"user","content":"hi"}]}'
```

**Anthropic 协议 —— 调用 Claude 模型（最直接）：**

```bash
curl http://localhost:4000/v1/messages \
  -H "x-api-key: $LITELLM_MASTER_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4.5",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "hi"}]
  }'
```

**Anthropic 协议 —— 调用非 Claude 模型（LiteLLM 自动协议转换）：**

```bash
curl http://localhost:4000/v1/messages \
  -H "x-api-key: $LITELLM_MASTER_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "qwen3-flash",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "hi"}]
  }'
```

### GaogeAI 代理（https://api.gaogeaii.com）

通过第三方代理访问 OpenAI 模型，**只支持 OpenAI 协议**（已实测：`/v1/messages` 直接 403，**不要**用 Anthropic 协议调这些模型）。

模型名沿用代理 `/v1/models` 返回的字面 id（`gpt-5.4` / `gpt-5.5` / `gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-image-2`），**这些不是 OpenAI 官方命名**——例如 `gpt-5.4` 实际走的是 gaogeaii 第三方代理，而非 OpenAI 直连。如果你想用 OpenAI 官方的 `gpt-4o` / `gpt-4o-mini`，请直接选上面 OpenAI 一栏的模型。

**调用示例：**

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.4","messages":[{"role":"user","content":"hi"}]}'
```

**如果代理方新增/移除模型**，改 `config.yaml` 里对应的 `model_name` 与上游 `model:` 字段（id 与 `/v1/models` 返回的 `data[].id` 一致）。

### 流式输出

两套端点都支持流式：

```bash
# OpenAI 风格
curl -N http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{"model":"claude-sonnet-4.5","stream":true,"messages":[{"role":"user","content":"hi"}]}'

# Anthropic 风格（message_start / content_block_delta / ...）
curl -N http://localhost:4000/v1/messages \
  -H "x-api-key: $LITELLM_MASTER_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-sonnet-4.5","stream":true,"max_tokens":1024,"messages":[{"role":"user","content":"hi"}]}'
```

## AI Coding 工具接入

### Cursor

可以同时配两个 provider，任选其一：

| Provider | Base URL | API Key | 模型 |
| --- | --- | --- | --- |
| OpenAI | `http://localhost:4000/v1` | `LITELLM_MASTER_KEY` | `gpt-4o-mini` / `qwen3-flash` / `claude-sonnet-4.5` |
| Anthropic | `http://localhost:4000` | `LITELLM_MASTER_KEY` | `claude-sonnet-4.5` / `claude-haiku-4.5` |

### Claude Code（Anthropic 原生 SDK）

> 如果你用 [cc switch](https://github.com/farion1231/cc-switch) 管理多个供应商，**跳到下一节**。

```bash
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_AUTH_TOKEN=$LITELLM_MASTER_KEY
# 之后所有 `claude` 命令的请求都会打到网关
```

`claude` 命令看到模型名 `claude-sonnet-4.5` 会直接用 Anthropic 协议走 `/v1/messages`；如果改成 `qwen3-flash`，LiteLLM 会把 Anthropic 协议转给 OpenAI 兼容上游再把响应转回 Anthropic 格式——tool_use、thinking 块都能保留。

写入 `~/.zshrc` / `~/.bashrc` 永久生效：

```bash
echo 'export ANTHROPIC_BASE_URL=http://localhost:4000' >> ~/.zshrc
echo "export ANTHROPIC_AUTH_TOKEN=$(grep ^LITELLM_MASTER_KEY .env | cut -d= -f2)" >> ~/.zshrc
```

### Claude Code + cc switch（推荐：可视化切换供应商）

[cc switch](https://github.com/farion1231/cc-switch) 是个 Claude Code 配置管理工具，可以让你在多个供应商（Anthropic / DeepSeek / 这套 LiteLLM 网关）之间一键切换。

![cc switch Claude Code 配置示例](docs/cc-switch-claude-code.png)

配置步骤：

**1. 编辑供应商 → 新建 `ai-gateway`，按下面填：**

| 字段 | 填什么 | 说明 |
| --- | --- | --- |
| 供应商名称 | `ai-gateway` | 任意起名 |
| 官网链接 | `http://localhost:4000` | 不影响实际请求 |
| **请求地址** | **`http://localhost:4000`** | ⚠️ **不要带 `/v1`**——Claude Code 会自动拼 `/v1/messages`，写成 `http://localhost:4000/v1` 会拼成 `/v1/v1/messages` 导致 404 |
| API Key | `.env` 里 `LITELLM_MASTER_KEY` 的值 | 必须 ≥32 字符、`sk-` 开头 |
| API 格式 | `Anthropic Messages (原生)` | Claude Code 必须用这个 |
| 认证字段 | `ANTHROPIC_AUTH_TOKEN（默认）` | cc switch 帮你写进 env，Claude Code 读得到 |
| **声明支持 1M** | **全部取消勾选** | ⚠️ 勾上会把 `[1M]` 拼到模型名后面，LiteLLM 找不到 |
| 禁用自动升级 | 勾选 | 否则 Claude Code 可能自动从 Sonnet 升级到 Opus，配置混乱 |

**模型映射参考**（按你的 `config.yaml` 注册的模型配）：

| 角色 | 显示名称 | 实际请求模型 |
| --- | --- | --- |
| Sonnet | `deepseek-v4-flash` | `deepseek-v4-flash` |
| Opus | `deepseek-v4-pro` | `deepseek-v4-pro` |
| Fable | `gpt-5.6-sol` | `gpt-5.6-sol` |
| Haiku | `gpt-5.6-terra` | `gpt-5.6-terra` |
| Subagent | `deepseek-v4-flash` | `deepseek-v4-flash` |
| 默认兜底模型 | `deepseek-v4-pro` | （选填，未识别角色时用） |

**2. 保存后 cc switch 会在 `~/.claude/settings.json` 写入类似：**

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:4000",
    "ANTHROPIC_AUTH_TOKEN": "sk-<your-master-key>",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-flash",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro",
    "ANTHROPIC_DEFAULT_FABLE_MODEL": "gpt-5.6-sol",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gpt-5.6-terra",
    ...
  }
}
```

**3. 启动 Claude Code：**

```bash
claude
```

**4. 验证：**

```bash
# 看 LiteLLM 是否真的收到请求（应看到 deepseek-v4-flash 等模型名）
npm run logs:litellm | grep -i deepseek
```

#### 常见坑

| 现象 | 原因 | 修复 |
| --- | --- | --- |
| `There's an issue with the selected model (xxx) ... It may not exist` | 请求地址带了 `/v1` → Claude Code 拼出 `/v1/v1/messages` → LiteLLM 404 → Claude Code 误判为 "model not exist" | 请求地址改成 `http://localhost:4000`（去掉 `/v1`） |
| `selected model: deepseek-v4-flash[1M]` 然后报 model not exist | "声明支持 1M" 勾选把 `[1M]` 拼到模型名 | 全部取消勾选 |
| UI 登录 / 模型列表 401 | `LITELLM_MASTER_KEY` 太短或不是 `sk-` 开头 | 生成 ≥32 字符的 `sk-...`，例：`sk-$(openssl rand -hex 24)` |
| 报错说请求没到 LiteLLM | cc switch 写入 `ANTHROPIC_AUTH_TOKEN` 但 Claude Code 期待 `ANTHROPIC_API_KEY` 等历史兼容性问题 | 升级到 cc switch 最新版，或用上面的 `Claude Code（裸 SDK）` 方案手动 export |
| 调 DeepSeek 直接 OK，调 ai-gateway 就不行 | DeepSeek 路径写的是 `https://api.deepseek.com/anthropic`（不带 `/v1`），而你 ai-gateway 路径带了 `/v1` | 路径对齐——都别带 `/v1` |

### Codex CLI + cc switch

[Codex CLI](https://github.com/openai/codex) 是 OpenAI 官方的代码 Agent，**走 OpenAI Responses API**（比 Chat Completions 更新的协议）。通过 cc switch 转发到 LiteLLM：

![cc switch Codex 配置示例](docs/cc-switch-codex.png)

**关键配置**（与 Claude Code 区别）：

| 字段 | 填什么 | 说明 |
| --- | --- | --- |
| 供应商名称 | `ai-gateway` | 任意起名 |
| 官网链接 | `http://localhost:4000` | 不影响实际请求 |
| **API 请求地址** | **`http://localhost:4000/v1`** | ⚠️ **这里要带 `/v1`**——与 Claude Code 相反，Codex CLI **不会**自动拼 `/v1/`，请求地址必须是完整的 endpoint |
| API Key | `.env` 里 `LITELLM_MASTER_KEY` 的值 | 必须 ≥32 字符、`sk-` 开头 |
| 默认模型 | `gpt-5.6-sol` | 任意已注册模型，例如 `deepseek-v4-flash` / `gpt-5.4` |
| 上游格式 | `Responses（原生）` | Codex CLI 走 OpenAI Responses API，LiteLLM 的 `/v1/responses` 端点能直接接收 |

**为什么请求地址要带 `/v1`？**

Codex CLI 不会在 base URL 后面拼路径，所以 base URL 必须是完整的 endpoint（`http://localhost:4000/v1`）。Claude Code 不一样，它会自己拼 `/v1/messages`，所以 base URL 不能带 `/v1`——这是两个 CLI 工具设计的根本差异。

**模型映射**（如果有多个 Codex 角色，可以像 Claude Code 那样配置）：在"模型映射"区域按需添加，例如把 `gpt-5.6-sol` 映射到上游的 `gpt-5.6-sol`。

启动 Codex：

```bash
codex
```

### Cline / Continue / Aider 等 OpenAI 兼容工具

- Provider: `OpenAI Compatible`
- Base URL: `http://localhost:4000/v1`
- API Key: `LITELLM_MASTER_KEY`
- 模型名：上面 `model_name` 列出的任意一项

## Web UI

LiteLLM 自带 Dashboard，启动后访问：

```
http://localhost:4000/ui
```

- Username: `admin`
- Password: `.env` 里的 `LITELLM_MASTER_KEY`（**必须是 ≥32 字符的 `sk-...` 字符串**，否则登录失败）

UI 里能做的事：

- **Models**：查看模型、设置每个模型的虚拟 key、cost / rate-limit
- **Usage**：按时间/模型/token 查看 spend
- **API Keys**：给不同用户/团队签发 virtual key，限制模型与预算
- **Logs**：实时流式查看每次请求的 request / response
- **Teams / Users**：多租户管理

## 常用命令

| 命令 | 作用 |
| --- | --- |
| `npm run start` | 后台启动 |
| `npm run stop` | 停止（保留数据卷） |
| `npm run restart` | 重启 litellm + postgres |
| `npm run restart:litellm` | 只重启 litellm 容器，postgres 不动 |
| `npm run reload` | **热加载 `config.yaml`**，不重启容器，0 停机 |
| `npm run env:apply` | **应用 `.env` 改动**到 litellm 容器（强制重建，env 才会重新注入） |
| `npm run down` | 同 stop |
| `npm run down:volumes` | 停止并删除 Postgres 数据卷（**会丢 spend logs**） |
| `npm run logs` | 跟踪所有服务日志 |
| `npm run logs:litellm` | 仅跟踪 litellm |
| `npm run psql` | 进入 Postgres 客户端 |
| `npm run pull` | 拉取最新镜像 |
| `npm run rebuild` | 重新构建并启动 |

## 端口

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| litellm | `${LITELLM_PORT:-4000}` | API 网关，同时暴露 OpenAI / Anthropic 协议 |
| litellm UI | `${LITELLM_PORT:-4000}/ui` | Dashboard |
| postgres | 5432 | 仅本机暴露，便于直接查 spend logs |

## 修改模型

所有路由信息都在 `config.yaml` 中。**当前没有配置 fallback**，每个模型名独立路由——如果上游失败会直接返回错误，不会自动降级。需要兜底的话在 `router_settings.fallbacks` 里加链路（参考 LiteLLM 官方文档）。

修改后只需热加载，不用重启：

```bash
npm run reload
```

## 热加载与重启策略

按"改了什么"决定走哪条路径：

| 改动文件 | 命令 | 停机时间 | 说明 |
| --- | --- | --- | --- |
| `config.yaml`（加/删模型、改 timeout、改 fallback） | `npm run reload` | **0 秒** | 走 LiteLLM 内建 `POST /config/reload` 端点，进程不重启 |
| `.env`（轮换 `OPENAI_API_KEY` / 改 `LITELLM_MASTER_KEY` 等） | `npm run env:apply` | ~10 秒 | **强制重建** litellm 容器以重新注入 env_file，postgres 不动 |
| `docker-compose.yml`（端口映射、卷、新增服务） | `npm run restart` | ~10 秒 | 整栈重启 |

⚠️ `npm run reload` 只会重新加载 `config.yaml`，**不会重新读取 `.env`**——`.env` 通过 `env_file:` 在容器启动时注入一次，进程内 env 不会反向同步。所以改了 `.env` 必须走 `env:apply` 或更重的重启。

⚠️ 注意 `env:apply` 内部用的是 `docker compose up -d --force-recreate` 而不是 `restart`——`restart` 只 stop+start 同一个容器实例，不会重新解析 `env_file`，改了 `.env` 跑 `restart:litellm` 会**感觉生效了但实际没生效**，是 docker compose 的一个常见坑。

如果改了 `DATABASE_URL`（postgres 账号/地址变了），用 `npm run restart` 让 postgres 也跟着重启。

## 故障排查

- **UI 登录失败**：`.env` 里的 `LITELLM_MASTER_KEY` 必须 ≥32 字符、以 `sk-` 开头。修改后 `npm run env:apply`。
- **某个 provider 模型报 401/403**：`.env` 里对应的 `XXX_API_KEY` 没填或填错，只影响该 provider，其它模型正常。
- **容器起不来**：`npm run logs:litellm` 看错误，常见是某个 `os.environ/XXX_API_KEY` 没设。
- **端口冲突**：编辑 `.env` 修改 `LITELLM_PORT`，然后 `npm run env:apply`。
- **数据库连接失败**：确认 `DATABASE_URL` 与 `docker-compose.yml` 中 postgres 的账号一致。
- **`pronunciation-service` 找不到**：那是另一个仓库的服务，先把 sensevoice 相关模型注释掉再启动，或在该仓库同网络下启动它。
- **Anthropic 协议下 tool_use 没回传**：LiteLLM 的 OpenAI↔Anthropic 转换对 function calling 支持完整，但部分 thinking 模型需要上游支持 `tool_choice`，否则工具调用会失败。可换非 thinking 的模型名（如 `claude-haiku-4.5`）验证。