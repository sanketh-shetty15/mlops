# """
# dashboard/charts.py
# ---------------------
# All Plotly chart builders for the Streamlit dashboard.
# All labels, tick text, axis titles, legend text → #000000 (black).
# """

# import pandas as pd
# import plotly.express as px
# import plotly.graph_objects as go

# # ── Colour palette ─────────────────────────────────────────────────────────────
# SEVERITY_COLOURS = {
#     "Fatal":   "#e63946",
#     "Serious": "#f4a261",
#     "Slight":  "#2ec4b6",
# }

# PALETTE = {
#     "navy":       "#0f3460",
#     "steel":      "#457b9d",
#     "teal":       "#2ec4b6",
#     "amber":      "#f4a261",
#     "red":        "#e63946",
#     "light_grey": "#f4f6f9",
#     "mid_grey":   "#dee2e6",
#     "text":       "#000000",
# }

# _CHART_TEMPLATE = "plotly_white"
# _BLACK = "#000000"
# _FONT  = dict(family="Segoe UI, sans-serif", color=_BLACK)

# # Every axis gets these defaults — all text black
# _AXIS  = dict(
#     tickfont=dict(color=_BLACK, size=11),
#     title_font=dict(color=_BLACK, size=12),
#     linecolor="#dee2e6",
#     zerolinecolor="#dee2e6",
# )


# def _ax(**extra):
#     """Merge extra kwargs on top of _AXIS defaults."""
#     d = dict(**_AXIS)
#     d.update(extra)
#     return d


# def _base_layout(**kwargs):
#     """Base layout with black font everywhere. Per-chart kwargs override."""
#     base = dict(
#         template=_CHART_TEMPLATE,
#         font=_FONT,
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f9fafb",
#         margin=dict(t=50, b=30, l=10, r=10),
#         xaxis=_ax(),
#         yaxis=_ax(),
#         legend=dict(
#             bgcolor="rgba(255,255,255,0.9)",
#             bordercolor="#dee2e6",
#             borderwidth=1,
#             font=dict(color=_BLACK, size=12),
#         ),
#     )
#     # Merge axis dicts so per-chart settings stack on top of defaults
#     for axis in ("xaxis", "yaxis", "yaxis2"):
#         if axis in kwargs:
#             merged = _ax()
#             merged.update(kwargs.pop(axis))
#             base[axis] = merged
#     if "margin" in kwargs:
#         base["margin"] = kwargs.pop("margin")
#     # Merge legend
#     if "legend" in kwargs:
#         leg = dict(**base["legend"])
#         leg.update(kwargs.pop("legend"))
#         base["legend"] = leg
#     base.update(kwargs)
#     return base


# # ── Severity Distribution ──────────────────────────────────────────────────────

# def chart_severity_donut(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No severity data available")

#     colours = [SEVERITY_COLOURS.get(s, "#adb5bd") for s in df["severity_label"]]
#     fig = go.Figure(go.Pie(
#         labels=df["severity_label"],
#         values=df["accident_count"],
#         hole=0.50,
#         marker=dict(colors=colours, line=dict(color="#ffffff", width=3)),
#         textinfo="label+percent",
#         textfont=dict(size=13, color=_BLACK),
#         hovertemplate=(
#             "<b>%{label}</b><br>"
#             "Accidents: %{value:,}<br>"
#             "Share: %{percent}<extra></extra>"
#         ),
#     ))
#     fig.update_layout(**_base_layout(
#         title=dict(text="Accident Severity Distribution",
#                    font=dict(size=15, color=_BLACK), x=0),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#ffffff",
#         legend=dict(orientation="h", yanchor="bottom", y=-0.15),
#         margin=dict(t=50, b=30, l=10, r=10),
#     ))
#     return fig


# def chart_severity_bar(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No severity data available")

#     colours = [SEVERITY_COLOURS.get(s, "#adb5bd") for s in df["severity_label"]]
#     fig = go.Figure(go.Bar(
#         x=df["severity_label"],
#         y=df["accident_count"],
#         marker=dict(color=colours, line=dict(color="#ffffff", width=1.5), opacity=0.92),
#         text=df["accident_count"].apply(lambda v: f"{v:,}"),
#         textposition="outside",
#         textfont=dict(size=12, color=_BLACK),
#         hovertemplate="<b>%{x}</b><br>Count: %{y:,}<extra></extra>",
#     ))
#     fig.update_layout(**_base_layout(
#         title=dict(text="Accidents by Severity",
#                    font=dict(size=15, color=_BLACK), x=0),
#         xaxis=dict(title="Severity", showgrid=False),
#         yaxis=dict(title="Number of Accidents", gridcolor="#e9ecef"),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#     ))
#     return fig


# # ── Accidents by Hour ──────────────────────────────────────────────────────────

# def chart_accidents_by_hour(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No hourly data available")

#     fig = go.Figure()
#     for sev, colour in SEVERITY_COLOURS.items():
#         col = f"{sev.lower()}_count"
#         if col in df.columns:
#             fig.add_trace(go.Bar(
#                 name=sev,
#                 x=df["accident_hour"],
#                 y=df[col],
#                 marker=dict(color=colour, opacity=0.88,
#                             line=dict(color="#ffffff", width=0.5)),
#                 hovertemplate=f"<b>Hour %{{x}}:00</b><br>{sev}: %{{y:,}}<extra></extra>",
#             ))

#     fig.update_layout(**_base_layout(
#         barmode="stack",
#         title=dict(text="Accidents by Hour of Day",
#                    font=dict(size=15, color=_BLACK), x=0),
#         xaxis=dict(title="Hour (24h)", tickmode="linear", tick0=0, dtick=2,
#                    showgrid=False),
#         yaxis=dict(title="Number of Accidents", gridcolor="#e9ecef"),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#         legend=dict(title=dict(text="Severity", font=dict(color=_BLACK)),
#                     orientation="h", yanchor="bottom", y=1.02,
#                     xanchor="right", x=1),
#     ))
#     return fig


# # ── Accidents by Weekday ───────────────────────────────────────────────────────

# def chart_accidents_by_weekday(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No weekday data available")

#     day_order = ["Monday", "Tuesday", "Wednesday", "Thursday",
#                  "Friday", "Saturday", "Sunday"]
#     if "weekday_name" in df.columns:
#         df = df.copy()
#         df["weekday_name"] = pd.Categorical(
#             df["weekday_name"], categories=day_order, ordered=True
#         )
#         df = df.sort_values("weekday_name")

