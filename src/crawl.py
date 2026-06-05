# defines crawling from data.go.kr
import json
import os
import requests
from time import sleep

from bs4 import BeautifulSoup as bs

from src.constants import (
    ULSAN_CITYCODE, ULSAN_PREFIX,
    ROUTEID
)

#import streamlit as st

KEYPATH = 'secret/key.txt'

def get_apikey(path: str):
    with open(path, "r") as f:
        return f.read().strip()


def crawl_route(route_id: str):
    """
    crawl route from 국토교통부
    """
    KEY = get_apikey(KEYPATH)
    PG_NO = 1
    NUM_OF_ROWS = 70
    TYPE = "json"
    usb_route_id = ULSAN_PREFIX + route_id

    ""
    BASE_URL = "http://apis.data.go.kr/1613000/BusRouteInfoInqireService/getRouteAcctoThrghSttnList"
    url_arguments = '?'
    url_arguments += f'&serviceKey={KEY}'
    url_arguments += f'&pageNo={PG_NO}'
    url_arguments += f'&numOfRows={NUM_OF_ROWS}'
    url_arguments += f'&_type={TYPE}'
    url_arguments += f'&cityCode={ULSAN_CITYCODE}'
    url_arguments += f'&routeId={usb_route_id}'

    response = requests.get(BASE_URL + url_arguments)

    resultcode = response.json()["response"]["header"]["resultCode"]
    assert resultcode == "00", f"resultcode is not 00: {resultcode}"

    return response.json()


def parse_route_json(json_data):
    """
    parse route json
    """
    return_list = []

    total_cnt = json_data["response"]["body"]["totalCount"]
    body_data = json_data["response"]["body"]["items"]["item"]

    print(f"total count: {total_cnt}, items count: {len(body_data)}")
    for item in body_data:
        nodeid = item["nodeid"]
        nodenm = item["nodenm"]
        nodeord = item["nodeord"]
        routeid = item["routeid"]
        node_tuple = (nodeord, nodeid, nodenm, routeid)
        return_list.append(node_tuple)

    return return_list


def crawl_holiday(year, month):
    KEY = get_apikey(KEYPATH)

    holiday_query = [
        "?serviceKey=" + KEY,
        f"solYear={year}",
        f"solMonth={month:02d}"
    ]
    holiday_query = '&'.join(holiday_query)

    holiday_url = [
        "http://apis.data.go.kr",
        "B090041",
        "openapi",
        "service",
        "SpcdeInfoService",
        "getRestDeInfo" + holiday_query,
    ]
    holiday_url = '/'.join(holiday_url)

    print("Crawling holiday from", holiday_url)

    response = requests.get(holiday_url)

    soup = bs(response.text, "html.parser")

    holidays = soup.find_all("locdate")
    holiday_list = [holiday.text for holiday in holidays]

    return holiday_list


def is_holiday(year, month, day, force=False):
    # check the holiday crawling file
    file_path = f'secret/holiday_{year}.json'

    if not os.path.exists(file_path) or force:
        holiday_list = []
        for month in range(1, 13):
            month_holiday = crawl_holiday(year, month)
            holiday_list.extend(month_holiday)
        with open(file_path, "w") as f:
            json.dump(holiday_list, f)
    else:
        with open(file_path, "r") as f:
            holiday_list = json.load(f)

    if f"{year}{month:02d}{day:02d}" in holiday_list:
        return True
    else:
        return False


def crawl_busstop(stopid: str):
    """
    Get the bus stop information from Ulsan city api
    """
    KEY = get_apikey(KEYPATH)
    PG_NO = 1
    NUM_OF_ROWS = 50

    BASE_URL = "http://openapi.its.ulsan.kr/UlsanAPI/getBusArrivalInfo.xo"
    url_arguments = [
        '?',
        f'serviceKey={KEY}',
        f'pageNo={PG_NO}',
        f'numOfRows={NUM_OF_ROWS}',
        f'stopid={stopid}'
    ]
    url_arguments = '&'.join(url_arguments)

    try:
        response = requests.get(BASE_URL + url_arguments)
    except requests.exceptions.RequestException as e:
        print("Error while fetching bus stop information:", stopid)
        return []
    soup = bs(response.text, "html.parser")
    bus_list = soup.find_all("row")

    ret_list = []
    for bus in bus_list:
        try:
            route_id = bus.find("routeid").text
            present = bus.find("presentstopnm").text
            vehicle_number = bus.find("vehicleno").text
            arrival_time = bus.find("arrivaltime").text
        except:
            route_id = None

        if route_id is None:
            continue

        ret_item = {
            "route_id": route_id,
            "present": present,
            "vehicle_no": vehicle_number,
            "arrival_time": arrival_time
        }
        ret_list.append(ret_item)

    return ret_list


