import math
import xml.etree.ElementTree as ET
import sys
import yaml

# dedeepyo : 7-Feb-2025 : Implementing bonding XML parser.
class Bonding:
    def __init__(self, name = "", material = "", shape = "", diameter = 0.00000, cross_section_area = 0.00000, pitch = 0.00000, offset = 0.00000, height = 0.00000):
        self.name = name
        self.material = material
        self.shape = shape
        self.diameter = diameter
        self.cross_section_area = cross_section_area
        self.pitch = pitch
        self.offset = offset
        self.height = height

    def set_name(self, name):    
        self.name = name

    def set_material(self, material):
        self.material = material

    def set_shape(self, shape):
        self.shape = shape

    def set_diameter(self, diameter):
        self.diameter = diameter

    def set_cross_section_area(self, cross_section_area):
        self.cross_section_area = cross_section_area

    def set_pitch(self, pitch):
        self.pitch = pitch

    def set_offset(self, offset):
        self.offset = offset

    def set_height(self, height):
        self.height = height

    def get_name(self):
        return self.name
    
    def get_material(self):
        return self.material
    
    def get_shape(self):
        return self.shape
    
    def get_diameter(self):
        return self.diameter
    
    def get_cross_section_area(self):
        return self.cross_section_area
    
    def get_pitch(self):    
        return self.pitch
    
    def get_offset(self):    
        return self.offset
    
    def get_height(self):    
        return self.height

    def __str__(self):
        return f"Bonding(name={self.name}, material={self.material}, shape={self.shape}, diameter={self.diameter}, cross_section_area={self.cross_section_area}, pitch={self.pitch}, offset={self.offset}, height={self.height})"
    


def bonding_definition_list_from_file(filename):
    # print("Reading bonding definitions from file: " + filename)
    # Read the XML file.
    tree = ET.parse(filename)
    root = tree.getroot()
    # Create a list of bonding objects.
    bonding_list = []
    # Iterate over the bonding definitions.
    for bonding_def in root:
        bonding = Bonding("", "", "", 0.00, 0.00, 0.00, 0.00, 0.00)

        attributes = bonding_def.attrib

        bonding.set_name(attributes["name"])
        bonding.set_material(attributes["material"])
        bonding.set_shape(attributes["shape"])
        bonding.set_diameter(float(attributes["diameter"] or 0.00))
        bonding.set_cross_section_area(float(attributes["cross_section_area"] or 0.00))
        bonding.set_pitch(float(attributes["pitch"] or 0.00))
        bonding.set_offset(float(attributes["offset"] or 0.00))
        bonding.set_height(float(attributes["height"] or 0.00))

        if( bonding.get_shape() == "sphere"):
            bonding.set_height(bonding.get_diameter())

        bonding_list.append(bonding)
        
    return bonding_list

if __name__ == "__main__":
    bonding_list = bonding_definition_list_from_file("configs/thermal-configs/bonding_definitions.xml")
    for bonding in bonding_list:
        print(bonding)

# dedeepyo : 7-Feb-2025