#     bar_colours = [
#         "#0f3460", "#1a4a7a", "#24608e", "#2e76a2",
#         "#388cb6", "#42a2ca", "#4cb8de"
#     ]

#     fig = go.Figure()
#     fig.add_trace(go.Bar(
#         name="Total Accidents",
#         x=df["weekday_name"],
#         y=df["accident_count"],
#         marker=dict(color=bar_colours, line=dict(color="#ffffff", width=1), opacity=0.90),
#         text=df["accident_count"].apply(lambda v: f"{v:,}"),
#         textposition="outside",
#         textfont=dict(size=11, color=_BLACK),
#         hovertemplate="<b>%{x}</b><br>Total: %{y:,}<extra></extra>",
#     ))
#     if "fatal_count" in df.columns:
#         fig.add_trace(go.Scatter(
#             name="Fatal",
#             x=df["weekday_name"],
#             y=df["fatal_count"],
#             mode="lines+markers",
#             line=dict(color=SEVERITY_COLOURS["Fatal"], width=2.5),
#             marker=dict(size=9, color=SEVERITY_COLOURS["Fatal"],
#                         line=dict(color="#ffffff", width=2)),
#             yaxis="y2",
#             hovertemplate="<b>%{x}</b><br>Fatal: %{y:,}<extra></extra>",
#         ))

#     fig.update_layout(**_base_layout(
#         title=dict(text="Accidents by Day of Week",
#                    font=dict(size=15, color=_BLACK), x=0),
#         xaxis=dict(title="Day of Week", showgrid=False),
#         yaxis=dict(title="Total Accidents", gridcolor="#e9ecef"),
#         yaxis2=dict(title="Fatal Accidents", overlaying="y", side="right",
#                     showgrid=False,
#                     title_font=dict(color=SEVERITY_COLOURS["Fatal"], size=12),
#                     tickfont=dict(color=SEVERITY_COLOURS["Fatal"], size=11)),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#         legend=dict(orientation="h", yanchor="bottom", y=1.02,
#                     xanchor="right", x=1),
#     ))
#     return fig


# # ── Weather vs Severity Heatmap ────────────────────────────────────────────────

# def chart_weather_severity_heatmap(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No weather vs severity data available")

#     pivot = df.pivot_table(
#         index="weather_description",
#         columns="severity_label",
#         values="accident_count",
#         aggfunc="sum",
#         fill_value=0,
#     )
#     col_order = [c for c in ["Slight", "Serious", "Fatal"] if c in pivot.columns]
#     pivot = pivot[col_order]
#     pivot["_total"] = pivot.sum(axis=1)
#     pivot = pivot.nlargest(15, "_total").drop(columns=["_total"])

#     z = pivot.values
#     x = list(pivot.columns)
#     y = list(pivot.index)

#     def _fmt(v):
#         return f"{v/1000:.3g}k" if v >= 1000 else str(int(v))

#     fig = go.Figure(go.Heatmap(
#         z=z,
#         x=x,
#         y=y,
#         colorscale=[
#             [0.0,  "#eaf4fb"],
#             [0.25, "#89c4e1"],
#             [0.5,  "#f4a261"],
#             [0.75, "#e76f51"],
#             [1.0,  "#e63946"],
#         ],
#         colorbar=dict(
#             title=dict(text="Accidents", font=dict(color=_BLACK)),
#             tickfont=dict(color=_BLACK),
#             thickness=14,
#             len=0.8,
#         ),
#         hovertemplate="<b>%{y}</b><br>%{x}: %{z:,}<extra></extra>",
#         showscale=True,
#     ))

#     # Manually place black annotations — the only reliable way
#     annotations = []
#     for i, row in enumerate(z):
#         for j, val in enumerate(row):
#             annotations.append(dict(
#                 x=x[j], y=y[i],
#                 text=_fmt(val),
#                 showarrow=False,
#                 font=dict(size=11, color=_BLACK, family="Segoe UI, sans-serif"),
#                 xref="x", yref="y",
#             ))

#     fig.update_layout(**_base_layout(
#         margin=dict(t=60, b=60, l=220, r=30),
#         xaxis=dict(side="bottom", title="Severity"),
#         yaxis=dict(title="Weather Condition"),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#ffffff",
#         annotations=annotations,
#         title=dict(text="Weather Condition vs Accident Severity",
#                    font=dict(size=15, color=_BLACK), x=0),
#     ))
#     return fig


# # ── Weather vs Severity Stacked Bar ───────────────────────────────────────────

# def chart_weather_severity_stacked_bar(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No weather vs severity data available")

#     pivot = df.pivot_table(
#         index="weather_description",
#         columns="severity_label",
#         values="accident_count",
#         aggfunc="sum",
#         fill_value=0,
#     ).reset_index()
#     pivot["_total"] = pivot[
#         [c for c in pivot.columns if c != "weather_description"]
#     ].sum(axis=1)
#     pivot = pivot.nlargest(12, "_total").drop(columns=["_total"])

#     fig = go.Figure()
#     for sev, colour in SEVERITY_COLOURS.items():
#         if sev in pivot.columns:
#             fig.add_trace(go.Bar(
#                 name=sev,
#                 x=pivot["weather_description"],
#                 y=pivot[sev],
#                 marker=dict(color=colour, opacity=0.90,
#                             line=dict(color="#ffffff", width=0.8)),
#                 hovertemplate=f"<b>%{{x}}</b><br>{sev}: %{{y:,}}<extra></extra>",
#             ))

#     fig.update_layout(**_base_layout(
#         barmode="stack",
#         title=dict(text="Accidents by Weather Condition & Severity",
#                    font=dict(size=15, color=_BLACK), x=0),
#         xaxis=dict(title="Weather Condition", tickangle=-35, showgrid=False),
#         yaxis=dict(title="Number of Accidents", gridcolor="#e9ecef"),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#         legend=dict(title=dict(text="Severity", font=dict(color=_BLACK)),
#                     orientation="h", yanchor="bottom", y=1.02,
#                     xanchor="right", x=1),
#         margin=dict(t=60, b=130, l=10, r=10),
#     ))
#     return fig


