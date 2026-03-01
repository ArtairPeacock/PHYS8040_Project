import sys
import numpy as np
import networkx as nx

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton,
    QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsLineItem
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPen, QColor
import pyqtgraph as pg


# ==========================================================
# Optical Physics
# ==========================================================

class OpticalSignal:
    def __init__(self, t, power, chirp, width):
        self.t = t
        self.power = power
        self.chirp = chirp
        self.width = width   # pulse width parameter
        
class SignalGenerator:

    @staticmethod
    def gaussian_pulse(
        peak_power=1.0,
        width_ps=8,
        chirp=0.0,
        window_ps=100,
        samples=4000
    ):
        t = np.linspace(-window_ps/2, window_ps/2, samples)

        power = peak_power * np.exp(-(t**2) / (2 * width_ps**2))

        # linear frequency chirp
        chirp_profile = chirp * (t / width_ps)

        return OpticalSignal(t, power, chirp_profile, width_ps)


class Components:

    @staticmethod
    def process(comp_type, signal):

        if comp_type == "SMF":
            length_km = 50
            alpha_db = 0.2          # attenuation
            beta2 = 17              # ps^2/km dispersion

            # attenuation
            signal.power *= 10 ** (-alpha_db * length_km / 10)

            # dispersion broadening
            broaden_factor = np.sqrt(
                1 + (beta2 * length_km / signal.width**2)**2
            )

            signal.width *= broaden_factor
            signal.power = np.exp(-(signal.t**2) / (2 * signal.width**2))

            # chirp added by dispersion
            signal.chirp += (beta2 * length_km / signal.width**2) * signal.t

        elif comp_type == "DCF":
            length_km = 10
            beta2 = -80
            alpha_db = 0.5

            signal.power *= 10 ** (-alpha_db * length_km / 10)

            broaden_factor = np.sqrt(
                1 + (beta2 * length_km / signal.width**2)**2
            )

            signal.width *= broaden_factor
            signal.power = np.exp(-(signal.t**2) / (2 * signal.width**2))

            signal.chirp += (beta2 * length_km / signal.width**2) * signal.t

        elif comp_type == "Amp":
            gain_db = 20
            noise_level = 0.01

            signal.power *= 10 ** (gain_db / 10)

            # ASE noise
            signal.power += noise_level * np.random.randn(len(signal.power))

        elif comp_type == "MZM":
            modulation_depth = 0.8
            signal.power *= (1 + modulation_depth * np.sin(0.2 * signal.t))
            signal.chirp += 0.05 * np.gradient(signal.power)

        elif comp_type == "Booster":
            gain_db = 10
            signal.power *= 10 ** (gain_db / 10)

        return signal


# ==========================================================
# Graphics Node
# ==========================================================

class ComponentNode(QGraphicsRectItem):
    def __init__(self, name):
        super().__init__(0, 0, 100, 50)

        self.name = name
        self.connections = []   #this tracks the wires

        self.setBrush(QColor("#e6f2ff"))
        self.setPen(QPen(Qt.black, 2))

        self.setFlags(
            QGraphicsRectItem.ItemIsMovable |
            QGraphicsRectItem.ItemIsSelectable
        )

        self.label = QGraphicsTextItem(name, self)
        self.label.setDefaultTextColor(Qt.black)
        self.label.setPos(25, 15)
        
class ConnectionLine(QGraphicsLineItem):
    def __init__(self, n1, n2):
        super().__init__()

        self.n1 = n1
        self.n2 = n2

        self.setPen(QPen(Qt.blue, 2))
        self.setFlags(QGraphicsLineItem.ItemIsSelectable)

        self.update_position()

    def update_position(self):
        p1 = self.n1.sceneBoundingRect().center()
        p2 = self.n2.sceneBoundingRect().center()
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())