def crawl_loc(route_id: str):
    """
    crawl location from 국토교통부
    """
    KEY = get_apikey("secret/key.txt")
    PG_NO = 1
    NUM_OF_ROWS = 70
    TYPE = "json"
    usb_route_id = ULSAN_PREFIX + route_id

    BASE_URL = "http://apis.data.go.kr/1613000/BusLcInfoInqireService/getRouteAcctoBusLcList"
    url_arguments = '?'
    url_arguments += f'&serviceKey={KEY}'
    url_arguments += f'&pageNo={PG_NO}'
    url_arguments += f'&numOfRows={NUM_OF_ROWS}'
    url_arguments += f'&_type={TYPE}'
    url_arguments += f'&cityCode={ULSAN_CITYCODE}'
    url_arguments += f'&routeId={usb_route_id}'

    # retry until success
    for _ in range(5):
        try:
            response = requests.get(BASE_URL + url_arguments)
            break
        except:
            sleep(5)

    try:
        resultcode = response.json()["response"]["header"]["resultCode"]
    except:
        print(response.text, flush=True)
        return None

    if resultcode != "00":
        print(f"resultcode is not 00: {resultcode}")
        return None

    return response.json()


def parse_busloc(json_data):
    """
    parse bus location json

    Input
    - json_data: json data from crawl_loc
    Output
    - return_list: list of bus location (nodeid, nodenm, vehicle_no)
    """
    return_list = []

    total_cnt = json_data["response"]["body"]["totalCount"]
    if total_cnt == 0:
        return return_list
    elif total_cnt == 1:
        body_data = [json_data["response"]["body"]["items"]["item"]]
    else:
        body_data = json_data["response"]["body"]["items"]["item"]

    for item in body_data:
        nodeid = item["nodeid"]
        nodeid = nodeid[len(ULSAN_PREFIX):]
        nodenm = item["nodenm"]
        vehicle_no = item["vehicleno"]
        node_tuple = (nodeid, nodenm, vehicle_no)
        return_list.append(node_tuple)

    return return_list


def request_timetable(page_no: int,
                      num_of_rows: int,
                      routeno: int,
                      day_of_week: int):
    """
    Get the bus stop information from Ulsan city api
    """
    KEY = get_apikey(KEYPATH)

    assert day_of_week in [0, 1, 2, 3, 4, 5, 6], "day_of_week must be in [0, 1, 2, 3, 4, 5, 6]"

    BASE_URL = "http://openapi.its.ulsan.kr/UlsanAPI/BusTimetable.xo"
    url_arguments = [
        '?',
        f'serviceKey={KEY}',
        f'pageNo={page_no}',
        f'numOfRows={num_of_rows}',
        f'routeNo={routeno}',
        f'dayOfWeek={day_of_week}'
    ]
    url_arguments = '&'.join(url_arguments)

    try:
        response = requests.get(BASE_URL + url_arguments)
    except requests.exceptions.RequestException as e:
        print("Error while fetching bus stop information:", routeno, day_of_week)
        print(e)
        # change to normal (if dayofweek is larger than 3 minus 3)
        if day_of_week > 3:
            day_of_week -= 3
            url_arguments = [
                '?',
                f'serviceKey={KEY}',
                f'pageNo={page_no}',
                f'numOfRows={num_of_rows}',
                f'routeNo={routeno}',
                f'dayOfWeek={day_of_week}'
            ]
            url_arguments = '&'.join(url_arguments)
        # retry
        for _ in range(5):
            try:
                response = requests.get(BASE_URL + url_arguments)
                break
            except requests.exceptions.RequestException as e:
                print("Error while fetching bus stop information:", routeno, day_of_week)
                print(e)
                sleep(5)
        
        print("Retry success")
        return None

    return response


