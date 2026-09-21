import obd
import threading
import csv
import os
from datetime import datetime
from PyQt6.QtWidgets import QLabel

# /dump to print current values
# /save to save to CSV
# /kill to end program


# Shared state
running = True
dump_requested = False
save_requested = False

# CSV output file
CSV_FILE = "obd2_data_log.csv"

# Create CSV with header if it doesn't exist
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp",
            "IAT (°C)",
            "Voltage (V)",
            "RPM",
            "Oil Temp (°C)",
            "Fuel Pressure (kPa)",
            "Coolant Temp (°C)",
            "Engine Load (%)"
        ])


def input_listener():
    global running, dump_requested, save_requested
    while True:
        cmd = input().strip().lower()
        if cmd == "/kill":
            print("Stopping...")
            running = False
            break
        elif cmd == "/dump":
            dump_requested = True
        elif cmd == "/save":
            save_requested = True
            print("Saving current values to CSV...")


# Start input listener thread
threading.Thread(target=input_listener, daemon=True).start()

# Connect to OBD
connection = obd.OBD(fast=False)

if not connection.is_connected():
    print("No OBD-II connection.")
    exit()

# Standard PIDs
CMD_IAT        = obd.commands.INTAKE_TEMP           # Intake Air Temp
CMD_VOLT       = obd.commands.CONTROL_MODULE_VOLTAGE
CMD_RPM        = obd.commands.RPM
CMD_OIL_TEMP   = obd.commands.OIL_TEMP             # Oil Temp
CMD_FUEL_PRESS  = obd.commands.FUEL_PRESSURE        # Oil Pressure
CMD_COOL_TEMP  = obd.commands.COOLANT_TEMP
CMD_ENGINE_LOAD = obd.commands.ENGINE_LOAD

# Last known values for change detection
last_values = {
    "iat": None,
    "volt": None,
    "rpm": None,
    "oil_temp": None,
    "oil_press": None,
    "cool_temp": None,
    "engine_load": None
}

# Current values
current_values = last_values.copy()

print("Monitoring… Commands: /kill, /dump, /save")

while running:
    # Query each PID safely
    responses = {
        "iat": connection.query(CMD_IAT),
        "volt": connection.query(CMD_VOLT),
        "rpm": connection.query(CMD_RPM),
        "oil_temp": connection.query(CMD_OIL_TEMP),
        "fuel_press": connection.query(CMD_FUEL_PRESS),
        "cool_temp": connection.query(CMD_COOL_TEMP),
        "engine_load": connection.query(CMD_ENGINE_LOAD)
    }

    # Extract valid values, keep metric units
    current_values["iat"]         = None if responses["iat"].is_null() else responses["iat"].value.to("degC")
    current_values["volt"]        = None if responses["volt"].is_null() else responses["volt"].value
    current_values["rpm"]         = None if responses["rpm"].is_null() else responses["rpm"].value.magnitude
    current_values["oil_temp"]    = None if responses["oil_temp"].is_null() else responses["oil_temp"].value.to("degC")
    current_values["fuel_press"]   = None if responses["fuel_press"].is_null() else responses["oil_press"].value.to("kPa")
    current_values["cool_temp"]   = None if responses["cool_temp"].is_null() else responses["cool_temp"].value.to("degC")
    current_values["engine_load"] = None if responses["engine_load"].is_null() else responses["engine_load"].value.magnitude

    # Print changes only
    for key, val in current_values.items():
        if val != last_values[key]:
            print(f"{key.replace('_',' ').title()}: {val if val is not None else 'N/A'}")
            last_values[key] = val

    # Handle /dump
    if dump_requested:
        print("----- CURRENT VALUES -----")
        print(f"Timestamp: {datetime.now()}")
        for key, val in current_values.items():
            print(f"{key.replace('_',' ').title()}: {val if val is not None else 'N/A'}")
        print("--------------------------")
        dump_requested = False

    # Handle /save
    if save_requested:
        with open(CSV_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now(),
                current_values["iat"] if current_values["iat"] is not None else "",
                current_values["volt"] if current_values["volt"] is not None else "",
                current_values["rpm"] if current_values["rpm"] is not None else "",
                current_values["oil_temp"] if current_values["oil_temp"] is not None else "",
                current_values["fuel_press"] if current_values["fuel_press"] is not None else "",
                current_values["cool_temp"] if current_values["cool_temp"] is not None else "",
                current_values["engine_load"] if current_values["engine_load"] is not None else ""
            ])
        print("Saved to", CSV_FILE)
        save_requested = False

print("Stopped cleanly.")
