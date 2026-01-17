import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
import time
import folium
from streamlit_folium import folium_static
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

#Command to run code: streamlit run weatherforecasting.py

# ================= CONFIG =================
st.set_page_config(
    page_title="Blue Horizon",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Theme selection & styling
theme = st.sidebar.selectbox("Theme", ["Light", "Dark"], index=0)

if theme == "Light":
    st.markdown("""
        <style>
            .stApp { background-color: #ffffff !important; color: #ffffff !important; }
            section[data-testid="stSidebar"] { background-color: #ffffff !important; color: #ffffff !important; }
            .stMarkdown, .stText, .stMetricLabel, .stMetricValue, h1, h2, h3, h4, h5, h6, p, span, div {
                color: #000000 !important;
            }
        </style>
    """, unsafe_allow_html=True)
else:  # Dark
    st.markdown("""
        <style>
            .stApp { background-color: #000000 !important; color: #e0e0e0 !important; }
            section[data-testid="stSidebar"] { background-color: #000000 !important; color: #e0e0e0 !important; }
            .stMarkdown, .stText, .stMetricLabel, .stMetricValue, h1, h2, h3, h4, h5, h6, p, span, div {
                color: #ffffff !important;
            }
            .stDataFrame, .stPlotlyChart { background-color: #ffffff !important; }
        </style>
    """, unsafe_allow_html=True)

st.title("🌤️ Blue Horizon")
st.markdown("Search any city worldwide • Real-time + forecast + air quality + historical + PDF export")

# Session state
if "current_city" not in st.session_state:
    st.session_state.current_city = "Bengaluru"
if "units" not in st.session_state:
    st.session_state.units = {"temp": "celsius", "wind": "kmh", "precip": "mm"}

# Main search bar
city_input = st.text_input(
    "Enter city name",
    value=st.session_state.current_city,
    placeholder="e.g. Bengaluru, Tokyo, New York, Paris, Mumbai",
    key="city_search_input"
)

if city_input.strip() and city_input.strip() != st.session_state.current_city:
    st.session_state.current_city = city_input.strip()
    st.rerun()

# Sidebar units
st.sidebar.subheader("Units")
st.session_state.units["temp"] = st.sidebar.radio("Temperature", ["celsius", "fahrenheit"])
st.session_state.units["wind"] = st.sidebar.radio("Wind Speed", ["kmh", "mph", "ms", "kn"])
st.session_state.units["precip"] = st.sidebar.radio("Precipitation", ["mm", "inch"])

# ================= HELPERS =================
WMO_CODES = {
    0: "Clear sky ☀️", 1: "Mainly clear 🌤️", 2: "Partly cloudy ⛅", 3: "Overcast ☁️",
    45: "Fog 🌫️", 48: "Rime fog 🌫️",
    51: "Light drizzle 🌦️", 53: "Moderate drizzle 🌦️", 55: "Dense drizzle 🌦️",
    61: "Slight rain 🌧️", 63: "Moderate rain 🌧️", 65: "Heavy rain 🌧️",
    71: "Slight snow ❄️", 73: "Moderate snow ❄️", 75: "Heavy snow ❄️",
    80: "Rain showers 🌧️", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm ⚡", 96: "Thunderstorm with hail ⚡🌨️"
}

def get_condition(code):
    return WMO_CODES.get(code, f"Unknown ({code})")

@st.cache_data(ttl=1800)
def get_coordinates(city_name):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city_name, "format": "json", "limit": 1}
    headers = {"User-Agent": "WeatherForecasterApp/1.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=5)
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", city_name)
        return None, None, None
    except:
        return None, None, None

@st.cache_data(ttl=600)
def fetch_weather(lat, lon, units):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation_probability",
        "hourly": "temperature_2m,weather_code,precipitation_probability",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,uv_index_max,precipitation_sum,sunrise,sunset",
        "timezone": "auto",
        "temperature_unit": units["temp"],
        "wind_speed_unit": units["wind"],
        "precipitation_unit": units["precip"],
        "forecast_days": 7
    }
    url = "https://api.open-meteo.com/v1/forecast?" + "&".join(f"{k}={v}" for k,v in params.items())
    try:
        r = requests.get(url, timeout=10).json()
        if "error" in r:
            st.error(r.get("reason", "API error"))
            return None
        return r
    except Exception as e:
        st.error(f"Fetch error: {e}")
        return None

@st.cache_data(ttl=600)
def fetch_air_quality(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "european_aqi,pm2_5,pm10,ozone"
    }
    url = "https://air-quality-api.open-meteo.com/v1/air-quality?" + "&".join(f"{k}={v}" for k,v in params.items())
    try:
        return requests.get(url, timeout=8).json()
    except:
        return None

@st.cache_data(ttl=1800)
def fetch_historical(lat, lon, units, start_date, end_date):
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "auto",
        "temperature_unit": units["temp"],
        "precipitation_unit": units["precip"]
    }
    url = "https://archive-api.open-meteo.com/v1/archive?" + "&".join(f"{k}={v}" for k,v in params.items())
    try:
        return requests.get(url, timeout=10).json()
    except:
        return None

