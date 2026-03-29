import streamlit as st
import polars as pl
import plotly.graph_objects as go
import math
from geopy.geocoders import Nominatim
from core import CTACrime

st.set_page_config(
    page_title = "CTA Crimes",
    layout = "wide",
    initial_sidebar_state = "expanded",
)

st.title("\U0001F687 CTA Crimes")
st.markdown(
    "Crimes in Chicago's rapid transit system in the last 30 days available (refreshed daily). Select crime type(s) and "
    "date range on the sidebar. The Chicago Police Department (CPD) partially redacts crime locations, so there is  "
    "some degree of imprecision. Each solid black dot denotes an incident of crime."
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

client = CTACrime(
    api_key_id = st.secrets["socrata_username"],
    api_key_secret = st.secrets["socrata_password"],
    token = st.secrets["socrata_app_token"]
)

@st.cache_data(ttl = 3600 * 24, show_spinner = "Fetching CTA crime data\u2026")
def load_crimes(client: CTACrime = client) -> pl.DataFrame:
    return client.get_cta_crimes(last_n_days = 30)

@st.cache_data(ttl = 3600 * 24 * 365, show_spinner = "Fetching CTA station locations\u2026")
def load_stations(client: CTACrime = client) -> pl.DataFrame:
    df = client.cta_rail_stations()

    df = df.with_columns(
        pl.col("the_geom").struct.field("coordinates").list.get(0).alias("lon"),
        pl.col("the_geom").struct.field("coordinates").list.get(1).alias("lat"),
    )

    return df

@st.cache_data(ttl = 3600 * 24 * 365, show_spinner = "Fetching CTA rail lines\u2026")
def load_rail_lines(client: CTACrime = client) -> dict:
    df = client.cta_rail_lines()

    features = []
    for geom in df["the_geom"].to_list():
        if geom is None:
            continue
        coords = geom.get("coordinates", []) if isinstance(geom, dict) else []
        if coords:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": coords,
                },
            })

    return {"type": "FeatureCollection", "features": features}

@st.cache_data(ttl = 3600 * 24 * 365, show_spinner = "Fetching community areas\u2026")
def load_community_areas(client: CTACrime = client) -> tuple:
    df = client.chicago_community_areas()

    features = []
    centroids = []

    for row in df.iter_rows(named = True):
        geom = row["the_geom"]
        name = row["community"]

        if geom is None:
            continue

        coords = geom.get("coordinates", []) if isinstance(geom, dict) else []
        geom_type = geom.get("type", "MultiPolygon") if isinstance(geom, dict) else "MultiPolygon"

        if not coords:
            continue

        features.append({
            "type": "Feature",
            "properties": {"name": name},
            "geometry": {"type": geom_type, "coordinates": coords},
        })

        all_lats, all_lons = [], []
        for polygon in coords:
            for ring in polygon:
                for lon, lat in ring:
                    all_lons.append(lon)
                    all_lats.append(lat)

        if all_lats:
            centroids.append({
                "community": name.title(),
                "lat": sum(all_lats) / len(all_lats),
                "lon": sum(all_lons) / len(all_lons),
            })

    geojson = {"type": "FeatureCollection", "features": features}
    centroids_df = pl.DataFrame(centroids)
    return geojson, centroids_df

crimes_df = load_crimes()
stations_df = load_stations()
rail_lines_geojson = load_rail_lines()
community_geojson, community_centroids = load_community_areas()

crime_types = sorted(crimes_df["primary_type"].unique().to_list())

st.sidebar.header("Filters")

selected_types = st.sidebar.multiselect(
    "Crime Type",
    options = crime_types,
    default = [],
)

min_date = crimes_df["date"].min()
max_date = crimes_df["date"].max()

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
    
