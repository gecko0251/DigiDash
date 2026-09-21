import sys
import os
import csv
import time
import queue
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, 
    QWidget, QPushButton, QHBoxLayout, QGridLayout, QFrame
)
from PyQt6.QtCore import QTimer, QThread, Qt, pyqtSignal
import obd

# ==============================================================================
# TOP-LEVEL UI BUTTON CONTROL DECLARATIONS
# Primary GUI action buttons referenced for fast structural access.
# ==============================================================================
btn_fast_toggle = None
btn_slow_toggle = None
btn_color_toggle = None
exit_btn = None
# ==============================================================================

CSV_FILE = "obd2_data_log.csv"

# Global telemetry cache initialized with default zero/null values
telemetry_cache = {
    "rpm": 0, "speed": 0, "cool_temp": 0, "maf": 0.0,
    "engine_load": 0.0, "throttle_pos": 0.0,
    "iat": 0, "timing_advance": 0.0, "fuel_status": "OFFLINE",
    "volt": 0.0, "oil_temp": 0, "fuel_press": 0
}

CSV_HEADERS = [
    "Timestamp", "RPM", "Speed_kmh", "CoolantTemp_C", "MAF_gps", 
    "Load_pct", "Throttle_pct", "IAT_C", "TimingAdv_deg", 
    "FuelStatus", "Volt_V", "OilTemp_C", "FuelPress_kPa"
]

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as f:
        csv.writer(f).writerow(CSV_HEADERS)


# Thread-safe queue for local disk writes
log_queue = queue.Queue()


class CSVLoggerThread(QThread):
    """Asynchronous disk writer thread preventing filesystem stalls on the UI thread."""
    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath
        self.running = True

    def run(self):
        with open(self.filepath, "a", newline="") as f:
            writer = csv.writer(f)
            while self.running or not log_queue.empty():
                try:
                    data = log_queue.get(timeout=0.2)
                    writer.writerow(data)
                    f.flush()
                    log_queue.task_done()
                except queue.Empty:
                    continue

    def stop(self):
        self.running = False


class OBDReconnectThread(QThread):
    """Background reconnect engine isolating blocking serial port scans and handshakes."""
    connection_established = pyqtSignal(object)

    def run(self):
        connection = None
        while connection is None or not connection.is_connected():
            try:
                connection = obd.OBD(fast=True)
                if connection.is_connected():
                    self.connection_established.emit(connection)
                    return
            except Exception:
                pass
            time.sleep(2)


class FastOBDWorkerThread(QThread):
    """High-frequency polling thread running as fast as the adapter/ECU bus permits."""
    connection_lost = pyqtSignal()

    def __init__(self, connection):
        super().__init__()
        self.connection = connection
        self.running = True
        self.collecting = False  # Off by default

    def update_connection(self, new_conn):
        self.connection = new_conn

    def run(self):
        while self.running:
            if not self.collecting:
                time.sleep(0.1)
                continue

            if not self.connection or not self.connection.is_connected():
                telemetry_cache["fuel_status"] = "OFFLINE"
                self.connection_lost.emit()
                time.sleep(1)
                continue

            try:
                r_rpm = self.connection.query(obd.commands.RPM)
                if not r_rpm.is_null():
                    telemetry_cache["rpm"] = int(r_rpm.value.magnitude)

                r_speed = self.connection.query(obd.commands.SPEED)
                if not r_speed.is_null():
                    telemetry_cache["speed"] = int(r_speed.value.to("kph").magnitude)

                r_load = self.connection.query(obd.commands.ENGINE_LOAD)
                if not r_load.is_null():
                    telemetry_cache["engine_load"] = round(r_load.value.magnitude, 1)

                r_tps = self.connection.query(obd.commands.THROTTLE_POS)
                if not r_tps.is_null():
                    telemetry_cache["throttle_pos"] = round(r_tps.value.magnitude, 1)

                r_maf = self.connection.query(obd.commands.MAF)
                if not r_maf.is_null():
                    telemetry_cache["maf"] = round(r_maf.value.magnitude, 2)

            except Exception:
                time.sleep(0.01)

    def stop(self):
        self.running = False


