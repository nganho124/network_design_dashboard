import plotly.graph_objects as go

def build_cost_comparison_chart(components, base_vals, scen_vals, is_scenario, prefix="€", suffix=""):
    """
    Generates a grouped bar chart comparing Baseline vs Scenario costs.
    """
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name='Baseline', x=components, y=base_vals,
        marker_color='#385D7F', text=[f"{prefix}{v:,.0f}{suffix}" for v in base_vals], textposition='auto'
    ))
    
    if is_scenario:
        fig.add_trace(go.Bar(
            name='Scenario', x=components, y=scen_vals,
            marker_color='#CB333B', text=[f"{prefix}{v:,.0f}{suffix}" for v in scen_vals], textposition='auto'
        ))
        
    fig.update_layout(
        barmode='group', height=400, margin=dict(t=20, b=20, l=0, r=0), 
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig

def build_capacity_utilization_chart(wh_base, wh_scen=None, is_scenario=False):
    """
    Generates a horizontal bar chart displaying used capacity vs total capacity.
    """
    wh_chart = wh_base.copy()
    if is_scenario and wh_scen is not None:
        wh_chart = wh_chart.merge(wh_scen, on='wh_name', how='left').fillna(0)
    else:
        wh_chart['scen_used'] = wh_chart['base_used']

    wh_chart = wh_chart.sort_values('capacity_pallets', ascending=True)

    fig_util = go.Figure()
    
    fig_util.add_trace(go.Bar(
        y=wh_chart['wh_name'], x=wh_chart['base_used'],
        name='Baseline Used', orientation='h', marker_color='#385D7F'
    ))
    
    if is_scenario:
        fig_util.add_trace(go.Bar(
            y=wh_chart['wh_name'], x=wh_chart['scen_used'],
            name='Scenario Used', orientation='h', marker_color='#CB333B'
        ))
        
    fig_util.add_trace(go.Scatter(
        y=wh_chart['wh_name'], x=wh_chart['capacity_pallets'],
        name='Max Capacity', mode='markers',
        # Changed marker line color to a neutral gray for dark mode compatibility
        marker=dict(symbol='line-ns', size=20, color='rgba(128,128,128,0.8)', line=dict(width=3)) 
    ))

    fig_util.update_layout(
        barmode='group',
        height=max(400, len(wh_chart) * 45),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig_util