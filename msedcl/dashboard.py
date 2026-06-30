import os
import calendar
import pandas as pd
from flask import Flask, render_template
import plotly.graph_objects as go
from datetime import datetime

CSV_FILE = r"C:\Users\TPSS\Desktop\CODING\Python\power_log.csv"

print("Dashboard running from:", os.getcwd())
print("Looking for CSV at:", os.path.abspath(CSV_FILE))
print("CSV exists:", os.path.exists(CSV_FILE))

app = Flask(__name__)


def empty_month_df(year, month):
    days = calendar.monthrange(year, month)[1]

    return pd.DataFrame({
        "full_date": [f"{year}-{month:02d}-{day:02d}" for day in range(1, days + 1)],
        "date": [str(day) for day in range(1, days + 1)],
        "outage_count": [0] * days,
        "total_minutes": [0] * days
    })


def make_month_graph(daily, title, div_id):
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=daily["date"],
        y=daily["outage_count"],
        name="Number of outages"
    ))

    fig.add_trace(go.Bar(
        x=daily["date"],
        y=daily["total_minutes"],
        name="Total outage time (minutes)"
    ))

    fig.update_layout(
        title={
            "text": f"<b>{title}</b>",
            "font": {
                "size": 20
            }
        },

        barmode="stack",

        xaxis=dict(title="Day", type="category"),

        yaxis=dict(title="Value"),

        legend=dict(
            title="Legend",
            orientation="h",
            yanchor="bottom",
            y=1.16,
            xanchor="center",
            x=0.5
        ),

        annotations=[
            dict(
                text="<i>Click or hover on the bars to get exact numbers.<br>Detailed logs are below the graph.</i>",
                x=0.5,
                y=1.15,
                xref="paper",
                yref="paper",
                showarrow=False,
                align="center",
                font=dict(
                    size=12,
                    color="#666666"
                )
            )
        ],

        margin=dict(
            t=160,
            l=60,
            r=30,
            b=60
        ),

        hovermode="x unified",

        height=500
    )

    return fig.to_html(
        full_html=False,
        div_id=div_id,
        config={
            "displaylogo": False,
            "toImageButtonOptions": {
                "format": "png",
                "filename": div_id,
                "height": 600,
                "width": 1100,
                "scale": 2
            }
        }
    )


def read_csv_safely():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame(columns=["Date", "Time", "Event"])

    if os.path.getsize(CSV_FILE) == 0:
        return pd.DataFrame(columns=["Date", "Time", "Event"])

    try:
        df = pd.read_csv(CSV_FILE)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=["Date", "Time", "Event"])

    if df.empty:
        return pd.DataFrame(columns=["Date", "Time", "Event"])

    if "Date" not in df.columns or "Time" not in df.columns or "Event" not in df.columns:
        df = pd.read_csv(CSV_FILE, names=["Date", "Time", "Event"])

    return df


def process_data():
    now = datetime.now()

    current_year = now.year
    current_month = now.month

    if current_month == 1:
        previous_year = current_year - 1
        previous_month = 12
    else:
        previous_year = current_year
        previous_month = current_month - 1

    current_daily = empty_month_df(current_year, current_month)
    previous_daily = empty_month_df(previous_year, previous_month)

    outages = []

    df = read_csv_safely()

    if not df.empty:
        df["DateTime"] = pd.to_datetime(
            df["Date"].astype(str) + " " + df["Time"].astype(str),
            errors="coerce"
        )

        df = df.dropna(subset=["DateTime"])
        df = df.sort_values("DateTime")

        start_time = None

        for _, row in df.iterrows():
            event = str(row["Event"]).strip()

            if event == "Power Lost":
                start_time = row["DateTime"]

            elif event == "Power Restored" and start_time is not None:
                end_time = row["DateTime"]
                duration_minutes = (end_time - start_time).total_seconds() / 60

                if duration_minutes >= 0.0833:
                    outages.append({
                        "full_date": start_time.strftime("%Y-%m-%d"),
                        "date": str(start_time.date()),
                        "start": start_time,
                        "end": end_time,
                        "duration_minutes": duration_minutes
                    })

                start_time = None

    if outages:
        outage_df = pd.DataFrame(outages)

        real_daily = outage_df.groupby("full_date").agg(
            outage_count=("duration_minutes", "count"),
            total_minutes=("duration_minutes", "sum")
        ).reset_index()

        real_daily["total_minutes"] = real_daily["total_minutes"].round(2)

        current_daily = current_daily.drop(
            columns=["outage_count", "total_minutes"]
        ).merge(
            real_daily,
            on="full_date",
            how="left"
        ).fillna(0)

        previous_daily = previous_daily.drop(
            columns=["outage_count", "total_minutes"]
        ).merge(
            real_daily,
            on="full_date",
            how="left"
        ).fillna(0)

    current_graph = make_month_graph(
        current_daily,
        f"Current Month - {calendar.month_name[current_month]} {current_year}",
        "current-month-graph"
    )

    previous_graph = make_month_graph(
        previous_daily,
        f"Previous Month - {calendar.month_name[previous_month]} {previous_year}",
        "previous-month-graph"
    )

    outages = sorted(
        outages,
        key=lambda x: x["start"],
        reverse=True
    )

    return current_graph, previous_graph, outages


@app.route("/")
def home():
    current_graph, previous_graph, outages = process_data()

    return render_template(
        "index.html",
        current_graph=current_graph,
        previous_graph=previous_graph,
        outages=outages
    )


if __name__ == "__main__":
    app.run(debug=True)