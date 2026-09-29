import streamlit as st


def info_page():
    st.title("Bus HeXA Information")
    
    st.write("""
             울산시 버스 노선정보가 24년 12월 21자로 개편되었습니다.
             이를 반영한 버스 시간표에 관한 정보를 제공하는 임시 페이지입니다.
             버스 출도착에 관한 정보를 추후에 제공할 계획이 있습니다.
             """)
    
    # show the information of the bus
    st.write("# Bus Route Map")
    st.image("media/graphisnotmap.png", caption="Graph route", use_container_width=True)
    
    st.write("## For Destination")
    
    # write a table of destination and bus number
    st.write("""
             | Destination | Bus Number |
             | ----------- | ---------- |
             | 울산역 (KTX Ulsan station) | 513 |
             | 구영리 (Guyoung-ri) | 513, 713, 753, 1115 |
             | 천상 (Chunsang) | 713, 743, 1115 |
             | 삼산 (Samsan, city) | 713, 743, 753, 1115 |
             | 신복교차로 (Sinbok) | 743, 753 |
             | 울산대학 (Ulsan university) | 743, 753 |
             | 성남동 (Sungnam-dong) | 713 |
             | 법원 (Ulsan court) | 743 |
             | 산단캠 | 753 |
             | 명촌 (Myungchon) | 713, 743, 753 |
             | 덕하 (Dukha) | 513 |
             | 시청 (City hall) | 513, 1115 |
             | 태화강역 (Taewhagang station) | 713, 743, 753, 1115 |
             | 현대중공업 (Hyundai Heavy Industries) | 1115 |
             """)
    
    st.write("## For Bus Number")
    
    st.warning("""713번, 1115번 노선은 천상을 경유하여 구영리를 지나갑니다. 
               Bus number 713 goes  Guyoung-ri **via Chunsang**.
               """)
    
    # write a table of bus number and destination
    st.write("""
             | Bus Number | Destination |
             | ---------- | ----------- |
             | 513 | 삼남 - 울산역(KTX) - **UNIST** - 구영리 - 굴화주공 - 시청 - 덕하 |
             | 713 | **UNIST** - 천상 - 구영리 - 굴화주공 - 태화루(국가정원) - 성남동 - 삼산 - 태화강역 - 명촌 |
             | 743 | **UNIST** - 천상 - 굴화주공 - 신복교차로 - 울산대학교 - 법원 - 공업탑 - 삼산 - 태화강역 - 명촌|
             | 753 | **UNIST** - 구영리 - 굴화주공 - 신복교차로 - 울산대학교 - 산학융합지구캠퍼스 - 공업탑 - 삼산 - 태화강역 - 명촌 |
             | 1115 | **UNIST** - 천상 - 구영리 - 굴화주공 - 태화루(국가정원) - 시청 - 삼산 - 태화강역 - 염포동 - 남목 - 현대중공업, 울산대학병원 - 일산해수욕장 - 꽃바위 |
             """)
    
    st.write("# Tips")
    
    st.error("513번은 방향을 반드시 확인하십시오. 앞쪽이 울산(시내)방향, 뒤쪽이 삼남(언양, 울산역) 방향입니다")
    
    st.markdown("""
                - 울산역에서 출발하는 경우 513번 버스를 이용하며 되나, 불가피한 경우 진목회관을 경유해 주세요 (경유노선: 318, 413, 523, 543, 5001).
                - 이전에 133을 타고 동구 방향으로 가시는 경우에는 태화강역에서 동구 방향 버스로 환승하시거나, 우미린2차에서 5002번으로 환승해주세요.
                - 부산 (노포) 방향으로 가시는 경우 743, 753번 버스를 타고 좋은삼정병원에서 **1224**번 (이전 1147번) 으로 환승해주세요.
                - 해운대 방향으로 가시는 경우 태화강역 가는 버스를 타고, 동해선으로 환승해주세요.
                - 시외-고속버스 이용시 신복교차로를 경유하면 편리합니다.
            """)
    
    st.markdown("""
                # Update
                -  2024-12-21: 울산시 버스 노선정보가 개편되었습니다. 임시 페이지가 개설되었습니다.
                -  2024-12-30: 베타버전으로 정류소 별 버스 도착정보를 제공합니다.
                -  2025-01-10: 베타버전으로 UNIST에서 출발하는 버스의 도착정보를 순서대로 제공합니다.
                -  2025-02-28: 버스 713, 743 시간표 업데이트
                -  2025-08-11: 버스 1115 시간표 업데이트
                """)
    
        # Query param-based hidden unlock with click counter
    try:
        params = st.query_params
        hexa_flag = params.get("hexa")
        if isinstance(hexa_flag, list):
            hexa_flag = hexa_flag[0]
    except Exception:
        # Fallback for older Streamlit versions
        try:
            hexa_flag = st.experimental_get_query_params().get("hexa", [None])[0]
        except Exception:
            hexa_flag = None

    try:
        hexa_count = int(hexa_flag) if hexa_flag is not None else 0
    except Exception:
        hexa_count = 0

    # Activate manager after 5 clicks (hexa>=5)
    if hexa_count == 6:
        try:
            from infopages.manager import manager_page
            manager_page()
        except Exception as e:
            st.error("Failed to load Manager page")
    
    
if __name__ == "__page__":
    info_page()