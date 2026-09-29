import streamlit as st
import pandas as pd

from src.constants import WEEKDAY_STR
from src.tools import (
    get_timetable, get_time, 
    get_busroute_info
)


def page():
    weekday, hr, minute = get_time()
    busnos, departure_dict = get_busroute_info()
    
    st.write(f"Current time is {WEEKDAY_STR[weekday]} {hr:02d}:{minute:02d}")
 
    busno = st.segmented_control("Select bus number", busnos, default=busnos[0])
    
    if busno is not None:
        options = ["Weekday", "Saturday", "Sunday/Holiday"]
        weekday = st.segmented_control("Select weekday", options, default=options[weekday])

        if weekday is None:
            st.warning("Please select a day of the week.")
            return
        weekday = options.index(weekday)
        
        terminals = departure_dict[busno]
        departure = st.selectbox("Select departure of bus: 출발지 선택", terminals)
    
        if departure is None:
            st.warning("Please select a departure.")
            return

        time_list = get_timetable(int(busno), weekday, departure)
    
        st.write("Timetable")
    
        # row: hour, column: minute
        timetable = {}
        for time in time_list:
            hr, min = time.split(':')
            if hr not in timetable.keys():
                timetable[hr] = [min]
            else:
                timetable[hr].append(min)
        
        time_dict = {"Hour": [], "Minute": []}
        for hr in sorted(timetable.keys()):
            time_dict["Hour"].append(hr)
            time_dict["Minute"].append(", ".join(timetable[hr]))

        df = pd.DataFrame(time_dict)
        df.set_index("Hour", inplace=True)
        config = {
            "_index": st.column_config.NumberColumn("Hour"),
            "Minute": st.column_config.Column("Minute"),
        }

        st.dataframe(df, column_config=config, width=300)


if __name__ == "__page__":
    page()
    