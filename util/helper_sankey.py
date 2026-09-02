import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

def build_sankey_chart(metrics_data, title):
    """
    Generates a Plotly Sankey diagram charting Supplier Type -> Warehouse -> State,
    colored by Product Group (Category).
    """
    in_agg = metrics_data['inbound_flows'].groupby(['supplier_group', 'wh_name', 'category'])['inbound_pallets'].sum().reset_index()
    out_agg = metrics_data['outbound_flows'].groupby(['wh_name', 'state', 'category'])['allocated_pallets'].sum().reset_index()

    all_nodes = list(pd.concat([
        in_agg['supplier_group'], in_agg['wh_name'],
        out_agg['wh_name'], out_agg['state']
    ]).unique())

    node_dict = {node: i for i, node in enumerate(all_nodes)}
    
    unique_categories = list(pd.concat([in_agg['category'], out_agg['category']]).unique())
    base_colors = px.colors.qualitative.Alphabet
    
    def hex_to_rgba(hex_code, opacity=0.5):
        hex_code = hex_code.lstrip('#')
        if len(hex_code) == 6:
            r, g, b = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
            return f"rgba({r},{g},{b},{opacity})"
        return hex_code

    category_colors = {cat: hex_to_rgba(base_colors[i % len(base_colors)]) for i, cat in enumerate(unique_categories)}

    sources, targets, values, link_colors, hover_text = [], [], [], [], []

    for _, row in in_agg.iterrows():
        if row['inbound_pallets'] > 0:
            sources.append(node_dict[row['supplier_group']])
            targets.append(node_dict[row['wh_name']])
            values.append(row['inbound_pallets'])
            link_colors.append(category_colors[row['category']])
            hover_text.append(row['category'])

    for _, row in out_agg.iterrows():
        if row['allocated_pallets'] > 0:
            sources.append(node_dict[row['wh_name']])
            targets.append(node_dict[row['state']])
            values.append(row['allocated_pallets'])
            link_colors.append(category_colors[row['category']])
            hover_text.append(row['category'])

    fig = go.Figure(data=[go.Sankey(
        arrangement="snap",
        node=dict(
            pad=15, thickness=20,
            line=dict(color="black", width=0.5),
            label=all_nodes,
            color="#385D7F"
        ),
        link=dict(
            source=sources, target=targets, value=values,
            color=link_colors,
            customdata=hover_text,
            hovertemplate='%{source.label} → %{target.label}<br><b>Product:</b> %{customdata}<br><b>Volume:</b> %{value:,.0f} Pallets<extra></extra>'
        )
    )])
    
    fig.update_layout(title_text=title, font_size=10, height=600, margin=dict(t=40, b=20, l=0, r=0))
    return fig