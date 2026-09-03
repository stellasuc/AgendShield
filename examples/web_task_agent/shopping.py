"""Deterministic local shopping environment used by the WebAgent demo.

The environment behaves like a small e-commerce site but never contacts a real
merchant or payment processor.  It deliberately exposes both rendered HTML and
an accessibility-tree-like observation because SHIELDAGENT evaluates WebAgents
that act from screenshots and AX trees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Any, Mapping


SHOPPING_PRODUCTS: tuple[dict[str, Any], ...] = (
    {
        "product_id": "AUD-QP600",
        "product": "QuietPro 600 无线降噪耳机",
        "category": "耳机",
        "price": 599.0,
        "rating": 4.8,
        "reviews": 1286,
        "stock": 23,
        "keywords": ("降噪", "耳机", "办公", "蓝牙", "noise cancelling", "headphones"),
        "description": "双设备连接，40 小时续航，适合开放式办公室。",
    },
    {
        "product_id": "AUD-FA420",
        "product": "FocusAir 420 头戴式降噪耳机",
        "category": "耳机",
        "price": 429.0,
        "rating": 4.6,
        "reviews": 864,
        "stock": 41,
        "keywords": ("降噪", "耳机", "通勤", "蓝牙", "noise cancelling", "headphones"),
        "description": "轻量化佩戴，支持环境声模式和 USB-C 快充。",
    },
    {
        "product_id": "KEY-ERGO89",
        "product": "ErgoType 89 人体工学机械键盘",
        "category": "键盘",
        "price": 489.0,
        "rating": 4.7,
        "reviews": 532,
        "stock": 18,
        "keywords": ("人体工学", "机械键盘", "办公", "keyboard", "ergonomic"),
        "description": "分区曲面键位，静音轴体，支持 Windows 与 macOS。",
    },
    {
        "product_id": "KEY-COMPACT68",
        "product": "Compact 68 便携机械键盘",
        "category": "键盘",
        "price": 269.0,
        "rating": 4.5,
        "reviews": 915,
        "stock": 37,
        "keywords": ("机械键盘", "便携", "keyboard", "compact"),
        "description": "68 键紧凑布局，三模连接，可热插拔。",
    },
    {
        "product_id": "MOU-VERT01",
        "product": "VertiComfort 人体工学鼠标",
        "category": "鼠标",
        "price": 219.0,
        "rating": 4.7,
        "reviews": 1104,
        "stock": 56,
        "keywords": ("人体工学", "鼠标", "办公", "mouse", "ergonomic"),
        "description": "57 度垂直握姿，静音按键，支持多设备切换。",
    },
    {
        "product_id": "MON-27QHD",
        "product": "ViewSpace 27 英寸 2K 显示器",
        "category": "显示器",
        "price": 1299.0,
        "rating": 4.9,
        "reviews": 347,
        "stock": 9,
        "keywords": ("显示器", "2k", "办公", "monitor", "qhd"),
        "description": "IPS 面板，USB-C 65W 供电，支持升降旋转。",
    },
)


def storefront_snapshot(
    *,
    query: str = "",
    max_price: float | None = None,
) -> dict[str, Any]:
    """Return a serializable storefront observation with HTML and an AX tree."""
    products = search_products(query=query, max_price=max_price)
    return {
        "environment": "shopping",
        "page_type": "search_results",
        "site_name": "Northstar Market",
        "query": query,
        "max_price": max_price,
        "result_count": len(products),
        "items": products,
        "html": _render_html(products, query, max_price),
        "accessibility_tree": _render_ax_tree(products, query),
    }


def product_detail_snapshot(product_id: str) -> dict[str, Any]:
    product = _public_product(_product(product_id))
    title = escape(str(product["product"]))
    html = (
        "<!doctype html><html lang='zh-CN'><body><nav><a href='/search'>返回搜索结果</a></nav>"
        f"<main data-product-id='{escape(product_id)}'><h1>{title}</h1>"
        f"<p>¥{float(product['price']):.2f} · {product['rating']} 分 · 库存 {product['stock']}</p>"
        f"<p>{escape(str(product['description']))}</p>"
        f"<button aria-label='将 {title} 加入购物车'>加入购物车</button></main></body></html>"
    )
    return {
        "environment": "shopping",
        "page_type": "product_detail",
        "site_name": "Northstar Market",
        "product": product,
        "html": html,
        "accessibility_tree": [
            {"role": "link", "accessible_name": "返回搜索结果"},
            {"role": "heading", "accessible_name": str(product["product"])},
            {"role": "text", "accessible_name": f"¥{float(product['price']):.2f}，评分 {product['rating']}"},
            {"role": "button", "accessible_name": f"将 {product['product']} 加入购物车"},
        ],
    }


def search_products(*, query: str = "", max_price: float | None = None) -> list[dict[str, Any]]:
    tokens = tuple(token for token in query.lower().replace("，", " ").split() if token)
    matches: list[dict[str, Any]] = []
    for product in SHOPPING_PRODUCTS:
        searchable = " ".join(
            (
                str(product["product"]),
                str(product["category"]),
                str(product["description"]),
                *(str(item) for item in product["keywords"]),
            )
        ).lower()
        if tokens and not all(token in searchable for token in tokens):
            continue
        if max_price is not None and float(product["price"]) > max_price:
            continue
        matches.append({key: value for key, value in product.items() if key != "keywords"})
    return sorted(matches, key=lambda item: (-float(item["rating"]), float(item["price"])))


def choose_product(items: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Choose the highest-rated item, using price as a deterministic tie-breaker."""
    if not items:
        return None
    selected = min(items, key=lambda item: (-float(item["rating"]), float(item["price"])))
    return dict(selected)


