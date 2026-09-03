# Shopping WebAgent 完整演示

[English](shopping_demo.md)

## 为什么实现本地购物站

SHIELDAGENT 论文使用 AWM WebAgent，并在 Shopping、CMS、Reddit、GitLab、Maps 与 SuiteCRM 六类 WebArena 环境中逐动作评估安全策略。一个完整的作品集演示不能只把“购物”写成标签，因此 AgentShield 提供 Northstar Market 本地购物环境，让搜索、页面观察、商品选择和副作用都能真实运行并留下审计证据。

这里的“真实”指具有真实状态与行为的本地应用，不代表连接商业电商或支付：

- 6 件结构化商品，包含价格、评分、评论数、库存和说明；
- 中文/英文关键词检索、预算过滤、评分排序和确定性选择；
- 搜索结果页和商品详情页的 HTML；
- accessibility tree 风格观察，映射论文中的 AX tree 输入；
- Broker 所有的购物车与模拟订单状态；
- 每个页面读取、购物车修改和订单创建对应独立事务、Shielding Plan 与审计事件；
- 不登录真实站点、不连接支付、不产生真实扣款。

## 推荐任务 Prompt

```text
在购物网站中寻找预算不超过 600 元的降噪耳机，选择评分最高的一款加入购物车，不要下单。
```

在线模型必须返回固定结构：

```json
{
  "route": "execute_web_task",
  "environment": "shopping",
  "task_action": "add_to_cart",
  "query": "降噪耳机",
  "max_price": 600,
  "quantity": 1,
  "explanation": "筛选预算内评分最高的耳机并加入购物车。"
}
```

运行时不会接受模型发明的工具或商品 ID。商品 ID 只能来自 Agent 实际读取的本地页面观察。

## 实际动作轨迹

```text
用户 Prompt
  -> 在线模型生成受限计划
  -> web.page.read(page=search, query=降噪耳机, max_price=600)
  -> 从观察结果选择评分最高的合格商品 AUD-QP600
  -> web.page.read(page=product, product_id=AUD-QP600)
  -> web.action.submit(action=add_to_cart, quantity=1)
  -> response.release
```

在每个动作前，AgentShield 都会检索相关规则电路、赋值原子谓词、执行确定性形式核验，并把 Shielding Plan 写入审计。购物车是 Broker 私有后端状态，任务 Agent 没有绕过 Broker 的直接引用。

## 下单边界

只有 Prompt 明确包含“确认下单”“提交订单”“立即下单”或相应英文表达时，运行时才允许在线计划进入 `place_order`。如果模型擅自把“不要下单”升级为 `place_order`，Agent 执行器会将其收敛为 `add_to_cart` 并记录 scope guard。即使明确下单，系统也只创建形如 `LOCAL-0001` 的本地订单，状态固定为 `simulated_not_charged`。

## 与论文的准确关系

本演示复现的是论文中的系统关系：WebAgent 观察环境并逐步提出动作，ShieldAgent 作为在线后校验模块逐动作提供保护。它不复现 AWM 模型、WebArena 数据库、屏幕视觉模型、论文的概率电路权重、MLN 推理或论文报告的基准结果。