# ==========================================================
# Main Window
# ==========================================================

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        
        self.connection_items = []
        self.component_counter = 0

        self.setWindowTitle("Fibre Optic Simulator")
        self.setGeometry(100, 100, 1300, 800)

        self.graph = nx.DiGraph()
        self.selected_node = None

        self._build_ui()

    # ------------------------------------------------------

    def _build_ui(self):

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # =======================
        # PLOTS
        # =======================

        plot_layout = QHBoxLayout()

        self.power_plot = pg.PlotWidget(title="OPTICAL POWER")
        self.power_plot.showGrid(x=True, y=True)
        self.power_plot.setLabel("bottom", "Time (ps)")
        self.power_plot.setLabel("left", "Power")

        self.chirp_plot = pg.PlotWidget(title="FREQUENCY CHIRP")
        self.chirp_plot.showGrid(x=True, y=True)
        self.chirp_plot.setLabel("bottom", "Time (ps)")
        self.chirp_plot.setLabel("left", "Chirp")

        plot_layout.addWidget(self.power_plot)
        plot_layout.addWidget(self.chirp_plot)
        main_layout.addLayout(plot_layout)

        # =======================
        # CANVAS
        # =======================

        self.scene = QGraphicsScene(0, 0, 1200, 400)
        self.view = QGraphicsView(self.scene)
        self.view.setBackgroundBrush(QColor("white"))
        main_layout.addWidget(self.view)

        self._draw_grid()

        # =======================
        # TOOLBAR
        # =======================

        toolbar = QHBoxLayout()

        components = ["Gaussian Pulse", "SMF", "DCF", "Amp", "MZM", "Booster", "OSA"]

        for name in components:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, n=name: self.add_component(n))
            toolbar.addWidget(btn)

        toolbar.addStretch()

        run_btn = QPushButton("RUN")
        run_btn.setStyleSheet("color: red; font-weight: bold;")
        run_btn.clicked.connect(self.run_simulation)

        exit_btn = QPushButton("EXIT")
        exit_btn.clicked.connect(self.close)

        toolbar.addWidget(run_btn)
        toolbar.addWidget(exit_btn)

        main_layout.addLayout(toolbar)

    # ------------------------------------------------------

    def _draw_grid(self):
        grid = 25
        pen = QPen(QColor(230, 230, 230))

        for x in range(0, 1200, grid):
            self.scene.addLine(x, 0, x, 400, pen)

        for y in range(0, 400, grid):
            self.scene.addLine(0, y, 1200, y, pen)

    # ------------------------------------------------------

    def add_component(self, name):

        node = ComponentNode(name)

        x_offset = 100 + (self.component_counter % 6) * 150
        y_offset = 80 + (self.component_counter // 6) * 120
        node.setPos(x_offset, y_offset)

        self.component_counter += 1

        self.scene.addItem(node)

        #Store correct internal type
        if name == "Gaussian Source":
            comp_type = "SOURCE"
        else:
            comp_type = name

        self.graph.add_node(node, type=comp_type)

        node.mousePressEvent = lambda event, n=node: self.node_clicked(n)
        
    # ------------------------------------------------------

    def node_clicked(self, node):

        if self.selected_node is None:
            self.selected_node = node
            node.setPen(QPen(Qt.red, 3))
        else:
            if node != self.selected_node:
                self.connect_nodes(self.selected_node, node)

            self.selected_node.setPen(QPen(Qt.black, 2))
            self.selected_node = None

    # ------------------------------------------------------

    def connect_nodes(self, n1, n2):

        # prevent duplicate edges
        if self.graph.has_edge(n1, n2):
            return

        connection = ConnectionLine(n1, n2)
        self.scene.addItem(connection)

        self.connection_items.append(connection)

        # store references on nodes
        n1.connections.append(connection)
        n2.connections.append(connection)

        self.graph.add_edge(n1, n2)

    # ------------------------------------------------------

    def run_simulation(self):

        if len(self.graph.nodes) == 0:
            print("System empty")
            return

        try:
            ordered_nodes = list(nx.topological_sort(self.graph))
        except:
            print("Cycle detected!")
            return

        signal = None
        source_found = False

        for node in ordered_nodes:
            comp_type = self.graph.nodes[node]["type"]

            # =========================
            # GAUSSIAN SOURCE
            # =========================
            if comp_type == "SOURCE":

                signal = SignalGenerator.gaussian_pulse(
                    peak_power=1,
                    width_ps=8,
                    chirp=0.2
                )

                source_found = True
                continue

            if signal is None:
                continue

            signal = Components.process(comp_type, signal)

        if not source_found:
            print("No Gaussian Source in system!")
            return

        self.power_plot.clear()
        self.chirp_plot.clear()

        self.power_plot.plot(signal.t, signal.power)
        self.chirp_plot.plot(signal.t, signal.chirp)


# ==========================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
