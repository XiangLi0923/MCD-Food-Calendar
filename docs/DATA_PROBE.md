# MCP 数据实测报告（DATA_PROBE）

> 时间：2026-10-19 13:19 ~ 13:22
> 方式：Python 标准库 MCP 客户端（streamable HTTP）直连 `https://mcp.mcd.cn`
> 门店：麦当劳烟台朝阳街餐厅（storeCode=3350325）
> 原始返回：`raw/*.json`（含 tools_list、营养、菜单、详情、核价、券）

---

## 一、连接与鉴权

| 项 | 实测结论 |
|---|---|
| 端点 | `https://mcp.mcd.cn`（POST，JSON-RPC 2.0） |
| 鉴权 | **`Authorization: Bearer <token>`，Bearer 前缀必需**；裸 token 返回 403 `校验鉴权authToken必填` |
| 协议版本 | `2025-03-26`，serverInfo = `mcd-mcp v1.0.0` |
| 会话 | 服务端不返回 `Mcp-Session-Id`，每次请求都需带 Authorization |
| GET | 不支持（403），只接受 POST |

## 二、工具盘点

`tools/list` 返回 **35 个工具**：now-time-info、query-my-account、query-my-coupons、query-store-coupons、available-coupons、auto-bind-coupons、query-meals、query-meal-detail、calculate-price、query-nearby-stores、delivery-query-stores、query-promotions、campaign-calendar、order-list、create-order、cancel-order、query-order、mall-*（6 个）、party-*（6 个）、draw-lottery、query-lottery-info、query-my-prizes、list-nutrition-foods、query-survey-coupon、query-meal-assistance。

## 三、核心接口实测结果

### 1. `list-nutrition-foods`（营养库）

- 参数：无
- 返回：`data` 为字符串，格式 `[160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:` + 160 行 CSV
- **字段齐全**：热量（kJ/kcal）、蛋白质(g)、脂肪(g)、碳水(g)、钠(mg)、钙(mg)
- **无产品 code**，只有中文名 → 与菜单关联只能靠名称匹配
- 实测范围：热量 2 ~ 1003 kcal；蛋白最高「芝士双层安格斯厚牛堡」1003kcal/58g；脂肪最低「大杯玉米杯」1g
- 支撑判断：四个模式的营养约束全部可用 ✅

### 2. `query-meals`（门店菜单）

- 参数：`storeCode` + `orderType=1` + `beType=1`（均为必填）
- 返回：15 个分类、**125 个餐品**，每个仅 `code` + `tags`
- 分类含：人气热卖、精选单人餐、鸡肉汉堡/卷、随心配1+1、大堡口福、巨无霸牛鱼肉堡、安格斯MAX、炸鸡、麦咖啡、**500大卡套餐**、饮品等
- 注意：**不含名称与价格**，需详情/核价接口补全

### 3. `query-meal-detail`（餐品详情）

- 参数：`storeCode` + `orderType` + `beType` + `code`
- 返回：`name`、`image`、`rounds[]`（套餐轮次：主食/小食/饮品 choices，含 diffPrice 加价）
- **无价格字段** → 价格必须走 `calculate-price`

### 4. `calculate-price`（价格核验）

- 参数：`storeCode` + `orderType` + `beType` + `items[]{productCode,quantity}`
- **价格单位 = 分**（实测 2990 = ¥29.90）
- **支持批量**：一次传 5 项，`productList[]` 分别返回 `subtotal` → 125 个餐品可 1~2 次调用算完
- 同时返回 `takeWayList`（堂食/外带）

### 5. `query-nearby-stores`（门店）

- **必须同时传 `keyword` + `city`**，只传其一报错 `600058 城市名或者关键词不能为空`
- 返回：storeCode、storeName、address、distance、营业时间、reservation

### 6. `available-coupons` / `query-store-coupons`（优惠券）

- `available-coupons`：正常返回可领券列表（标题+图片）
- `query-store-coupons`：需要 storeCode；实测该店 `data: []`（当前无券，如实处理空结果）

## 四、关键工程结论与红线

| # | 结论 | 对策 |
|---|---|---|
| 1 | 价格单位是**分** | 统一 `fen_to_yuan()` 换算，代码内禁止直接展示原始值 |
| 2 | 营养表**无 code**，靠名称匹配 | 实测 20 个餐品 46 个子项，命中率 **85%**；未命中（多为新品如龙焰系列）标注「营养数据暂无」，不猜 |
| 3 | 125 餐品 × 详情 = 高频调用 | 本地缓存菜单+详情（会话级），限流 600/min |
| 4 | 套餐营养需**子项累加** | detail.rounds[].choices[] → 营养表匹配 → 求和 |
| 5 | 门店搜索参数挑剔 | keyword + city 双传 |
| 6 | 券接口可能返回空数组 | 空结果如实显示，不编造 |

## 五、对四个模式的支撑判断

| 模式 | 数据支撑 | 结论 |
|---|---|---|
| 日常 | 营养（热量/蛋白/脂肪/钠）+ 价格 + 轮换 | ✅ 可做 |
| 省钱 | 批量核价 + available-coupons | ✅ 可做 |
| 燃脂 | energyKcal + protein 精确到克 | ✅ 可做（官方还有「500大卡套餐」分类可直接引用） |
| 病号 | fat / sodium / protein 三字段客观筛选 | ✅ 可做（低脂候选：玉米杯 1g、热朱古力 2g 等） |

## 六、遗留风险

1. 营养表 160 条与菜单 125 个售卖单元非一一对应（单品 vs 套餐），85% 匹配率需在 UI 上明确标注缺失项。
2. 部分门店/时段菜单会变化，价格与供应以实时调用为准。
3. 时令新品营养数据滞后（龙焰系列未入营养表），属官方数据更新节奏，不自行补数据。
