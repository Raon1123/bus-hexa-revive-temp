import streamlit as st

from src.scripts import notify_lastbus
from src.crawl import crawl_busstop
from src.tools import (
    get_timetable, get_time, 
    get_route_id, get_busroute_info,
    pretty_time)

COLS = 3
VISUALIZE = 2

def unist_buspage():
    via_row = st.columns(COLS)
    via_bus_list = []

    from_row = st.columns(COLS)
    from_bus_list = []

    weekday, hr, minute = get_time()
    _, departures = get_busroute_info()

    for key, val in departures.items():
        if "UNIST" in val:
            # input not UNIST
            direction = val[0] if val[0] != "UNIST" else val[1]
            from_bus_list.append((key, "UNIST", direction))
        else:
            # input UNIST
            via_bus_list.append((key, val[0], val[1]))
            via_bus_list.append((key, val[1], val[0]))
        
        print(f"Bus {key} - Departure: {val[0]}, Direction: {val[1]}")

    for id, col in enumerate(via_row + from_row):
        tile = col.container()
        if id < 2:
            # via
            if id >= len(via_bus_list):
                continue
            busno, departure, direction = via_bus_list[id]
            target_route_id = get_route_id(busno, direction)

            postfix = {
                "덕하": " (시내)",
                "삼남": " (울산역)"
            }

            direction = direction.split()[0]
            if direction in postfix:
                direction += "행" + postfix[direction]

            tile.write(f"#### {busno} {direction}")
            cnt = 0

            bus_list = crawl_busstop("196040234")
            for bus in bus_list:
                route_id = bus["route_id"]
                arrival_time = bus["arrival_time"]
                present = bus["present"]
                vehicle_no = bus["vehicle_no"]

                if route_id == target_route_id:
                    arrival_time, _, _ = pretty_time(arrival_time)

                    tile.write(f"{present} {arrival_time}")
                    cnt += 1
            
            time_list = get_timetable(int(busno), weekday, departure)

            # time after now
            time_list = [t for t in time_list if int(t.split(':')[0]) > hr or 
                        (int(t.split(':')[0]) == hr and int(t.split(':')[1]) >= minute)]

            # write first two bus
            for i in range(VISUALIZE- cnt):
                if i >= len(time_list):
                    tile.write(notify_lastbus)
                    break
                else:
                    tile.write(f"{time_list[i]} 출발 예정")

        else:
            # from
            busno, departure, direction = from_bus_list[id - 3]
            tile.write(f"#### {busno} {direction}행")

            time_list = get_timetable(int(busno), weekday, departure)

            # time after now
            time_list = [t for t in time_list if int(t.split(':')[0]) > hr or 
                        (int(t.split(':')[0]) == hr and int(t.split(':')[1]) >= minute)]

            # write first two bus
            for i in range(VISUALIZE):
                if i >= len(time_list):
                    tile.write(notify_lastbus)
                    break
                else:
                    tile.write(f"{time_list[i]} 출발 예정")


if __name__ == '__page__':
    unist_buspage()