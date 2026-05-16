# dedeepyo : 3-Feb-2025 : Implementing heatsink XML parser.
import math
import xml.etree.ElementTree as ET
import sys
import yaml

class HeatSink:
    def __init__(self, name, material, fin_height, fin_thickness, fin_count, fin_offset, base_thickness, base_width, base_length, hc, fluid_speed, bind_to_ambient, cooled_by):
        self.name = name
        self.material = material
        self.fin_height = fin_height
        self.fin_thickness = fin_thickness
        self.fin_count = fin_count
        self.fin_offset = fin_offset
        self.base_thickness = base_thickness
        self.base_width = base_width
        self.base_length = base_length
        self.hc = hc
        self.fluid_speed = fluid_speed
        self.bind_to_ambient = bind_to_ambient
        self.cooled_by = cooled_by

    def set_name(self, name):
        self.name = name

    def set_material(self, material):
        self.material = material

    def set_fin_height(self, fin_height):
        self.fin_height = fin_height

    def set_fin_thickness(self, fin_thickness):
        self.fin_thickness = fin_thickness

    def set_fin_count(self, fin_count):
        self.fin_count = fin_count

    def set_fin_offset(self, fin_offset):
        self.fin_offset = fin_offset

    def set_base_thickness(self, base_thickness):
        self.base_thickness = base_thickness

    def set_base_width(self, base_width):
        self.base_width = base_width

    def set_base_length(self, base_length):
        self.base_length = base_length

    def set_hc(self, hc):
        self.hc = hc

    def set_fluid_speed(self, fluid_speed):
        self.fluid_speed = fluid_speed

    def set_bind_to_ambient(self, bind_to_ambient):
        self.bind_to_ambient = bind_to_ambient

    def set_cooled_by(self, cooled_by):
        self.cooled_by = cooled_by

    def get_name(self):
        return self.name
    
    def get_material(self):
        return self.material
    
    def get_fin_height(self):
        return self.fin_height
    
    def get_fin_thickness(self):
        return self.fin_thickness
    
    def get_fin_count(self):
        return self.fin_count
    
    def get_fin_offset(self):
        return self.fin_offset
    
    def get_base_thickness(self):
        return self.base_thickness
    
    def get_base_width(self):
        return self.base_width
    
    def get_base_length(self):
        return self.base_length
    
    def get_hc(self):
        return self.hc
    
    def get_fluid_speed(self):
        return self.fluid_speed
    
    def get_bind_to_ambient(self):
        return self.bind_to_ambient
    
    def get_cooled_by(self):    
        return self.cooled_by
    
    def __str__(self):
        return f"Heatsink name: {self.name}, Material: {self.material}, Fin height: {self.fin_height}, Fin thickness: {self.fin_thickness}, Fin count: {self.fin_count}, Fin offset: {self.fin_offset}, Base thickness: {self.base_thickness}, Base width: {self.base_width}, Base length: {self.base_length}, Heat Transfer Coefficient: {self.hc}, Fluid speed: {self.fluid_speed}, Bind to ambient: {self.bind_to_ambient}, Cooled by: {self.cooled_by}"

# Assuming only a single heatsink is used in a design.
def heatsink_definition_list_from_file(filename):
    # print("Reading heatsink definitions from file: " + filename)
    # Read the XML file.
    tree = ET.parse(filename)
    root = tree.getroot()
    # Create a list of heatsink objects.
    heatsink_list = []
    # Iterate over the heatsink definitions.
    for heatsink_def in root:
        # Create an heatsink object.
        heatsink = HeatSink(name = "", material = "", fin_height = 0.0, fin_thickness = 0.0, fin_count = 0, fin_offset = 0.0, base_thickness = 0.0, base_width = 0.0, base_length = 0.0, hc = 0.0, fluid_speed = 0.0, bind_to_ambient = 0.0, cooled_by = 0.0)
        
        attributes = heatsink_def.attrib

        heatsink.set_name(attributes["name"])
        heatsink.set_material(attributes["material"])
        heatsink.set_fin_height(float(attributes["fin_height"] or 0.00))
        heatsink.set_fin_thickness(float(attributes["fin_thickness"] or 0.00))
        heatsink.set_fin_count(int(attributes["fin_count"] or 0))
        heatsink.set_fin_offset(float(attributes["fin_offset"] or 0.00))
        heatsink.set_base_thickness(float(attributes["base_thickness"] or 0.00))
        heatsink.set_base_width(float(attributes["base_width"] or 0.00))
        heatsink.set_base_length(float(attributes["base_length"] or 0.00))
        heatsink.set_hc(float(attributes["hc"] or 0.00))
        heatsink.set_fluid_speed(float(attributes["fluid_speed"] or 0.00))
        heatsink.set_cooled_by(attributes["cooled_by"])
        
        if(attributes["bind_to_ambient"] == "True"):
            heatsink.set_bind_to_ambient(True)
        elif(attributes["bind_to_ambient"] == "False"):
            heatsink.set_bind_to_ambient(False)
        else:
            print("Error: bind_to_ambient should be either True or False.")
        
        if(heatsink.get_cooled_by() == "air"):
            if(heatsink.get_name() == "heatsink_air_cooled"):
                v = heatsink.get_fluid_speed()
                if(v != 0.00):
                    if(v > 29.00):
                        raise ValueError("Air speed cannot be greater than 29.00 m/s.")
                    elif(attributes["hc"] != "" and attributes["fluid_speed"] != ""):
                        raise Exception("Both hc and fluid_speed cannot be specified.")
                    else:
                        hc = 12.12 - 1.16 * v + 11.6 * math.sqrt(v)
                        heatsink.set_hc(hc)

        # Append the heatsink object to the list.
        heatsink_list.append(heatsink)
    # Return the list of heatsink objects.
    return heatsink_list

if __name__ == "__main__":
    heatsink_list = heatsink_definition_list_from_file("configs/thermal-configs/heatsink_definitions.xml")
    for heatsink in heatsink_list:
        print(heatsink)
        # if(heatsink.get_bind_to_ambient()):
        #     print("Heatsink is bound to ambient.")
        # else:
        #     print("Heatsink is not bound to ambient.")

# dedeepyo : 4-Feb-2025