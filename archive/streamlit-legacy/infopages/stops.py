import streamlit as st

from src.constants import ROUTEID, STOP_IDS, SERACH_STOPS
from src.crawl import crawl_busstop
from src.tools import pageblock_busstop, get_timestr

UPDATE_THRESHOLD = 10
WARNING_THRESHOLD = 30

def busstop_page():
    stop_id = st.selectbox("정류소를 선택해주세요 (Select bus stop)",
                         SERACH_STOPS,
                         format_func=lambda x: STOP_IDS[x])
    
    if stop_id is not None:
        
        if 'arrival' not in st.session_state:
            st.session_state['arrival'] = crawl_busstop(str(stop_id))
            st.session_state['timestamp'] = get_timestr() # HHMMSS
            st.session_state['stop_id'] = stop_id
        else:
            now_time = get_timestr()
            # update if 10 seconds passed
            if int(now_time) - int(st.session_state['timestamp']) > UPDATE_THRESHOLD:
                st.session_state['arrival'] = crawl_busstop(str(stop_id))
                st.session_state['timestamp'] = now_time
            if stop_id != st.session_state['stop_id']:
                st.session_state['arrival'] = crawl_busstop(str(stop_id))
                st.session_state['timestamp'] = now_time
                st.session_state['stop_id'] = stop_id
        bus_list = st.session_state['arrival']
        
        # target only in ROUTEID
        target_bus_list = [bus for bus in bus_list if bus['route_id'] in ROUTEID.keys()]
        pageblock_busstop(target_bus_list, ROUTEID, verbose=True)
        
        if len(target_bus_list) == 0:
            st.error("운행 중인 버스가 없습니다. No running bus.")
        
        # warning if first and second bus is over WARNING_THRESHOLD
        if len(target_bus_list) > 2:
            first_bus = target_bus_list[0]
            second_bus = target_bus_list[1]
            
            first_time = int(first_bus['arrival_time'])
            second_time = int(second_bus['arrival_time'])
            
            if second_time - first_time > WARNING_THRESHOLD*60:
                st.warning("첫 번째 버스와 두 번째 버스의 차이가 30분 이상입니다. 버스 시간을 확인해주세요. The difference between the first and second buses is over 30 minutes. Please check the bus time.")


if __name__ == "__page__":
    busstop_page()