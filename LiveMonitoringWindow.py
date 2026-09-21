import obd
import threading
from PyQt6.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QLabel

# Flag to stop the loop
running = True

def input_listener():
    global running
    while True:
        cmd = input().strip().lower()
        if cmd == "/kill":
            print("Stopping...")
            running = False
            break


class LiveMonitoringWindow:
    # TODO: Break this up
    def __init__(self):
        self.layout = QVBoxLayout()

        iat_label = QLabel()
        volt_label = QLabel()
        rpm_label = QLabel()
        QVBoxLayout().addWidget(iat_label)
        QVBoxLayout().addWidget(volt_label)
        QVBoxLayout().addWidget(rpm_label)

        # Start input listener in background
        threading.Thread(target=input_listener, daemon=True).start()
        # Connect to OBD
        connection = obd.OBD(fast=False)
        if not connection.is_connected():
            print("No OBD-II connection.")
            exit()

        CMD_IAT = obd.commands.INTAKE_TEMP
        CMD_VOLT = obd.commands.CONTROL_MODULE_VOLTAGE
        CMD_RPM = obd.commands.RPM

        last_iat = None
        last_volt = None
        last_rpm = None

        print("Monitoring… Type /kill to stop.")

        while running:
            # Query each PID safely
            iat_resp = connection.query(CMD_IAT)
            volt_resp = connection.query(CMD_VOLT)
            rpm_resp = connection.query(CMD_RPM)

            # Extract values only if the response is valid
            iat = None if iat_resp.is_null() else iat_resp.value
            volt = None if volt_resp.is_null() else volt_resp.value
            rpm = None if rpm_resp.is_null() else rpm_resp.value

            # Change detection
            if iat != last_iat:
                iat_label.setText(iat if iat is not None else 'N/A')
                print("IAT:", iat if iat is not None else "N/A")
                last_iat = iat

            if volt != last_volt:
                volt_label.setText(volt if volt is not None else 'N/A')
                print("Voltage:", volt if volt is not None else "N/A")
                last_volt = volt

            if rpm != last_rpm:
                rpm_label.setText(rpm if rpm is not None else 'N/A')
                print("RPM:", rpm if rpm is not None else "N/A")
                last_rpm = rpm

        print("Stopped cleanly.")





