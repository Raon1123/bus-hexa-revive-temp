import streamlit as st
import pandas as pd
import textwrap

from src.constants import WEEKDAY_STR
from src.tools import (
    get_timetable, get_time, 
    get_busroute_info
)

# Define colors for specific bus numbers for easy identification
BUS_COLORS = {
    513: "#D32F2F", # Red
    713: "#388E3C", # Green
    743: "#1976D2", # Blue
    753: "#7B1FA2", # Purple
    1115: "#F57C00", # Orange
}

def highlight_bus_rows(row):
    """
    Highlight the row based on the bus number (index).
    """
    bus_no = row.name # The index value
    color = BUS_COLORS.get(bus_no, "")
    if color:
        return [f'background-color: {color}'] * len(row)
    return [''] * len(row)

def page():
    weekday, hr, minute = get_time()
    busnos, departure_dict = get_busroute_info()

    st.write(f"Current time is {WEEKDAY_STR[weekday]} {hr:02d}:{minute:02d}")

    options = ["Weekday", "Saturday", "Sunday/Holiday"]
    week_selection = st.segmented_control("Select weekday", options, default=options[weekday])

    if week_selection is None:
        st.warning("Please select a day of the week.")
        return
    
    selected_weekday_idx = options.index(week_selection)

    # Prepare data for Time-Centric view (Group by Hour)
    schedules_by_hour = {} # {hour_str: [(minute_str, busno_int), ...]}

    # Sort busnos to keep order consistent
    busnos = sorted([int(b) for b in busnos])
    
    # Iterate through all buses and collect their schedules
    for busno in busnos:
        busno_str = str(busno)
        if busno_str in departure_dict and len(departure_dict[busno_str]) > 0:
            departure_point = departure_dict[busno_str][0]
            try:
                # get_timetable returns a list of "HH:MM" strings
                time_list = get_timetable(busno, selected_weekday_idx, departure_point)
                
                if time_list:
                    for time_str in time_list:
                        # expected format "HH:MM"
                        parts = time_str.split(':')
                        if len(parts) >= 2:
                            hr, mn = parts[0], parts[1]
                            if hr not in schedules_by_hour:
                                schedules_by_hour[hr] = []
                            schedules_by_hour[hr].append((mn, busno))
            except Exception as e:
                # Silently fail or log? For now, just skip if data issues
                pass

    if not schedules_by_hour:
        st.info("No timetable data available.")
        return

    # Sort the hours
    sorted_hours = sorted(schedules_by_hour.keys())

    # Build and display HTML Table
    html_code = generate_timetable_html(schedules_by_hour, sorted_hours)
    st.html(html_code)

def generate_timetable_html(schedules_by_hour, sorted_hours):
    # Using textwrap.dedent to avoid Markdown interpreting indented HTML as code blocks
    html_template = """
    <style>
        .timetable-table {{
            width: 100%;
            border-collapse: collapse;
            font-family: sans-serif;
            font-size: 0.9rem;
            table-layout: fixed; /* Allow specific column widths */
        }}
        .timetable-table th, .timetable-table td {{
            text-align: left;
            padding: 8px;
            border-bottom: 1px solid #eee;
            vertical-align: middle;
        }}
        .timetable-table th {{
            background-color: #f0f2f6;
            border-bottom: 2px solid #ddd;
        }}
        /* Specific column widths */
        .timetable-table th:first-child, .timetable-table td:first-child {{
            width: 50px; /* Narrower Hour column */
            text-align: center;
            font-weight: bold;
        }}
        .timetable-table th:nth-child(2), .timetable-table td:nth-child(2) {{
            width: auto; /* Allow Minutes to take remaining space */
        }}
        .timetable-row:hover {{
            background-color: #f9f9f9;
        }}
        .bus-badge {{
            display: inline-block;
            margin-right: 8px;
            margin-bottom: 4px;
            font-weight: bold;
        }}
    </style>
    <table class="timetable-table">
        <thead>
            <tr>
                <th>Hour</th>
                <th>Minutes</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
    """

    rows_html = ""
    for hr in sorted_hours:
        # Sort departures within the hour by minute, then by bus number
        departures = sorted(schedules_by_hour[hr], key=lambda x: (x[0], x[1]))
        
        minutes_html = []
        for mn, busno in departures:
            color = BUS_COLORS.get(busno, "#333") # default dark grey if not found
            
            minutes_html.append(
                f'<span class="bus-badge" style="color: {color};">{mn} ({busno})</span>'
            )
        
        minutes_str = " ".join(minutes_html)
        
        rows_html += f"""
            <tr class="timetable-row">
                <td>{hr}</td>
                <td>{minutes_str}</td>
            </tr>
        """

    # Generate Legend HTML
    legend_items = []
    for bus_no in sorted(BUS_COLORS.keys()):
        color = BUS_COLORS[bus_no]
        legend_items.append(
            f'<span style="color: {color}; font-weight: bold; margin-right: 15px;">{bus_no}</span>'
        )
    legend_html = f'<div style="margin-bottom: 10px; padding: 5px;">{"".join(legend_items)}</div>'

    final_html = textwrap.dedent(html_template).strip().format(rows=rows_html)
    return legend_html + final_html

if __name__ == "__page__":
    page()