# # ── Hotspot Map ────────────────────────────────────────────────────────────────

# def chart_hotspot_map(df: pd.DataFrame) -> go.Figure:
#     if df.empty or "latitude" not in df.columns:
#         return _empty_chart("No location data available")

#     df = df.dropna(subset=["latitude", "longitude"]).copy()
#     if df.empty:
#         return _empty_chart("No valid coordinates in selected data")

#     centre_lat = df["latitude"].mean()
#     centre_lon = df["longitude"].mean()

#     hover_cols = {
#         "latitude": False, "longitude": False,
#         "severity_label": True, "number_of_casualties": True,
#     }
#     for col in ["accident_date", "road_type_name", "weather_description"]:
#         if col in df.columns:
#             hover_cols[col] = True

#     common_kwargs = dict(
#         data_frame=df, lat="latitude", lon="longitude",
#         color="severity_label", color_discrete_map=SEVERITY_COLOURS,
#         hover_data=hover_cols, zoom=5,
#         center={"lat": centre_lat, "lon": centre_lon},
#         opacity=0.75,
#         title="Accident Location Map — Great Britain",
#     )

#     try:
#         fig = px.scatter_map(**common_kwargs, map_style="carto-positron")
#     except AttributeError:
#         fig = px.scatter_mapbox(**common_kwargs, mapbox_style="carto-positron")

#     fig.update_traces(marker=dict(size=5))
#     fig.update_layout(
#         font=_FONT,
#         paper_bgcolor="#ffffff",
#         margin=dict(t=50, b=0, l=0, r=0),
#         height=520,
#         legend=dict(
#             title=dict(text="Severity", font=dict(color=_BLACK, size=12)),
#             font=dict(color=_BLACK),
#             bgcolor="rgba(255,255,255,0.92)",
#             bordercolor="#dee2e6",
#             borderwidth=1,
#             orientation="v",
#         ),
#         title=dict(text="Accident Location Map — Great Britain",
#                    font=dict(size=15, color=_BLACK), x=0),
#     )
#     return fig


# # ── Road Type vs Severity ──────────────────────────────────────────────────────

# def chart_road_type_severity(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No road type data available")

#     pivot = df.pivot_table(
#         index="road_type_name",
#         columns="severity_label",
#         values="accident_count",
#         aggfunc="sum",
#         fill_value=0,
#     ).reset_index()
#     pivot["_total"] = pivot[
#         [c for c in pivot.columns if c not in ("road_type_name",)]
#     ].sum(axis=1)
#     pivot = pivot.sort_values("_total", ascending=False).drop(columns=["_total"])

#     fig = go.Figure()
#     for sev, colour in SEVERITY_COLOURS.items():
#         if sev in pivot.columns:
#             fig.add_trace(go.Bar(
#                 name=sev,
#                 x=pivot["road_type_name"],
#                 y=pivot[sev],
#                 marker=dict(color=colour, opacity=0.90,
#                             line=dict(color="#ffffff", width=1)),
#                 hovertemplate=f"<b>%{{x}}</b><br>{sev}: %{{y:,}}<extra></extra>",
#             ))

#     fig.update_layout(**_base_layout(
#         barmode="group",
#         title=dict(text="Accidents by Road Type & Severity",
#                    font=dict(size=15, color=_BLACK), x=0),
#         xaxis=dict(title="Road Type", tickangle=-25, showgrid=False),
#         yaxis=dict(title="Number of Accidents", gridcolor="#e9ecef"),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#         legend=dict(title=dict(text="Severity", font=dict(color=_BLACK)),
#                     orientation="h", yanchor="bottom", y=1.02,
#                     xanchor="right", x=1),
#         margin=dict(t=60, b=110, l=10, r=10),
#     ))
#     return fig


# # ── Utility ────────────────────────────────────────────────────────────────────

# def _empty_chart(message: str = "No data available") -> go.Figure:
#     fig = go.Figure()
#     fig.add_annotation(
#         text=message, xref="paper", yref="paper",
#         x=0.5, y=0.5, showarrow=False,
#         font=dict(size=15, color="#adb5bd"),
#     )
#     fig.update_layout(
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#         xaxis=dict(visible=False),
#         yaxis=dict(visible=False),
#         margin=dict(t=20, b=20),
#         font=_FONT,
#     )
#     return fig
















# """
# dashboard/charts.py
# ---------------------
# All Plotly chart builders for the Streamlit dashboard.
# All labels, tick text, axis titles, legend text → #000000 (black).
# """

# import pandas as pd
# import plotly.express as px
# import plotly.graph_objects as go

# # ── Colour palette ─────────────────────────────────────────────────────────────
# SEVERITY_COLOURS = {
#     "Fatal":   "#e63946",
#     "Serious": "#f4a261",
#     "Slight":  "#2ec4b6",
# }

# PALETTE = {
#     "navy":       "#0f3460",
#     "steel":      "#457b9d",
#     "teal":       "#2ec4b6",
#     "amber":      "#f4a261",
#     "red":        "#e63946",
#     "light_grey": "#f4f6f9",
#     "mid_grey":   "#dee2e6",
#     "text":       "#000000",
# }

# _CHART_TEMPLATE = "plotly_white"
# _BLACK = "#172033"
# _FONT  = dict(family="Segoe UI, sans-serif", color=_BLACK)

# # Every axis gets these defaults — all text black
# _AXIS  = dict(
#     tickfont=dict(color=_BLACK, size=11),
#     title_font=dict(color=_BLACK, size=12),
#     linecolor="#cbd5e1",
#     zerolinecolor="#cbd5e1",
#     gridcolor="#e2e8f0",
# )


# def _ax(**extra):
#     """Merge extra kwargs on top of _AXIS defaults."""
#     d = dict(**_AXIS)
#     d.update(extra)
#     return d


