import plotly.graph_objects as go
import streamlit_highcharts as hct

def render_highcharts_waterfall(components, base_vals, scen_vals=None, is_scenario=False, value_title="EUR", format_millions=False):
    """
    Generates a theme-adaptive grouped Waterfall chart using Highcharts.
    """
    series_list = []
    
    # --- Baseline Series ---
    base_data = []
    for comp, val in zip(components, base_vals):
        point = {"name": comp, "y": float(val)}
        if format_millions:
            point["dataLabels"] = {"format": f"{val / 1000000:.1f}M"}
        base_data.append(point)
        
    base_total = sum(base_vals)
    base_total_point = {"name": "Total", "isSum": True, "color": "#193661"}
    if format_millions:
        base_total_point["dataLabels"] = {"format": f"{base_total / 1000000:.1f}M"}
    base_data.append(base_total_point)
    
    series_list.append({
        "name": "Baseline",
        "data": base_data,
        "color": "#385D7F",
        "dataLabels": {
            "enabled": True,
            "format": '{point.y:,.0f}',
            "verticalAlign": "top",
            "y": -20,
            "style": {
                "fontSize": "13px", 
                "fontWeight": "bold", 
                "color": "var(--text-color)", # Theme-adaptive text
                "textOutline": "none"         # Prevents white halos on dark mode
            }
        },
        "pointPadding": 0.05
    })
    
    # --- Scenario Series ---
    if is_scenario and scen_vals:
        scen_data = []
        for comp, val in zip(components, scen_vals):
            point = {"name": comp, "y": float(val)}
            if format_millions:
                point["dataLabels"] = {"format": f"{val / 1000000:.1f}M"}
            scen_data.append(point)
            
        scen_total = sum(scen_vals)
        scen_total_point = {"name": "Total", "isSum": True, "color": "#7A121C"}
        if format_millions:
            scen_total_point["dataLabels"] = {"format": f"{scen_total / 1000000:.1f}M"}
        scen_data.append(scen_total_point)
        
        series_list.append({
            "name": "Scenario",
            "data": scen_data,
            "color": "#CB333B",
            "dataLabels": {
                "enabled": True,
                "format": '{point.y:,.0f}',
                "verticalAlign": "top",
                "y": -20,
                "style": {
                    "fontSize": "13px", 
                    "fontWeight": "bold", 
                    "color": "var(--text-color)", # Theme-adaptive text
                    "textOutline": "none"
                }
            },
            "pointPadding": 0.05
        })

    # --- Highcharts Configuration ---
    chart_config = {
        "chart": {"type": "waterfall", "height": 450, "backgroundColor": "transparent"},
        "title": {"text": ""},
        "xAxis": {
            "type": "category",
            "labels": {"style": {"color": "var(--text-color)"}},
            "lineColor": "var(--text-color)",
            "tickColor": "var(--text-color)"
        },
        "yAxis": {
            "title": {"text": value_title, "style": {"color": "var(--text-color)"}},
            "labels": {"style": {"color": "var(--text-color)"}},
            "gridLineColor": "rgba(128, 128, 128, 0.2)" # Neutral grid line
        },
        "legend": {
            "enabled": True,
            "itemStyle": {"color": "var(--text-color)", "fontWeight": "normal"},
            "itemHoverStyle": {"color": "var(--primary-color)"}
        },
        "tooltip": {
            "pointFormat": '<b>{point.y:,.0f}</b>',
            "backgroundColor": "var(--background-color)",
            "style": {"color": "var(--text-color)"}
        },
        "series": series_list,
        "exporting": {"enabled": False},
        "credits": {"enabled": False}
    }

    return hct.streamlit_highcharts(chart_config, 450)