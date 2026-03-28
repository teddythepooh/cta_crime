import streamlit as st
import polars as pl
import plotly.graph_objects as go
from core import CTACrime

st.set_page_config(
    page_title = "CTA Crimes",
    layout = "wide",
    initial_sidebar_state = "expanded",
)

st.title("\U0001F687 CTA Crimes")
st.markdown(
    "Crimes in or along Chicago's train system up to the last 30 days (refreshed daily). Select crime type(s) and "
    "date range on the sidebar. The Chicago Police Department does not make incidents from the last seven days "
    "publicly available, hence this dashboard is delayed by a week."
)

LINE_COLORS = {
    "Red":      "#C60C30",
    "Blue":     "#00A1DE",
    "Brown":    "#62361B",
    "Green":    "#009B3A",
    "Orange":   "#F9461C",
    "Pink":     "#E27EA6",
    "Purple":   "#522398",
    "Yellow":   "#F9E300",
    "Multiple": "#FFFFFF",
}



@st.cache_data(ttl = 3600 * 24, show_spinner = "Fetching CTA crime data\u2026")
def load_crimes() -> pl.DataFrame:
    client = CTACrime()
    df = client.get_cta_crimes(last_n_days = 30)

    df = df.with_columns(
        pl.col("date").str.to_datetime().alias("date"),
        pl.col("longitude").cast(pl.Float64),
        pl.col("latitude").cast(pl.Float64),
    )
    
    return df

@st.cache_data(ttl = 3600 * 24 * 365, show_spinner = "Fetching CTA station locations\u2026")
def load_stations() -> pl.DataFrame:
    client = CTACrime()
    df = client.cta_train_coordinates()

    df = df.with_columns(
        pl.col("the_geom").struct.field("coordinates").list.get(0).alias("lon"),
        pl.col("the_geom").struct.field("coordinates").list.get(1).alias("lat"),
    )
    
    return df

crimes_df = load_crimes()
stations_df = load_stations()

crime_types = sorted(crimes_df["primary_type"].unique().to_list())

st.sidebar.header("Filters")

selected_types = st.sidebar.multiselect(
    "Crime Type",
    options = crime_types,
    default = [],
)

min_date = crimes_df["date"].min().date()
max_date = crimes_df["date"].max().date()

date_range = st.sidebar.date_input(
    "Date Range",
    value = (min_date, max_date),
    min_value = min_date,
    max_value = max_date,
)

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

filtered = crimes_df.filter(
    pl.col("primary_type").is_in(selected_types)
    & (pl.col("date").dt.date() >= start_date)
    & (pl.col("date").dt.date() <= end_date)
)

col1, col2 = st.columns(2)
col1.metric("Total Crimes", len(filtered))
col2.metric(
    "Date Range",
    f"{start_date.strftime('%b %d')} \u2013 {end_date.strftime('%b %d')}",
)

fig = go.Figure()

valid_stations = stations_df.filter(
    pl.col("lat").is_not_null()
    & pl.col("lon").is_not_null()
    & pl.col("legend").is_not_null()
    & (pl.col("legend") != "")
)


    
for line_name, color in LINE_COLORS.items():
    subset = valid_stations.filter(
        pl.col("legend").str.contains(f"{line_name}")
    )
    if len(subset) == 0:
        continue
    
    if line_name == "Multiple":
        fig.add_trace(
            go.Scattermapbox(
                lat = subset["lat"].to_list(),
                lon = subset["lon"].to_list(),
                mode = "markers",
                marker = dict(size = 12, color = "black"),
                showlegend = False,
                hoverinfo = "none",
            )
        )
        
    fig.add_trace(
        go.Scattermapbox(
            lat = subset["lat"].to_list(),
            lon = subset["lon"].to_list(),
            mode = "markers",
            marker = dict(size = 9, color = color, opacity = 0.9),
            name = f"{line_name} {'Lines' if line_name == 'Multiple' else 'Line'}",
            hovertext = subset["longname"].to_list(),
            hoverinfo = "text",
        )
    )
    
if len(filtered) > 0:
    fig.add_trace(
        go.Scattermapbox(
            lat = filtered["latitude"].to_list(),
            lon = filtered["longitude"].to_list(),
            mode = "markers",
            marker = dict(
                size = 10,
                color = "black"
            ),
            name = "Crimes",
            hovertext = [
                f"{row['primary_type']}<br>{row['date']:%Y-%m-%d %H:%M}<br>{row['location_description']}"
                for row in filtered.iter_rows(named = True)
            ],
            hoverinfo = "text",
        )
    )

fig.update_layout(
    mapbox = dict(
        style = "carto-positron",
        center = dict(lat = 41.8781, lon = -87.6298),
        zoom = 10.5,
    ),
    margin = dict(l = 0, r = 0, t = 0, b = 0),
    height = 650,
    legend = dict(
        yanchor = "top",
        y = 0.99,
        xanchor = "left",
        x = 0.01,
        bgcolor = "rgba(255,255,255,0.8)",
    ),
)

st.plotly_chart(fig, width = "stretch")