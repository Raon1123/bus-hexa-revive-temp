"""
Temporal page of bushexa application

Only show timetable of the bus
"""
import streamlit as st

from src.scripts import notify_beta

def main():
    # page title
    logo = "media/hexaLogo.ico"
    
    st.set_page_config(page_title="Bus HeXA - UNIST 버스정보 사이트",
                       page_icon=logo,
                       layout="wide",
                       menu_items={
                            "About": "UNIST 버스정보 사이트입니다. 버스번호별, 버스정보, UNIST에서 출발하는 버스, UNIST로 가는 버스, 버스 시간표, 버스 운행 로그를 확인할 수 있습니다."
                       })

    #st.info(notify_beta)
    #st.info(" 8월 16일부터 1115번 버스가 유니스트를 종점으로 운행합니다. 1115번 버스는 천상, 구영리, 굴화, 태화루, 시청, 삼산동, 태화강역, 염포동, 남목, 현대중공업, 울산대학병원 , 일산해수욕장, 꽃바위로 가는 버스입니다. 급행노선으로써, **카드 2300원**의 요금이 부과됩니다. (현금 2,500원) Starting August 16, Bus No. 1115 will extend its route to UNIST as the final stop. Bus No. 1115 travels through Cheonsang, Guyeong-ri, Gulhwa, Taehwa Pavilion, City Hall, Samsan-dong, Taehwagang Station, Yeompodong, Nammok, Hyundai Heavy Industries, Ulsan University Hospital, and Ilsan Beach before heading to Kkotbawi terminal. As this is an express service, the fare is 2,300 KRW in card. (2,500 KRW in cash)")
    
    busno_page = st.Page("infopages/busno.py", title="버스번호별", icon="🚌")
    info_page = st.Page("infopages/info.py", title="버스정보", icon="ℹ️")
    unist_board_page = st.Page("infopages/unist_board.py", title="From UNIST", icon="➡️")
    stops_page = st.Page("infopages/stops.py", title="To UNIST", icon="⬅️")
    board_page = st.Page("infopages/departure_board.py", title="Departure Board", icon="🕒", default=True)
    running_table_page = st.Page("infopages/running_table.py", title="Running Log", icon="🚏")
    unist_timetable_page = st.Page("infopages/unist_timetable.py", title="UNIST Timetable", icon="🕒")

    pg = st.navigation({
        "Information": [info_page],
        "Timetable": [busno_page, running_table_page, unist_timetable_page],
        "Tracking": [unist_board_page, stops_page, board_page]})
    pg.run()
    
    st.write("Made by [HeXA](https://hexa.pro)")
    

if __name__ == "__main__":
    # read xlsx to json
    main()
    