# def _base_layout(**kwargs):
#     """Base layout with black font everywhere. Per-chart kwargs override."""
#     base = dict(
#         template=_CHART_TEMPLATE,
#         font=_FONT,
#         hoverlabel=dict(bgcolor="#ffffff", bordercolor="#cbd5e1", font=dict(color=_BLACK, family="Segoe UI, sans-serif")),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f9fafb",
#         margin=dict(t=50, b=30, l=10, r=10),
#         xaxis=_ax(),
#         yaxis=_ax(),
#         legend=dict(
#             bgcolor="rgba(255,255,255,0.9)",
#             bordercolor="#dee2e6",
#             borderwidth=1,
#             font=dict(color=_BLACK, size=12),
#         ),
#     )
#     # Merge axis dicts so per-chart settings stack on top of defaults
#     for axis in ("xaxis", "yaxis", "yaxis2"):
#         if axis in kwargs:
#             merged = _ax()
#             merged.update(kwargs.pop(axis))
#             base[axis] = merged
#     if "margin" in kwargs:
#         base["margin"] = kwargs.pop("margin")
#     # Merge legend
#     if "legend" in kwargs:
#         leg = dict(**base["legend"])
#         leg.update(kwargs.pop("legend"))
#         base["legend"] = leg
#     base.update(kwargs)
#     return base


# # ── Severity Distribution ──────────────────────────────────────────────────────

# def chart_severity_donut(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No severity data available")

#     colours = [SEVERITY_COLOURS.get(s, "#adb5bd") for s in df["severity_label"]]
#     fig = go.Figure(go.Pie(
#         labels=df["severity_label"],
#         values=df["accident_count"],
#         hole=0.50,
#         marker=dict(colors=colours, line=dict(color="#ffffff", width=3)),
#         textinfo="label+percent",
#         textfont=dict(size=13, color=_BLACK),
#         hovertemplate=(
#             "<b>%{label}</b><br>"
#             "Accidents: %{value:,}<br>"
#             "Share: %{percent}<extra></extra>"
#         ),
#     ))
#     fig.update_layout(**_base_layout(
#         title=dict(text="Accident Severity Distribution",
#                    font=dict(size=15, color=_BLACK), x=0),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#ffffff",
#         legend=dict(orientation="h", yanchor="bottom", y=-0.15),
#         margin=dict(t=50, b=30, l=10, r=10),
#     ))
#     return fig


# def chart_severity_bar(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No severity data available")

#     colours = [SEVERITY_COLOURS.get(s, "#adb5bd") for s in df["severity_label"]]
#     fig = go.Figure(go.Bar(
#         x=df["severity_label"],
#         y=df["accident_count"],
#         marker=dict(color=colours, line=dict(color="#ffffff", width=1.5), opacity=0.92),
#         text=df["accident_count"].apply(lambda v: f"{v:,}"),
#         textposition="outside",
#         textfont=dict(size=12, color=_BLACK),
#         hovertemplate="<b>%{x}</b><br>Count: %{y:,}<extra></extra>",
#     ))
#     fig.update_layout(**_base_layout(
#         title=dict(text="Accidents by Severity",
#                    font=dict(size=15, color=_BLACK), x=0),
#         xaxis=dict(title="Severity", showgrid=False),
#         yaxis=dict(title="Number of Accidents", gridcolor="#e9ecef"),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#     ))
#     return fig


# # ── Accidents by Hour ──────────────────────────────────────────────────────────

# def chart_accidents_by_hour(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No hourly data available")

#     fig = go.Figure()
#     for sev, colour in SEVERITY_COLOURS.items():
#         col = f"{sev.lower()}_count"
#         if col in df.columns:
#             fig.add_trace(go.Bar(
#                 name=sev,
#                 x=df["accident_hour"],
#                 y=df[col],
#                 marker=dict(color=colour, opacity=0.88,
#                             line=dict(color="#ffffff", width=0.5)),
#                 hovertemplate=f"<b>Hour %{{x}}:00</b><br>{sev}: %{{y:,}}<extra></extra>",
#             ))

#     fig.update_layout(**_base_layout(
#         barmode="stack",
#         title=dict(text="Accidents by Hour of Day",
#                    font=dict(size=15, color=_BLACK), x=0),
#         xaxis=dict(title="Hour (24h)", tickmode="linear", tick0=0, dtick=2,
#                    showgrid=False),
#         yaxis=dict(title="Number of Accidents", gridcolor="#e9ecef"),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#         legend=dict(title=dict(text="Severity", font=dict(color=_BLACK)),
#                     orientation="h", yanchor="bottom", y=1.02,
#                     xanchor="right", x=1),
#     ))
#     return fig


# # ── Accidents by Weekday ───────────────────────────────────────────────────────

# def chart_accidents_by_weekday(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No weekday data available")

#     day_order = ["Monday", "Tuesday", "Wednesday", "Thursday",
#                  "Friday", "Saturday", "Sunday"]
#     if "weekday_name" in df.columns:
#         df = df.copy()
#         df["weekday_name"] = pd.Categorical(
#             df["weekday_name"], categories=day_order, ordered=True
#         )
#         df = df.sort_values("weekday_name")

#     bar_colours = [
#         "#0f3460", "#1a4a7a", "#24608e", "#2e76a2",
#         "#388cb6", "#42a2ca", "#4cb8de"
#     ]

#     fig = go.Figure()
#     fig.add_trace(go.Bar(
#         name="Total Accidents",
#         x=df["weekday_name"],
#         y=df["accident_count"],
#         marker=dict(color=bar_colours, line=dict(color="#ffffff", width=1), opacity=0.90),
#         text=df["accident_count"].apply(lambda v: f"{v:,}"),
#         textposition="outside",
#         textfont=dict(size=11, color=_BLACK),
#         hovertemplate="<b>%{x}</b><br>Total: %{y:,}<extra></extra>",
#     ))
#     if "fatal_count" in df.columns:
#         fig.add_trace(go.Scatter(
#             name="Fatal",
#             x=df["weekday_name"],
#             y=df["fatal_count"],
#             mode="lines+markers",
#             line=dict(color=SEVERITY_COLOURS["Fatal"], width=2.5),
#             marker=dict(size=9, color=SEVERITY_COLOURS["Fatal"],
#                         line=dict(color="#ffffff", width=2)),
#             yaxis="y2",
#             hovertemplate="<b>%{x}</b><br>Fatal: %{y:,}<extra></extra>",
#         ))

#     fig.update_layout(**_base_layout(
#         title=dict(text="Accidents by Day of Week",
#                    font=dict(size=15, color=_BLACK), x=0),
#         xaxis=dict(title="Day of Week", showgrid=False),
#         yaxis=dict(title="Total Accidents", gridcolor="#e9ecef"),
#         yaxis2=dict(title="Fatal Accidents", overlaying="y", side="right",
#                     showgrid=False,
#                     title_font=dict(color=_BLACK, size=12),
#                     tickfont=dict(color=_BLACK, size=11)),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#         legend=dict(orientation="h", yanchor="bottom", y=1.02,
#                     xanchor="right", x=1),
#     ))
#     return fig