address_street = st.sidebar.text_input(
    "Enter your street number and name below to pin it in the map (a purple dot) for reference.",
    placeholder = "190 S LaSalle St",
)
st.sidebar.text_input("City", value = "Chicago", disabled = True)
st.sidebar.text_input("State", value = "Illinois", disabled = True)

searched_location = None
if address_street:
    full_address = f"{address_street}, Chicago, Illinois"
    geolocator = Nominatim(user_agent = "cta-crimes-dashboard")
    try:
        location = geolocator.geocode(full_address, timeout = 5)
        if location:
            searched_location = {"lat": location.latitude, "lon": location.longitude, "label": location.address}
        else:
            st.sidebar.warning("Address not found.")
    except Exception:
        st.sidebar.warning("Geocoding failed. Try again.")

filtered = crimes_df.filter(
    pl.col("primary_type").is_in(selected_types)
    & (pl.col("date") >= start_date)
    & (pl.col("date") <= end_date)
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

fig.add_trace(
    go.Choroplethmapbox(
        geojson = community_geojson,
        locations = [f["properties"]["name"] for f in community_geojson["features"]],
        featureidkey = "properties.name",
        z = [1] * len(community_geojson["features"]),
        colorscale = [[0, "rgba(180, 180, 180, 0.25)"], [1, "rgba(180, 180, 180, 0.25)"]],
        marker = dict(line = dict(width = 1, color = "rgba(100, 100, 100, 0.5)")),
        hovertext = [f["properties"]["name"].title() for f in community_geojson["features"]],
        hoverinfo = "text",
        showscale = False,
        showlegend = False,
    )
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
            mode = "markers+text",
            marker = dict(size = 9, color = color, opacity = 0.9),
            text = subset["longname"].to_list(),
            textfont = dict(size = 9),
            textposition = "top center",
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
                color = "black",
            ),
            name = "Crimes",
            hovertext = [
                f"{row['primary_type']}<br>{row['date']}<br>{row['location_description']}"
                for row in filtered.iter_rows(named = True)
            ],
            hoverinfo = "text",
        )
    )
    
if searched_location:
    def make_circle(lat, lon, radius_miles = 1, n_points = 64):
        radius_km = radius_miles * 1.60934
        lats, lons = [], []
        for i in range(n_points + 1):
            angle = math.radians(360 * i / n_points)
            dlat = (radius_km / 111.32) * math.cos(angle)
            dlon = (radius_km / (111.32 * math.cos(math.radians(lat)))) * math.sin(angle)
            lats.append(lat + dlat)
            lons.append(lon + dlon)
        return lats, lons

    circle_lats, circle_lons = make_circle(searched_location["lat"], searched_location["lon"])

    fig.add_trace(
        go.Scattermapbox(
            lat = circle_lats,
            lon = circle_lons,
            mode = "lines",
            line = dict(width = 3, color = "purple"),
            fill = "toself",
            fillcolor = "rgba(128, 0, 128, 0.15)",
            name = "One-Mile Radius",
            hoverinfo = "skip",
        )
    )

    fig.add_trace(
        go.Scattermapbox(
            lat = [searched_location["lat"]],
            lon = [searched_location["lon"]],
            mode = "markers",
            marker = dict(size = 10, color = "purple"),
            name = "Your Address",
            hoverinfo = "skip",
        )
    )

fig.update_layout(
    mapbox = dict(
        style = "white-bg",
        center = (
            dict(lat = searched_location["lat"], lon = searched_location["lon"]) if searched_location
            else dict(lat = 41.8781, lon = -87.6298)
        ),
        zoom = 10.5,
        layers = [
            dict(
                below = "traces",
                sourcetype = "raster",
                sourceattribution = "\u00a9 OpenStreetMap contributors, \u00a9 CARTO",
                source = ["https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"],
            ),
            dict(
                below = "traces",
                sourcetype = "geojson",
                source = rail_lines_geojson,
                type = "line",
                color = "grey",
                line = dict(width = 2, dash = [4, 2]),
            ),
        ],
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