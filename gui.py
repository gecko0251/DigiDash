from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMainWindow, QApplication, QComboBox, QToolBar, QStatusBar
import os
import sys
import LiveMonitoringWindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aleko's Racecar OBD")
        file_list = ["None"]
        for f in os.listdir():
            if f.endswith(".py") and (f != "gui.py"):
                file_list.append(f)

        script_select_widget = QComboBox()

        script_select_tool = QAction("Script", self)
        script_select_tool.triggered.connect( self.set_script_toolbar )

        # Combobox setup
        script_select_widget.addItems(file_list)
        script_select_widget.currentIndexChanged.connect( self.set_script_combo )

        self.setCentralWidget(script_select_widget)

        # menu setup
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        file_menu.addAction(script_select_tool)

        self.setMenuWidget(file_menu)



    def set_script_combo(self, script):
        if script == 2: #'LiveMonitoringWindow.py':
            live_monitor = LiveMonitoringWindow.LiveMonitoringWindow()
            self.setLayout(live_monitor.layout)

    def set_script_toolbar(self, f):
        print(f)

app = QApplication(sys.argv)
window = MainWindow()
window.show()

app.exec()