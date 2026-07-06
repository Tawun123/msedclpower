import json
import time
import threading
from datetime import datetime

from paho.mqtt import client as mqtt
from plyer import notification

BROKER = "localhost"
DEVICE = "0x18690afffe37d329"

STATE_TOPIC = f"zigbee2mqtt/{DEVICE}"
GET_TOPIC = f"zigbee2mqtt/{DEVICE}/get"

OUTAGE_TIMEOUT = 10
RESTORE_GRACE_PERIOD = 15

power_out = False
last_success = time.time()
last_restore_time = 0

lock = threading.Lock()


def notify(title, message):
    notification.notify(title=title, message=message, timeout=10)


def log_event(event):
    now = datetime.now()

    with open("power_log.csv", "a") as f:
        f.write(f"{now:%Y-%m-%d},{now:%H:%M:%S},{event}\n")

    print(f"{now:%H:%M:%S} - {event}")


def poll_loop():
    while True:
        client.publish(GET_TOPIC, json.dumps({"state": ""}))
        time.sleep(2)


def outage_monitor():
    global power_out

    while True:
        with lock:
            elapsed = time.time() - last_success
            since_restore = time.time() - last_restore_time

            if (
                not power_out
                and elapsed > OUTAGE_TIMEOUT
                and since_restore > RESTORE_GRACE_PERIOD
            ):
                power_out = True
                log_event("Power Lost")
                notify("Power Outage", "Kitchen Zigbee device appears offline")

        time.sleep(1)


def on_message(client, userdata, msg):
    global power_out, last_success, last_restore_time

    if msg.topic == STATE_TOPIC:
        with lock:
            last_success = time.time()

            if power_out:
                power_out = False
                last_restore_time = time.time()

                log_event("Power Restored")
                notify("Power Restored", "Kitchen Zigbee device is back online")

        print(f"{datetime.now():%H:%M:%S} Device responded")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message

client.connect(BROKER, 1883, 60)
client.subscribe(STATE_TOPIC)

threading.Thread(target=poll_loop, daemon=True).start()
threading.Thread(target=outage_monitor, daemon=True).start()

print("Power monitor running...")
client.loop_forever()