# # ── Weather vs Severity Heatmap ────────────────────────────────────────────────

# def chart_weather_severity_heatmap(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No weather vs severity data available")

#     pivot = df.pivot_table(
#         index="weather_description",
#         columns="severity_label",
#         values="accident_count",
#         aggfunc="sum",
#         fill_value=0,
#     )
#     col_order = [c for c in ["Slight", "Serious", "Fatal"] if c in pivot.columns]
#     pivot = pivot[col_order]
#     pivot["_total"] = pivot.sum(axis=1)
#     pivot = pivot.nlargest(15, "_total").drop(columns=["_total"])

#     z = pivot.values
#     x = list(pivot.columns)
#     y = list(pivot.index)

#     def _fmt(v):
#         return f"{v/1000:.3g}k" if v >= 1000 else str(int(v))

#     fig = go.Figure(go.Heatmap(
#         z=z,
#         x=x,
#         y=y,
#         colorscale=[
#             [0.0,  "#eaf4fb"],
#             [0.25, "#89c4e1"],
#             [0.5,  "#f4a261"],
#             [0.75, "#e76f51"],
#             [1.0,  "#e63946"],
#         ],
#         colorbar=dict(
#             title=dict(text="Accidents", font=dict(color=_BLACK)),
#             tickfont=dict(color=_BLACK),
#             thickness=14,
#             len=0.8,
#         ),
#         hovertemplate="<b>%{y}</b><br>%{x}: %{z:,}<extra></extra>",
#         showscale=True,
#     ))

#     # Manually place black annotations — the only reliable way
#     annotations = []
#     for i, row in enumerate(z):
#         for j, val in enumerate(row):
#             annotations.append(dict(
#                 x=x[j], y=y[i],
#                 text=_fmt(val),
#                 showarrow=False,
#                 font=dict(size=11, color=_BLACK, family="Segoe UI, sans-serif"),
#                 xref="x", yref="y",
#             ))

#     fig.update_layout(**_base_layout(
#         margin=dict(t=60, b=60, l=220, r=30),
#         xaxis=dict(side="bottom", title="Severity"),
#         yaxis=dict(title="Weather Condition"),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#ffffff",
#         annotations=annotations,
#         title=dict(text="Weather Condition vs Accident Severity",
#                    font=dict(size=15, color=_BLACK), x=0),
#     ))
#     return fig


# # ── Weather vs Severity Stacked Bar ───────────────────────────────────────────

# def chart_weather_severity_stacked_bar(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No weather vs severity data available")

#     pivot = df.pivot_table(
#         index="weather_description",
#         columns="severity_label",
#         values="accident_count",
#         aggfunc="sum",
#         fill_value=0,
#     ).reset_index()
#     pivot["_total"] = pivot[
#         [c for c in pivot.columns if c != "weather_description"]
#     ].sum(axis=1)
#     pivot = pivot.nlargest(12, "_total").drop(columns=["_total"])

#     fig = go.Figure()
#     for sev, colour in SEVERITY_COLOURS.items():
#         if sev in pivot.columns:
#             fig.add_trace(go.Bar(
#                 name=sev,
#                 x=pivot["weather_description"],
#                 y=pivot[sev],
#                 marker=dict(color=colour, opacity=0.90,
#                             line=dict(color="#ffffff", width=0.8)),
#                 hovertemplate=f"<b>%{{x}}</b><br>{sev}: %{{y:,}}<extra></extra>",
#             ))

#     fig.update_layout(**_base_layout(
#         barmode="stack",
#         title=dict(text="Accidents by Weather Condition & Severity",
#                    font=dict(size=15, color=_BLACK), x=0),
#         xaxis=dict(title="Weather Condition", tickangle=-35, showgrid=False),
#         yaxis=dict(title="Number of Accidents", gridcolor="#e9ecef"),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#         legend=dict(title=dict(text="Severity", font=dict(color=_BLACK)),
#                     orientation="h", yanchor="bottom", y=1.02,
#                     xanchor="right", x=1),
#         margin=dict(t=60, b=130, l=10, r=10),
#     ))
#     return fig


# # ── Hotspot Map ────────────────────────────────────────────────────────────────

# def chart_hotspot_map(df: pd.DataFrame) -> go.Figure:
#     if df.empty or "latitude" not in df.columns:
#         return _empty_chart("No location data available")

#     df = df.dropna(subset=["latitude", "longitude"]).copy()
#     if df.empty:
#         return _empty_chart("No valid coordinates in selected data")

#     centre_lat = df["latitude"].mean()
#     centre_lon = df["longitude"].mean()

#     hover_cols = {
#         "latitude": False, "longitude": False,
#         "severity_label": True, "number_of_casualties": True,
#     }
#     for col in ["accident_date", "road_type_name", "weather_description"]:
#         if col in df.columns:
#             hover_cols[col] = True

#     common_kwargs = dict(
#         data_frame=df, lat="latitude", lon="longitude",
#         color="severity_label", color_discrete_map=SEVERITY_COLOURS,
#         hover_data=hover_cols, zoom=5,
#         center={"lat": centre_lat, "lon": centre_lon},
#         opacity=0.75,
#         title="Accident Location Map — Great Britain",
#     )

#     try:
#         fig = px.scatter_map(**common_kwargs, map_style="carto-positron")
#     except AttributeError:
#         fig = px.scatter_mapbox(**common_kwargs, mapbox_style="carto-positron")

#     fig.update_traces(marker=dict(size=5))
#     fig.update_layout(
#         font=_FONT,
#         paper_bgcolor="#ffffff",
#         margin=dict(t=50, b=0, l=0, r=0),
#         height=520,
#         legend=dict(
#             title=dict(text="Severity", font=dict(color=_BLACK, size=12)),
#             font=dict(color=_BLACK),
#             bgcolor="rgba(255,255,255,0.92)",
#             bordercolor="#dee2e6",
#             borderwidth=1,
#             orientation="v",
#         ),
#         title=dict(text="Accident Location Map — Great Britain",
#                    font=dict(size=15, color=_BLACK), x=0),
#     )
#     return fig


