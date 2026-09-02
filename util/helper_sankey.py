import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

def build_sankey_chart(metrics_data, title):
    """
    Generates a Plotly Sankey diagram charting Supplier Type -> Warehouse -> State,
    colored by SOURCE NODE (each supplier type / warehouse gets a consistent color,
    its outgoing links inherit it) rather than by product group — with ~18 product
    groups the per-category coloring produced too many colors/links to read.
    """
    in_agg = metrics_data['inbound_flows'].groupby(['supplier_group', 'wh_name'])['inbound_pallets'].sum().reset_index()
    out_agg = metrics_data['outbound_flows'].groupby(['wh_name', 'state'])['allocated_pallets'].sum().reset_index()

    all_nodes = list(pd.concat([
        in_agg['supplier_group'], in_agg['wh_name'],
        out_agg['wh_name'], out_agg['state']
    ]).unique())

    node_dict = {node: i for i, node in enumerate(all_nodes)}

    def hex_to_rgba(hex_code, opacity=0.5):
        hex_code = hex_code.lstrip('#')
        if len(hex_code) == 6:
            r, g, b = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
            return f"rgba({r},{g},{b},{opacity})"
        return hex_code

    # only nodes that ever act as a link SOURCE need a color (supplier types, warehouses) —
    # target-only nodes (states) stay neutral so the chart isn't fighting for palette space
    source_nodes = list(pd.concat([in_agg['supplier_group'], out_agg['wh_name']]).unique())
    base_colors = px.colors.qualitative.Set2
    node_colors = {node: base_colors[i % len(base_colors)] for i, node in enumerate(source_nodes)}
    NEUTRAL = "#B0B0B0"

    sources, targets, values, link_colors = [], [], [], []

    for _, row in in_agg.iterrows():
        if row['inbound_pallets'] > 0:
            sources.append(node_dict[row['supplier_group']])
            targets.append(node_dict[row['wh_name']])
            values.append(row['inbound_pallets'])
            link_colors.append(hex_to_rgba(node_colors[row['supplier_group']]))

    for _, row in out_agg.iterrows():
        if row['allocated_pallets'] > 0:
            sources.append(node_dict[row['wh_name']])
            targets.append(node_dict[row['state']])
            values.append(row['allocated_pallets'])
            link_colors.append(hex_to_rgba(node_colors[row['wh_name']]))

    node_display_colors = [node_colors.get(n, NEUTRAL) for n in all_nodes]

    fig = go.Figure(data=[go.Sankey(
        arrangement="snap",
        node=dict(
            pad=15, thickness=20,
            line=dict(color="black", width=0.5),
            label=all_nodes,
            color=node_display_colors
        ),
        link=dict(
            source=sources, target=targets, value=values,
            color=link_colors,
            hovertemplate='%{source.label} → %{target.label}<br><b>Volume:</b> %{value:,.0f} Pallets<extra></extra>'
        )
    )])

    fig.update_layout(title_text=title, font_size=10, height=600, margin=dict(t=40, b=20, l=0, r=0))
    return fig