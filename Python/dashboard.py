import os
import time
import subprocess
import shutil
from functools import wraps 
from pathlib import Path
import calendar
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash
import plotly.graph_objects as go
from datetime import datetime

CSV_FILE = Path(__file__).resolve().parent / "power_log.csv"

print("Dashboard running from:", os.getcwd())
print("Looking for CSV at:", os.path.abspath(CSV_FILE))
print("CSV exists:", os.path.exists(CSV_FILE))

app = Flask(__name__)
app.secret_key = "293923d5-1d31-46a0-860a-2d36dbe55d2"

ADMIN_PASSWORD = "lushh1wb"


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin"))
        return func(*args, **kwargs)
    return wrapper

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
@app.route("/admin", methods=["GET"])
def admin():
    if not session.get("admin_logged_in"):
        return render_template("admin.html", logged_in=False)

    csv_text = ""

    if CSV_FILE.exists():
        try:
            df = pd.read_csv(CSV_FILE)

            if "Date" not in df.columns or "Time" not in df.columns or "Event" not in df.columns:
                df = pd.read_csv(CSV_FILE, names=["Date", "Time", "Event"])

            df["DateTime"] = pd.to_datetime(
                df["Date"].astype(str) + " " + df["Time"].astype(str),
                errors="coerce"
            )

            df = df.sort_values("DateTime", ascending=False)

            df = df.drop(columns=["DateTime"])

            csv_text = df.to_csv(index=False)

        except Exception:
            csv_text = CSV_FILE.read_text(encoding="utf-8", errors="replace")
    else:
        csv_text = ""

    return render_template(
        "admin.html",
        logged_in=True,
        csv_text=csv_text
    )


@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("password", "")

    if password == ADMIN_PASSWORD:
        session["admin_logged_in"] = True
        return redirect(url_for("admin"))

    flash("Wrong password.")
    return redirect(url_for("admin"))


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin"))


@app.route("/admin/save-csv", methods=["POST"])
@admin_required
def admin_save_csv():
    csv_text = request.form.get("csv_text", "")

    if not csv_text.strip():
        flash("CSV was empty, so it was not saved.")
        return redirect(url_for("admin"))

    try:
        if CSV_FILE.exists():
            backup_file = CSV_FILE.with_name("power_log_backup.csv")
            shutil.copy(CSV_FILE, backup_file)

        CSV_FILE.write_text(
            csv_text.strip() + "\n",
            encoding="utf-8"
        )

        flash("CSV file saved. Backup created as power_log_backup.csv.")

    except Exception as e:
        flash(f"CSV save failed. Original file was not changed. Error: {e}")

    return redirect(url_for("admin"))


@app.route("/admin/wifi-scan", methods=["POST"])
@admin_required
def admin_wifi_scan():
    try:
        subprocess.run(
            ["sudo", "nmcli", "dev", "wifi", "rescan", "ifname", "wlan0"],
            capture_output=True,
            text=True,
            timeout=20
        )

        time.sleep(3)

        result = subprocess.run(
            ["nmcli", "-f", "SSID,SIGNAL,SECURITY,CHAN", "dev", "wifi", "list", "ifname", "wlan0"],
            capture_output=True,
            text=True,
            timeout=20
        )

        if result.stdout.strip():
            flash(result.stdout)
        else:
            flash(result.stderr if result.stderr else "No Wi-Fi networks found.")

    except Exception as e:
        flash(f"Wi-Fi scan failed: {e}")

    return redirect(url_for("admin"))


@app.route("/admin/wifi-connect", methods=["POST"])
@admin_required
def admin_wifi_connect():
    ssid = request.form.get("ssid", "").strip()
    password = request.form.get("wifi_password", "").strip()

    if not ssid:
        flash("Wi-Fi name cannot be empty.")
        return redirect(url_for("admin"))

    try:
        result = subprocess.run(
            [
                "sudo",
                "nmcli",
                "dev",
                "wifi",
                "connect",
                ssid,
                "password",
                password,
                "ifname",
                "wlan0"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            flash(f"Wi-Fi change command sent successfully. The Pi may disconnect briefly. Output: {result.stdout}")
        else:
            flash(f"Wi-Fi change failed: {result.stderr}")

    except Exception as e:
        flash(f"Wi-Fi change failed: {e}")

    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