# # ── Road Type vs Severity ──────────────────────────────────────────────────────

# def chart_road_type_severity(df: pd.DataFrame) -> go.Figure:
#     if df.empty:
#         return _empty_chart("No road type data available")

#     pivot = df.pivot_table(
#         index="road_type_name",
#         columns="severity_label",
#         values="accident_count",
#         aggfunc="sum",
#         fill_value=0,
#     ).reset_index()
#     pivot["_total"] = pivot[
#         [c for c in pivot.columns if c not in ("road_type_name",)]
#     ].sum(axis=1)
#     pivot = pivot.sort_values("_total", ascending=False).drop(columns=["_total"])

#     fig = go.Figure()
#     for sev, colour in SEVERITY_COLOURS.items():
#         if sev in pivot.columns:
#             fig.add_trace(go.Bar(
#                 name=sev,
#                 x=pivot["road_type_name"],
#                 y=pivot[sev],
#                 marker=dict(color=colour, opacity=0.90,
#                             line=dict(color="#ffffff", width=1)),
#                 hovertemplate=f"<b>%{{x}}</b><br>{sev}: %{{y:,}}<extra></extra>",
#             ))

#     fig.update_layout(**_base_layout(
#         barmode="group",
#         title=dict(text="Accidents by Road Type & Severity",
#                    font=dict(size=15, color=_BLACK), x=0),
#         xaxis=dict(title="Road Type", tickangle=-25, showgrid=False),
#         yaxis=dict(title="Number of Accidents", gridcolor="#e9ecef"),
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#         legend=dict(title=dict(text="Severity", font=dict(color=_BLACK)),
#                     orientation="h", yanchor="bottom", y=1.02,
#                     xanchor="right", x=1),
#         margin=dict(t=60, b=110, l=10, r=10),
#     ))
#     return fig


# # ── Utility ────────────────────────────────────────────────────────────────────

# def _empty_chart(message: str = "No data available") -> go.Figure:
#     fig = go.Figure()
#     fig.add_annotation(
#         text=message, xref="paper", yref="paper",
#         x=0.5, y=0.5, showarrow=False,
#         font=dict(size=15, color=_BLACK),
#     )
#     fig.update_layout(
#         paper_bgcolor="#ffffff",
#         plot_bgcolor="#f8f9fa",
#         xaxis=dict(visible=False),
#         yaxis=dict(visible=False),
#         margin=dict(t=20, b=20),
#         font=_FONT,
#     )
#     return fig






