def crawl_timetable(routeno: int,
                    day_of_week: int):
    MAX_RETRY = 5
    request_row = 50

    # first find total_cnt from response
    
    for retry in range(MAX_RETRY):
        response = request_timetable(1, request_row, routeno, day_of_week)
        if response is None or response.status_code != 200:
            print("Error on response", routeno, day_of_week, "retrying", retry)
            sleep(5)
            continue
        break
    else:
        print("Failed to get response after retries", routeno, day_of_week)
        return None

    soup = bs(response.text, "html.parser")
    total_cnt = soup.tableinfo.totalcnt.text
    total_cnt = int(total_cnt)

    if total_cnt == 0:
        return []

    # find bus timetable information
    import streamlit as st
    
    bus_timetable = []
    for page in range(1, (total_cnt // request_row) + 2):
        sleep(1)
        for retry in range(MAX_RETRY):
            response = request_timetable(page, request_row, routeno, day_of_week)
            print("request", page)
            if response is None or response.status_code != 200:
                print("Error on response", routeno, day_of_week, page, "retrying", retry)
                sleep(5)
                continue
            break
        else:
            print("Failed to get response after retries", routeno, day_of_week, page)
            continue
        st.text(f"Requesting page {page} for route {routeno}, day {day_of_week}")
        ## if response is list...
        if isinstance(response, list):
            print("response is list")
            print(response)
            continue
        if response is None or response.status_code != 200:
            print("Error on response", routeno, day_of_week, page)
            st.error(f"Error on response for route {routeno}, day {day_of_week}, page {page}")
            # retry after sleep
            sleep(5)
            response = request_timetable(page, request_row, routeno, day_of_week)
            if response is None or response.status_code != 200:
                print("Retry failed on response", routeno, day_of_week, page)
                st.error(f"Retry failed on response for route {routeno}, day {day_of_week}, page {page}")
                continue
            st.success(f"Retry success for route {routeno}, day {day_of_week}, page {page}")

        soup = bs(response.text, "html.parser")
        items = soup.find_all("row")
        for item in items:
            item_time = item.time.text
            item_time = item_time[:2] + ':' + item_time[2:4]

            item_direction = item.direction.text
            item_direction = int(item_direction)

            bus_timetable.append((item_time, item_direction))

    return bus_timetable


def crawl_target_timetable(is_vacation: bool=False):
    day_of_week = [0, 1, 2]
    week_offset = 0 if not is_vacation else 3

    # from ROUTEID make a pair of busno and routeid
    bus_no_to_route_id = {}
    for key, value in ROUTEID.items():
        route_id = key
        busno = value[0]
        departure = value[2]
        if busno not in bus_no_to_route_id:
            bus_no_to_route_id[busno] = [(route_id, departure)]
        else:
            bus_no_to_route_id[busno].append((route_id, departure))

    bus_no_to_direction = {}
    for busno, route_info in bus_no_to_route_id.items():
        # sort route_info as route_id
        route_info.sort(key=lambda x: x[0])  # Sort by route_id
        # route_id to direction, less route_id has 1
        for i, (route_id, departure) in enumerate(route_info):
            direction = 1 if i == 0 else 2
            if busno not in bus_no_to_direction:
                bus_no_to_direction[busno] = [(route_id, departure, direction)]
            else:
                bus_no_to_direction[busno].append((route_id, departure, direction))

    import streamlit as st
    timetable_dict = {}
    for busno in bus_no_to_direction.keys():
        timetable_dict[busno] = {}
        for week in day_of_week:
            _week = week + week_offset
            timetable_dict[busno][week] = {}
            
            st.text(f"Requesting for route {busno}, day {week}")

            timetable = crawl_timetable(busno, _week)
            if timetable is None or len(timetable) == 0:
                print("Error on crawl_timetable", busno, _week)
                continue

            route_info = bus_no_to_direction[busno]

            for (time, direction) in timetable:
                for (route_id, departure, route_direction) in route_info:
                    if direction == route_direction:
                        if departure not in timetable_dict[busno][week]:
                            timetable_dict[busno][week][departure] = [time]
                        else:
                            timetable_dict[busno][week][departure].append(time)
        sleep(10)

    # write to json under timetable
    for busno, timetable in timetable_dict.items():
        busno = str(busno)
        if not os.path.exists('timetable'):
            os.makedirs('timetable')
        with open(f'timetable/{busno}.json', 'w') as f:
            json.dump(timetable, f, ensure_ascii=False, indent=4)

if __name__ == '__main__':
    #is_holiday(2026, 1, 1)
    crawl_target_timetable(is_vacation=True)

