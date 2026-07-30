import sys
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox,
    QPushButton, QLabel, QFileDialog, QListWidget, QListWidgetItem,
    QMessageBox)


from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# import your engine (assumes engine/ package is beside this file)
from engine.scenario import Scenario
from engine.runner import run_monte_carlo, save_single_run, load_run_json, load_summaries, load_scenario

def steps_from_weeks(weeks: int, school_hours_per_day: int = 8) -> int:
    return int(weeks) * 5 * school_hours_per_day


class Worker(QThread):
    finished = Signal(dict, str)  # (result_data, mode)
    failed = Signal(str)

    def __init__(self, scenario: Scenario, mode: str, out_dir: str):
        super().__init__()
        self.scenario = scenario
        self.mode = mode  # "single" or "mc"
        self.out_dir = out_dir

    def run(self):
        try:
            steps = steps_from_weeks(self.scenario.weeks, self.scenario.school_hours_per_day)
            if self.mode == "single":
                out = save_single_run(self.scenario, steps=steps, out_dir=self.out_dir, seed=self.scenario.base_seed)
                self.finished.emit({"out_dir": str(out)}, "single_saved")
            else:
                out = run_monte_carlo(
                    self.scenario,
                    steps=steps,
                    n_runs=self.scenario.n_runs,
                    out_dir=self.out_dir,
                    base_seed=self.scenario.base_seed,
                )
                self.finished.emit({"out_dir": str(out)}, "mc")
        except Exception as e:
            self.failed.emit(str(e))


