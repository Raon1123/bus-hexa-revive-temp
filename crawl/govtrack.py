from time import sleep


from src.constants import ROUTEID, STOP_IDS
from src.crawl import crawl_loc, parse_busloc
from src.tools import get_now
from crawl.db import BUS_TIMELOG

"""
{'response': {'header': {'resultCode': '00', 'resultMsg': 'NORMAL SERVICE.'}, 'body': {'items': {'item': [{'nodeid': 'USB196040221', 'nodenm': '굴화마을', 'nodeord': 29, 'routenm': 713, 'routetp': '일반버스', 'vehicleno': '울산71자3238'}, {'nodeid': 'USB193040419', 'nodenm': '시외고속버스터미널', 'nodeord': 43, 'routenm': 713, 'routetp': '일반버스', 'vehicleno': '울산71자3229'}, {'nodeid': 'USB999000148', 'nodenm': '명촌차고지(종점)', 'nodeord': 48, 'routenm': 713, 'routetp': '일반버스', 'vehicleno': '울산71자3213'}]}, 'numOfRows': 70, 'pageNo': 1, 'totalCount': 3}}}
"""

def busloc_status(db: BUS_TIMELOG,
                  route_id: str,
                  bus_timeline: dict):
    """
    get bus location status
    """
    try:
        response_json = crawl_loc(route_id)
    except Exception as e:
        print(f"Error: while crawling location for route {route_id}: {e}")
        # retry 5 times with sleep 1 second
        for i in range(5):
            sleep(1)
            try:
                response_json = crawl_loc(route_id)
                break
            except Exception as e:
                print(f"Retry {i+1} failed: {e}")
        else:
            print(f"All retries failed for route {route_id}")
            return

    if response_json is None:
        return
    
    timestamp = get_now()
    timestamp = timestamp.strftime("%Y%m%d_%H:%M:%S")

    try:
        busloc_list = parse_busloc(response_json)
    except Exception as e:
        print(f"Error: {e}")
        print(f"response as follows: {response_json}")
        # save error log
        log_file = f"/app/logs/error_{route_id}_{timestamp}.json"
        with open(log_file, 'w') as f:
            f.write(str(response_json))
        return

    stop_ids = ROUTEID[route_id][3]

    for busloc in busloc_list:
        nodeid, nodenm, vehicle_no = busloc

        if vehicle_no not in bus_timeline.keys():
            bus_timeline[vehicle_no] = ''

        if nodeid != bus_timeline[vehicle_no]:
            if nodeid in stop_ids:
                print_str = f"{timestamp}\t{nodeid}\t{route_id}\t{vehicle_no}\t{STOP_IDS[nodeid]}\n"
                with open(logging_file, 'a') as f:
                    f.write(print_str)
                insert_query(db, timestamp, nodeid, route_id, vehicle_no)
            bus_timeline[vehicle_no] = nodeid


def insert_query(db: BUS_TIMELOG,
                 timestamp: str,
                 stop_id: str,
                 route_id: str,
                 vehicle_number: str,):
    db.insert_log((timestamp, stop_id, route_id, vehicle_number))   


if __name__ == "__main__":
    bus_timeline = {}

    db = BUS_TIMELOG()

    logging_file = "/app/logs/logs.tsv"
    first_row = "time\tstop_id\troute_id\tvehicle_number\tstop_name\n"
    with open(logging_file, 'w') as f:
        f.write(first_row)

    while True:
        timestamp = get_now()

        if timestamp.hour >= 1 and timestamp.hour < 5:
            sleep(600)
            continue

        timestamp = timestamp.strftime("%Y%m%d_%H:%M:%S")
        print(f"timestamp: {timestamp}", flush=True)
        
        for route_id in ROUTEID.keys():
            if not route_id in bus_timeline.keys():
                bus_timeline[route_id] = {}
            route_timeline = bus_timeline[route_id]

            busloc_status(db, route_id, route_timeline)

        sleep(20)

