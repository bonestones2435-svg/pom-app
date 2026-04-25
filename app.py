import streamlit as st
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import folium
from folium.plugins import HeatMap
from streamlit.components.v1 import html

st.set_page_config(page_title="POM Heatmap Tool")

st.title("POM Heatmap Generator")

########################################
# FILE UPLOAD
########################################
gps_file = st.file_uploader("Upload GPS KML", type=["kml"])
data_file = st.file_uploader("Upload Data File", type=["csv","txt"])

########################################
# DATA INTEGRITY FUNCTION
########################################
def data_integrity_score(df):
    numeric_cols = [
        "Log Number","Ozone","Cell Temp","Cell Pressure",
        "PDV","BattV","Latitude","Longitude","Altitude","GPSquality"
    ]

    total = 0
    errors = 0

    for col in numeric_cols:
        if col in df.columns:
            total += len(df[col])
            converted = pd.to_numeric(df[col], errors='coerce')
            errors += ((converted.isnull()) & (df[col].notnull())).sum()

    if total == 0:
        return 0

    return round(100 * (1 - errors / total), 2)

########################################
# KML PARSER
########################################
def parse_kml(file):
    tree = ET.parse(file)
    root = tree.getroot()

    lat, lon = [], []

    for elem in root.iter():
        if "coord" in elem.tag.lower() or "coordinates" in elem.tag.lower():
            if elem.text:
                lines = elem.text.strip().split()
                for line in lines:
                    parts = line.split(",")
                    if len(parts) >= 2:
                        lon.append(float(parts[0]))
                        lat.append(float(parts[1]))

    return pd.DataFrame({"lat": lat, "lon": lon})

########################################
# RUN PROCESS
########################################
if st.button("Generate"):

    if gps_file is None or data_file is None:
        st.error("Upload both files first")
    else:

        ########################################
        # LOAD DATA
        ########################################
        if data_file.name.endswith(".csv"):
            df = pd.read_csv(data_file, skiprows=5, header=None)
        else:
            df = pd.read_csv(data_file, header=None)

        df = df.iloc[:, :12]

        df.columns = [
            "Log Number","Ozone","Cell Temp","Cell Pressure",
            "PDV","BattV","Latitude","Longitude","Altitude",
            "GPSquality","Date","Time"
        ]

        ########################################
        # DATA INTEGRITY
        ########################################
        score = data_integrity_score(df)

        st.subheader(f"Data Integrity: {score}%")

        st.progress(score / 100)

        ########################################
        # POM DATA
        ########################################
        df["Time"] = pd.to_datetime(df["Time"], format="%H:%M:%S", errors="coerce")
        df["Ozone"] = pd.to_numeric(df["Ozone"], errors="coerce")

        df = df.dropna(subset=["Time", "Ozone"])

        pom = df[["Time", "Ozone"]].set_index("Time")

        ########################################
        # GPS DATA
        ########################################
        gps = parse_kml(gps_file)

        if gps.empty:
            st.error("No GPS data found in KML")
            st.stop()

        gps["Time"] = pd.date_range(
            start=pom.index.min(),
            end=pom.index.max(),
            periods=len(gps)
        )
        gps = gps.set_index("Time")

        ########################################
        # ALIGN
        ########################################
        pom_resampled = pom.resample("1S").mean().interpolate()
        gps_resampled = gps.resample("1S").mean().interpolate()

        data = pd.concat([pom_resampled, gps_resampled], axis=1).dropna()

        ########################################
        # MAP
        ########################################
        m = folium.Map(
            location=[data["lat"].mean(), data["lon"].mean()],
            zoom_start=14,
            tiles="CartoDB positron"
        )

        heat_data = [[r["lat"], r["lon"], r["Ozone"]] for _, r in data.iterrows()]
        HeatMap(heat_data, radius=3).add_to(m)

        html_map = m._repr_html_()
        html(html_map, height=500)