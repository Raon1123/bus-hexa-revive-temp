import streamlit as st

from src.constants import WEEKDAY_STR, ROUTEID, VIA_STOPS
from src.crawl import crawl_busstop
from src.scripts import notify_lastbus
from src.tools import (
    get_time, get_timetable, 
    get_busroute_info,
    get_now, get_timestr,
    is_not_early
)

def board_page():
    weekday, hr, minute = get_time()
    busnos, departure_dict = get_busroute_info()

    st.write(f"Current time is {WEEKDAY_STR[weekday]} {hr:02d}:{minute:02d}")

    time_list = []
    
    def after_timelist(timetable: list,
                       departure: str,
                       terminal: str,
                       hr: int, 
                       minute: int):
        return [(bus_number, terminal, f"{departure.split()[0]} 출발예정", arrival_time) for arrival_time in timetable if is_not_early(arrival_time, hr, minute)]

    for bus_number in busnos:
        departures = departure_dict[bus_number]

        if "UNIST" in departures:
            timetable = get_timetable(int(bus_number), weekday, "UNIST")
            terminal = departures[0] if departures[0] != "UNIST" else departures[1]

            time_list += after_timelist(timetable, "UNIST", terminal, hr, minute)
        else:
            departure, terminal = departures
            timetable = get_timetable(int(bus_number), weekday, departure)
            time_list += after_timelist(timetable, departure, terminal, hr, minute)

            terminal, departure = departures
            timetable = get_timetable(int(bus_number), weekday, departure)
            time_list += after_timelist(timetable, departure, terminal, hr, minute)
            
    if len(time_list) == 0:
        st.warning(notify_lastbus)
        return
    
    # add running bus
    try:
        bus_list = crawl_busstop("196040234")
    except Exception as e:
        st.error("Error while fetching bus information. Please try again later.")
        #st.exception(e)
        return
    if len(bus_list) == 0:
        st.warning("운행 중인 버스가 없습니다. (No running bus)")
        return
    for bus in bus_list:
        route_id = bus['route_id']
        arrival_time = bus['arrival_time']
        present = bus['present']

        bus_number = ROUTEID[route_id][0]
        terminal = ROUTEID[route_id][1]

        # add arrival time
        arrival_time = get_timestr(get_now([0,0,int(arrival_time)]), "%H:%M")

        # remove same number and terminal in time_list
        rm_index = []
        for idx, time_info in enumerate(time_list):
            if time_info[0] == bus_number and time_info[1].split()[0] == terminal.split()[0]:
                rm_index.append(idx)
                
        for idx in rm_index[::-1]:
            time_list.pop(idx)
                
        time_list.append((bus_number, terminal, present, arrival_time))
    
    # order by arrival time
    time_list.sort(key=lambda x: x[3])

    st.write("Timetable")

    time_frame = []
    for bus_time in time_list:
        bus_number, terminal, present, arrival_time = bus_time
        via_string = VIA_STOPS[bus_number][terminal.split()[0]]
        present = f"{terminal.split()[0]}행 {present}"
        time_frame.append((arrival_time, bus_number, present, via_string))
    
    html_str = html_timetable(time_frame[:10])
    
    st.markdown(html_str, unsafe_allow_html=True)
    

def html_timetable(time_frame: list):
    html_string = "<table>"
    first_time = "23:59"
    second_time = "23:59"
    
    # head column
    columns = ["노선번호", "출발 시각", "현재 위치"]
    column_string = "<tr>"
    for column in columns:
        column_string += f"<th scope=\"col\">{column}</th>"
    column_string += "</tr>"
    html_string += column_string
    
    for time_info in time_frame:
        bus_column = "<tr>"
        arrival_time = time_info[0]
        depart_hr, depart_minute = arrival_time.split(":")
        bus_number = time_info[1]
        present = time_info[2]
        via_string = time_info[3]
        
        flag = ""
        if present.split()[-1] != "출발예정":
            present += " 도착"

        if not (bus_number == "513" and present.split()[-1] == "출발예정"):
            if is_not_early(first_time, depart_hr, depart_minute):
                first_time = time_info[0]
                flag = "<p style=\"color:#DC143C\"><b>FIRST</b></p>"
            elif is_not_early(second_time, depart_hr, depart_minute):
                second_time = time_info[0]
                flag = "<p style=\"color:#0000CD\"><b>SECOND</b></p>"
            
        bus_column += "<td rowspan=\"2\">" + bus_number + "</td>"
        bus_column += "<td>" + arrival_time + "</td>"
        bus_column += "<td>" + present + "</td>"
        bus_column += "</tr>"
        
        bus_column += "<tr>"
        bus_column += "<td>" + flag + "</td>"
        bus_column += "<td>" + via_string + "</td>"
        
        bus_column += "</tr>"
        html_string += bus_column
        
    html_string += "</table>"
    
    return html_string


if __name__ == "__page__":
    board_page()