class MplPlot(QWidget):
    def __init__(self, title=""):
        super().__init__()
        self.fig = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title(title)

        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)

    def plot_lines(self, x, series: dict, xlabel="t", ylabel="value"):
        self.ax.clear()
        for label, y in series.items():
            self.ax.plot(x, y, label=label)
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.legend()
        self.fig.tight_layout()
        self.canvas.draw()

    def plot_box(self, df: pd.DataFrame, cols: list[str], title=""):
        self.ax.clear()
        data = [df[c].dropna().values for c in cols]
        self.ax.boxplot(data, labels=cols, vert=True)
        self.ax.set_title(title)
        self.fig.tight_layout()
        self.canvas.draw()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("School Pandemic — Scenario Lab")
        self.resize(1200, 750)

        self.out_dir = "results"
        self.last_single_result = None  # dict from run_one()
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tab_scenario = self.build_scenario_tab()
        self.tab_results = self.build_results_tab()
        self.tab_compare = self.build_compare_tab()

        self.tabs.addTab(self.tab_scenario, "Scenario")
        self.tabs.addTab(self.tab_results, "Results")
        self.tabs.addTab(self.tab_compare, "Compare")
        self.worker = None

    def refresh_results_browser(self):
        self.res_scenarios.clear()
        self.res_runs.clear()
        self.res_files.clear()

        base = Path(self.out_dir)
        base.mkdir(parents=True, exist_ok=True)

        for scen_dir in sorted([p for p in base.iterdir() if p.is_dir()]):
            it = QListWidgetItem(scen_dir.name)
            it.setData(Qt.UserRole, scen_dir)
            self.res_scenarios.addItem(it)

    def on_res_scenario_selected(self):
        self.res_runs.clear()
        self.res_files.clear()

        items = self.res_scenarios.selectedItems()
        if not items:
            return
        scen_dir = items[0].data(Qt.UserRole)

        runs = sorted([p for p in scen_dir.iterdir() if p.is_dir()], reverse=True)
        for r in runs:
            it = QListWidgetItem(r.name)
            it.setData(Qt.UserRole, r)
            self.res_runs.addItem(it)

    def on_res_run_selected(self):
        self.res_files.clear()

        items = self.res_runs.selectedItems()
        if not items:
            return
        run_dir = items[0].data(Qt.UserRole)

        files = sorted(run_dir.glob("run_*.json"))
        for f in files:
            it = QListWidgetItem(f.name)
            it.setData(Qt.UserRole, f)
            self.res_files.addItem(it)

    def on_res_load_clicked(self):
        items = self.res_files.selectedItems()
        if not items:
            QMessageBox.warning(self, "No run selected", "Select a run_XXX.json file first.")
            return
        path = items[0].data(Qt.UserRole)
        self.load_run_into_results(path)

    def load_run_into_results(self, run_json_path: Path):
        try:
            res = load_run_json(run_json_path)
            self.populate_results_from_saved_run(res, run_json_path)
        except Exception as e:
            QMessageBox.critical(self, "Load failed", str(e))

    def populate_results_from_saved_run(self, res: dict, run_json_path: Path):
        summary = res.get("summary", {})
        meta = res.get("meta", {})
        scen = meta.get("scenario", {})
        df = pd.DataFrame(res.get("timeseries", {}))

        self.results_summary.setText(
            f"Loaded: {run_json_path}\n\n"
            f"Scenario: {scen.get('name','?')}\n"
            f"Seed: {meta.get('seed','?')} | Steps: {meta.get('steps','?')} | Created: {meta.get('created_at','?')}\n\n"
            f"Ever infected (pupils): {summary.get('ever_infected_pupils','?')}\n"
            f"Ever infected (teachers): {summary.get('ever_infected_teachers','?')}\n"
            f"Ever infected (staff): {summary.get('ever_infected_staff','?')}\n"
            f"Ever infected (total): {summary.get('ever_infected_total','?')}\n"
            f"Missed school days (total): {summary.get('missed_school_days_total','?')}\n"
        )

        if df.empty or "t" not in df.columns:
            return

        t = df["t"].values

        # Infectious curves
        self.plot_infectious.plot_lines(
            t,
            {
                "I_pupils": df.get("I_pupils", pd.Series([0]*len(df))).values,
                "I_teachers": df.get("I_teachers", pd.Series([0]*len(df))).values,
                "I_staff": df.get("I_staff", pd.Series([0]*len(df))).values,
            },
            xlabel="School hour",
            ylabel="Count (I)",
        )

        # Ever infected curves
        total_p = df["S_pupils"].iloc[0]
        total_t = df["S_teachers"].iloc[0]
        total_s = df["S_staff"].iloc[0]

        self.plot_ever.plot_lines(
            t,
            {
                "Ever infected pupils": (total_p - df["S_pupils"]).values,
                "Ever infected teachers": (total_t - df["S_teachers"]).values,
                "Ever infected staff": (total_s - df["S_staff"]).values,
            },
            xlabel="School hour",
            ylabel="Ever infected",
        )


    # ---------- Scenario Tab ----------
    def build_scenario_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        form_box = QGroupBox("Scenario parameters")
        form = QFormLayout(form_box)

        self.name = QLineEdit("daily_testing")

        self.weeks = QSpinBox(); self.weeks.setRange(1, 52); self.weeks.setValue(8)
        self.n_runs = QSpinBox(); self.n_runs.setRange(1, 2000); self.n_runs.setValue(100)
        self.base_seed = QSpinBox(); self.base_seed.setRange(0, 10_000_000); self.base_seed.setValue(1234)

        self.classes_per_grade = QSpinBox(); self.classes_per_grade.setRange(1, 20); self.classes_per_grade.setValue(5)
        self.pupils_per_class = QSpinBox(); self.pupils_per_class.setRange(5, 35); self.pupils_per_class.setValue(22)
        self.num_staff = QSpinBox(); self.num_staff.setRange(0, 200); self.num_staff.setValue(10)

        self.base_beta = QDoubleSpinBox(); self.base_beta.setDecimals(4); self.base_beta.setRange(0.0, 1.0); self.base_beta.setValue(0.02)

        self.testing = QComboBox()
        self.testing.addItems(["None", "Daily (every 8h)", "Custom interval (hours)"])
        self.testing_interval = QSpinBox(); self.testing_interval.setRange(1, 10_000); self.testing_interval.setValue(8)

        self.pupil_vax = QDoubleSpinBox(); self.pupil_vax.setDecimals(2); self.pupil_vax.setRange(0.0, 1.0); self.pupil_vax.setValue(0.2)
        self.teacher_vax = QDoubleSpinBox(); self.teacher_vax.setDecimals(2); self.teacher_vax.setRange(0.0, 1.0); self.teacher_vax.setValue(0.8)
        self.staff_vax = QDoubleSpinBox(); self.staff_vax.setDecimals(2); self.staff_vax.setRange(0.0, 1.0); self.staff_vax.setValue(0.8)

        self.ext_mode = QComboBox(); self.ext_mode.addItems(["linear", "step"])
        self.ext_low = QDoubleSpinBox(); self.ext_low.setDecimals(8); self.ext_low.setRange(0.0, 1.0); self.ext_low.setValue(1e-5)
        self.ext_high = QDoubleSpinBox(); self.ext_high.setDecimals(8); self.ext_high.setRange(0.0, 1.0); self.ext_high.setValue(5e-5)

        self.out_of_class = QDoubleSpinBox(); self.out_of_class.setDecimals(3); self.out_of_class.setRange(0.0, 1.0); self.out_of_class.setValue(0.02)

        form.addRow("Scenario name", self.name)
        form.addRow("Weeks", self.weeks)
        form.addRow("Monte Carlo runs (N)", self.n_runs)
        form.addRow("Base seed", self.base_seed)

        form.addRow("Classes per grade", self.classes_per_grade)
        form.addRow("Pupils per class", self.pupils_per_class)
        form.addRow("Non-teaching staff", self.num_staff)

        form.addRow("Base beta", self.base_beta)
        form.addRow("Testing mode", self.testing)
        form.addRow("Custom testing interval (hours)", self.testing_interval)

        form.addRow("Pupil vaccination rate", self.pupil_vax)
        form.addRow("Teacher vaccination rate", self.teacher_vax)
        form.addRow("Staff vaccination rate", self.staff_vax)

        form.addRow("External force mode", self.ext_mode)
        form.addRow("External force low", self.ext_low)
        form.addRow("External force high", self.ext_high)

        form.addRow("Out-of-class contact rate", self.out_of_class)

        layout.addWidget(form_box)

        btn_row = QHBoxLayout()
        self.btn_single = QPushButton("Run single simulation (save)")
        self.btn_mc = QPushButton("Run Monte Carlo (save to Results/)")
        self.btn_pick_out = QPushButton("Choose Results folder…")
        self.lbl_out = QLabel(f"Results folder: {self.out_dir}")

        self.btn_single.clicked.connect(self.run_single)
        self.btn_mc.clicked.connect(self.run_mc)
        self.btn_pick_out.clicked.connect(self.pick_out_dir)

        btn_row.addWidget(self.btn_single)
        btn_row.addWidget(self.btn_mc)
        btn_row.addWidget(self.btn_pick_out)
        btn_row.addStretch(1)

        layout.addLayout(btn_row)
        layout.addWidget(self.lbl_out)

        self.status = QLabel("Ready.")
        layout.addWidget(self.status)

        return w

    def pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Results folder", str(Path.cwd()))
        if d:
            self.out_dir = d
            self.lbl_out.setText(f"Results folder: {self.out_dir}")

    def build_scenario(self) -> Scenario:
        # external force points as your spec (baseline → increase at week4 → decrease at week8)
        low = float(self.ext_low.value())
        high = float(self.ext_high.value())
        ext_points = [(0, low), (3, low), (4, high), (7, high), (8, low)]

        testing_mode = self.testing.currentText()
        if testing_mode.startswith("None"):
            interval = None
        elif testing_mode.startswith("Daily"):
            interval = 8
        else:
            interval = int(self.testing_interval.value())

        sc = Scenario(
            name=self.name.text().strip() or "scenario",
            classes_per_grade=int(self.classes_per_grade.value()),
            pupils_per_class=int(self.pupils_per_class.value()),
            num_staff=int(self.num_staff.value()),

            base_beta=float(self.base_beta.value()),
            testing_interval_hours=interval,

            pupil_vaccination_rate=float(self.pupil_vax.value()),
            teacher_vaccination_rate=float(self.teacher_vax.value()),
            staff_vaccination_rate=float(self.staff_vax.value()),

            ext_force_mode=self.ext_mode.currentText(),
            ext_force_points=ext_points,

            out_of_class_contact_rate=float(self.out_of_class.value()),

            weeks=int(self.weeks.value()),
            n_runs=int(self.n_runs.value()),
            base_seed=int(self.base_seed.value()),
        )
        return sc

    def run_single(self):
        scenario = self.build_scenario()
        self.status.setText("Running single simulation...")
        self.worker = Worker(scenario, mode="single", out_dir=self.out_dir)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def run_mc(self):
        scenario = self.build_scenario()
        self.status.setText("Running Monte Carlo...")
        self.worker = Worker(scenario, mode="mc", out_dir=self.out_dir)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_failed(self, msg: str):
        self.status.setText("Error.")
        QMessageBox.critical(self, "Run failed", msg)

    def on_finished(self, payload: dict, mode: str):
        if mode == "single_saved":
            self.status.setText(f"Single run saved to: {payload['out_dir']}")
            QMessageBox.information(self, "Single run finished", f"Saved to:\n{payload['out_dir']}")
            # Auto-load run_000.json into Results tab
            run_dir = Path(payload["out_dir"])
            self.load_run_into_results(run_dir / "run_000.json")
            self.tabs.setCurrentWidget(self.tab_results)
            # refresh compare lists
            self.refresh_compare_lists()

        elif mode == "mc":
            self.status.setText(f"Monte Carlo finished. Saved to: {payload['out_dir']}")
            QMessageBox.information(self, "Monte Carlo finished", f"Saved to:\n{payload['out_dir']}")
            self.refresh_compare_lists()

    # ---------- Results Tab ----------
    def build_results_tab(self):
        w = QWidget()
        outer = QVBoxLayout(w)

        top_row = QHBoxLayout()

        # Left panel: saved run browser
        browser = QGroupBox("Saved Results Browser")
        b_layout = QVBoxLayout(browser)

        self.res_scenarios = QListWidget()
        self.res_runs = QListWidget()
        self.res_files = QListWidget()

        self.btn_res_refresh = QPushButton("Refresh")
        self.btn_res_load = QPushButton("Load selected run file")

        b_layout.addWidget(self.btn_res_refresh)
        b_layout.addWidget(QLabel("Scenario"))
        b_layout.addWidget(self.res_scenarios)
        b_layout.addWidget(QLabel("Run timestamp folder"))
        b_layout.addWidget(self.res_runs)
        b_layout.addWidget(QLabel("Run file (run_XXX.json)"))
        b_layout.addWidget(self.res_files)
        b_layout.addWidget(self.btn_res_load)

        # Right panel: summary + plots
        view = QGroupBox("Run View")
        v_layout = QVBoxLayout(view)

        self.results_summary = QLabel("Select a saved run_XXX.json and click Load.")
        self.results_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v_layout.addWidget(self.results_summary)

        self.plot_infectious = MplPlot("Infectious over time (I)")
        self.plot_ever = MplPlot("Ever infected (cumulative)")

        plots_row = QHBoxLayout()
        plots_row.addWidget(self.plot_infectious, 1)
        plots_row.addWidget(self.plot_ever, 1)
        v_layout.addLayout(plots_row)

        top_row.addWidget(browser, 1)
        top_row.addWidget(view, 2)

        outer.addLayout(top_row)

        # Wiring
        self.btn_res_refresh.clicked.connect(self.refresh_results_browser)
        self.res_scenarios.itemSelectionChanged.connect(self.on_res_scenario_selected)
        self.res_runs.itemSelectionChanged.connect(self.on_res_run_selected)
        self.btn_res_load.clicked.connect(self.on_res_load_clicked)

        self.refresh_results_browser()
        return w


    def populate_results_from_single(self, res: dict):
        summary = res["summary"]
        meta = res["meta"]
        self.results_summary.setText(
            f"Scenario: {meta['scenario']['name']}\n"
            f"Seed: {meta['seed']} | Steps: {meta['steps']} | Created: {meta['created_at']}\n\n"
            f"Ever infected (pupils): {summary['ever_infected_pupils']}\n"
            f"Ever infected (teachers): {summary['ever_infected_teachers']}\n"
            f"Ever infected (staff): {summary['ever_infected_staff']}\n"
            f"Ever infected (total): {summary['ever_infected_total']}\n"
            f"Missed school days (total): {summary['missed_school_days_total']:.2f}\n"
        )

        df = pd.DataFrame(res["timeseries"])
        t = df["t"].values

        self.plot_infectious.plot_lines(
            t,
            {
                "I_pupils": df["I_pupils"].values,
                "I_teachers": df["I_teachers"].values,
                "I_staff": df["I_staff"].values,
            },
            xlabel="School hour",
            ylabel="Count (I)",
        )

        # ever infected = total - S
        total_p = df["S_pupils"].iloc[0]
        total_t = df["S_teachers"].iloc[0]
        total_s = df["S_staff"].iloc[0]
        self.plot_ever.plot_lines(
            t,
            {
                "Ever infected pupils": (total_p - df["S_pupils"]).values,
                "Ever infected teachers": (total_t - df["S_teachers"]).values,
                "Ever infected staff": (total_s - df["S_staff"]).values,
            },
            xlabel="School hour",
            ylabel="Ever infected",
        )

    # ---------- Compare Tab ----------
    def build_compare_tab(self):
        w = QWidget()
        layout = QHBoxLayout(w)

        left = QVBoxLayout()
        right = QVBoxLayout()

        self.btn_refresh = QPushButton("Refresh Results list")
        self.btn_refresh.clicked.connect(self.refresh_compare_lists)

        self.list_scenarios = QListWidget()
        self.list_runs = QListWidget()
        self.btn_load_run = QPushButton("Load selected run into comparison")
        self.btn_load_run.clicked.connect(self.load_selected_run)

        left.addWidget(self.btn_refresh)
        left.addWidget(QLabel("Scenarios in Results/"))
        left.addWidget(self.list_scenarios)
        left.addWidget(QLabel("Runs (timestamps)"))
        left.addWidget(self.list_runs)
        left.addWidget(self.btn_load_run)

        self.loaded_runs = QListWidget()
        self.btn_clear_loaded = QPushButton("Clear loaded")
        self.btn_clear_loaded.clicked.connect(self.loaded_runs.clear)

        self.compare_plot = MplPlot("Compare distributions (boxplots)")
        self.compare_stats = QLabel("Load multiple runs to compare.")
        self.compare_stats.setTextInteractionFlags(Qt.TextSelectableByMouse)

        right.addWidget(QLabel("Loaded runs for comparison"))
        right.addWidget(self.loaded_runs)
        right.addWidget(self.btn_clear_loaded)
        right.addWidget(self.compare_stats)
        right.addWidget(self.compare_plot)

        layout.addLayout(left, 1)
        layout.addLayout(right, 2)

        self.list_scenarios.itemSelectionChanged.connect(self.on_scenario_selected)

        self.refresh_compare_lists()
        return w

    def refresh_compare_lists(self):
        self.list_scenarios.clear()
        base = Path(self.out_dir)
        base.mkdir(parents=True, exist_ok=True)

        for scen_dir in sorted([p for p in base.iterdir() if p.is_dir()]):
            item = QListWidgetItem(scen_dir.name)
            item.setData(Qt.UserRole, scen_dir)
            self.list_scenarios.addItem(item)

        self.list_runs.clear()

    def on_scenario_selected(self):
        self.list_runs.clear()
        items = self.list_scenarios.selectedItems()
        if not items:
            return
        scen_dir = items[0].data(Qt.UserRole)

        runs = sorted([p for p in scen_dir.iterdir() if p.is_dir()], reverse=True)
        for r in runs:
            it = QListWidgetItem(r.name)
            it.setData(Qt.UserRole, r)
            self.list_runs.addItem(it)

    def load_selected_run(self):
        run_items = self.list_runs.selectedItems()
        if not run_items:
            return

        run_dir = run_items[0].data(Qt.UserRole)
        df = load_summaries(run_dir)
        sc = load_scenario(run_dir)

        # store in loaded list
        it = QListWidgetItem(f"{sc['name']} / {run_dir.name}")
        it.setData(Qt.UserRole, (run_dir, df, sc))
        self.loaded_runs.addItem(it)

        self.update_comparison_view()

    def update_comparison_view(self):
        # Combine summaries from all loaded runs
        all_blocks = []
        labels = []

        for i in range(self.loaded_runs.count()):
            run_dir, df, sc = self.loaded_runs.item(i).data(Qt.UserRole)
            label = f"{sc['name']}:{run_dir.name}"
            labels.append(label)
            dfi = df.copy()
            dfi["__label__"] = label
            all_blocks.append(dfi)

        if not all_blocks:
            self.compare_stats.setText("Load multiple runs to compare.")
            return

        big = pd.concat(all_blocks, ignore_index=True)

        # Stats text
        metric = "ever_infected_pupils"
        stats = big.groupby("__label__")[metric].agg(["mean", "std", "min", "max", "count"])
        self.compare_stats.setText(f"Metric: {metric}\n\n{stats.to_string()}")

        # Boxplot per scenario-run group
        cols = []
        # make a temporary wide df for boxplot
        wide = {}
        for label in labels:
            wide[label] = big.loc[big["__label__"] == label, metric].values
        wide_df = pd.DataFrame(dict([(k, pd.Series(v)) for k, v in wide.items()]))

        self.compare_plot.plot_box(wide_df, cols=list(wide_df.columns), title=f"Comparison: {metric}")


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
