import numpy as np
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsTextItem, QGraphicsLineItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen, QPixmap


# ==========================================================
# Optical Physics
# ==========================================================

class OpticalSignal:
    def __init__(self, t, field):
        self.t = t
        self.dt = t[1] - t[0]
        self.field = field
        self.total_dispersion = 0

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
    def process(comp_type, signal, params):

        if comp_type == "SMF":

            length_km = params.get("length", 50)
            alpha_db = params.get("alpha", 0.2)
            beta2 = params.get("beta2", 17)

            loss_linear = 10 ** (-alpha_db * length_km / 20)
            signal.field *= loss_linear

            signal.total_dispersion += beta2 * length_km
            signal = Components.apply_dispersion(signal, beta2, length_km)

        elif comp_type == "DCF":

            beta2_dcf = params.get("beta2", -80)
            alpha_db = params.get("alpha", 0.5)

            total_disp = signal.total_dispersion

            if beta2_dcf == 0:
                print("DCF beta2 cannot be zero")
                return signal

            length_km = - total_disp / beta2_dcf

            loss_linear = 10 ** (-alpha_db * length_km / 20)
            signal.field *= loss_linear

            signal = Components.apply_dispersion(signal, beta2_dcf, length_km)

            signal.total_dispersion = 0

        elif comp_type == "Amp":

            gain_db = params.get("gain_db", 20)
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

            Vpi = params.get("Vpi", 1.0)
            V0 = params.get("V0", 1.0)
            freq = params.get("freq", 0.5)
            alpha = params.get("alpha", 2.0)

            Vt = V0 * np.sin(2 * np.pi * freq * signal.t)

            amplitude = np.cos(np.pi * Vt / (2 * Vpi))
            phase = alpha * np.sin(2 * np.pi * freq * signal.t)

            signal.field *= amplitude * np.exp(1j * phase)

        return signal


# ==========================================================
# Graphics
# ==========================================================

class ComponentNode(QGraphicsPixmapItem):
    def __init__(self, name, image_path, main_window):
        pixmap = QPixmap(image_path)

        if pixmap.isNull():
            print(f"ERROR: Failed to load image: {image_path}")
            pixmap = QPixmap(80, 80)
            pixmap.fill(Qt.red)

        pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        super().__init__(pixmap)

        self.name = name
        self.main_window = main_window
        self.connections = []

        self.setFlags(
            QGraphicsPixmapItem.ItemIsMovable |
            QGraphicsPixmapItem.ItemIsSelectable |
            QGraphicsPixmapItem.ItemSendsGeometryChanges
        )

        # Label
        self.label = QGraphicsTextItem(name)
        self.label.setParentItem(self)

        text_rect = self.label.boundingRect()
        img_rect = self.boundingRect()

        self.label.setPos(
            (img_rect.width() - text_rect.width()) / 2,
            img_rect.height() + 5
        )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.main_window.node_clicked(self)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        self.main_window.open_parameter_dialog(self)

    def itemChange(self, change, value):
        if change == QGraphicsPixmapItem.ItemPositionChange:
            for connection in self.connections:
                connection.update_position()
        return super().itemChange(change, value)


class ConnectionLine(QGraphicsLineItem):
    def __init__(self, n1, n2):
        super().__init__()

        self.n1 = n1
        self.n2 = n2

        self.setPen(QPen(Qt.blue, 2))
        self.update_position()

    def update_position(self):
        p1 = self.n1.sceneBoundingRect().center()
        p2 = self.n2.sceneBoundingRect().center()
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())
