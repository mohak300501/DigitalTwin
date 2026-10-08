import sys
from pathlib import Path
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox,
    QFormLayout, QSlider, QGroupBox, QTextBrowser, QHeaderView
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QIcon, QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

if getattr(sys, "frozen", False):
    # Running as a PyInstaller executable
    ROOT = Path(sys.executable).resolve().parent
else:
    # Running normally with Python
    ROOT = Path(__file__).resolve().parent

# Source path is needed only when running from source
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(ROOT / "src"))

from ups_twin import DigitalTwin, TwinConfig, load_telemetry, assess_health

DATA_FILE_CSV = ROOT / "ups_telemetry.csv"
DATA_FILE_XLSX = ROOT / "ups_telemetry.xlsx"

def get_active_data_file():
    if DATA_FILE_CSV.exists():
        return DATA_FILE_CSV
    return DATA_FILE_XLSX

class TelemetryTab(QWidget):
    def __init__(self, df, latest, twin, pred):
        super().__init__()
        layout = QVBoxLayout(self)

        # Health Assessment
        health = assess_health({
            "soc_pct": latest["%Cap"],
            "load_pct": latest["%Wout"],
            "ambient_c": latest["T1ambC"],
            "Vbat": latest["Vbat"],
        })

        info_label = QLabel(f"<b>Current Health:</b> {health['severity']} → {'; '.join(health['flags'])}")
        info_label.setObjectName("infoLabel")
        layout.addWidget(info_label)

        metrics_layout = QHBoxLayout()
        metrics = [
            ("Battery SOC", f"{latest['%Cap']:.0f}%"),
            ("Battery voltage", f"{latest['Vbat']:.2f} V"),
            ("UPS temperature", f"{latest['TupsC']:.1f} °C"),
            ("Load", f"{latest['%Wout']:.1f}%")
        ]
        for name, val in metrics:
            group = QGroupBox(name)
            glayout = QVBoxLayout()
            val_label = QLabel(val)
            val_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            glayout.addWidget(val_label)
            group.setLayout(glayout)
            metrics_layout.addWidget(group)
        
        layout.addLayout(metrics_layout)

        # Plotly replacement with Matplotlib
        self.figure = Figure(figsize=(8, 6))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        ax1 = self.figure.add_subplot(211)
        ax1.plot(pred["timestamp"], pred["%Cap"], label="SOC %", color='blue')
        ax1.set_ylabel("SOC (%)", color='blue')
        ax1_twin = ax1.twinx()
        ax1_twin.plot(pred["timestamp"], pred["Vbat"], label="Vbat V", color='orange')
        ax1_twin.set_ylabel("Battery voltage (V)", color='orange')
        ax1.set_title("Observed Telemetry: SOC & Voltage")
        ax1.grid(True)

        ax2 = self.figure.add_subplot(212)
        ax2.plot(pred["timestamp"], pred["%Wout"], label="Load %", color='green')
        ax2.set_ylabel("Load (%Wout)", color='green')
        ax2_twin = ax2.twinx()
        ax2_twin.plot(pred["timestamp"], pred["TupsC"], label="UPS temp °C", color='red')
        ax2_twin.plot(pred["timestamp"], pred["T1ambC"], label="Ambient °C", color='purple', linestyle='--')
        ax2_twin.set_ylabel("Temperature (°C)", color='red')
        ax2.set_title("Observed Telemetry: Load & Temperature")
        ax2.grid(True)
        
        self.figure.tight_layout()