@dataclass(slots=True)
class LocalShoppingBackend:
    """Stateful local cart and simulated order backend owned by the broker."""

    cart: dict[str, int] = field(default_factory=dict)
    orders: list[dict[str, Any]] = field(default_factory=list)

    def apply(self, action: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if action == "add_to_cart":
            product = _product(str(arguments.get("product_id", "")))
            quantity = _quantity(arguments.get("quantity", 1))
            if product["stock"] < quantity:
                raise ValueError("Requested quantity exceeds local inventory")
            self.cart[product["product_id"]] = self.cart.get(product["product_id"], 0) + quantity
            return {
                "status": "cart_updated",
                "action": action,
                "selected_product": _public_product(product),
                "cart": self.cart_snapshot(),
            }
        if action == "place_order":
            if not self.cart:
                raise ValueError("Cannot place an order with an empty cart")
            order = {
                "order_id": f"LOCAL-{len(self.orders) + 1:04d}",
                "status": "simulated_not_charged",
                "items": self.cart_snapshot()["items"],
                "total": self.cart_snapshot()["total"],
            }
            self.orders.append(order)
            self.cart.clear()
            return {"status": "order_recorded", "action": action, "order": order, "cart": self.cart_snapshot()}
        if action == "record_view":
            return {"status": "view_recorded", "action": action, "cart": self.cart_snapshot()}
        raise ValueError(f"Unsupported shopping action: {action}")

    def cart_snapshot(self) -> dict[str, Any]:
        items = []
        for product_id, quantity in self.cart.items():
            product = _product(product_id)
            items.append(
                {
                    **_public_product(product),
                    "quantity": quantity,
                    "subtotal": round(float(product["price"]) * quantity, 2),
                }
            )
        return {
            "items": items,
            "item_count": sum(item["quantity"] for item in items),
            "total": round(sum(item["subtotal"] for item in items), 2),
            "currency": "CNY",
        }


def _product(product_id: str) -> dict[str, Any]:
    for product in SHOPPING_PRODUCTS:
        if product["product_id"] == product_id:
            return product
    raise ValueError(f"Unknown local product: {product_id}")


def _quantity(value: Any) -> int:
    try:
        quantity = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Quantity must be an integer") from exc
    if not 1 <= quantity <= 5:
        raise ValueError("Quantity must be between 1 and 5")
    return quantity


def _public_product(product: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in product.items() if key != "keywords"}


def _render_html(products: list[dict[str, Any]], query: str, max_price: float | None) -> str:
    cards = "".join(
        "<article data-product-id='{id}'><h2>{name}</h2><p>¥{price:.2f} · {rating} 分 · 库存 {stock}</p>"
        "<button aria-label='将 {name} 加入购物车'>加入购物车</button></article>".format(
            id=escape(str(item["product_id"])),
            name=escape(str(item["product"])),
            price=float(item["price"]),
            rating=float(item["rating"]),
            stock=int(item["stock"]),
        )
        for item in products
    )
    budget = "不限" if max_price is None else f"¥{max_price:.2f}"
    return (
        "<!doctype html><html lang='zh-CN'><body><header><h1>Northstar Market</h1></header>"
        f"<main><form role='search'><input aria-label='搜索商品' value='{escape(query)}'></form>"
        f"<p>预算：{budget}；找到 {len(products)} 件商品</p>{cards}</main></body></html>"
    )


def _render_ax_tree(products: list[dict[str, Any]], query: str) -> list[dict[str, str]]:
    tree = [
        {"role": "banner", "accessible_name": "Northstar Market"},
        {"role": "searchbox", "accessible_name": "搜索商品", "value": query},
        {"role": "status", "accessible_name": f"找到 {len(products)} 件商品"},
    ]
    for item in products:
        tree.extend(
            (
                {"role": "heading", "accessible_name": str(item["product"])},
                {"role": "text", "accessible_name": f"¥{float(item['price']):.2f}，评分 {item['rating']}"},
                {"role": "button", "accessible_name": f"将 {item['product']} 加入购物车"},
            )
        )
    return tree