"""
dashboard/charts.py
---------------------
All Plotly chart builders for the Streamlit dashboard.
All labels, tick text, axis titles, legend text → #000000 (black).
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── Colour palette ─────────────────────────────────────────────────────────────
SEVERITY_COLOURS = {
    "Fatal":   "#e63946",
    "Serious": "#f4a261",
    "Slight":  "#2ec4b6",
}

PALETTE = {
    "navy":       "#0f3460",
    "steel":      "#457b9d",
    "teal":       "#2ec4b6",
    "amber":      "#f4a261",
    "red":        "#e63946",
    "light_grey": "#f4f6f9",
    "mid_grey":   "#dee2e6",
    "text":       "#000000",
}

_CHART_TEMPLATE = "plotly_white"
_BLACK = "#172033"
_FONT  = dict(family="Segoe UI, sans-serif", color=_BLACK)

# Every axis gets these defaults — all text black
_AXIS  = dict(
    tickfont=dict(color=_BLACK, size=11),
    title_font=dict(color=_BLACK, size=12),
    linecolor="#cbd5e1",
    zerolinecolor="#cbd5e1",
    gridcolor="#e2e8f0",
    title=dict(font=dict(color=_BLACK, size=12)),
)


def _ax(**extra):
    """Merge extra kwargs on top of _AXIS defaults."""
    d = dict(**_AXIS)
    d.update(extra)
    return d


def _base_layout(**kwargs):
    """Base layout with black font everywhere. Per-chart kwargs override."""
    base = dict(
        template=_CHART_TEMPLATE,
        font=_FONT,
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#cbd5e1", font=dict(color=_BLACK, family="Segoe UI, sans-serif")),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f9fafb",
        margin=dict(t=50, b=30, l=10, r=10),
        xaxis=_ax(),
        yaxis=_ax(),
        legend=dict(
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#dee2e6",
            borderwidth=1,
            font=dict(color=_BLACK, size=12),
        ),
    )
    # Merge axis dicts so per-chart settings stack on top of defaults
    for axis in ("xaxis", "yaxis", "yaxis2"):
        if axis in kwargs:
            merged = _ax()
            merged.update(kwargs.pop(axis))
            base[axis] = merged
    if "margin" in kwargs:
        base["margin"] = kwargs.pop("margin")
    # Merge legend
    if "legend" in kwargs:
        leg = dict(**base["legend"])
        leg.update(kwargs.pop("legend"))
        base["legend"] = leg
    base.update(kwargs)
    return base


# ── Severity Distribution ──────────────────────────────────────────────────────

def chart_severity_donut(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_chart("No severity data available")

    colours = [SEVERITY_COLOURS.get(s, "#adb5bd") for s in df["severity_label"]]
    fig = go.Figure(go.Pie(
        labels=df["severity_label"],
        values=df["accident_count"],
        hole=0.50,
        marker=dict(colors=colours, line=dict(color="#ffffff", width=3)),
        textinfo="label+percent",
        textfont=dict(size=13, color=_BLACK),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Accidents: %{value:,}<br>"
            "Share: %{percent}<extra></extra>"
        ),
    ))
    fig.update_layout(**_base_layout(
        title=dict(text="Accident Severity Distribution",
                   font=dict(size=15, color=_BLACK), x=0),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend=dict(orientation="h", yanchor="bottom", y=-0.15),
        margin=dict(t=50, b=30, l=10, r=10),
    ))
    return fig


def chart_severity_bar(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_chart("No severity data available")

    colours = [SEVERITY_COLOURS.get(s, "#adb5bd") for s in df["severity_label"]]
    fig = go.Figure(go.Bar(
        x=df["severity_label"],
        y=df["accident_count"],
        marker=dict(color=colours, line=dict(color="#ffffff", width=1.5), opacity=0.92),
        text=df["accident_count"].apply(lambda v: f"{v:,}"),
        textposition="outside",
        textfont=dict(size=12, color=_BLACK),
        hovertemplate="<b>%{x}</b><br>Count: %{y:,}<extra></extra>",
    ))
    fig.update_layout(**_base_layout(
        title=dict(text="Accidents by Severity",
                   font=dict(size=15, color=_BLACK), x=0),
        xaxis=dict(title="Severity", showgrid=False),
        yaxis=dict(title="Number of Accidents", gridcolor="#e9ecef"),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8f9fa",
    ))
    return fig


# ── Accidents by Hour ──────────────────────────────────────────────────────────

def chart_accidents_by_hour(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_chart("No hourly data available")

    fig = go.Figure()
    for sev, colour in SEVERITY_COLOURS.items():
        col = f"{sev.lower()}_count"
        if col in df.columns:
            fig.add_trace(go.Bar(
                name=sev,
                x=df["accident_hour"],
                y=df[col],
                marker=dict(color=colour, opacity=0.88,
                            line=dict(color="#ffffff", width=0.5)),
                hovertemplate=f"<b>Hour %{{x}}:00</b><br>{sev}: %{{y:,}}<extra></extra>",
            ))

    fig.update_layout(**_base_layout(
    barmode="stack",
    title=dict(
        text="Accidents by Hour of Day",
        font=dict(size=15, color=_BLACK),
        x=0,
    ),
    xaxis=dict(
        title=dict(
            text="Hour (24h)",
            font=dict(color=_BLACK, size=12),
        ),
        tickfont=dict(color=_BLACK, size=11),
        tickmode="linear",
        tick0=0,
        dtick=2,
        showgrid=False,
    ),
    yaxis=dict(
        title=dict(
            text="Number of Accidents",
            font=dict(color=_BLACK, size=12),
        ),
        tickfont=dict(color=_BLACK, size=11),
        gridcolor="#e9ecef",
    ),
    paper_bgcolor="#ffffff",
    plot_bgcolor="#f8f9fa",
    legend=dict(
        title=dict(text="Severity", font=dict(color=_BLACK)),
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
    ),
    ))
    return fig


# ── Accidents by Weekday ───────────────────────────────────────────────────────

def chart_accidents_by_weekday(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_chart("No weekday data available")

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"]
    if "weekday_name" in df.columns:
        df = df.copy()
        df["weekday_name"] = pd.Categorical(
            df["weekday_name"], categories=day_order, ordered=True
        )
        df = df.sort_values("weekday_name")

    bar_colours = [
        "#0f3460", "#1a4a7a", "#24608e", "#2e76a2",
        "#388cb6", "#42a2ca", "#4cb8de"
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Total Accidents",
        x=df["weekday_name"],
        y=df["accident_count"],
        marker=dict(color=bar_colours, line=dict(color="#ffffff", width=1), opacity=0.90),
        text=df["accident_count"].apply(lambda v: f"{v:,}"),
        textposition="outside",
        textfont=dict(size=11, color=_BLACK),
        hovertemplate="<b>%{x}</b><br>Total: %{y:,}<extra></extra>",
    ))
    if "fatal_count" in df.columns:
        fig.add_trace(go.Scatter(
            name="Fatal",
            x=df["weekday_name"],
            y=df["fatal_count"],
            mode="lines+markers",
            line=dict(color=SEVERITY_COLOURS["Fatal"], width=2.5),
            marker=dict(size=9, color=SEVERITY_COLOURS["Fatal"],
                        line=dict(color="#ffffff", width=2)),
            yaxis="y2",
            hovertemplate="<b>%{x}</b><br>Fatal: %{y:,}<extra></extra>",
        ))

    fig.update_layout(**_base_layout(
    title=dict(
        text="Accidents by Day of Week",
        font=dict(size=15, color=_BLACK),
        x=0,
    ),
    xaxis=dict(
        title=dict(
            text="Day of Week",
            font=dict(color=_BLACK, size=12),
        ),
        tickfont=dict(color=_BLACK, size=11),
        showgrid=False,
    ),
    yaxis=dict(
        title=dict(
            text="Total Accidents",
            font=dict(color=_BLACK, size=12),
        ),
        tickfont=dict(color=_BLACK, size=11),
        gridcolor="#e9ecef",
    ),
    yaxis2=dict(
        title=dict(
            text="Fatal Accidents",
            font=dict(color=_BLACK, size=12),
        ),
        overlaying="y",
        side="right",
        showgrid=False,
        tickfont=dict(color=_BLACK, size=11),
    ),
    paper_bgcolor="#ffffff",
    plot_bgcolor="#f8f9fa",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
    ),
    ))
    return fig


# ── Weather vs Severity Heatmap ────────────────────────────────────────────────

def chart_weather_severity_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_chart("No weather vs severity data available")

    pivot = df.pivot_table(
        index="weather_description",
        columns="severity_label",
        values="accident_count",
        aggfunc="sum",
        fill_value=0,
    )
    col_order = [c for c in ["Slight", "Serious", "Fatal"] if c in pivot.columns]
    pivot = pivot[col_order]
    pivot["_total"] = pivot.sum(axis=1)
    pivot = pivot.nlargest(15, "_total").drop(columns=["_total"])

    z = pivot.values
    x = list(pivot.columns)
    y = list(pivot.index)

    def _fmt(v):
        return f"{v/1000:.3g}k" if v >= 1000 else str(int(v))

    fig = go.Figure(go.Heatmap(
        z=z,
        x=x,
        y=y,
        colorscale=[
            [0.0,  "#eaf4fb"],
            [0.25, "#89c4e1"],
            [0.5,  "#f4a261"],
            [0.75, "#e76f51"],
            [1.0,  "#e63946"],
        ],
        colorbar=dict(
            title=dict(text="Accidents", font=dict(color=_BLACK)),
            tickfont=dict(color=_BLACK),
            thickness=14,
            len=0.8,
        ),
        hovertemplate="<b>%{y}</b><br>%{x}: %{z:,}<extra></extra>",
        showscale=True,
    ))

    # Manually place black annotations — the only reliable way
    annotations = []
    for i, row in enumerate(z):
        for j, val in enumerate(row):
            annotations.append(dict(
                x=x[j], y=y[i],
                text=_fmt(val),
                showarrow=False,
                font=dict(size=11, color=_BLACK, family="Segoe UI, sans-serif"),
                xref="x", yref="y",
            ))

    fig.update_layout(**_base_layout(
    margin=dict(t=60, b=60, l=220, r=30),
    xaxis=dict(
        side="bottom",
        title=dict(
            text="Severity",
            font=dict(color="#172033", size=12),
        ),
        tickfont=dict(color="#172033", size=11),
    ),
    yaxis=dict(
        title=dict(
            text="Weather Condition",
            font=dict(color="#172033", size=12),
        ),
        tickfont=dict(color="#172033", size=11),
    ),
    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",
    annotations=annotations,
    title=dict(
        text="Weather Condition vs Accident Severity",
        font=dict(size=15, color=_BLACK),
        x=0,
    ),
    ))
    return fig


# ── Weather vs Severity Stacked Bar ───────────────────────────────────────────

def chart_weather_severity_stacked_bar(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_chart("No weather vs severity data available")

    pivot = df.pivot_table(
        index="weather_description",
        columns="severity_label",
        values="accident_count",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    pivot["_total"] = pivot[
        [c for c in pivot.columns if c != "weather_description"]
    ].sum(axis=1)
    pivot = pivot.nlargest(12, "_total").drop(columns=["_total"])

    fig = go.Figure()
    for sev, colour in SEVERITY_COLOURS.items():
        if sev in pivot.columns:
            fig.add_trace(go.Bar(
                name=sev,
                x=pivot["weather_description"],
                y=pivot[sev],
                marker=dict(color=colour, opacity=0.90,
                            line=dict(color="#ffffff", width=0.8)),
                hovertemplate=f"<b>%{{x}}</b><br>{sev}: %{{y:,}}<extra></extra>",
            ))

    fig.update_layout(**_base_layout(
        barmode="stack",
        title=dict(text="Accidents by Weather Condition & Severity",
                   font=dict(size=15, color=_BLACK), x=0),
        xaxis=dict(title="Weather Condition", tickangle=-35, showgrid=False),
        yaxis=dict(title="Number of Accidents", gridcolor="#e9ecef"),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8f9fa",
        legend=dict(title=dict(text="Severity", font=dict(color=_BLACK)),
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        margin=dict(t=60, b=130, l=10, r=10),
    ))
    return fig


# ── Hotspot Map ────────────────────────────────────────────────────────────────

def chart_hotspot_map(df: pd.DataFrame) -> go.Figure:
    if df.empty or "latitude" not in df.columns:
        return _empty_chart("No location data available")

    df = df.dropna(subset=["latitude", "longitude"]).copy()
    if df.empty:
        return _empty_chart("No valid coordinates in selected data")

    centre_lat = df["latitude"].mean()
    centre_lon = df["longitude"].mean()

    hover_cols = {
        "latitude": False, "longitude": False,
        "severity_label": True, "number_of_casualties": True,
    }
    for col in ["accident_date", "road_type_name", "weather_description"]:
        if col in df.columns:
            hover_cols[col] = True

    common_kwargs = dict(
        data_frame=df, lat="latitude", lon="longitude",
        color="severity_label", color_discrete_map=SEVERITY_COLOURS,
        hover_data=hover_cols, zoom=5,
        center={"lat": centre_lat, "lon": centre_lon},
        opacity=0.75,
        title="Accident Location Map — Great Britain",
    )

    try:
        fig = px.scatter_map(**common_kwargs, map_style="carto-positron")
    except AttributeError:
        fig = px.scatter_mapbox(**common_kwargs, mapbox_style="carto-positron")

    fig.update_traces(marker=dict(size=5))
    fig.update_layout(
        font=_FONT,
        paper_bgcolor="#ffffff",
        margin=dict(t=50, b=0, l=0, r=0),
        height=520,
        legend=dict(
            title=dict(text="Severity", font=dict(color=_BLACK, size=12)),
            font=dict(color=_BLACK),
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#dee2e6",
            borderwidth=1,
            orientation="v",
        ),
        title=dict(text="Accident Location Map — Great Britain",
                   font=dict(size=15, color=_BLACK), x=0),
    )
    return fig


# ── Road Type vs Severity ──────────────────────────────────────────────────────

def chart_road_type_severity(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_chart("No road type data available")

    pivot = df.pivot_table(
        index="road_type_name",
        columns="severity_label",
        values="accident_count",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    pivot["_total"] = pivot[
        [c for c in pivot.columns if c not in ("road_type_name",)]
    ].sum(axis=1)
    pivot = pivot.sort_values("_total", ascending=False).drop(columns=["_total"])

    fig = go.Figure()
    for sev, colour in SEVERITY_COLOURS.items():
        if sev in pivot.columns:
            fig.add_trace(go.Bar(
                name=sev,
                x=pivot["road_type_name"],
                y=pivot[sev],
                marker=dict(color=colour, opacity=0.90,
                            line=dict(color="#ffffff", width=1)),
                hovertemplate=f"<b>%{{x}}</b><br>{sev}: %{{y:,}}<extra></extra>",
            ))

    fig.update_layout(**_base_layout(
    barmode="group",
    title=dict(
        text="Accidents by Road Type & Severity",
        font=dict(size=15, color=_BLACK),
        x=0,
    ),
    xaxis=dict(
        title=dict(
            text="Road Type",
            font=dict(color=_BLACK, size=12),
        ),
        tickfont=dict(color=_BLACK, size=11),
        tickangle=-25,
        showgrid=False,
    ),
    yaxis=dict(
        title=dict(
            text="Number of Accidents",
            font=dict(color=_BLACK, size=12),
        ),
        tickfont=dict(color=_BLACK, size=11),
        gridcolor="#e9ecef",
    ),
    paper_bgcolor="#ffffff",
    plot_bgcolor="#f8f9fa",
    legend=dict(
        title=dict(text="Severity", font=dict(color=_BLACK)),
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
    ),
    margin=dict(t=60, b=110, l=10, r=10),
    ))
    return fig

# ── Utility ────────────────────────────────────────────────────────────────────

def _empty_chart(message: str = "No data available") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=15, color=_BLACK),
    )
    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8f9fa",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        margin=dict(t=20, b=20),
        font=_FONT,
    )
    return fig