class SlowOBDWorkerThread(QThread):
    """Low-frequency polling thread updating slow-moving parameters every 1.5 seconds."""
    def __init__(self, connection):
        super().__init__()
        self.connection = connection
        self.running = True
        self.collecting = False  # Off by default

    def update_connection(self, new_conn):
        self.connection = new_conn

    def run(self):
        while self.running:
            if not self.collecting:
                time.sleep(0.5)
                continue

            if not self.connection or not self.connection.is_connected():
                time.sleep(1.5)
                continue

            try:
                r_cool = self.connection.query(obd.commands.COOLANT_TEMP)
                r_iat = self.connection.query(obd.commands.INTAKE_TEMP)
                r_timing = self.connection.query(obd.commands.TIMING_ADVANCE)
                r_status = self.connection.query(obd.commands.FUEL_STATUS)

                r_volt = self.connection.query(obd.commands.CONTROL_MODULE_VOLTAGE)
                r_oil = self.connection.query(obd.commands.OIL_TEMP)
                r_fuel = self.connection.query(obd.commands.FUEL_PRESSURE)

                if not r_cool.is_null(): telemetry_cache["cool_temp"] = int(r_cool.value.to("degC").magnitude)
                if not r_iat.is_null(): telemetry_cache["iat"] = int(r_iat.value.to("degC").magnitude)
                if not r_timing.is_null(): telemetry_cache["timing_advance"] = round(r_timing.value.magnitude, 1)
                if not r_status.is_null(): telemetry_cache["fuel_status"] = str(r_status.value)

                if not r_volt.is_null(): telemetry_cache["volt"] = round(r_volt.value.magnitude, 2)
                if not r_oil.is_null(): telemetry_cache["oil_temp"] = int(r_oil.value.to("degC").magnitude)
                if not r_fuel.is_null(): telemetry_cache["fuel_press"] = int(r_fuel.value.to("kPa").magnitude)

            except Exception:
                pass

            time.sleep(1.5)

    def stop(self):
        self.running = False


class SquareGaugeBox(QFrame):
    """Custom Square Component supporting dynamic range coloring and full-box flashing alerts."""
    def __init__(self, title_text, width=140, height=110, accent_color="#ff5500", title_font_size=None, val_font_size=None):
        super().__init__()
        self.setFixedSize(width, height)
        self.accent_color = accent_color
        self.flash_state = False

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        if title_font_size is None:
            title_font_size = "18px" if width > 140 else "16px"
        if val_font_size is None:
            val_font_size = "26px" if width > 140 else "22px"

        self.title = QLabel(title_text)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value = QLabel("0")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_font_size = title_font_size
        self.val_font_size = val_font_size

        layout.addWidget(self.title)
        layout.addWidget(self.value)
        self.setLayout(layout)

        self.apply_theme(accent_color)

    def apply_theme(self, color_hex):
        self.accent_color = color_hex
        self.setStyleSheet(f"""
            SquareGaugeBox {{
                background-color: #000000;
                border: 3px solid {color_hex};
                border-radius: 2px;
            }}
        """)
        self.title.setStyleSheet(f"color: {color_hex}; font-family: 'Courier New', monospace; font-weight: bold; font-size: {self.title_font_size}; border: none;")
        self.value.setStyleSheet(f"color: {color_hex}; font-family: 'Courier New', monospace; font-weight: bold; font-size: {self.val_font_size}; border: none;")

    def set_val(self, text_val, state="BASE", flash_text="WARNING", flash_color="#FF0000"):
        """
        state: "BASE", "YELLOW", "RED", "FLASH"
        """
        if state == "FLASH":
            self.flash_state = not self.flash_state
            bg_color = flash_color if self.flash_state else "#000000"
            text_color = "#FFFFFF" if self.flash_state else flash_color
            
            self.setStyleSheet(f"""
                SquareGaugeBox {{
                    background-color: {bg_color};
                    border: 3px solid #FFFFFF;
                    border-radius: 2px;
                }}
            """)
            self.title.setStyleSheet(f"color: {text_color}; font-family: 'Courier New', monospace; font-weight: bold; font-size: {self.title_font_size}; border: none;")
            self.value.setStyleSheet(f"color: {text_color}; font-family: 'Courier New', monospace; font-weight: bold; font-size: {self.val_font_size}; border: none;")
            self.value.setText(flash_text)
            return

        # Normal states reset background to black
        self.value.setText(str(text_val))
        display_color = self.accent_color
        if state == "YELLOW":
            display_color = "#FFFF00"
        elif state == "RED":
            display_color = "#FF0000"

        self.setStyleSheet(f"""
            SquareGaugeBox {{
                background-color: #000000;
                border: 3px solid {self.accent_color};
                border-radius: 2px;
            }}
        """)
        self.title.setStyleSheet(f"color: {self.accent_color}; font-family: 'Courier New', monospace; font-weight: bold; font-size: {self.title_font_size}; border: none;")
        self.value.setStyleSheet(f"color: {display_color}; font-family: 'Courier New', monospace; font-weight: bold; font-size: {self.val_font_size}; border: none;")


