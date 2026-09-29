import datetime
import os
import json

from typing import (
    Union, Optional,
    List
)

import openpyxl
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup

from src.constants import ROUTEID, UNIST_STR
from src.crawl import is_holiday

def get_now(after: Optional[List[int]] = None):
    now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=9)))
    
    if after is not None:
        now = now + datetime.timedelta(hours=after[0], minutes=after[1], seconds=after[2])
    
    return now


def get_weekday(now: Union[datetime.datetime, datetime.date]=None):
    if isinstance(now, datetime.date):
        now = datetime.datetime(now.year, now.month, now.day)
    day_of_week = now.weekday()
    year, month, day = now.year, now.month, now.day 
    
    if is_holiday(year, month, day):
        day_of_week = 2
    elif day_of_week in [5, 6]:
        day_of_week = day_of_week - 4
    else:
        day_of_week = 0
        
    return day_of_week


def get_time():
    now = get_now()
    hr, minute = now.hour, now.minute
    
    day_of_week = get_weekday(now)

    return day_of_week, hr, minute


def get_timestr(now: datetime.datetime=None,
                timeformat: str="%H%M%S"):
    if now is None:
        now = get_now()
    return now.strftime(timeformat)


def log_string(log_str: str):
    timestamp = get_timestr()
    print(timestamp, ":", log_str)


def get_timetable_xlsx(busno: Union[str, int], 
                       weekday: int, 
                       departure: str):
    matching_dict = {
        0: "workingday",
        1: "Saturday",
        2: "SunHoliday"
    }
    
    assert weekday in matching_dict.keys(), "Invalid weekday"
    
    if isinstance(busno, str):
        busno = int(busno)
    bus_no_dict = {
        513: "513(구337)",
        713: "713(구133)",
        743: "743(구733)",
        753: "753(구743)",
        1115: "1115"
    }
    
    assert busno in bus_no_dict.keys(), "Invalid bus number"
    
    file_name = os.path.join("timetable", "{}.xlsx".format(matching_dict[weekday]))
    
    wb = openpyxl.load_workbook(file_name)
    sheet = wb[bus_no_dict[busno]]
    df = pd.DataFrame(sheet.values)
    
    # collect every column with matching departure
    start_row = 0
    departure_col = []
    for i, row in enumerate(df.values):
        for j, col in enumerate(row):
            if departure == str(col):
                departure_col.append(j)
        if len(departure_col) > 0 and start_row == 0:
            start_row = i
            break
    
    # get the timetable
    timetable = []
    for i, row in enumerate(df.values):
        if i <= start_row:
            continue
        for j in departure_col:
            if row[j] is not None:
                time = str(row[j])
                # as format 00:00:00
                if len(time) == 8:
                    timetable.append(time[:5])
                else:
                    if len(time) == 3:
                        timetable.append("0" + time[0] + ":" + time[1:])
                    else:
                        timetable.append(time[:2] + ":" + time[2:])
                                           
    # sort the timetable
    timetable.sort()
    return timetable


def get_timetable(bus_number: int, 
                  weekday: int, 
                  departure: str):
    departure = departure.split()[0]
    file_name = "timetable/{}.json".format(bus_number)
    with open(file_name, "r") as f:
        timetable = json.load(f)
    timetable = timetable[str(weekday)][departure]
    return timetable


def init_timetable():
    busnos, departure_dict = get_busroute_info()
    weekdays = [0, 1, 2]
    
    for busno in busnos:
        timetable_dict = {}
        for weekday in weekdays:
            timetable_dict[weekday] = {}
            for departure in departure_dict[busno]:
                departure = departure.split()[0]

                if departure == "UNIST":
                    _departure = UNIST_STR[busno]
                else:
                    _departure = departure

                timetable = get_timetable_xlsx(busno, weekday, _departure)
                timetable_dict[weekday][departure] = timetable
                #save the timetable to json
        with open("timetable/{}.json".format(busno), "w") as f:
            json.dump(timetable_dict, f, ensure_ascii=False)
            print("Save timetable to json")
    
    
def pageblock_busstop(bus_list: list,
                      route_str: dict,
                      verbose: bool = False):
    table_str = "| Bus Number | Arrival Time | Present Stop | Vehicle Number |\n| ---------- | ------------ | ------------ | -------------- |\n"
    
    for bus in bus_list:
        route_id = bus['route_id']
        arrival_time = bus['arrival_time']
        present = bus['present']
        vehicle_no = bus['vehicle_no']

        direction_str = f"{route_str[route_id][0]} {route_str[route_id][1].split()[0]}행 {' '.join(route_str[route_id][1].split()[1:])}"

        arrival_time, _, _ = pretty_time(arrival_time)
        
        table_str += f"| {direction_str}  | {arrival_time} | {present} | {vehicle_no} |\n"
    
    if len(bus_list) == 0:
        table_str += "| - | 운행 중인 버스가 없습니다. | No BUS | - |\n"
        
    if verbose:
        st.write(table_str)
    
    return table_str
    

def get_route_id(busno: int,
                 departure: str,):
    departure = departure.split()[0]
    for route_id, route_info in ROUTEID.items():
        if route_info[0] == busno and route_info[1].split()[0] == departure:
            return route_id


def pretty_time(arrival_time: Union[int, str]):
    if isinstance(arrival_time, str):
        arrival_time = int(arrival_time)

    arrival_min = arrival_time // 60
    arrival_sec = arrival_time % 60

    pretty_string = ""

    if arrival_min == 0:
        pretty_string = f"{arrival_sec}초"
    else:
        pretty_string = f"{arrival_min}분 {arrival_sec}초"

    return pretty_string, arrival_min, arrival_sec


def is_not_early(arrival_time: str,
                 hr: Union[int, str],
                 minute: Union[int, str]):
    if isinstance(hr, str):
        hr = int(hr)
    if isinstance(minute, str):
        minute = int(minute)
    
    arrival_hr = int(arrival_time.split(":")[0])
    arrival_min = int(arrival_time.split(":")[1])

    if arrival_hr > hr or (arrival_hr == hr and arrival_min >= minute):
        return True
    return False


def get_busroute_info():
    busnos = []
    departure_dict = {}

    for routes in ROUTEID.values():
        bus_number = routes[0]
        if bus_number not in busnos:
            busnos.append(bus_number)
        
        if bus_number not in departure_dict.keys():
            departure_dict[bus_number] = []
        
        departure = routes[2]
        if departure not in departure_dict[bus_number]:
            departure_dict[bus_number].append(departure)

    return busnos, departure_dict


if __name__ == "__main__":
    init_timetable()