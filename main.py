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
    def __init__(self, t, field):
        self.t = t
        self.dt = t[1] - t[0]
        self.field = field  # complex field

    @property
    def power(self):
        return np.abs(self.field) ** 2


class SignalGenerator:

    @staticmethod
    def gaussian_pulse(
        peak_power=1.0,
        width_ps=8,
        chirp=0.0,
        window_ps=100,
        samples=4096
    ):
        t = np.linspace(-window_ps/2, window_ps/2, samples)
        amplitude = np.sqrt(peak_power) * np.exp(-(t**2)/(2*width_ps**2))
        phase = chirp * (t**2)/(2*width_ps**2)
        field = amplitude * np.exp(1j * phase)
        return OpticalSignal(t, field)


class Components:

    @staticmethod
    def apply_dispersion(signal, beta2, length_km):

        N = len(signal.t)
        dt = signal.dt

        freq = np.fft.fftfreq(N, d=dt)
        omega = 2 * np.pi * freq

        spectrum = np.fft.fft(signal.field)

        dispersion_phase = np.exp(
            -1j * 0.5 * beta2 * length_km * omega**2
        )

        spectrum *= dispersion_phase
        signal.field = np.fft.ifft(spectrum)

        return signal

    @staticmethod
    def process(comp_type, signal):

        if comp_type == "SMF":

            length_km = 50
            alpha_db = 0.2
            beta2 = 17  # ps^2/km

            loss_linear = 10 ** (-alpha_db * length_km / 20)
            signal.field *= loss_linear

            signal = Components.apply_dispersion(signal, beta2, length_km)

        elif comp_type == "DCF":

            length_km = 10
            alpha_db = 0.5
            beta2 = -80

            loss_linear = 10 ** (-alpha_db * length_km / 20)
            signal.field *= loss_linear

            signal = Components.apply_dispersion(signal, beta2, length_km)

        elif comp_type == "Amp":

            gain_db = 20
            gain_linear = 10 ** (gain_db / 20)
            signal.field *= gain_linear

            noise = 0.001 * (
                np.random.randn(len(signal.field))
                + 1j * np.random.randn(len(signal.field))
            )

            signal.field += noise

        elif comp_type == "OSA":
            return signal

        elif comp_type == "MZM":
            modulation_depth = 0.8
            power = signal.power
            power *= (1 + modulation_depth * np.sin(0.2 * signal.t))

        elif comp_type == "Booster":
            gain_db = 10
            gain_linear = 10 ** (gain_db / 20)
            signal.field *= gain_linear

        return signal


# ==========================================================
# Graphics Node
# ==========================================================

class ComponentNode(QGraphicsRectItem):
    def __init__(self, name):
        super().__init__(0, 0, 100, 50)

        self.name = name
        self.connections = []

        self.setBrush(QColor("#e6f2ff"))
        self.setPen(QPen(Qt.black, 2))

        self.setFlags(
            QGraphicsRectItem.ItemIsMovable |
            QGraphicsRectItem.ItemIsSelectable |
            QGraphicsRectItem.ItemSendsGeometryChanges
        )

        self.label = QGraphicsTextItem(name, self)
        self.label.setDefaultTextColor(Qt.black)
        self.label.setPos(25, 15)

    def itemChange(self, change, value):

        if change == QGraphicsRectItem.ItemPositionChange:
            for connection in self.connections:
                connection.update_position()

        return super().itemChange(change, value)


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

    def _build_ui(self):

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

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

        self.scene = QGraphicsScene(0, 0, 1200, 400)
        self.view = QGraphicsView(self.scene)
        self.view.setBackgroundBrush(QColor("white"))
        main_layout.addWidget(self.view)

        self._draw_grid()

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

    def _draw_grid(self):
        grid = 25
        pen = QPen(QColor(230, 230, 230))

        for x in range(0, 1200, grid):
            self.scene.addLine(x, 0, x, 400, pen)

        for y in range(0, 400, grid):
            self.scene.addLine(0, y, 1200, y, pen)

    def add_component(self, name):

        node = ComponentNode(name)

        index = len(self.graph.nodes)

        x_offset = 100 + (index % 6) * 150
        y_offset = 80 + (index // 6) * 120

        node.setPos(x_offset, y_offset)
        self.scene.addItem(node)

        comp_type = "SOURCE" if name == "Gaussian Pulse" else name
        self.graph.add_node(node, type=comp_type)

        node.mousePressEvent = lambda event, n=node: self.node_clicked(n)

    def node_clicked(self, node):

        if self.selected_node is None:
            self.selected_node = node
            node.setPen(QPen(Qt.red, 3))
        else:
            if node != self.selected_node:
                self.connect_nodes(self.selected_node, node)

            self.selected_node.setPen(QPen(Qt.black, 2))
            self.selected_node = None

    def connect_nodes(self, n1, n2):

        if self.graph.has_edge(n1, n2):
            return

        if n1 == n2:
            return

        connection = ConnectionLine(n1, n2)
        self.scene.addItem(connection)

        self.connection_items.append(connection)
        n1.connections.append(connection)
        n2.connections.append(connection)

        # Ensure both nodes exist with attributes
        if n1 not in self.graph:
            return
        if n2 not in self.graph:
            return

        self.graph.add_edge(n1, n2)

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
            node_data = self.graph.nodes[node]
            comp_type = node_data.get("type", None)

            if comp_type is None:
                continue

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

        self.power_plot.plot(signal.t, signal.power, pen=pg.mkPen('b', width=2))

        phase = np.unwrap(np.angle(signal.field))
        chirp = np.gradient(phase, signal.dt)

        self.chirp_plot.plot(signal.t, chirp, pen=pg.mkPen('r', width=2))

    def keyPressEvent(self, event):

        if event.key() == Qt.Key_Delete:

            for item in self.scene.selectedItems():

                if isinstance(item, ComponentNode):
                    self.delete_component(item)

                elif isinstance(item, ConnectionLine):
                    self.delete_connection(item)

        else:
            super().keyPressEvent(event)

    def delete_component(self, node):

        for connection in list(node.connections):
            self.delete_connection(connection)

        if node in self.graph:
            self.graph.remove_node(node)

        self.scene.removeItem(node)

    def delete_connection(self, connection):

        n1 = connection.n1
        n2 = connection.n2

        if self.graph.has_edge(n1, n2):
            self.graph.remove_edge(n1, n2)

        if connection in n1.connections:
            n1.connections.remove(connection)

        if connection in n2.connections:
            n2.connections.remove(connection)

        if connection in self.connection_items:
            self.connection_items.remove(connection)

        self.scene.removeItem(connection)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
