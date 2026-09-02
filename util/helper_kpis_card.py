import streamlit as st
from streamlit_extras.stylable_container import stylable_container

def formatCurrency(value):
    if abs(value) >= 1000000 or value <= -1000000:
        return "{:,.1f} M".format(value / 1000000)
    else:
        return "{:,.0f}".format(round(value, 1))

def createValueBox(main_scenario_name, kpi_type, compare_scenario_name, main_scenario_value, compare_scenario_value, unit="CBM", color="var(--primary-color)"):
    with stylable_container(
        key=f'kpi_std_{kpi_type.replace(" ", "")}',
        css_styles="""
        {
            background-color: var(--secondary-background-color);
            border-radius: 4px;
            text-align: center;
            padding-bottom: 15px;
            font-family: var(--font);
            box-shadow: 0px 2px 4px rgba(0, 0, 0, 0.1);
        }
        """
        ):
        if compare_scenario_value == 0:
            gap_percent = 0
        else:
            gap_percent = (main_scenario_value - compare_scenario_value) * 100 / compare_scenario_value

        main_scenario_value_formatted = formatCurrency(main_scenario_value)
        string_name = f"<b style='color: var(--text-color); font-size: 15px; margin: 0; padding: 0; text-align: center;'>{kpi_type}</b>"
        string_value = f"<b style='font-size: 30px; color: {color}; font-weight: bold;'>{main_scenario_value_formatted}</b><span style='font-size: 15px; color: var(--text-color);'> {unit}</span>"
        
        gap_percent = round(gap_percent, 1)
        if main_scenario_name == compare_scenario_name:
            string_perc = f"<text style='font-size: 14px; text-align: center; color: var(--text-color)'>Main scenario</text>"
        elif gap_percent > 0:
            string_perc = f"<text style='font-size: 14px; text-align: center; color: var(--text-color);'><b>+{gap_percent}</b>% vs. {compare_scenario_name}</text>"
        else:
            string_perc = f"<text style='font-size: 14px; text-align: center; color: var(--text-color);'><b>{gap_percent}</b>% vs. {compare_scenario_name}</text>"

        html_content = f"""
            <div style = "margin: 0; padding: 0;">
                <div>{string_name}</div>
                <div>{string_value}</div>
                <div class="small-box-footer" style = "background-color: rgba(128, 128, 128, 0.1); padding: 0; margin: 0; position: relative; display: block">
                    {string_perc}
                </div>
            </div>
        """
        st.markdown(html_content, unsafe_allow_html=True)


def create_kpi_card(main_scenario_name, kpi_type, compare_scenario_name, main_value, compare_value, column, unit, color="var(--primary-color)"):
    with column:
        createValueBox(main_scenario_name, kpi_type, compare_scenario_name, float(main_value), float(compare_value), unit, color)


def createValueBox_wBackground(main_scenario_name, kpi_type, compare_scenario_name, main_scenario_value, compare_scenario_value, unit="CBM", color="var(--primary-color)"):
    with stylable_container(
        key=f'kpi_bg_{kpi_type.replace(" ", "")}',
        css_styles="""
        {
            background-color: var(--secondary-background-color);
            border-radius: 4px;
            text-align: center;
            padding-bottom: 15px;
            font-family: var(--font);
            box-shadow: 0px 2px 4px rgba(0, 0, 0, 0.1);
        }
        """
        ):
        if compare_scenario_value == 0:
            gap_percent = 0
        else:
            gap_percent = (main_scenario_value - compare_scenario_value) * 100 / compare_scenario_value

        main_scenario_value_formatted = formatCurrency(main_scenario_value)
        string_name = f"<b style='color: var(--text-color); font-size: 15px; margin: 0; padding: 0; text-align: center;'>{kpi_type}</b>"
        string_value = f"<b style='font-size: 30px; color: {color}; font-weight: bold;'>{main_scenario_value_formatted}</b><span style='font-size: 15px; color: var(--text-color);'> {unit}</span>"
        
        gap_percent = round(gap_percent, 1)
        
        if main_scenario_name == compare_scenario_name:
            string_perc = "<text style='font-size: 14px; text-align: center; color: var(--text-color)'>Main scenario</text>"
            bg_color = "rgba(128, 128, 128, 0.1)"
        elif gap_percent > 0:
            string_perc = f"<text style='font-size: 14px; text-align: center; color: #FFFFFF;'><b>+{gap_percent}</b>% vs. {compare_scenario_name}</text>"
            bg_color = "#CB333B" # Red for cost increase
        else:
            string_perc = f"<text style='font-size: 14px; text-align: center; color: #FFFFFF;'><b>{gap_percent}</b>% vs. {compare_scenario_name}</text>"
            bg_color = "rgba(11, 156, 49, 1)" # Green for cost savings

        html_content = f"""
            <div style = "margin: 0; padding: 0;">
                <div>{string_name}</div>
                <div>{string_value}</div>
                <div class="small-box-footer" style = "background-color: {bg_color}; padding: 0; margin: 0; position: relative; display: block">
                    {string_perc}
                </div>
            </div>
        """
        st.markdown(html_content, unsafe_allow_html=True)


def create_kpi_card_wbackground(main_scenario_name, kpi_type, compare_scenario_name, main_value, compare_value, column, unit, color="var(--primary-color)"):
    with column:
        createValueBox_wBackground(main_scenario_name, kpi_type, compare_scenario_name, float(main_value), float(compare_value), unit, color)