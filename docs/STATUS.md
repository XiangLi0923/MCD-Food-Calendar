# 项目状态（单一事实源）

> 最后更新：2026-10-25 18:00 · 报名截止 2026-10-25 23:59

## 一句话

选餐魔盒已从"CLI 能跑"长成"**网页可用**"：像素风单页、左右两栏、组合成一顿饭、每盒展开明细与热量、
结果页可继续用一句话调整。报名 Issue #1382 已提交。

## 已完成

| 类别 | 内容 |
|---|---|
| 文档 | `README.md`（V2）、`MCP_INTEGRATION.md`、`CONTEST_DECLARATION.md`（官方原文）、`mcp-config.example.json`、`skill/SKILL.md`、`docs/PRD_V2.md`、`docs/PRD_CHANGELOG.md`、`docs/MVP_IMPLEMENTATION_PLAN.md`、`docs/CHAIN_REPORT.md` |
| 代码 | `mcd_box/`：mcp_client / adapter / candidates / **meals** / recommend / entry / **nutrition** / **enrich** / render / cli |
| 网页 | `server.py`（标准库 http.server + CORS + 多端口回退）、`web/index.html`（像素风单页）、`start_web.cmd` |
| 脚本 | `verify_chain.py`（链路验证）、`build_snapshot.py`（快照）、`smoke_candidates.py`（候选体检）、`probe_*.py`（早期探针，保留失败记录） |
| 数据 | `data/snapshot/3350325.json`（112 条菜单）、`details_3350325.json`（43 个套餐子项）、`nutrition.json`（160 条营养） |
| 测试 | `tests/test_rules.py` 19 项，全绿（含组合价相加、热量完整性） |
| 仓库 | https://github.com/XiangLi0923/MCD-Food-Calendar （public，main） |

## 已验证的数据事实（门店 3350112）

- 菜单：**106 个售卖单元 / 14 个分类**；同一餐品跨分类重复 8 个（必须按 code 去重）。
- 价格：¥3.90 – ¥73.00，**中位数 ¥23.50**；`query-meals` 自带 `currentPrice`。
- 两个价格口径 **18/102 不一致**（10-21 样本）（核价接口未应用会员优惠）→ 展示用现价。
- 营养：160 条、无 code、名称匹配抽样 84.8% → **不参与推荐，不展示**。
- 单次开盒成本：1 次 `query-meals`，约 0.4s；缓存 10 分钟。

## 未实现（明确不做或后置）

- P1：单品换餐、帮我带文本、偏好记忆、多档随机、更强文本解析（L1 LLM）、活动/上新加权。
- P2：一周菜单、自组组合、历史订单个性化。
- 不做：点餐支付、营养目标求解、Web 界面、账号体系。

## 风险与阻塞

| # | 风险 | 状态 |
|---|---|---|
| 1 | 报名 Issue 必须由本人提交 | 待用户操作 |
| 2 | `workbuddy.md` 需导出完整对话（含失败记录） | 待用户操作 |
| 3 | 榜单按 Star 排名，当前 0 star | 需要有传播物料（截图/一句话） |
| 6 | 公网链接未部署 | 若要公开，只能用快照模式（不能带个人 Token） |
| 4 | GitHub MCP 连接器不可用 | 不影响开发，git CLI 正常 |
| 5 | 菜单每天变动（106 vs 昨天 102） | 已用缓存 + 快照兜底 |

## 下一步

1. 截图三张卡（在线 / 离线各一张），放进 README 或 PR 描述。
2. 用户导出 `workbuddy.md`。
3. 官方仓库提交报名 Issue（格式：`【参赛申请】` + 项目名称/地址/简介，标题正文不空行、裸链接）。
4. 之后每改一次代码，重跑 `unittest` 与本文件更新。

## 变更记录

- 10-21：仓库初始化，数据链路验证；`mcd_box` 取数层与候选层。
- 10-22：三规则推荐、三入口、卡片渲染、离线快照、14 项测试；交付文档五件套。