def generate_pdf(city, weather):
    filename = f"{city.replace(' ', '_')}_weather_report.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(f"Weather Report - {city}", styles['Title']))
    story.append(Spacer(1, 12))

    if weather and "current" in weather:
        c = weather["current"]
        u = weather["current_units"]
        story.append(Paragraph(f"Current: {c['temperature_2m']} {u['temperature_2m']}", styles['Normal']))
        story.append(Paragraph(f"Feels like: {c['apparent_temperature']} {u['apparent_temperature']}", styles['Normal']))
        story.append(Paragraph(f"Condition: {get_condition(c.get('weather_code', 0))}", styles['Normal']))

    if weather and "daily" in weather:
        story.append(Paragraph("7-Day Forecast:", styles['Heading2']))
        for i in range(len(weather["daily"]["time"])):
            d = weather["daily"]
            story.append(Paragraph(
                f"{d['time'][i]}: Max {d['temperature_2m_max'][i]}° / Min {d['temperature_2m_min'][i]}°",
                styles['Normal']
            ))

    doc.build(story)
    return filename

# ================= MAIN LOGIC =================
lat, lon, display_name = get_coordinates(st.session_state.current_city)

if lat is None or lon is None:
    st.error(f"Could not find city: {st.session_state.current_city}")
    st.stop()

st.subheader(f"Weather for {display_name or st.session_state.current_city}")

weather = fetch_weather(lat, lon, st.session_state.units)
air = fetch_air_quality(lat, lon)

if not weather:
    st.info("Loading weather data...")
    st.stop()

tabs = st.tabs(["Current", "Hourly", "Daily", "Air Quality", "Map", "Historical", "Export PDF"])

# Current
with tabs[0]:
    c = weather["current"]
    u = weather["current_units"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Temperature", f"{c['temperature_2m']} {u['temperature_2m']}", f"Feels like {c['apparent_temperature']}")
    col2.metric("Humidity", f"{c['relative_humidity_2m']}%")
    col3.metric("Wind", f"{c['wind_speed_10m']} {u['wind_speed_10m']}")
    col4.metric("Rain Prob", f"{c.get('precipitation_probability', '—')}%")
    st.metric("Condition", get_condition(c["weather_code"]))

# Hourly
with tabs[1]:
    h = weather["hourly"]
    df_h = pd.DataFrame({
        "Time": pd.to_datetime(h["time"][:24]).strftime("%H:%M"),
        f"Temp ({weather['hourly_units']['temperature_2m']})": h["temperature_2m"][:24],
        "Rain %": h["precipitation_probability"][:24]
    })
    fig_h = go.Figure()
    fig_h.add_trace(go.Scatter(x=df_h["Time"], y=df_h.iloc[:,1], name="Temp"))
    fig_h.add_trace(go.Bar(x=df_h["Time"], y=df_h["Rain %"], name="Rain %", yaxis="y2", opacity=0.4))
    fig_h.update_layout(yaxis2=dict(title="Rain %", overlaying="y", side="right"))
    st.plotly_chart(fig_h, use_container_width=True)
    st.dataframe(df_h, use_container_width=True)

# Daily
with tabs[2]:
    d = weather["daily"]
    df_d = pd.DataFrame({
        "Date": d["time"],
        f"Max ({weather['daily_units']['temperature_2m_max']})": d["temperature_2m_max"],
        f"Min ({weather['daily_units']['temperature_2m_min']})": d["temperature_2m_min"],
        "Precip sum": d["precipitation_sum"]
    })
    st.dataframe(df_d, use_container_width=True)

# Air Quality
with tabs[3]:
    if air and "current" in air:
        a = air["current"]
        col1, col2 = st.columns(2)
        col1.metric("European AQI", a.get("european_aqi", "—"))
        col2.metric("PM2.5", a.get("pm2_5", "—"))
    else:
        st.info("Air quality data not available")

# Map
with tabs[4]:
    m = folium.Map(location=[lat, lon], zoom_start=10)
    folium.Marker(
        [lat, lon],
        popup=f"{display_name}<br>{weather['current']['temperature_2m']}° • {get_condition(weather['current']['weather_code'])}"
    ).add_to(m)
    folium_static(m, width=700, height=500)

# Historical
with tabs[5]:
    st.subheader("Historical (last 7 days)")
    end_d = date.today()
    start_d = end_d - timedelta(days=7)
    col1, col2 = st.columns(2)
    sd = col1.date_input("From", start_d)
    ed = col2.date_input("To", end_d)

    hist = fetch_historical(lat, lon, st.session_state.units, sd.strftime("%Y-%m-%d"), ed.strftime("%Y-%m-%d"))
    if hist and "daily" in hist:
        df_hist = pd.DataFrame({
            "Date": hist["daily"]["time"],
            "Max Temp": hist["daily"]["temperature_2m_max"],
            "Min Temp": hist["daily"]["temperature_2m_min"]
        })
        st.line_chart(df_hist.set_index("Date")[["Max Temp", "Min Temp"]])
        st.dataframe(df_hist)

# PDF Export
with tabs[6]:
    if st.button("Generate & Download PDF Report"):
        pdf_file = generate_pdf(st.session_state.current_city, weather)
        with open(pdf_file, "rb") as f:
            st.download_button(
                "Download Report",
                f,
                file_name=pdf_file,
                mime="application/pdf"
            )

st.caption(f"Last update: {datetime.now().strftime('%Y-%m-%d %H:%M IST')} • Data: Open-Meteo • Built by Aabhinav Sarkar")
