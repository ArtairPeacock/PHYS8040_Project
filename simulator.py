import numpy as np
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsTextItem, QGraphicsLineItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen, QPixmap

# ==========================================================
# Optical Physics
# ==========================================================

#optical signal class gets operated on by components
class OpticalSignal:
	#initialises the signal properties
    def __init__(self, t, field):
        self.t = t
        self.dt = t[1] - t[0]
        self.field = field
        self.total_dispersion = 0

    @property #shortcut for creating a getter or setter method
    def power(self):
        return np.abs(self.field) ** 2

class SignalGenerator:

    @staticmethod #makes the method independant of the object, no need to create object to use the method
    def gaussian_pulse(
        peak_power=1.0,
        width_ps=8,
        chirp=0.0,
        window_ps=100,
        samples=4096
    ):
		#calculates the time, amplitude, phase, and electric field, then applies to OpticalSignal
        t = np.linspace(-window_ps/2, window_ps/2, samples)
        amplitude = np.sqrt(peak_power) * np.exp(-(t**2)/(2*width_ps**2))
        phase = chirp * (t**2)/(2*width_ps**2)
        field = amplitude * np.exp(1j * phase)
        return OpticalSignal(t, field)

#defines the components and handles how each component interacts
#with the OpticalSignal class
class Components:
	
	#used with SMF and DCF to properly apply dispersion to signal
    @staticmethod
    def apply_dispersion(signal, beta2, length_km):

        N = len(signal.t)
        dt = signal.dt

		#return the discrete Fourier transform of frequencies N and timestep dt
        freq = np.fft.fftfreq(N, d=dt)
        omega = 2 * np.pi * freq #angular frequency

        spectrum = np.fft.fft(signal.field)

        dispersion_phase = np.exp(
            -1j * 0.5 * beta2 * length_km * omega**2
        )

		#calculates the new field and signal
        spectrum *= dispersion_phase
        signal.field = np.fft.ifft(spectrum)

        return signal

    @staticmethod
    def process(comp_type, signal, params):
		#components selected by checking the name of the component

		#Single Mode Fibre (SMF)
        if comp_type == "SMF":

            length_km = params.get("length", 50)
            alpha_db = params.get("alpha", 0.2)
            beta2 = params.get("beta2", 17)

			#calculate attenuation, applied to signal
            loss_linear = 10 ** (-alpha_db * length_km / 20)
            signal.field *= loss_linear

			#calculate dispersion, apply to signal
            signal.total_dispersion += beta2 * length_km
            signal = Components.apply_dispersion(signal, beta2, length_km)

		#Dispersion Compensating Fibre (DCF)
        elif comp_type == "DCF":

            beta2_dcf = params.get("beta2", -80)
            alpha_db = params.get("alpha", 0.5)

            total_disp = signal.total_dispersion

			#checks that beta coefficient is not 0
            if beta2_dcf == 0:
                print("DCF beta2 cannot be zero")
                return signal

			#calculates the correct length of DCF for dispersion compensation
            length_km = - total_disp / beta2_dcf

            loss_linear = 10 ** (-alpha_db * length_km / 20)
            signal.field *= loss_linear

            signal = Components.apply_dispersion(signal, beta2_dcf, length_km)

            signal.total_dispersion = 0

		#optical amplifier
        elif comp_type == "Amp":

            gain_db = params.get("gain_db", 20)
            gain_linear = 10 ** (gain_db / 20)
            
            #apply gain to the signal
            signal.field *= gain_linear

			#calculate the noise and add it to the signal
			#randn returns (len(signal.field)) number of random values in Gaussian distribution
            noise = 0.001 * (
                np.random.randn(len(signal.field))
                + 1j * np.random.randn(len(signal.field)) 
            )

            signal.field += noise

		#Optical Spectrum Analyser (OSA)
        elif comp_type == "OSA":
            return signal

		#Mach Zender Modulator (MZM)
        elif comp_type == "MZM":

            Vpi = params.get("Vpi", 1.0)
            V0 = params.get("V0", 1.0)
            freq = params.get("freq", 0.5)
            alpha = params.get("alpha", 2.0)

            Vt = V0 * np.sin(2 * np.pi * freq * signal.t)

			#calculate phase and amplitude, apply to signal
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

		#checks if there is no image in the path specified
        if pixmap.isNull():
            print(f"ERROR: Failed to load image: {image_path}")
            pixmap = QPixmap(80, 80)
            pixmap.fill(Qt.red)

        pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        super().__init__(pixmap)

        self.name = name
        self.main_window = main_window
        self.connections = []

		#sets properties (flags) of the pixmap object as true
		# | is bitwise OR operator
        self.setFlags(
            QGraphicsPixmapItem.ItemIsMovable |
            QGraphicsPixmapItem.ItemIsSelectable |
            QGraphicsPixmapItem.ItemSendsGeometryChanges
        )

        #label
        self.label = QGraphicsTextItem(name)
        self.label.setParentItem(self)

        text_rect = self.label.boundingRect()
        img_rect = self.boundingRect()

        self.label.setPos(
            (img_rect.width() - text_rect.width()) / 2,
            img_rect.height() + 5
        )

	#allows using the left mouse button to control things in the canvas
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.main_window.node_clicked(self)
        super().mouseReleaseEvent(event)

	#opens the parameter menu for each node
    def contextMenuEvent(self, event):
        self.main_window.open_parameter_dialog(self)

    def itemChange(self, change, value):
        if change == QGraphicsPixmapItem.ItemPositionChange:
            for connection in self.connections:
                connection.update_position()
        return super().itemChange(change, value)

#creates a connection line between two nodes, n1 and n2
class ConnectionLine(QGraphicsLineItem):
    def __init__(self, n1, n2):
        super().__init__()

        self.n1 = n1
        self.n2 = n2

		#can change the colour using Qt.x where x is the colour
        self.setPen(QPen(Qt.blue, 2))
        
        #allows lines to be selected and deleted
        self.setFlags(QGraphicsLineItem.ItemIsSelectable)
        self.update_position()

    def update_position(self):
        p1 = self.n1.sceneBoundingRect().center()
        p2 = self.n2.sceneBoundingRect().center()
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())