class ScenarioTab(QWidget):
    def __init__(self, twin, latest):
        super().__init__()
        self.twin = twin
        layout = QHBoxLayout(self)
        
        # Controls
        controls = QGroupBox("Scenario Parameters")
        form = QFormLayout()
        
        self.start_soc = QSlider(Qt.Orientation.Horizontal)
        self.start_soc.setRange(10, 100)
        self.start_soc.setValue(int(latest["%Cap"]))
        self.lbl_soc = QLabel(str(self.start_soc.value()))
        self.start_soc.valueChanged.connect(lambda v: self.lbl_soc.setText(str(v)))
        form.addRow("Starting SOC (%):", self.lbl_soc)
        form.addRow("", self.start_soc)

        self.load_pct = QSlider(Qt.Orientation.Horizontal)
        self.load_pct.setRange(1, 90)
        self.load_pct.setValue(20)
        self.lbl_load = QLabel(str(self.load_pct.value()))
        self.load_pct.valueChanged.connect(lambda v: self.lbl_load.setText(str(v)))
        form.addRow("Constant load (%):", self.lbl_load)
        form.addRow("", self.load_pct)

        self.ambient = QSlider(Qt.Orientation.Horizontal)
        self.ambient.setRange(10, 45)
        self.ambient.setValue(int(latest["T1ambC"]))
        self.lbl_ambient = QLabel(str(self.ambient.value()))
        self.ambient.valueChanged.connect(lambda v: self.lbl_ambient.setText(str(v)))
        form.addRow("Ambient temperature (°C):", self.lbl_ambient)
        form.addRow("", self.ambient)

        self.duration = QSlider(Qt.Orientation.Horizontal)
        self.duration.setRange(15, 480)
        self.duration.setSingleStep(15)
        self.duration.setValue(180)
        self.lbl_duration = QLabel(str(self.duration.value()))
        self.duration.valueChanged.connect(lambda v: self.lbl_duration.setText(str(v)))
        form.addRow("Outage duration (min):", self.lbl_duration)
        form.addRow("", self.duration)

        btn = QPushButton("Simulate")
        btn.clicked.connect(self.run_simulation)
        form.addRow(btn)

        self.result_lbl = QLabel("")
        self.result_lbl.setObjectName("resultLabel")
        form.addRow(self.result_lbl)

        controls.setLayout(form)
        layout.addWidget(controls, 1)

        # Plot
        self.figure = Figure(figsize=(5, 4))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout.addWidget(self.canvas, 2)

        self.run_simulation()

    def run_simulation(self):
        sim = self.twin.simulate_outage(
            self.start_soc.value(), 
            self.load_pct.value(), 
            self.ambient.value(), 
            self.duration.value()
        )
        self.ax.clear()
        if not sim.empty:
            self.ax.plot(sim["elapsed_min"], sim["soc_pct"], marker='o', color='red')
            self.ax.set_ylim(0, 100)
            self.ax.set_xlabel("Elapsed minutes")
            self.ax.set_ylabel("SOC (%)")
            self.ax.set_title("Simulated Outage")
            self.ax.grid(True)
            self.figure.tight_layout()
            self.canvas.draw()
            
            end_soc = sim.iloc[-1]['soc_pct']
            msg = f"Predicted end SOC: {end_soc:.1f}%"
            if end_soc <= self.twin.cfg.low_soc_pct:
                msg += "\n(Warning: Reaches low-SOC threshold)"
            self.result_lbl.setText(msg)


class ArrheniusTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        desc = QLabel(
            "<b>Arrhenius Equation Effect on Battery Life</b><br>"
            "Battery lifespan is highly sensitive to temperature. As a rule of thumb derived from the Arrhenius equation, "
            "battery life halves for every 10°C increase above the standard operating temperature (usually 25°C).<br>"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        controls = QGroupBox("Temperature Control")
        form = QFormLayout()
        
        self.temp_slider = QSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setRange(10, 60)
        self.temp_slider.setValue(25)
        self.lbl_temp = QLabel(f"{self.temp_slider.value()} °C")
        
        self.temp_slider.valueChanged.connect(self.update_plot)
        
        form.addRow("Operating Temperature:", self.lbl_temp)
        form.addRow("", self.temp_slider)
        controls.setLayout(form)
        layout.addWidget(controls)

        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout.addWidget(self.canvas)

        self.update_plot()

    def update_plot(self):
        val = self.temp_slider.value()
        self.lbl_temp.setText(f"{val} °C")
        
        temps = np.linspace(10, 60, 100)
        # Base life factor at 25C is 1.0
        life_factors = 1.0 / (2 ** ((temps - 25) / 10.0))
        
        current_factor = 1.0 / (2 ** ((val - 25) / 10.0))
        
        self.ax.clear()
        self.ax.plot(temps, life_factors * 100, label='Expected Lifespan %', color='blue')
        self.ax.axvline(x=val, color='red', linestyle='--', label=f'Current: {val}°C (Life: {current_factor*100:.1f}%)')
        self.ax.scatter([val], [current_factor*100], color='red', zorder=5)
        
        self.ax.set_xlabel("Temperature (°C)")
        self.ax.set_ylabel("Expected Lifespan (%)")
        self.ax.set_title("Battery Lifespan vs Temperature")
        self.ax.grid(True)
        self.ax.legend()
        self.figure.tight_layout()
        self.canvas.draw()


class ImportDataTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout(self)

        lbl = QLabel("Import additional CSV telemetry data and append it to the dataset.")
        layout.addWidget(lbl)

        btn = QPushButton("Select CSV to Import")
        btn.clicked.connect(self.import_csv)
        layout.addWidget(btn)
        layout.addStretch()

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select CSV file", "", "CSV Files (*.csv)")
        if path:
            try:
                new_df = pd.read_csv(path)
                
                # Check for existing csv, else xlsx
                target_csv = DATA_FILE_CSV
                if not target_csv.exists() and DATA_FILE_XLSX.exists():
                    existing_df = pd.read_excel(DATA_FILE_XLSX)
                elif target_csv.exists():
                    existing_df = pd.read_csv(target_csv)
                else:
                    existing_df = pd.DataFrame()
                
                if not existing_df.empty:
                    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                else:
                    combined_df = new_df
                
                # Save to CSV
                combined_df.to_csv(target_csv, index=False)
                
                QMessageBox.information(self, "Success", f"Data appended successfully to {target_csv.name}!")
                
                # Request main window to reload
                self.main_window.load_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import data: {str(e)}")


class SummaryTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml(
            "<h2>Digital Twin Summary</h2>"
            "<p>A <b>Digital Twin</b> is a virtual representation of an object or system that spans its lifecycle, "
            "is updated from real-time data, and uses simulation, machine learning and reasoning to help decision-making.</p>"
            "<p>In this application, the Digital Twin models an <b>APC Smart-UPS</b>. It relies on a calibrated state model "
            "rather than a first-principles electrochemical model. It tracks:</p>"
            "<ul>"
            "<li><b>Battery SOC (State of Charge):</b> Evolves based on measured load and usable energy.</li>"
            "<li><b>Battery Voltage:</b> A calibrated surrogate model based on telemetry.</li>"
            "<li><b>UPS Temperature:</b> Calibrated surrogate tracking ambient conditions and load.</li>"
            "</ul>"
            "<p>This enables predictive simulations such as estimating battery outage durations and health assessments.</p>"
        )
        layout.addWidget(browser)


class DigitalTwinApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Twin App")
        self.resize(1000, 800)
        
        logo_path = ROOT / "DRDO-logo.png"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))

        qss_path = ROOT / "style.qss"
        if qss_path.exists():
            with open(qss_path, "r") as f:
                self.setStyleSheet(f.read())

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        self.setCentralWidget(main_widget)

        header_layout = QHBoxLayout()
        logo_label = QLabel()
        if logo_path.exists():
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap(str(logo_path)).scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pixmap)
        
        title_label = QLabel("UPS Digital Twin")
        title_label.setObjectName("headerTitle")
        
        header_layout.addWidget(logo_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        self.load_data()

    def load_data(self):
        # Clear existing tabs
        self.tabs.clear()
        
        data_file = get_active_data_file()
        if not data_file.exists():
            QMessageBox.warning(self, "Data Missing", "No telemetry data found!")
            return

        try:
            # We patch data.py to read CSV if needed, or we just rely on pd.read_csv here.
            # But load_telemetry uses pd.read_excel right now. Let's patch load_telemetry dynamically or use data.py fix.
            df, warnings = load_telemetry(data_file)
            twin = DigitalTwin(TwinConfig()).fit(df)
            pred = twin.predict_observed(df)
            latest = pred.iloc[-1]
            
            self.tabs.addTab(TelemetryTab(df, latest, twin, pred), "Dashboard")
            self.tabs.addTab(ScenarioTab(twin, latest), "Scenario Simulator")
            self.tabs.addTab(ArrheniusTab(), "Arrhenius Equation")
            self.tabs.addTab(ImportDataTab(self), "Import Data")
            self.tabs.addTab(SummaryTab(), "Digital Twin Summary")
            
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Data", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DigitalTwinApp()
    window.show()
    sys.exit(app.exec())
