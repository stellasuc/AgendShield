from __future__ import annotations

from agentshield.observability import SecuritySnapshot


def render_state(snapshot: SecuritySnapshot) -> None:
    import streamlit as st

    st.markdown("#### 数据状态")
    if not snapshot.data_objects:
        st.info("本次运行没有发现数据对象。")
        return
    by_id = {item.object_id: item for item in snapshot.data_objects}
    selected = st.selectbox(
        "选择数据对象",
        options=tuple(by_id),
        key=f"data-object-{snapshot.run_id}",
    )
    item = by_id[selected]
    first, second = st.columns(2)
    first.metric("数据分类", item.classification.replace("_", " ").title())
    second.metric(
        "是否含个人信息",
        "是" if item.contains_personal_data else "否",
    )
    st.markdown("**来源**")
    st.caption(item.source or "运行时派生对象")
    st.markdown("**任务目的**")
    st.caption(item.purpose or "未声明")
    st.markdown("**信息类别**")
    st.caption(", ".join(item.categories) if item.categories else "未检测到")
    if item.recipients:
        st.markdown("**接收方**")
        st.caption(", ".join(item.recipients))
    if item.transformations:
        st.markdown("**处理方式**")
        st.caption(", ".join(item.transformations))
    if item.safe_summary:
        st.success(item.safe_summary)
    fingerprint = item.content_fingerprint or "unavailable"
    st.caption(f"内容指纹：{fingerprint[:16]}…")
