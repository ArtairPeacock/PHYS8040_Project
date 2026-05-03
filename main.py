import sys
import numpy as np
import networkx as nx

from simulator import (
    OpticalSignal,
    SignalGenerator,
    Components,
    ComponentNode,
    ConnectionLine
)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton,
    QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsLineItem, QDialog, QFormLayout, 
    QLineEdit, QDialogButtonBox, QFileDialog,
    QGraphicsPixmapItem
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPen, QColor, QPixmap
from pyqtgraph.exporters import ImageExporter
import pyqtgraph as pg

# ==========================================================
# Main Window
# ==========================================================

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
       
        #define the paths to the symbol assests
        self.symbols = {
        "Gaussian Pulse": "symbols/gasussian_pulse_symbol.png",
        "SMF": "symbols/single_mode_fibre_symbol.png",
        "DCF": "symbols/dispersion_compensating_fibre_symbol.png",
        "Amp": "symbols/optical_amplifier_symbol.png",
        "MZM": "symbols/mach_zender_modulator_symbol.png",
        "Booster": "symbols/booster.png",
        "OSA": "symbols/optical_spectrum_analyser_symbol.png"
        }

		#container to keep track of which components are connected
        self.connection_items = []
        self.component_counter = 0
		
		#sets the size of the window, and initalises the graphs
        self.setWindowTitle("Fibre Optic Simulator")
        self.setGeometry(100, 100, 1300, 800)

        self.graph = nx.DiGraph()
        self.selected_node = None

        self._build_ui()

    def _build_ui(self):

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central) #stacks elements of layout vertically

        plot_layout = QHBoxLayout() #makes a horizontal box layout for plots

		#creating the power and chirp plots to add to plot_layout
        self.power_plot = pg.PlotWidget(title="OPTICAL POWER")
        self.power_plot.showGrid(x=True, y=True)
        self.power_plot.setLabel("bottom", "Time (ps)")
        self.power_plot.setLabel("left", "Power (mW)")

        self.chirp_plot = pg.PlotWidget(title="FREQUENCY CHIRP")
        self.chirp_plot.showGrid(x=True, y=True)
        self.chirp_plot.setLabel("bottom", "Time (ps)")
        self.chirp_plot.setLabel("left", "Chirp (Hz/s)")

		#adding plots to the layout, then layout to the main window
        plot_layout.addWidget(self.power_plot)
        plot_layout.addWidget(self.chirp_plot)
        main_layout.addLayout(plot_layout)

		#creates the canvas area, and adds it to the main window
        self.scene = QGraphicsScene(0, 0, 1200, 400) #x, y, width, height of canvas area
        self.view = QGraphicsView(self.scene)
        self.view.setBackgroundBrush(QColor("white"))
        main_layout.addWidget(self.view)

        self._draw_grid()

        toolbar = QHBoxLayout()

        components = ["Gaussian Pulse", "SMF", "DCF", "Amp", "MZM", "OSA"]

        for name in components:
            btn = QPushButton(name)
            #lambda used to code behaviour of button cleanly
            btn.clicked.connect(lambda checked, n=name: self.add_component(n))
            toolbar.addWidget(btn)

		#pushes buttons to bottom of the GUI, by creating space above them
        toolbar.addStretch() 

		#defining buttons, then adding to toolbar, toolbar then added to main layout
        run_btn = QPushButton("RUN")
        run_btn.setStyleSheet("color: red; font-weight: bold;")
        run_btn.clicked.connect(self.run_simulation)
        toolbar.addWidget(run_btn)

        save_btn = QPushButton("SAVE PLOTS")
        save_btn.clicked.connect(self.save_plots)
        toolbar.addWidget(save_btn)
        
        exit_btn = QPushButton("EXIT")
        exit_btn.clicked.connect(self.close)
        toolbar.addWidget(exit_btn)

        main_layout.addLayout(toolbar)

	#draws the grids of the canvas area
    def _draw_grid(self):
        grid = 25
        pen = QPen(QColor(230, 230, 230))

        for x in range(0, 1200, grid):
            self.scene.addLine(x, 0, x, 400, pen)

        for y in range(0, 400, grid):
            self.scene.addLine(0, y, 1200, y, pen)

    def add_component(self, name):
		
		#adds selected component to the canvas with default properties
        if name == "Gaussian Pulse":
            comp_type = "SOURCE"
            params = {"peak_power": 1, "width": 8, "chirp": 0.2}

        elif name == "MZM":
            comp_type = "MZM"
            params = {"Vpi": 1, "V0": 1, "freq": 0.5, "alpha": 2.0}

        elif name == "SMF":
            comp_type = "SMF"
            params = {"length": 50, "alpha": 0.2, "beta2": 17}
            
        elif name == "DCF":
            comp_type = "DCF"
            params = {"length": 10, "alpha": 0.5, "beta2": -80}
            
        elif name == "Amp":
            comp_type = "Amp"
            params = {"gain_db": 20}
      
        else:
            comp_type = name
            params = {}

		#loads the image for the respective component
        image_path = self.symbols.get(name, None)

        if image_path is None:
            print(f"No symbol for {name}")
            return

        node = ComponentNode(name, image_path, self)
        
        self.graph.add_node(node, type=comp_type, params=params)

        index = len(self.graph.nodes)
		
		#defining position on the canvas, sets the position
		#then addes the node to the canvas
        x_offset = 100 + (index % 6) * 150
        y_offset = 80 + (index // 6) * 120

        node.setPos(x_offset, y_offset)
        self.scene.addItem(node)

    def node_clicked(self, node):

		#selects current node if there is no node selected
        if self.selected_node is None:
            self.selected_node = node
            node.setOpacity(0.6)  #visual feedback

        else:
            if node != self.selected_node:
                self.connect_nodes(self.selected_node, node)

            self.selected_node.setOpacity(1.0)
            self.selected_node = None

	#method for connecting nodes
    def connect_nodes(self, n1, n2):
		#nodes are n1 and n2
		
        if self.graph.has_edge(n1, n2):
            return

        if n1 == n2:
            return

		#defines the connection between n1 and n2, adds the connection
		#to the canvas and adds the connection to the signal path
		#in connection_items
        connection = ConnectionLine(n1, n2)
        self.scene.addItem(connection)

        self.connection_items.append(connection)
        n1.connections.append(connection)
        n2.connections.append(connection)

        #ensure both nodes exist with attributes
        if n1 not in self.graph:
            return
        if n2 not in self.graph:
            return

        self.graph.add_edge(n1, n2)
        
    #method for parameter dialog
    def open_parameter_dialog(self, node):

		#define the dialog menu and the parameters you can change
        data = self.graph.nodes[node]
        params = data.get("params", {})

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{node.name} Parameters")

        layout = QFormLayout(dialog)

        inputs = {}

		#gets the parameters for the node types and 
		#adds them to the dialog menu
        for key, value in params.items():
            line = QLineEdit(str(value))
            layout.addRow(key, line)
            inputs[key] = line

		#buttons in the parameter menu
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        layout.addWidget(buttons)

		#defines save when changing the parameters of a node
        def save():
            for key in inputs:
                try:
                    params[key] = float(inputs[key].text())
                except:
                    pass
            dialog.accept()

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)

        dialog.exec()

    def run_simulation(self):
		
		#checks if there are no nodes in the canvas
        if len(self.graph.nodes) == 0:
            print("System empty")
            return

		#checks there are nodes in the canvas
        try:
            ordered_nodes = list(nx.topological_sort(self.graph))
        except:
            print("Cycle detected!")
            return

        signal = None
        source_found = False

		#loops through the list of nodes in the canvas
		#and applies the process to the signal
        for node in ordered_nodes:
            node_data = self.graph.nodes[node]
            comp_type = node_data.get("type", None)
            params = node_data.get("params", {})

            if comp_type is None:
                continue
			
			#checks if the gaussian pulse in the canvas
            if comp_type == "SOURCE":
                signal = SignalGenerator.gaussian_pulse(
                    peak_power=params.get("peak_power", 1),
                    width_ps=params.get("width", 8),
                    chirp=params.get("chirp", 0.2)
                )
                source_found = True
                continue

            if signal is None:
                continue

            signal = Components.process(comp_type, signal, params)

		#if no source is in canvas, prints error message
        if not source_found:
            print("No Gaussian Source in system!")
            return

		#clears both plots, then replots with the newly calculated values
        self.power_plot.clear()
        self.chirp_plot.clear()

        self.power_plot.plot(signal.t, signal.power, pen=pg.mkPen('r', width=2))

        phase = np.unwrap(np.angle(signal.field))
        chirp = np.gradient(phase, signal.dt)

        self.chirp_plot.plot(signal.t, chirp, pen=pg.mkPen('b', width=2))

	#defines pressing a block for deleting connections and nodes
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
        
    def save_plots(self):

        #open file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Plots",
            "",
            "PNG Files (*.png);;All Files (*)"
        )

        if not file_path:
            return

        #ensure filename has no extension duplication
        base_path = file_path.replace(".png", "")

        #export power plot
        power_exporter = ImageExporter(self.power_plot.plotItem)
        power_exporter.export(base_path + "_power.png")

        #export chirp plot
        chirp_exporter = ImageExporter(self.chirp_plot.plotItem)
        chirp_exporter.export(base_path + "_chirp.png")

        print(f"Plots saved to:\n{base_path}_power.png\n{base_path}_chirp.png")

#launching the GUI
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
