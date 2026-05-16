from .anemoi_sim import AnemoiSim
from .neural_sim import NeuralModelSim

class SimulatorFactory:
    @staticmethod
    def get_simulator(type, name):
        if type == 'Anemoi':
            return AnemoiSim(name = name)
        elif type == 'NeuralModel':
            return NeuralModelSim()
        else:
            raise ValueError("Unsupported simulator type")
