import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import folium
from folium.plugins import HeatMap
import branca.colormap as cm
import streamlit as st
import base64
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io

############################
# PAGE CONFIG + CUSTOM CSS
############################

st.set_page_config(page_title="AQTrack", layout="wide", page_icon="🌬️")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.stApp { background-color: #0d1117; color: #e6edf3; }

.aq-header {
    background: linear-gradient(135deg, #161b22 0%, #0d1117 60%, #1a2332 100%);
    border: 1px solid #21262d; border-radius: 12px;
    padding: 32px 40px; margin-bottom: 28px;
    position: relative; overflow: hidden;
}
.aq-header::before {
    content: ''; position: absolute; top: -40px; right: -40px;
    width: 180px; height: 180px;
    background: radial-gradient(circle, rgba(56,189,248,0.12) 0%, transparent 70%);
    border-radius: 50%;
}
.aq-title {
    font-family: 'Space Mono', monospace; font-size: 2.4rem;
    font-weight: 700; color: #f0f6fc; margin: 0 0 6px 0; letter-spacing: -1px;
}
.aq-subtitle { font-size: 0.95rem; color: #8b949e; margin: 0; font-weight: 300; }
.aq-badge {
    display: inline-block; background: rgba(56,189,248,0.12); color: #38bdf8;
    border: 1px solid rgba(56,189,248,0.25); border-radius: 20px;
    padding: 3px 12px; font-size: 0.75rem; font-family: 'Space Mono', monospace;
    margin-top: 12px; letter-spacing: 0.5px;
}
.section-label {
    font-family: 'Space Mono', monospace; font-size: 0.7rem; color: #38bdf8;
    letter-spacing: 2px; text-transform: uppercase; margin-bottom: 10px;
}
.metric-card {
    background: #161b22; border: 1px solid #21262d; border-radius: 10px;
    padding: 18px 20px; text-align: center; margin-bottom: 8px;
}
.metric-label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
.metric-value { font-family: 'Space Mono', monospace; font-size: 1.5rem; font-weight: 700; color: #f0f6fc; }
.metric-unit  { font-size: 0.7rem; color: #8b949e; margin-top: 2px; }
.integrity-good { color: #3fb950; }
.integrity-warn { color: #d29922; }
.integrity-bad  { color: #f85149; }
.overlap-ok   { border-left: 3px solid #3fb950; }
.overlap-fail { border-left: 3px solid #f85149; }
.outlier-chip {
    display: inline-block; background: rgba(248,81,73,0.12); color: #f85149;
    border: 1px solid rgba(248,81,73,0.3); border-radius: 6px;
    padding: 4px 10px; font-size: 0.8rem; font-family: 'Space Mono', monospace;
    margin: 4px 4px 4px 0;
}
div[data-testid="stSelectbox"] label,
div[data-testid="stFileUploader"] label,
div[data-testid="stDateInput"] label,
div[data-testid="stTimeInput"] label {
    color: #8b949e !important; font-size: 0.8rem !important;
    text-transform: uppercase; letter-spacing: 1px;
}
.stButton > button {
    background: #238636 !important; color: #ffffff !important;
    border: 1px solid #2ea043 !important; border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important; font-weight: 600 !important;
    padding: 10px 28px !important; font-size: 0.95rem !important;
}
.stButton > button:hover { background: #2ea043 !important; border-color: #3fb950 !important; }
div[data-testid="stSidebar"] { background-color: #161b22 !important; border-right: 1px solid #21262d; }
div[data-testid="stSidebar"] * { color: #e6edf3 !important; }
.stProgress > div > div { background: linear-gradient(90deg, #238636, #3fb950) !important; }
a { color: #38bdf8 !important; text-decoration: none; font-weight: 500; }
a:hover { text-decoration: underline; }
hr { border-color: #21262d !important; }
</style>
""", unsafe_allow_html=True)

############################
# HEADER
############################

st.markdown("""
<div class="aq-header">
    <div class="aq-title">🌬️ AQTrack</div>
    <div class="aq-subtitle">Air quality heatmap generator — POM &amp; POPS device support</div>
    <div class="aq-badge">v2.0 · NASA EnAACT</div>
</div>
""", unsafe_allow_html=True)

############################
# SIDEBAR
############################

with st.sidebar:
    st.markdown('<div class="section-label">Device</div>', unsafe_allow_html=True)
    device = st.selectbox("Device", ["POM", "POPS"], label_visibility="collapsed")

    st.markdown("---")
    st.markdown('<div class="section-label">Session Info</div>', unsafe_allow_html=True)
    time_of_day   = st.selectbox("Time of Day", ["Morning", "Midday", "Evening"])
    session_label = st.text_input("Session Label (optional)", placeholder="e.g. Harlem Walk 1")

    st.markdown("---")
    st.markdown('<div class="section-label">Map View</div>', unsafe_allow_html=True)
    map_mode = st.radio("Display Mode", ["Heatmap", "Scatter (colored dots)"], index=0)

    st.markdown("---")
    st.caption("Upload sensor CSV + GPS file to generate georeferenced air quality maps with statistics and time-series plots.")

############################
# HELPERS
############################

def get_download_link(file_path, label, filename):
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f'<a href="data:file/html;base64,{b64}" download="{filename}">{label}</a>'

def get_csv_download_link(df, label, filename):
    b64 = base64.b64encode(df.to_csv(index=False).encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}">{label}</a>'

def integrity_color(score):
    if score >= 95: return "integrity-good", "Excellent"
    if score >= 80: return "integrity-warn", "Acceptable"
    return "integrity-bad", "Poor"

def data_integrity(df, cols):
    errors, total = 0, 0
    for col in cols:
        if col in df.columns:
            total += len(df[col])
            converted = pd.to_numeric(df[col], errors="coerce")
            errors += ((converted.isnull()) & (df[col].notnull())).sum()
    return 0 if total == 0 else round(100 * (1 - errors / total), 2)

def show_integrity(score):
    cls, label = integrity_color(score)
    st.markdown(f"""<div class="metric-card">
        <div class="metric-label">Data Integrity</div>
        <div class="metric-value {cls}">{score}%</div>
        <div class="metric-unit">{label}</div>
    </div>""", unsafe_allow_html=True)
    st.progress(score / 100)

############################
# SUMMARY STATS + OUTLIERS
# raw_data = full unmerged sensor series (for accurate stats)
# map_data = GPS-aligned data (for outlier timestamp chips)
############################

def show_summary_stats(raw_data, map_data, value_col, unit):
    # Stats calculated from raw sensor data
    mean_v = raw_data[value_col].mean()
    max_v  = raw_data[value_col].max()
    min_v  = raw_data[value_col].min()
    std_v  = raw_data[value_col].std()
    threshold = mean_v + 2.5 * std_v

    # Outlier chips sourced from aligned map_data (has timestamps + coords)
    outliers = map_data[map_data[value_col] > threshold]

    st.markdown('<div class="section-label" style="margin-top:24px;">Walk Statistics</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    for col, lbl, val in [(c1,"Mean",mean_v),(c2,"Max",max_v),(c3,"Min",min_v),(c4,"Std Dev",std_v)]:
        col.markdown(f"""<div class="metric-card">
            <div class="metric-label">{lbl}</div>
            <div class="metric-value">{val:.1f}</div>
            <div class="metric-unit">{unit}</div>
        </div>""", unsafe_allow_html=True)

    if not outliers.empty:
        st.markdown('<div class="section-label" style="margin-top:20px;">Outlier Spikes</div>', unsafe_allow_html=True)
        time_col = "index" if "index" in outliers.columns else outliers.columns[0]
        chips = ""
        for _, row in outliers.head(10).iterrows():
            t = row[time_col].strftime("%H:%M:%S") if hasattr(row[time_col], "strftime") else str(row[time_col])
            chips += f'<span class="outlier-chip">{t} → {row[value_col]:.1f} {unit}</span>'
        st.markdown(chips, unsafe_allow_html=True)
        if len(outliers) > 10:
            st.caption(f"…and {len(outliers)-10} more above {threshold:.1f} {unit}")

    return outliers

############################
# TIME SERIES PLOT
############################

def show_timeseries(data, value_col, label, unit, color, outliers=None, ylim=None):
    st.markdown(f'<div class="section-label" style="margin-top:24px;">{label} Over Time</div>', unsafe_allow_html=True)

    time_col = "index" if "index" in data.columns else data.columns[0]
    fig, ax = plt.subplots(figsize=(12, 3))
    fig.patch.set_facecolor("#161b22")
    ax.set_facecolor("#0d1117")

    ax.plot(data[time_col], data[value_col], color=color, linewidth=0.8, alpha=0.85)
    ax.fill_between(data[time_col], data[value_col], alpha=0.15, color=color)

    if outliers is not None and not outliers.empty:
        ax.scatter(outliers[time_col], outliers[value_col],
                   color="#f85149", s=18, zorder=5, label="Outliers")
        ax.legend(facecolor="#161b22", edgecolor="#21262d", labelcolor="#e6edf3", fontsize=8)

    if ylim is not None:
        ax.set_ylim(ylim)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))
    ax.tick_params(colors="#8b949e", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#21262d")
    ax.set_ylabel(unit, color="#8b949e", fontsize=8)
    ax.grid(True, color="#21262d", linewidth=0.5, linestyle="--")
    plt.xticks(rotation=30)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="#161b22")
    buf.seek(0)
    st.image(buf, use_container_width=True)
    plt.close()

############################
# OVERLAP CHECK
############################

def check_overlap(start_a, end_a, start_b, end_b, label_a, label_b):
    overlap_start = max(start_a, start_b)
    overlap_end   = min(end_a,   end_b)

    st.markdown('<div class="section-label" style="margin-top:20px;">Time Overlap Check</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"""<div class="metric-card">
        <div class="metric-label">{label_a} Range</div>
        <div class="metric-value" style="font-size:1rem;">{start_a.strftime('%H:%M:%S')}</div>
        <div class="metric-unit">→ {end_a.strftime('%H:%M:%S')}</div>
    </div>""", unsafe_allow_html=True)
    c2.markdown(f"""<div class="metric-card">
        <div class="metric-label">{label_b} Range</div>
        <div class="metric-value" style="font-size:1rem;">{start_b.strftime('%H:%M:%S')}</div>
        <div class="metric-unit">→ {end_b.strftime('%H:%M:%S')}</div>
    </div>""", unsafe_allow_html=True)

    if overlap_start < overlap_end:
        duration = int((overlap_end - overlap_start).total_seconds())
        mins, secs = divmod(duration, 60)
        c3.markdown(f"""<div class="metric-card overlap-ok">
            <div class="metric-label">Overlap</div>
            <div class="metric-value" style="font-size:1rem;">{overlap_start.strftime('%H:%M:%S')}</div>
            <div class="metric-unit">→ {overlap_end.strftime('%H:%M:%S')} · {mins}m {secs}s</div>
        </div>""", unsafe_allow_html=True)
    else:
        c3.markdown(f"""<div class="metric-card overlap-fail">
            <div class="metric-label">No Overlap</div>
            <div class="metric-value" style="font-size:0.9rem;color:#f85149;">Check files</div>
            <div class="metric-unit">Time windows do not intersect</div>
        </div>""", unsafe_allow_html=True)
        st.stop()

############################
# MAP BUILDER
############################

def build_map(data, lat_col, lon_col, value_col, mode, filename,
              legend_html=None, colormap=None, vmin=None, vmax=None):
    m = folium.Map(
        location=[data[lat_col].mean(), data[lon_col].mean()],
        zoom_start=15, tiles="CartoDB positron"
    )

    _vmin = vmin if vmin is not None else data[value_col].min()
    _vmax = vmax if vmax is not None else data[value_col].max()

    cmap = colormap or cm.LinearColormap(
        ["blue", "cyan", "yellow", "orange", "red"],
        vmin=_vmin, vmax=_vmax
    )

    if mode == "Heatmap":
        heat_data = [[row[lat_col], row[lon_col], row[value_col]] for _, row in data.iterrows()]
        HeatMap(heat_data, radius=3, blur=3, max_zoom=24).add_to(m)
        cmap.add_to(m)
        if legend_html:
            m.get_root().html.add_child(folium.Element(legend_html))
    else:
        cmap.add_to(m)
        for _, row in data.iterrows():
            color = cmap(row[value_col])
            folium.CircleMarker(
                location=[row[lat_col], row[lon_col]],
                radius=3, color=color, fill=True,
                fill_color=color, fill_opacity=0.85, weight=0,
                popup=f"{value_col}: {row[value_col]:.2f}"
            ).add_to(m)
        if legend_html:
            m.get_root().html.add_child(folium.Element(legend_html))

    m.save(filename)
    return m

############################
# GPX PARSER
############################

def parse_gpx(gpx_file):
    tree = ET.parse(gpx_file)
    root = tree.getroot()
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    records = []
    for trkpt in root.iter(f"{ns}trkpt"):
        lat = float(trkpt.attrib["lat"])
        lon = float(trkpt.attrib["lon"])
        time_elem = trkpt.find(f"{ns}time")
        if time_elem is not None:
            ts = pd.to_datetime(time_elem.text, utc=True).tz_localize(None)
            records.append({"time": ts, "lat": lat, "lon": lon})
    return pd.DataFrame(records).sort_values("time").reset_index(drop=True)

############################
# POM PIPELINE
############################

def run_pom(csv_file, gpx_file, time_of_day, session_label, map_mode):
    label = session_label if session_label else f"POM · {time_of_day}"
    st.markdown(f'<div class="section-label" style="margin-top:8px;">Results — {label}</div>', unsafe_allow_html=True)

    df_raw    = pd.read_csv(csv_file, skiprows=5, header=None)
    ozone     = pd.to_numeric(df_raw.iloc[:, 1], errors="coerce")
    time_only = pd.to_datetime(df_raw.iloc[:, 11], format="%H:%M:%S", errors="coerce")
    pom       = pd.DataFrame({"time": time_only, "ozone": ozone}).dropna()

    try:
        df_raw.columns = [
            "Log Number","Ozone","Cell Temp","Cell Pressure","PDV",
            "BattV","Latitude","Longitude","Altitude","GPSquality","Date","Time"
        ]
    except ValueError:
        pass

    score = data_integrity(df_raw, [
        "Log Number","Ozone","Cell Temp","Cell Pressure","PDV",
        "BattV","Latitude","Longitude","Altitude","GPSquality"
    ])

    c_info, c_int = st.columns([2, 1])
    with c_info:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">Ozone Points Loaded</div>
            <div class="metric-value">{len(pom):,}</div>
        </div>""", unsafe_allow_html=True)
    with c_int:
        show_integrity(score)

    gps = parse_gpx(gpx_file)
    if gps.empty:
        st.error("No GPS points found in GPX file.")
        st.stop()

    gpx_date = gps["time"].iloc[0].date()
    pom["time"] = pom["time"].apply(
        lambda t: t.replace(year=gpx_date.year, month=gpx_date.month, day=gpx_date.day)
    )

    check_overlap(pom["time"].min(), pom["time"].max(),
                  gps["time"].min(),  gps["time"].max(), "POM", "GPX")

    # Align
    pom_r = pom.set_index("time").resample("1s").mean()
    gps_r = gps.set_index("time").resample("1s").mean()
    pom_r["ozone"] = pom_r["ozone"].interpolate()
    gps_r["lat"]   = gps_r["lat"].interpolate()
    gps_r["lon"]   = gps_r["lon"].interpolate()
    data = pd.concat([pom_r, gps_r], axis=1).dropna().reset_index()

    if data.empty:
        st.error("No aligned data points. Check time windows.")
        st.stop()

    st.caption(f"✓ {len(data):,} aligned data points")

    # Stats from raw POM sensor data; outlier chips from GPS-aligned data
    outliers = show_summary_stats(pom, data, "ozone", "ppb")
    show_timeseries(data, "ozone", "Ozone Concentration", "ppb", "#38bdf8", outliers)

    st.markdown('<div class="section-label" style="margin-top:24px;">Map</div>', unsafe_allow_html=True)

    legend_html = '''
    <div style="position:fixed;bottom:50px;left:50px;width:320px;background:#1a1a2e;
    border:1px solid #333;z-index:9999;font-size:13px;padding:12px;border-radius:8px;
    color:#e6edf3;box-shadow:0 4px 12px rgba(0,0,0,0.5);">
    <b style="font-family:monospace;">Ozone (ppb)</b><br>
    <span style="font-size:10px;color:#8b949e;">(EPA 8-hour categories)</span><br><br>
    <div style="width:100%;height:14px;border-radius:4px;
    background:linear-gradient(to right,blue 0%,cyan 27%,yellow 42%,orange 52%,red 65%,purple 100%);
    margin-bottom:6px;"></div>
    <div style="display:grid;grid-template-columns:repeat(6,1fr);font-size:10px;text-align:center;color:#8b949e;">
    <span>0</span><span>54</span><span>70</span><span>85</span><span>105</span><span>200+</span>
    </div>
    <div style="font-size:10px;text-align:center;margin-top:8px;color:#8b949e;">
    Good → Moderate → USG → Unhealthy → Very Unhealthy → Hazardous
    </div></div>'''

    pom_cmap = cm.LinearColormap(
        ["blue", "cyan", "yellow", "orange", "red"],
        vmin=0, vmax=200,
        caption="Ozone (ppb)"
    )

    map_file = "pom_ozone_map.html"
    build_map(data, "lat", "lon", "ozone", map_mode, map_file,
              legend_html=legend_html, colormap=pom_cmap, vmin=0, vmax=200)

    st.success(f"✅ Map generated — {len(data):,} points plotted")
    st.markdown(
        get_download_link(map_file, "📥 Download Map (HTML)", "pom_ozone_map.html") + " &nbsp;|&nbsp; " +
        get_csv_download_link(data[["index","ozone","lat","lon"]], "📊 Download Data (CSV)", "pom_data.csv"),
        unsafe_allow_html=True
    )
    with open(map_file, "r", encoding="utf-8") as f:
        st.components.v1.html(f.read(), height=600)

############################
# POPS PM2.5 CALCULATION
############################

def calculate_pm2_5(row):
    bin_cols = [f"b{i}" for i in range(16)]
    SD = row[bin_cols].values
    PF = row[" POPS_Flow"]
    if PF == 0 or np.isnan(PF): return np.nan
    Dp = np.array([0.14,0.17,0.205,0.249,0.302,0.366,0.443,0.537,
                   0.651,0.789,0.956,1.159,1.404,1.702,2.062,2.500])
    return 2 * np.sum((4/3) * np.pi * (Dp/2)**3 * SD / PF)

############################
# POPS ALIGNMENT
############################

def prepare_heatmap_data(pops_df, gps_df, value_col):
    gps = gps_df.rename(columns={"lat": "latitude", "lon": "longitude"})

    pw = pops_df.set_index("DateTime_utc")
    gw = gps.set_index("time")

    pr = pw[[value_col]].resample("1s").mean()
    gr = gw[["latitude","longitude"]].resample("1s").mean()

    pr[value_col]   = pr[value_col].interpolate()
    gr["latitude"]  = gr["latitude"].interpolate()
    gr["longitude"] = gr["longitude"].interpolate()

    return pd.concat([pr, gr], axis=1).dropna().reset_index()

############################
# POPS PIPELINE
############################

def run_pops(csv_file, gpx_file, time_of_day, session_label, map_mode):
    label = session_label if session_label else f"POPS · {time_of_day}"
    st.markdown(f'<div class="section-label" style="margin-top:8px;">Results — {label}</div>', unsafe_allow_html=True)

    # --- Load POPS CSV ---
    pops_df = pd.read_csv(csv_file).copy()
    pops_df["DateTime_utc"] = pd.to_datetime(pops_df["DateTime"], unit="s", utc=True).dt.tz_localize(None)
    if "PM2p5_ug_m3" not in pops_df.columns:
        pops_df["PM2p5_ug_m3"] = pops_df.apply(calculate_pm2_5, axis=1)

    score = data_integrity(pops_df, ["DateTime","PartCon","PM2p5_ug_m3"])
    c_info, c_int = st.columns([2, 1])
    with c_info:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">POPS Points Loaded</div>
            <div class="metric-value">{len(pops_df):,}</div>
        </div>""", unsafe_allow_html=True)
    with c_int:
        show_integrity(score)

    # --- Parse GPX ---
    gps_df = parse_gpx(gpx_file)
    if gps_df.empty:
        st.error("No GPS points found in GPX file.")
        st.stop()

    # --- Overlap check ---
    check_overlap(
        pops_df["DateTime_utc"].min(), pops_df["DateTime_utc"].max(),
        gps_df["time"].min(),          gps_df["time"].max(),
        "POPS", "GPX"
    )

    # -----------------------------------------------
    # PM2.5
    # -----------------------------------------------
    st.markdown("---")
    st.markdown('<div class="section-label">PM2.5</div>', unsafe_allow_html=True)
    pm25_data = prepare_heatmap_data(pops_df, gps_df, "PM2p5_ug_m3")
    st.caption(f"✓ {len(pm25_data):,} aligned points")

    # Stats from raw pops_df; outlier chips from GPS-aligned pm25_data
    pm25_outliers = show_summary_stats(pops_df, pm25_data, "PM2p5_ug_m3", "µg/m³")
    show_timeseries(pm25_data, "PM2p5_ug_m3", "PM2.5 Concentration", "µg/m³", "#38bdf8", pm25_outliers)

    pm25_file = "pops_pm25_map.html"
    pm25_cmap = cm.LinearColormap(
        ["blue", "cyan", "yellow", "orange", "red"],
        vmin=0, vmax=50,
        caption="PM2.5 (µg/m³)"
    )
    build_map(pm25_data, "latitude", "longitude", "PM2p5_ug_m3", map_mode, pm25_file,
              colormap=pm25_cmap, vmin=0, vmax=50)

    st.markdown('<div class="section-label" style="margin-top:16px;">PM2.5 Map</div>', unsafe_allow_html=True)
    st.markdown(
        get_download_link(pm25_file, "📥 Download PM2.5 Map", "pops_pm25_map.html") + " &nbsp;|&nbsp; " +
        get_csv_download_link(pm25_data, "📊 Download PM2.5 CSV", "pm25_data.csv"),
        unsafe_allow_html=True
    )
    with open(pm25_file, "r", encoding="utf-8") as f:
        st.components.v1.html(f.read(), height=500)

    # -----------------------------------------------
    # PartCon
    # -----------------------------------------------
    st.markdown("---")
    st.markdown('<div class="section-label">Particle Concentration</div>', unsafe_allow_html=True)
    partcon_data = prepare_heatmap_data(pops_df, gps_df, "PartCon")
    st.caption(f"✓ {len(partcon_data):,} aligned points")

    # Stats from raw pops_df; outlier chips from GPS-aligned partcon_data
    pc_outliers = show_summary_stats(pops_df, partcon_data, "PartCon", "#/cm³")
    show_timeseries(partcon_data, "PartCon", "Particle Concentration", "#/cm³", "#a78bfa", pc_outliers)

    partcon_file = "pops_partcon_map.html"
    pc_vmin = partcon_data["PartCon"].min()
    pc_vmax = partcon_data["PartCon"].max()
    pc_cmap = cm.LinearColormap(
        ["blue", "cyan", "yellow", "orange", "red"],
        vmin=pc_vmin, vmax=pc_vmax,
        caption="Particle Concentration (#/cm³)"
    )
    build_map(partcon_data, "latitude", "longitude", "PartCon", map_mode, partcon_file,
              colormap=pc_cmap, vmin=pc_vmin, vmax=pc_vmax)

    st.markdown('<div class="section-label" style="margin-top:16px;">Particle Concentration Map</div>', unsafe_allow_html=True)
    st.markdown(
        get_download_link(partcon_file, "📥 Download PartCon Map", "pops_partcon_map.html") + " &nbsp;|&nbsp; " +
        get_csv_download_link(partcon_data, "📊 Download PartCon CSV", "partcon_data.csv"),
        unsafe_allow_html=True
    )
    with open(partcon_file, "r", encoding="utf-8") as f:
        st.components.v1.html(f.read(), height=500)

    st.success("✅ All POPS maps generated")

############################
# MAIN — FILE UPLOADERS
############################

st.markdown('<div class="section-label">Upload Files</div>', unsafe_allow_html=True)

if device == "POM":
    c1, c2 = st.columns(2)
    with c1:
        csv_file = st.file_uploader("POM CSV", type=["csv"])
    with c2:
        gpx_file = st.file_uploader("GPX Track", type=["gpx"])

    st.markdown("")
    if st.button("🗺️ Generate Map"):
        if csv_file is None or gpx_file is None:
            st.error("Please upload both the CSV and GPX files.")
            st.stop()
        with st.spinner("Processing data and building map…"):
            run_pom(csv_file, gpx_file, time_of_day, session_label, map_mode)

elif device == "POPS":
    c1, c2 = st.columns(2)
    with c1:
        csv_file = st.file_uploader("POPS CSV", type=["csv"])
    with c2:
        gpx_file = st.file_uploader("GPX Track", type=["gpx"])

    st.markdown("")
    if st.button("🗺️ Generate Maps"):
        if csv_file is None or gpx_file is None:
            st.error("Please upload both the CSV and GPX files.")
            st.stop()
        with st.spinner("Processing data and building maps…"):
            run_pops(csv_file, gpx_file, time_of_day, session_label, map_mode)
