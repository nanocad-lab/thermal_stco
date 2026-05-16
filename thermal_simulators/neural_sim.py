from .base import ThermalSimulator

class NeuralModelSim(ThermalSimulator):
    def simulate(self, box_list):
        raise NotImplementedError("NeuralModelSim not implemented")
