from __future__ import annotations

from agentshield.observability import SecuritySnapshot


def render_lineage(snapshot: SecuritySnapshot) -> None:
    import graphviz
    import streamlit as st

    st.markdown("#### 数据如何流转")
    if not snapshot.data_objects and not snapshot.lineage:
        st.info("本次运行没有可展示的数据流转。")
        return
    graph = graphviz.Digraph()
    graph.attr(rankdir="LR", bgcolor="transparent", pad="0.2")
    graph.attr(
        "node",
        shape="box",
        style="rounded,filled",
        fontname="Helvetica",
        fontsize="10",
        color="#94a3b8",
        fillcolor="#f8fafc",
        fontcolor="#0f172a",
    )
    known = {item.object_id for item in snapshot.data_objects}
    for item in snapshot.data_objects:
        label = f"{item.object_id}\\n{item.classification}"
        fill = "#fef2f2" if item.contains_personal_data else "#ecfdf5"
        graph.node(item.object_id, label, fillcolor=fill)
    for edge in snapshot.lineage:
        if edge.source not in known:
            graph.node(edge.source, edge.source, shape="ellipse")
        if edge.target not in known:
            graph.node(
                edge.target,
                edge.target,
                shape="ellipse",
                fillcolor="#eff6ff",
            )
        graph.edge(edge.source, edge.target, label=edge.transformation)
    st.graphviz_chart(graph, width="stretch")
    st.caption(
        "节点代表数据对象与分类；连线来自实际修复记录和已成功执行的效果目标。"
    )