class RaceDashboard(QMainWindow):
    """Main UI thread executing layout loops at 60 FPS."""
    def __init__(self):
        global btn_fast_toggle, btn_slow_toggle, btn_color_toggle, exit_btn
        super().__init__()

        self.setWindowTitle("Engine Telemetry")
        self.setStyleSheet("background-color: #000000;")

        # Color Theme State Management (#ff5500 -> #D3D3D3 -> #FFB000 -> #00FF43)
        self.color_palette = ["#ff5500", "#D3D3D3", "#FFB000", "#00FF43"]
        self.current_color_idx = 0

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ---------------- GRID CONTAINER (ASYMMETRIC LAYOUT) ----------------
        grid_layout = QGridLayout()
        grid_layout.setSpacing(15)

        # Large left gauge sizing (225x165)
        # Standard right gauge height matching row height (165) for top/bottom edge alignment
        self.gauges = {
            "rpm": SquareGaugeBox("RPM", width=225, height=165, accent_color=self.get_active_color(), title_font_size="27px", val_font_size="39px"),
            "speed": SquareGaugeBox("SPEED", width=225, height=165, accent_color=self.get_active_color(), title_font_size="27px", val_font_size="39px"),
            "cool_temp": SquareGaugeBox("COOL T", width=225, height=165, accent_color=self.get_active_color(), title_font_size="27px", val_font_size="39px"),
            "oil_temp": SquareGaugeBox("OIL T", width=160, height=165, accent_color=self.get_active_color()),
            "fuel_press": SquareGaugeBox("FUEL P", width=160, height=165, accent_color=self.get_active_color()),
            "volt": SquareGaugeBox("VOLTS", width=160, height=165, accent_color=self.get_active_color()),
            "maf": SquareGaugeBox("MAF g/s", width=160, height=165, accent_color=self.get_active_color()),
            "engine_load": SquareGaugeBox("LOAD %", width=160, height=165, accent_color=self.get_active_color()),
            "throttle_pos": SquareGaugeBox("TPS %", width=160, height=165, accent_color=self.get_active_color()),
            "iat": SquareGaugeBox("IAT C", width=160, height=165, accent_color=self.get_active_color()),
            "timing_advance": SquareGaugeBox("TIMING", width=160, height=165, accent_color=self.get_active_color()),
            "fuel_status": SquareGaugeBox("F-SYS", width=160, height=165, accent_color=self.get_active_color())
        }

        # 1. Left Stacked Primary Gauges (Column 0, Rows 0 to 2)
        grid_layout.addWidget(self.gauges["rpm"], 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.gauges["speed"], 1, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.gauges["cool_temp"], 2, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignCenter)

        # 2. Right Side: 3x3 Grid of Standard Gauges (Columns 1 to 3, Rows 0 to 2)
        right_gauges = [
            self.gauges["oil_temp"], self.gauges["fuel_press"], self.gauges["volt"],
            self.gauges["maf"], self.gauges["engine_load"], self.gauges["throttle_pos"],
            self.gauges["iat"], self.gauges["timing_advance"], self.gauges["fuel_status"]
        ]

        for idx, widget in enumerate(right_gauges):
            row = idx // 3
            col = (idx % 3) + 1  # Offset by 1 column for the left stack
            grid_layout.addWidget(widget, row, col, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignCenter)

        # Reusable Button Styles for Active vs Inactive state
        self.style_off = """
            QPushButton {
                background-color: #D3D3D3; 
                color: #000000;
                font-family: 'Courier New', monospace; 
                font-size: 14px; 
                font-weight: bold;
                padding: 6px 0px; 
                border: 2px solid #A9A9A9;
            }
            QPushButton:hover { 
                background-color: #FFFFFF; 
                color: #000000; 
            }
        """

        self.style_on = """
            QPushButton {
                background-color: #00FF43; 
                color: #000000;
                font-family: 'Courier New', monospace; 
                font-size: 14px; 
                font-weight: bold;
                padding: 6px 0px; 
                border: 2px solid #FFFFFF;
            }
            QPushButton:hover { 
                background-color: #7BFF9F; 
                color: #000000; 
            }
        """

        # Fast Collection Button
        btn_fast_toggle = QPushButton("FAST")
        btn_fast_toggle.setFixedWidth(160)
        btn_fast_toggle.setStyleSheet(self.style_off)
        btn_fast_toggle.clicked.connect(self.toggle_fast_collection)

        # Slow Collection Button
        btn_slow_toggle = QPushButton("SLOW")
        btn_slow_toggle.setFixedWidth(160)
        btn_slow_toggle.setStyleSheet(self.style_off)
        btn_slow_toggle.clicked.connect(self.toggle_slow_collection)

        # Display Color Toggle Button
        btn_color_toggle = QPushButton("COLOR")
        btn_color_toggle.setFixedWidth(160)
        btn_color_toggle.setStyleSheet(self.style_off)
        btn_color_toggle.clicked.connect(self.cycle_display_color)

        # Exit Button placed below left column
        exit_btn = QPushButton("EXIT DASH")
        exit_btn.setFixedWidth(225)
        exit_btn.setStyleSheet(self.style_off)
        exit_btn.clicked.connect(self.shutdown)

        # 3. Add Control Buttons aligned directly underneath their respective columns
        grid_layout.addWidget(exit_btn, 3, 0, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(btn_fast_toggle, 3, 1, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(btn_slow_toggle, 3, 2, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(btn_color_toggle, 3, 3, Qt.AlignmentFlag.AlignCenter)

        main_layout.addLayout(grid_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Initialize Background Threads
        self.logger_thread = CSVLoggerThread(CSV_FILE)
        self.logger_thread.start()

        self.reconnect_thread = None
        self.fast_worker = FastOBDWorkerThread(None)
        self.slow_worker = SlowOBDWorkerThread(None)

        self.fast_worker.connection_lost.connect(self.trigger_reconnect)
        self.fast_worker.start()
        self.slow_worker.start()

        self.trigger_reconnect()

        # UI Refresh Loop (~60 FPS)
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.refresh_screen)
        self.ui_timer.start(16)

        # Queue Logging Dispatcher Loop (2 Hz)
        self.logging_timer = QTimer()
        self.logging_timer.timeout.connect(self.queue_log_entry)
        self.logging_timer.start(500)

    def get_active_color(self):
        return self.color_palette[self.current_color_idx]

    def cycle_display_color(self):
        self.current_color_idx = (self.current_color_idx + 1) % len(self.color_palette)
        active_color = self.get_active_color()
        for widget in self.gauges.values():
            widget.apply_theme(active_color)

    def toggle_fast_collection(self):
        self.fast_worker.collecting = not self.fast_worker.collecting
        is_on = self.fast_worker.collecting
        btn_fast_toggle.setStyleSheet(self.style_on if is_on else self.style_off)

    def toggle_slow_collection(self):
        self.slow_worker.collecting = not self.slow_worker.collecting
        is_on = self.slow_worker.collecting
        btn_slow_toggle.setStyleSheet(self.style_on if is_on else self.style_off)

    def trigger_reconnect(self):
        if self.reconnect_thread is None or not self.reconnect_thread.isRunning():
            self.reconnect_thread = OBDReconnectThread()
            self.reconnect_thread.connection_established.connect(self.on_connection_established)
            self.reconnect_thread.start()

    def on_connection_established(self, connection):
        self.fast_worker.update_connection(connection)
        self.slow_worker.update_connection(connection)

    def refresh_screen(self):
        c = telemetry_cache
        
        # 1. RPM Gauge (6200 RPM Shift Warning)
        if c["rpm"] > 6200:
            self.gauges["rpm"].set_val(c["rpm"], state="RED")
        else:
            self.gauges["rpm"].set_val(c["rpm"], state="BASE")

        # 2. Speed
        self.gauges["speed"].set_val(f"{c['speed']} KM/H", state="BASE")

        # 3. Coolant Temp Range Logic
        cool = c["cool_temp"]
        if cool >= 110:
            self.gauges["cool_temp"].set_val(f"{cool}°C", state="FLASH", flash_text="WARNING", flash_color="#FF0000")
        elif (105 <= cool < 110) or cool < 85:
            self.gauges["cool_temp"].set_val(f"{cool}°C", state="RED")
        elif (85 <= cool < 90) or (102 < cool <= 105):
            self.gauges["cool_temp"].set_val(f"{cool}°C", state="YELLOW")
        else:
            self.gauges["cool_temp"].set_val(f"{cool}°C", state="BASE")

        # 4. Oil Temp Range Logic
        oil = c["oil_temp"]
        if oil >= 109:
            self.gauges["oil_temp"].set_val(f"{oil}°C", state="FLASH", flash_text="WARNING", flash_color="#FF0000")
        elif 0 < oil < 95:
            self.gauges["oil_temp"].set_val(f"{oil}°C", state="FLASH", flash_text="NOT WARM", flash_color="#FFFF00")
        elif 105 < oil < 109:
            self.gauges["oil_temp"].set_val(f"{oil}°C", state="YELLOW")
        else:
            self.gauges["oil_temp"].set_val(f"{oil}°C", state="BASE")

        # 5. MAF Range Logic
        maf = c["maf"]
        if maf >= 5.0 or (0 < maf < 2.5):
            self.gauges["maf"].set_val(maf, state="RED")
        elif (2.5 <= maf < 3.0) or (4.0 < maf < 5.0):
            self.gauges["maf"].set_val(maf, state="YELLOW")
        else:
            self.gauges["maf"].set_val(maf, state="BASE")

        # 6. Timing Advance Range Logic
        ta = c["timing_advance"]
        if ta < 0:
            self.gauges["timing_advance"].set_val(f"{ta}°", state="FLASH", flash_text="WARNING", flash_color="#FF0000")
        elif (0 <= ta <= 2) or (ta >= 23):
            self.gauges["timing_advance"].set_val(f"{ta}°", state="RED")
        elif (2 < ta < 8) or (15 < ta < 23):
            self.gauges["timing_advance"].set_val(f"{ta}°", state="YELLOW")
        else:
            self.gauges["timing_advance"].set_val(f"{ta}°", state="BASE")

        # 7. Voltage Range Logic
        v = c["volt"]
        if 0 < v < 12.0:
            self.gauges["volt"].set_val(f"{v}V", state="FLASH", flash_text="CRIT LOW V", flash_color="#FF0000")
        elif 12.0 <= v < 13.5:
            self.gauges["volt"].set_val(f"{v}V", state="YELLOW")
        else:
            self.gauges["volt"].set_val(f"{v}V", state="BASE")

        # 8. Base Dash Color Gauges
        self.gauges["fuel_press"].set_val(f"{c['fuel_press']} kPa", state="BASE")
        self.gauges["engine_load"].set_val(f"{c['engine_load']}%", state="BASE")
        self.gauges["throttle_pos"].set_val(f"{c['throttle_pos']}%", state="BASE")
        self.gauges["iat"].set_val(f"{c['iat']}°C", state="BASE")
        self.gauges["fuel_status"].set_val(c["fuel_status"], state="BASE")

    def queue_log_entry(self):
        c = telemetry_cache
        row = [
            datetime.now().strftime('%H:%M:%S.%f')[:-3],
            c["rpm"], c["speed"], c["cool_temp"], c["maf"],
            c["engine_load"], c["throttle_pos"],
            c["iat"], c["timing_advance"], c["fuel_status"],
            c["volt"], c["oil_temp"], c["fuel_press"]
        ]
        log_queue.put(row)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.shutdown()

    def shutdown(self):
        self.fast_worker.stop()
        self.slow_worker.stop()
        self.logger_thread.stop()

        self.fast_worker.wait()
        self.slow_worker.wait()
        self.logger_thread.wait()

        self.close()
        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    dash = RaceDashboard()
    dash.showFullScreen()

    sys.exit(app.exec())
