import datetime
import streamlit as st
import pandas as pd

from src.constants import ROUTEID, STOP_IDS
from src.tools import get_timetable, get_weekday
from crawl.db import BUS_TIMELOG


def stop_name_filter(name: str):
    # if ( ) remove it
    if '(' in name:
        name = name[:name.index('(')]
    return name


def board_page():
    db = BUS_TIMELOG()
    
    st.info("시범적으로 과거의 운행 정보를 제공합니다. 이를 통해 버스의 도착 시간을 예측할 수 있습니다.")
    
    targetdate = st.date_input("날짜를 선택하세요", 
                      datetime.date.today() - datetime.timedelta(days=1),
                      format="YYYY.MM.DD")
    # targetdate to datetime
    day_of_week = get_weekday(targetdate)

    route_ids = list(ROUTEID.keys())
    
    targetroute = st.selectbox("노선을 선택하세요",
                               route_ids,
                               format_func=lambda x: f"{ROUTEID[x][0]}번 {ROUTEID[x][1]}행")
    #targetroute = "195000222"
    
    stops = ROUTEID[targetroute][3]
    stop_nms = [stop_name_filter(STOP_IDS[stop]) for stop in stops]
    
    timetable = get_timetable(ROUTEID[targetroute][0], day_of_week, ROUTEID[targetroute][1])
    timetable = [parse_timetable(time) for time in timetable]
    
    logs = db.get_log_by_route_id(targetroute, targetdate.strftime("%Y%m%d"))
    logs = [(parse_timelog(log[0]), *log[1:]) for log in logs]

    runnings = parse_runs(logs, targetroute, start_stop=stops[1])
    runnings.sort(key=lambda x: x[0][0])

    table = {k: [] for k in stops}

    if len(runnings) == 0:
        st.error("검색된 버스가 없습니다.")
        return
    
    for run in runnings:
        pass_stops = list(set([log[1] for log in run]))
            
        for log in run:
            table[log[1]].append(log[0].strftime("%H:%M"))
        
        # check if stops[0] in runnings
        flag = any(log[1] == stops[0] for log in run)
        if not flag:
            first_stop = stops[0]
            # find nearest time in timetable
            first_time = run[0][0]
            first_time = first_time.time() # datetime.time
            departure_time = None
            for time in timetable:
                if time >= first_time:
                    break
                departure_time = time
            if departure_time is not None:
                table[first_stop].append(departure_time.strftime("%H:%M"))
            else:
                table[first_stop].append("미")
            
        for s in stops[1:]:
            if s not in pass_stops:
                table[s].append("レ")


    try:
        df = pd.DataFrame(table)
        df.columns = stop_nms
        # transpose
        df = df.T
        st.write(df)
    except Exception as e:
        print("Error", len(runnings))
        for k, v in table.items():
            print(len(v), k, v)
        st.error(e)


def parse_timelog(timelog: str):
    """
    Parse timelog string to datetime
    
    Input:
    - timelog: str (e.g. 20210819_12:00:00 or 2021-08-19_12:00:00)
    Output:
    - datetime.datetime
    """
    date, time = timelog.split("_")
    
    if '-' in date:
        date = date.replace("-", "")
    year = int(date[:4])
    month = int(date[4:6])
    day = int(date[6:])
    hour = int(time[:2])
    minute = int(time[3:5])
    second = int(time[6:])
    
    # return time type
    return datetime.datetime(year, month, day, hour, minute, second)


def parse_timetable(time: str):
    hour, minute = time.split(":")
    hour = int(hour)
    minute = int(minute)
    return datetime.time(hour, minute)


def parse_runs(logs: list,
               route_id: str,
               start_stop: str=None,
               verbose: bool=False):
    runs = []
    vehicle_numbers = list(set([log[4] for log in logs]))
    
    for vehicle_number in vehicle_numbers:
        vehicle_log = [log for log in logs if log[4] == vehicle_number]
        vehicle_log.sort(key=lambda x: x[0])
        
        vehicle_log = parse_each_vehicle(vehicle_log, route_id)
        runs.extend(vehicle_log)
                
    return runs


def parse_each_vehicle(logs: list,
                       route_id: str):
    """
    Parse each vehicle log
    
    Input:
    - log: list of log
    Output:
    - list of (datetime, stop_id, route_id, vehicle_number)
    """
    rets = []
    stop_ids = ROUTEID[route_id][3]

    route = []
    prev_stop = -1

    for log in logs:
        try:
            timestamp, stop_id, route_id, vehicle_number = log
        except:
            timestamp, stop_id, route_id, _, vehicle_number, _ = log
        # find index of stop_id in stop_ids
        try:
            stop_idx = stop_ids.index(stop_id)
        except:
            continue

        if prev_stop < stop_idx:
            route.append((timestamp, stop_id, route_id, vehicle_number))
            prev_stop = stop_idx
        else:
            prev_stop = -1
            rets.append(route.copy())
            route.clear()

    return rets


if __name__ == '__page__':
    board_page()