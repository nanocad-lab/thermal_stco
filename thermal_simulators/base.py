from abc import ABC, abstractmethod

class ThermalSimulator(ABC):
    @abstractmethod
    def simulate(self, box_list):
        pass
