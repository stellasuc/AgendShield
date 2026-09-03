# Complete Shopping WebAgent demo

[简体中文](shopping_demo.zh-CN.md)

## Why a local store is included

The SHIELDAGENT paper evaluates an AWM WebAgent across Shopping, CMS, Reddit, GitLab, Maps, and SuiteCRM WebArena environments. AgentShield therefore includes Northstar Market: a stateful local shopping environment where page observations, product selection, and side effects actually execute and produce audit evidence.

“Real” here means a functional local application, not a commercial storefront or payment integration. The environment provides six structured products, bilingual keyword search, budget filtering, rating-based selection, search and product-detail HTML, accessibility-tree-style observations, a broker-owned cart, and simulated non-charging orders. Every read and state change is mediated and audited. No live site, account, payment processor, or real charge is involved.

## Recommended prompt

```text
在购物网站中寻找预算不超过 600 元的降噪耳机，选择评分最高的一款加入购物车，不要下单。
```

The online model must return the fixed `execute_web_task` schema. It cannot invent tools or product IDs; IDs must originate from the local page observation. The actual trajectory reads search results, selects the highest-rated eligible product, reads its detail page, submits `add_to_cart` through the Capability Broker, and releases a response.

An order is permitted only when the prompt explicitly confirms submission. Even then, the backend creates only a `LOCAL-*` order with `simulated_not_charged` status.

## Exact relationship to the paper

This demo implements the paper's system relationship: a WebAgent observes an environment and proposes actions step by step, while ShieldAgent checks those actions online. It does not reproduce AWM, the WebArena databases, a screenshot vision model, learned probabilistic circuit weights, MLN inference, or the paper's benchmark results.
