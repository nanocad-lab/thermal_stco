import math
import xml.etree.ElementTree as ET
import sys
import yaml

def assembly_process_definition_list_from_file(filename):
    # print("Reading assembly process definitions from file: " + filename)
    # Read the XML file.
    tree = ET.parse(filename)
    root = tree.getroot()
    # Create a list of assembly process objects.
    assembly_process_list = []
    # Iterate over the assembly process definitions.
    for assembly_process_def in root:
        # Create an assembly process object.
        assembly_process = Assembly(name = "", materials_cost_per_mm2 = 0.0, picknplace_machine_cost = 0.0,
                                      picknplace_machine_lifetime = 0.0, picknplace_machine_uptime = 0.0, picknplace_technician_yearly_cost = 0.0,
                                      picknplace_time = 0.0, picknplace_group = 0, bonding_machine_cost = 0.0, bonding_machine_lifetime = 0.0,
                                      bonding_machine_uptime = 0.0, bonding_machine_technician_yearly_cost = 0.0, bonding_time = 0.0,
                                      bonding_group = 0, die_separation = 0.0, edge_exclusion = 0.0, bonding_pitch = 0.0, max_pad_current_density = 0.0,
                                      alignment_yield = 0.0, bonding_yield = 0.0, dielectric_bond_defect_density = 0.0, static = False)
        
        attributes = assembly_process_def.attrib

        assembly_process.set_name(attributes["name"])
#        # The following would set machine and technician parameters as a list of an undefined length.
#        # This has been switched to defining these parameters in terms of two values, one for bonding and one for pick and place.
#        # Leaving this for now, in case a reason comes up to rever to the old version.
#        assembly_process.set_machine_cost_list([float(x) for x in attributes["machine_cost_list"].split(',')])
#        assembly_process.set_machine_lifetime_list([float(x) for x in attributes["machine_lifetime_list"].split(',')])
#        assembly_process.set_machine_uptime_list([float(x) for x in attributes["machine_uptime_list"].split(',')])
#        assembly_process.set_technician_yearly_cost_list([float(x) for x in attributes["technician_yearly_cost_list"].split(',')])
        assembly_process.set_materials_cost_per_mm2(float(attributes["materials_cost_per_mm2"]))
        assembly_process.set_picknplace_machine_cost(float(attributes["picknplace_machine_cost"]))
        assembly_process.set_picknplace_machine_lifetime(float(attributes["picknplace_machine_lifetime"]))
        assembly_process.set_picknplace_machine_uptime(float(attributes["picknplace_machine_uptime"]))
        assembly_process.set_picknplace_technician_yearly_cost(float(attributes["picknplace_technician_yearly_cost"]))
        assembly_process.set_picknplace_time(float(attributes["picknplace_time"]))
        assembly_process.set_picknplace_group(int(attributes["picknplace_group"]))
        assembly_process.set_bonding_machine_cost(float(attributes["bonding_machine_cost"]))
        assembly_process.set_bonding_machine_lifetime(float(attributes["bonding_machine_lifetime"]))
        assembly_process.set_bonding_machine_uptime(float(attributes["bonding_machine_uptime"]))
        assembly_process.set_bonding_technician_yearly_cost(float(attributes["bonding_technician_yearly_cost"]))
        assembly_process.set_bonding_time(float(attributes["bonding_time"]))
        assembly_process.set_bonding_group(int(attributes["bonding_group"]))
        assembly_process.compute_picknplace_cost_per_second()
        assembly_process.compute_bonding_cost_per_second()
        assembly_process.set_die_separation(float(attributes["die_separation"]))
        assembly_process.set_edge_exclusion(float(attributes["edge_exclusion"]))
        assembly_process.set_bonding_pitch(float(attributes["bonding_pitch"]))
        assembly_process.set_max_pad_current_density(float(attributes["max_pad_current_density"]))
        assembly_process.set_alignment_yield(float(attributes["alignment_yield"]))
        assembly_process.set_bonding_yield(float(attributes["bonding_yield"]))
        assembly_process.set_dielectric_bond_defect_density(float(attributes["dielectric_bond_defect_density"]))

        assembly_process.set_static()

        # Append the assembly process object to the list.
        assembly_process_list.append(assembly_process)
    # Return the list of assembly process objects.
    return assembly_process_list


class Assembly:
    def __init__(self, name = "", materials_cost_per_mm2 = None, picknplace_machine_cost = None,
                 picknplace_machine_lifetime = None, picknplace_machine_uptime = None, picknplace_technician_yearly_cost = None,
                 picknplace_time = None, picknplace_group = None, bonding_machine_cost = None, bonding_machine_lifetime = None,
                 bonding_machine_uptime = None, bonding_machine_technician_yearly_cost = None, bonding_time = None,
                 bonding_group = None, die_separation = None, edge_exclusion = None, max_pad_current_density = None,
                 bonding_pitch = None, alignment_yield = None, bonding_yield = None, dielectric_bond_defect_density = None,
                 static = True) -> None:
#    def __init__(self, name = "", machine_cost_list = [], machine_lifetime_list = [], machine_uptime_list = [], technician_yearly_cost_list = [], materials_cost_per_mm2 = None, picknplace_time = None, picknplace_group = None, bonding_time = None, bonding_group = None, die_separation = None, edge_exclusion = None, max_pad_current_density = None, bonding_pitch = None, alignment_yield = None, bonding_yield = None, dielectric_bond_defect_density = None, static = True) -> None:
        self.name = name
#        self.machine_cost_list = machine_cost_list
#        self.machine_lifetime_list = machine_lifetime_list
#        self.machine_uptime_list = machine_uptime_list
#        self.technician_yearly_cost_list = technician_yearly_cost_list
        self.materials_cost_per_mm2 = materials_cost_per_mm2
        self.picknplace_machine_cost = picknplace_machine_cost
        self.picknplace_machine_lifetime = picknplace_machine_lifetime
        self.picknplace_machine_uptime = picknplace_machine_uptime
        self.picknplace_technician_yearly_cost = picknplace_technician_yearly_cost
        self.picknplace_time = picknplace_time
        self.picknplace_group = picknplace_group
        self.bonding_machine_cost = bonding_machine_cost
        self.bonding_machine_lifetime = bonding_machine_lifetime
        self.bonding_machine_uptime = bonding_machine_uptime
        self.bonding_machine_technician_yearly_cost = bonding_machine_technician_yearly_cost
        self.bonding_time = bonding_time
        self.bonding_group = bonding_group
        self.die_separation = die_separation                # Given Parameter
        self.edge_exclusion = edge_exclusion                # Given Parameter
        self.max_pad_current_density = max_pad_current_density  # Given Parameter
        self.bonding_pitch = bonding_pitch
        self.picknplace_cost_per_second = None
        self.bonding_cost_per_second = None
        self.bonding_yield = bonding_yield
        self.alignment_yield = alignment_yield
        self.dielectric_bond_defect_density = dielectric_bond_defect_density
        self.static = static
        if self.name == "" or self.machine_cost_list == [] or self.machine_lifetime_list == [] or self.machine_uptime_list == [] or self.technician_yearly_cost_list == [] or self.materials_cost_per_mm2 is None or self.picknplace_time is None or self.picknplace_group is None or self.bonding_time is None or self.bonding_group is None:
            # print("Warning: Assembly not fully defined. Setting non-static.")
            self.static = False
            # print("Assembly process " + self.name + " has parameters machine_cost_list = " + str(self.machine_cost_list) + ", machine_lifetime_list = " + str(self.machine_lifetime_list) + ", machine_uptime_list = " + str(self.machine_uptime_list) + ", technician_yearly_cost_list = " + str(self.technician_yearly_cost_list) + ", materials_cost_per_mm2 = " + str(self.materials_cost_per_mm2) + ", picknplace_time = " + str(self.picknplace_time) + ", picknplace_group = " + str(self.picknplace_group) + ", bonding_time = " + str(self.bonding_time) + ", bonding_group = " + str(self.bonding_group) + ".")
        else:
            self.compute_picknplace_cost_per_second()
            self.compute_bonding_cost_per_second()
            self.static = False
        
        return

    # ====== Get/Set Functions ======

    def get_name(self) -> str:
        return self.name

    def set_name(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.name = value
            return 0
    
#    def get_machine_cost_list_len(self) -> int:
#        return len(self.machine_cost_list)
#
#    def get_machine_cost_list(self) -> list:
#        return self.machine_cost_list
#
#    def set_machine_cost_list(self, value) -> int:
#        if (self.static):
#            print("Error: Cannot change static assembly process.")
#            return 1
#        else:
#            self.machine_cost_list = value
#            return 0
#    
#    def get_machine_cost(self, index) -> float:
#        return self.machine_cost_list[index]
#
#    def set_machine_cost(self, index, value) -> int:
#        if (self.static):
#            print("Error: Cannot change static assembly process.")
#            return 1
#        else:
#            self.machine_cost_list[index] = value
#            return 0
#
#    def set_machine_lifetime_list(self, value) -> int:
#        if (self.static):
#            print("Error: Cannot change static assembly process.")
#            return 1
#        else:
#            self.machine_lifetime_list = value
#            return 0
#    
#    def get_machine_lifetime(self, index) -> float:
#        return self.machine_lifetime_list[index]
#
#    def set_machine_lifetime(self, index, value) -> int:
#        if (self.static):
#            print("Error: Cannot change static assembly process.")
#            return 1
#        else:
#            self.machine_lifetime_list[index] = value
#            return 0
#    
#    def get_machine_uptime_list_len(self) -> int:
#        return len(self.machine_uptime_list)
#
#    def get_machine_uptime_list(self) -> list:
#        return self.machine_uptime_list
#
#    def set_machine_uptime_list(self, value) -> int:
#        if (self.static):
#            print("Error: Cannot change static assembly process.")
#            return 1
#        else:
#            self.machine_uptime_list = value
#            return 0
#    
#    def get_machine_uptime(self, index) -> float:
#        return self.machine_uptime_list[index]
#
#    def set_machine_uptime(self, index, value) -> int:
#        if (self.static):
#            print("Error: Cannot change static assembly process.")
#            return 1
#        else:
#            self.machine_uptime_list[index] = value
#            return 0
#
#    def get_technician_yearly_cost_list_len(self) -> int:
#        return len(self.technician_yearly_cost_list)
#
#    def get_technician_yearly_cost_list(self) -> list:
#        return self.technician_yearly_cost_list
#
#    def set_technician_yearly_cost_list(self, value) -> int:
#        if (self.static):
#            print("Error: Cannot change static assembly process.")
#            return 1
#        else:
#            self.technician_yearly_cost_list = value
#            return 0
#    
#    def get_technician_yearly_cost(self, index) -> float:
#        return self.technician_yearly_cost_list[index]
#
#    def set_technician_yearly_cost(self, index, value) -> int:
#        if (self.static):
#            print("Error: Cannot change static assembly process.")
#            return 1
#        else:
#            self.technician_yearly_cost_list[index] = value
#            return 0
    
    def get_materials_cost_per_mm2(self) -> float:
        return self.materials_cost_per_mm2

    def set_materials_cost_per_mm2(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.materials_cost_per_mm2 = value
            return 0
    
    def get_picknplace_machine_cost(self) -> float:
        return self.picknplace_machine_cost
    
    def set_picknplace_machine_cost(self, value) -> float:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.picknplace_machine_cost = value
            return 0

    def get_picknplace_machine_lifetime(self) -> float:
        return self.picknplace_machine_lifetime
    
    def set_picknplace_machine_lifetime(self, value) -> float:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.picknplace_machine_lifetime = value
            return 0
        
    def get_picknplace_machine_uptime(self) -> float:
        return self.picknplace_machine_uptime
    
    def set_picknplace_machine_uptime(self, value) -> float:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.picknplace_machine_uptime = value
            return 0 

    def get_picknplace_technician_yearly_cost(self) -> float:
        return self.picknplace_technician_yearly_cost
    
    def set_picknplace_technician_yearly_cost(self, value) -> float:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.picknplace_technician_yearly_cost = value
            return 0
    
    def get_picknplace_time(self) -> float:
        return self.picknplace_time

    def set_picknplace_time(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.picknplace_time = value
            return 0

    def get_picknplace_group(self) -> str:
        return self.picknplace_group

    def set_picknplace_group(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.picknplace_group = value
            return 0

    def get_bonding_machine_cost(self) -> float:
        return self.bonding_machine_cost
    
    def set_bonding_machine_cost(self, value) -> float:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.bonding_machine_cost = value
            return 0
        
    def get_bonding_machine_lifetime(self) -> float:
        return self.bonding_machine_lifetime
    
    def set_bonding_machine_lifetime(self, value) -> float:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.bonding_machine_lifetime = value
            return 0

    def get_bonding_machine_uptime(self) -> float:
        return self.bonding_machine_uptime

    def set_bonding_machine_uptime(self, value) -> float:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.bonding_machine_uptime = value
            return 0
 
    def get_bonding_technician_yearly_cost(self) -> float:
        return self.bonding_machine_technician_yearly_cost
    
    def set_bonding_technician_yearly_cost(self, value) -> float:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.bonding_machine_technician_yearly_cost = value
            return 0

    def get_bonding_time(self) -> float:
        return self.bonding_time

    def set_bonding_time(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.bonding_time = value
            return 0

    def get_bonding_group(self) -> str:
        return self.bonding_group

    def set_bonding_group(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static assembly process.")
            return 1
        else:
            self.bonding_group = value
            return 0

    def get_die_separation(self) -> float:
        return self.die_separation
    
    def set_die_separation(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static chip.")
            return 1
        else:
            self.die_separation = value
            return 0
        
    def get_edge_exclusion(self) -> float:
        return self.edge_exclusion
    
    def set_edge_exclusion(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static chip.")
            return 1
        else:
            self.edge_exclusion = value
            return 0

    def get_bonding_pitch(self) -> float:
        return self.bonding_pitch
    
    def set_bonding_pitch(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static chip.")
            return 1
        else:
            self.bonding_pitch = value
            return 0

    def get_max_pad_current_density(self) -> float:
        return self.max_pad_current_density
    
    def set_max_pad_current_density(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static chip.")
            return 1
        else:
            self.max_pad_current_density = value
            return 0

    def get_power_per_pad(self,core_voltage) -> float:
        pad_area = math.pi*(self.bonding_pitch/4)**2
        current_per_pad = self.max_pad_current_density*pad_area
        power_per_pad = current_per_pad*core_voltage
        return power_per_pad

    def get_alignment_yield(self) -> float:
        return self.alignment_yield
    
    def set_alignment_yield(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static chip.")
            return 1
        else:
            self.alignment_yield = value
            return 0
        
    def get_bonding_yield(self) -> float:
        return self.bonding_yield
    
    def set_bonding_yield(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static chip.")
            return 1
        else:
            self.bonding_yield = value
            return 0

    def get_dielectric_bond_defect_density(self) -> float:
        return self.dielectric_bond_defect_density
    
    def set_dielectric_bond_defect_density(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static chip.")
            return 1
        else:
            self.dielectric_bond_defect_density = value
            return 0

    def get_picknplace_cost_per_second(self) -> float:
        if self.picknplace_cost_per_second is None:
            self.compute_picknplace_cost_per_second()
        return self.picknplace_cost_per_second
    
    def set_picknplace_cost_per_second(self) -> int:
        self.picknplace_cost_per_second = self.compute_picknplace_cost_per_second()
        return 0

    def get_bonding_cost_per_second(self) -> float:
        if self.bonding_cost_per_second is None:
            self.compute_bonding_cost_per_second()
        return self.bonding_cost_per_second
    
    def set_bonding_cost_per_second(self) -> int:
        self.bonding_cost_per_second = self.compute_bonding_cost_per_second()
        return 0

    def get_static(self) -> bool:
        return self.static    

    def set_static(self) -> int:
        self.static = True
        return 0 

    # ===== End of Get/Set Functions =====

    # ===== Print Functions =====

    def print_description(self):
        print("Assembly Process Description:")
        print("\tPick and Place Group: " + str(self.get_picknplace_group()))
        print("\tPick and Place Time: " + str(self.get_picknplace_time()))
        print("\tBonding Group: " + str(self.get_bonding_group()))
        print("\tBonding Time: " + str(self.get_bonding_time()))
        print("\tMaterials Cost per mm2: " + str(self.get_materials_cost_per_mm2()))
        print("\tMachine Cost is " + str(self.get_picknplace_machine_cost()) + " for the picknplace machine and " + str(self.get_bonding_machine_cost()) + " for the bonding machine.")
        print("\tTechnician Yearly Cost is " + str(self.get_picknplace_technician_yearly_cost()) + " for picknplace and " + str(self.get_bonding_technician_yearly_cost()) + " for bonding.")
        print("\tMachine Uptime is " + str(self.get_picknplace_machine_uptime()) + " for the picknplace machine and " + str(self.get_bonding_machine_uptime()) + " for the bonding machine.")
        print("\tMachine Lifetime is " + str(self.get_picknplace_machine_lifetime()) + " for the picknplace machine and " + str(self.get_bonding_machine_lifetime()) + " for the bonding machine.")
        return

    # ===== End of Print Functions =====

    # repr / string
    def __repr__(self):
        # only name
        return self.name
    
    def __str__(self):
        # only name
        return self.name

    # ===== Other Functions =====

    def compute_picknplace_time(self, n_chips):
        picknplace_steps = math.ceil(n_chips/self.picknplace_group)
        time = self.picknplace_time*picknplace_steps
        return time
    
    def compute_bonding_time(self, n_chips):
        bonding_steps = math.ceil(n_chips/self.bonding_group)
        time = self.bonding_time*bonding_steps
        return time
    
    def assembly_time(self, n_chips):
        time = self.compute_picknplace_time() + self.compute_bonding_time()
        return time

    def compute_picknplace_cost_per_second(self):
        machine_cost_per_year = self.get_picknplace_machine_cost()/self.get_picknplace_machine_lifetime()
        technician_cost_per_year = self.get_picknplace_technician_yearly_cost()
        picknplace_cost_per_year = machine_cost_per_year + technician_cost_per_year
        picknplace_cost_per_second = picknplace_cost_per_year/(365*24*60*60)*self.get_picknplace_machine_uptime()
        self.picknplace_cost_per_second = picknplace_cost_per_second
        return picknplace_cost_per_second
    
    def compute_bonding_cost_per_second(self):
        machine_cost_per_year = self.get_bonding_machine_cost()/self.get_bonding_machine_lifetime()
        technician_cost_per_year = self.get_bonding_technician_yearly_cost()
        bonding_cost_per_year = machine_cost_per_year + technician_cost_per_year
        bonding_cost_per_second = bonding_cost_per_year/(365*24*60*60)*self.get_bonding_machine_uptime()
        self.bonding_cost_per_second = bonding_cost_per_second
        return bonding_cost_per_second

    # Assembly cost includes cost of machine time and materials cost.
    def assembly_cost(self, n_chips, area):
        # TODO: Remove critical bonds from the argument list here since yield is calculated elsewhere.
        assembly_cost = self.get_picknplace_cost_per_second()*self.compute_picknplace_time(n_chips) + self.get_bonding_cost_per_second()*self.compute_bonding_time(n_chips)
        assembly_cost += self.get_materials_cost_per_mm2()*area
        return assembly_cost

    def assembly_yield(self, n_chips, n_bonds, area):
        assem_yield = 1.0
        assem_yield *= self.alignment_yield**n_chips
        assem_yield *= self.bonding_yield**n_bonds

        # If hybrid bonding, there is some yield impact of the dielectric bond.
        # This uses a defect density and area number which approximates the negative binomial yield model with no clustering.
        dielectric_bond_area = area
        dielectric_bond_yield = 1 - self.get_dielectric_bond_defect_density()*dielectric_bond_area
        assem_yield *= dielectric_bond_yield

        return assem_yield

    # ===== End of Other Functions =====


def connection_definition_list_from_file(filename):
    # print("Reading IO definitions from file: " + filename)
    # Read the XML file.
    tree = ET.parse(filename)
    root = tree.getroot()
    connection_list = []
    # Iterate over the connection definitions.
    for connection_def in root:
        # Create a connection object.
        connection = Connection(block0 = "", block1 = "")
        attributes = connection_def.attrib
        connection.set_block0(attributes["block0"])
        connection.set_block1(attributes["block1"])
        # Append the connection object to the list.
        connection_list.append(connection)
    
    # Return the list of connection objects.
    return connection_list


class Connection:
    def __init__(self, block0 = "", block1 = "") -> None:
        self.block0 = block0
        self.block1 = block1

    # ====== Get/Set Functions ======

    def get_block0(self) -> str:
        return self.block0
    
    def set_block0(self, value) -> int:
        self.block0 = value
        return 0
    
    def get_block1(self) -> str:
        return self.block1
    
    def set_block1(self, value) -> int:
        self.block1 = value
        return 0

    # ===== End of Get/Set Functions =====
    
# dedeepyo : 17-Nov-2024 : Implementing counter for chiplet definition
def count_child_chiplets(floorplan_on_parent, floorplan_dict_on_parent):
    floorplan_on_parent = floorplan_on_parent.replace(" ", "")
    floorplan_on_parent = {c: floorplan_on_parent.count(c) for c in floorplan_on_parent}
    floorplan_dict_on_parent = floorplan_dict_on_parent.strip().split(" ")
    floorplan_dict_on_parent = [c for c in floorplan_dict_on_parent if c != ""]
    floorplan_dict_on_parent = [c.split(":") for c in floorplan_dict_on_parent]
    floorplan_dict_on_parent = {c[0]: c[1].replace("(", "").replace(")", "").replace("*", "") for c in floorplan_dict_on_parent}
    children_count_dict = {floorplan_dict_on_parent[c]: floorplan_on_parent[c] for c in floorplan_dict_on_parent.keys()}
    return children_count_dict
# dedeepyo : 17-Nov-2024

def chiplet_definiton_list_from_file(file, variable_dict):
    #example file:
    # <chip name="interposer"
    #     bb_area=""
    #     bb_cost=""
    #     bb_quality=""
    #     bb_power=""
    #     aspect_ratio=""
    #     x_location=""
    #     y_location=""
        
    #     core_area="0.0"
    #     fraction_memory="0.0"
    #     fraction_logic="0.0"
    #     fraction_analog="1.0"
    #     reticle_share="1.0"
    #     buried="False"
    #     assembly_process="silicon_individual_bonding"
    #     test_process="test_process_0"
    #     stackup="1:organic_substrate,6:5nm_global_metal"
    #     wafer_process="process_1"
    #     v_rail="5"
    #     reg_eff="1.0"
    #     reg_type="none"
    #     core_voltage="1.0"
    #     power="0.0"
    #     quantity="1000000"

    #     floorplan="
    #     H  X  H
    #     X  D* X
    #     H  X  H"
    #     floorplan_dict="
    #     D:GPU
    #     H:(HBM0,HBM1,HBM2,HBM3)
    #     "
    #     >
    #     <chip name="GPU"
    #         bb_area=""
    #         bb_cost=""
    #         bb_quality=""
    #         bb_power=""
    #         aspect_ratio=""
    #         x_location=""
    #         y_location=""
        
    #         core_area="10.0"
    #         fraction_memory="0.0"
    #         fraction_logic="1.0"
    #         fraction_analog="0.0"
    #         reticle_share="1.0"
    #         buried="False"
    #         assembly_process="silicon_individual_bonding"
    #         test_process="test_process_0"
    #         stackup="1:5nm_active,2:5nm_advanced_metal,2:5nm_intermediate_metal,2:5nm_global_metal"
    #         wafer_process="process_1"
    #         v_rail="5,1.8"
    #         reg_eff="1.0,0.9"
    #         reg_type="none,side"
    #         core_voltage="1.0"
    #         power="100.0"
    #         quantity="1000000"

    #         floorplan=""
    #         floorplan_dict="">
    #         <chip name="MEM"
    #             bb_area=""
    #             bb_cost=""
    #             bb_quality=""
    #             bb_power=""
    #             aspect_ratio=""
    #             x_location=""
    #             y_location=""
        
    #             core_area="10.0"
    #             fraction_memory="1.0"
    #             fraction_logic="0.0"
    #             fraction_analog="0.0"
    #             reticle_share="1.0"
    #             buried="False"
    #             assembly_process="organic_simultaneous_bonding"
    #             test_process="test_process_0"
    #             stackup="1:5nm_active,2:5nm_advanced_metal,2:5nm_intermediate_metal,2:5nm_global_metal"
    #             wafer_process="process_1"
    #             v_rail="5,1.8"
    #             reg_eff="1.0,0.9"
    #             reg_type="none,side"
    #             core_voltage="1.0"
    #             power="10.0"
    #             quantity="1000000"

    #             floorplan=""
    #             floorplan_dict="">
    #         </chip>
    #     </chip>
    #     <chip name="HBM0"
    #         bb_area=""
    #         bb_cost=""
    #         bb_quality=""
    #         bb_power=""
    #         aspect_ratio=""
    #         x_location=""
    #         y_location=""

    #         core_area="10.0"
    #         fraction_memory="1.0"
    #         fraction_logic="0.0"
    #         fraction_analog="0.0"
    #         reticle_share="1.0"
    #         buried="False"
    #         assembly_process="organic_simultaneous_bonding"
    #         test_process="test_process_0"
    #         stackup="1:5nm_active,2:5nm_advanced_metal,2:5nm_intermediate_metal,2:5nm_global_metal"
    #         wafer_process="process_1"
    #         v_rail="5,1.8"
    #         reg_eff="1.0,0.9"
    #         reg_type="none,side"
    #         core_voltage="1.0"
    #         power="10.0"
    #         quantity="1000000"

    #         floorplan=""
    #         floorplan_dict="">
    #     </chip>
    #     <chip name="HBM1"
    #         bb_area=""
    #         bb_cost=""
    #         bb_quality=""
    #         bb_power=""
    #         aspect_ratio=""
    #         x_location=""
    #         y_location=""

    #         core_area="10.0"
    #         fraction_memory="1.0"
    #         fraction_logic="0.0"
    #         fraction_analog="0.0"
    #         reticle_share="1.0"
    #         buried="False"
    #         assembly_process="organic_simultaneous_bonding"
    #         test_process="test_process_0"
    #         stackup="1:5nm_active,2:5nm_advanced_metal,2:5nm_intermediate_metal,2:5nm_global_metal"
    #         wafer_process="process_1"
    #         v_rail="5,1.8"
    #         reg_eff="1.0,0.9"
    #         reg_type="none,side"
    #         core_voltage="1.0"
    #         power="10.0"
    #         quantity="1000000"

    #         floorplan=""
    #         floorplan_dict="">
    #     </chip>
    #     <chip name="HBM2"
    #         bb_area=""
    #         bb_cost=""
    #         bb_quality=""
    #         bb_power=""
    #         aspect_ratio=""
    #         x_location=""
    #         y_location=""

    #         core_area="10.0"
    #         fraction_memory="1.0"
    #         fraction_logic="0.0"
    #         fraction_analog="0.0"
    #         reticle_share="1.0"
    #         buried="False"
    #         assembly_process="organic_simultaneous_bonding"
    #         test_process="test_process_0"
    #         stackup="1:5nm_active,2:5nm_advanced_metal,2:5nm_intermediate_metal,2:5nm_global_metal"
    #         wafer_process="process_1"
    #         v_rail="5,1.8"
    #         reg_eff="1.0,0.9"
    #         reg_type="none,side"
    #         core_voltage="1.0"
    #         power="10.0"
    #         quantity="1000000"

    #         floorplan=""
    #         floorplan_dict="">
    #     </chip>
    #     <chip name="HBM3"
    #         bb_area=""
    #         bb_cost=""
    #         bb_quality=""
    #         bb_power=""
    #         aspect_ratio=""
    #         x_location=""
    #         y_location=""

    #         core_area="10.0"
    #         fraction_memory="1.0"
    #         fraction_logic="0.0"
    #         fraction_analog="0.0"
    #         reticle_share="1.0"
    #         buried="False"
    #         assembly_process="organic_simultaneous_bonding"
    #         test_process="test_process_0"
    #         stackup="1:5nm_active,2:5nm_advanced_metal,2:5nm_intermediate_metal,2:5nm_global_metal"
    #         wafer_process="process_1"
    #         v_rail="5,1.8"
    #         reg_eff="1.0,0.9"
    #         reg_type="none,side"
    #         core_voltage="1.0"
    #         power="10.0"
    #         quantity="1000000"

    #         floorplan=""
    #         floorplan_dict="">
    #     </chip>
    # </chip>
    # Read the XML file.

    def attrib_variable_handling(value, variable_dict):
        if value == "":
            return 0.0
        # if value begins with $, it's not a float, it's a variable
        if value[0] == "$":
            variable_name = value[1:]
            if(variable_name[0] == "(" and variable_name[-1] == ")"):
                return eval(variable_name[1:-1], {}, variable_dict)
            else:
                if variable_name not in variable_dict:
                    print("Error: Variable " + variable_name + " not defined.")
                    return None
                return variable_dict[variable_name]
        return float(value)

    def parse_chiplet(chiplet_def, variable_dict, prefix = "", suffix = ""):        

        # Create a chiplet object.
        chiplet = Chiplet(name="", core_area=0.0, aspect_ratio= 1.0, fraction_memory=0.0, fraction_logic=0.0, fraction_analog=0.0,
                           assembly_process="", stackup="", power=0.0, floorplan="", floorplan_dict="")

        attributes = chiplet_def.attrib
        chiplet_full_name = attributes["name"] + suffix
        if (prefix != ""):
            chiplet_full_name = prefix + "." + chiplet_full_name
        
        chiplet.set_name(chiplet_full_name)
        try:
            chiplet.set_aspect_ratio(float(attributes["aspect_ratio"]))
        except:
            chiplet.set_aspect_ratio(1.0)
        chiplet.set_fraction_memory(float(attributes["fraction_memory"]))
        chiplet.set_fraction_logic(float(attributes["fraction_logic"]))
        chiplet.set_fraction_analog(float(attributes["fraction_analog"]))
        chiplet.set_floorplan(attributes["floorplan"])
        chiplet.set_floorplan_dict(attributes["floorplan_dict"])
        power = attrib_variable_handling(attributes["power"], variable_dict)
        chiplet.set_power(power)

        # dedeepyo : 18-Nov-2024 : Added fake attribute
        # We need to raise Warning if the chiplet is fake and it contains non-empty values for core_area and stackup attributes.
        # first check if core_area begins with $
        core_area = attrib_variable_handling(attributes["core_area"], variable_dict)
        if(core_area == 0.0):
            core_area = attrib_variable_handling(attributes["bb_area"], variable_dict) 
        if(attributes["fake"].strip() == "True"):
            chiplet.set_fake(True)
            if core_area != 0.0:
                print("Warning: Fake chiplet " + chiplet_full_name + " has non-zero core area.")
            if attributes["stackup"].strip() != "":
                print("Warning: Fake chiplet " + chiplet_full_name + " has a stackup defined.")
            if attributes["assembly_process"].strip() != "":
                print("Warning: Fake chiplet " + chiplet_full_name + " has an assembly process defined.")
        elif(attributes["fake"].strip() == "False"):
            chiplet.set_fake(False)
            chiplet.set_stackup(attributes["stackup"])
            chiplet.set_core_area(core_area)
            chiplet.set_assembly_process(attributes["assembly_process"])
        else:
            print("Error: Fake attribute for chiplet " + chiplet_full_name + " is not set to True or False.")
                    
        # dedeepyo : 18-Nov-2024

        # dedeepyo : 16-Nov-2024 : Implementing recursive chiplet definitions
        # Check if the chiplet has a floorplan.
        # Understanding is, initally, chiplet_def is SAME as root, NOT an array containing root. root = ET.parse(file).getroot() . 
        if attributes["floorplan"].strip() != "":
            children_count_dict = count_child_chiplets(attributes["floorplan"], attributes["floorplan_dict"])
        # dedeepyo : 17-Nov-2024

        # Check if the chiplet has child chiplets.
        if len(chiplet_def) > 0:
            # Parse the child chiplets recursively.
            for child_chiplet_def in chiplet_def:
                try:
                    c = children_count_dict[child_chiplet_def.attrib["name"]]
                except:
                    c = 1
                if(c > 1):
                    for i in range(c):
                        child_chiplet = parse_chiplet(child_chiplet_def, variable_dict, chiplet_full_name, '#' + str(i))
                        chiplet.add_child_chiplet(child_chiplet)
                else:
                    child_chiplet = parse_chiplet(child_chiplet_def, variable_dict, chiplet_full_name, "")
                    chiplet.add_child_chiplet(child_chiplet)

        return chiplet

    tree = ET.parse(file)
    root = tree.getroot()
    chiplet_list = []

    # Parse the root chiplet.
    root_chiplet = parse_chiplet(root, variable_dict, "", "")
    chiplet_list.append(root_chiplet)
    # print("Root Chiplet: ", root_chiplet)
    # Parse the child chiplets of the root chiplet.
    # for child_chiplet_def in root:
    #     child_chiplet = parse_chiplet(child_chiplet_def, variable_dict, root_chiplet.get_name(), "")
    return chiplet_list

class Chiplet:
    def __init__(self, name = "", core_area = 0.0, aspect_ratio = 1.0, fraction_memory = 0.0, fraction_logic = 0.0, fraction_analog = 0.0,
                 assembly_process = "", stackup = "", power = 0.0, floorplan = "", floorplan_dict = "", height = 0.0, fake = False) -> None:
        self.name = name
        self.core_area = core_area
        self.aspect_ratio = aspect_ratio
        self.fraction_memory = fraction_memory
        self.fraction_logic = fraction_logic
        self.fraction_analog = fraction_analog
        self.assembly_process = assembly_process
        self.stackup = stackup
        self.power = power
        self.floorplan = floorplan
        self.floorplan_dict = floorplan_dict
        self.child_chiplets = []
        self.connections = set()
        self.height = height
        self.fixed = False
        self.box_representation = None
        self.assigned_floorplan = False
        self.fake = fake

    # ====== Get/Set Functions ======

    def set_assigned_floorplan(self, value) -> int:
        self.assigned_floorplan = value
        return 0
    
    def is_assigned_floorplan(self) -> bool:
        return self.assigned_floorplan

    def get_box_representation(self):
        return self.box_representation
    
    def set_box_representation(self, value):
        self.box_representation = value
        return 0

    def get_name(self) -> str:
        return self.name
    
    # dedeepyo : 15-Nov-2024 : Added get_chiplet_type for current instantiation of what and get_chiplet_prefix for parents
    # Restriction : Chiplet type name (eg. GPU, MEM, HBM, interposer, wafer) should not contain any #
    def get_chiplet_type(self) -> str:
        current_chiplet_type = self.name.split(".")[-1].split("#")[0]
        # current_chiplet_type = ''.join([i for i in current_chiplet_type if not i.isdigit()])
        return current_chiplet_type
    
    def get_chiplet_type_instant(self) -> str:
        return self.name.split(".")[-1]

    def get_chiplet_prefix(self) -> str:
        c = len(self.name.split(".")[-1])
        prefix = self.name[:-c]
        return prefix
    # dedeepyo : 17-Nov-2024

    # dedeepyo : 18-Nov-2024 : Added set_fake and get_fake for current chiplet
    def set_fake(self, value):
        self.fake = value
    
    def get_fake(self):
        return self.fake    
    # dedeepyo : 18-Nov-2024 
    
    def set_name(self, value) -> int:
        self.name = value
        return 0

    def get_core_area(self) -> float:
        return self.core_area
    
    def set_core_area(self, value) -> int:
        self.core_area = value
        return 0
    
    def get_height(self) -> float:
        return self.height
    
    def set_height(self, value) -> int:
        self.height = value
        return 0
        
    def get_aspect_ratio(self) -> float:
        return self.aspect_ratio
    
    def set_aspect_ratio(self, value) -> int:
        self.aspect_ratio = value
        return 0

    def get_fraction_memory(self) -> float:
        return self.fraction_memory
    
    def set_fraction_memory(self, value) -> int:
        self.fraction_memory = value
        return 0

    def get_fraction_logic(self) -> float:
        return self.fraction_logic
    
    def set_fraction_logic(self, value) -> int:
        self.fraction_logic = value
        return 0

    def get_fraction_analog(self) -> float:
        return self.fraction_analog
    
    def set_fraction_analog(self, value) -> int:
        self.fraction_analog = value
        return 0

    def get_assembly_process(self) -> str:
        return self.assembly_process
    
    def set_assembly_process(self, value) -> int:
        self.assembly_process = value
        return 0

    def get_stackup(self) -> str:
        return self.stackup
    
    def set_stackup(self, value) -> int:
        self.stackup = value
        return 0

    def get_power(self) -> float:
        return self.power
    
    def set_power(self, value) -> int:
        self.power = value
        return 0

    def get_floorplan(self) -> str:
        return self.floorplan
    
    def set_floorplan(self, value) -> int:
        self.floorplan = value
        return 0
    
    def get_floorplan_dict(self) -> str:
        return self.floorplan_dict
    
    def set_floorplan_dict(self, value) -> int:
        self.floorplan_dict = value
        return 0
    
    def get_child_chiplets(self) -> list:
        return self.child_chiplets
    
    def add_child_chiplet(self, value) -> int:
        self.child_chiplets.append(value)
        return 0
    
    def set_child_chiplets(self, value) -> int:
        self.child_chiplets = value
        return 0

    def get_connections(self) -> set:
        return self.connections
    
    def add_connection(self, value) -> int:
        self.connections.add(value)
        return 0
    
    def set_connections(self, value) -> int:
        self.connections = value
        return 0
    
    def get_fixed(self) -> bool:
        return self.fixed
    
    def set_fixed(self, value) -> int:
        self.fixed = value
        return 0
    # ===== End of Get/Set Functions =====

    # add a repr
    # should only print name, assembly, connections
    def __repr__(self):
        return f"Chiplet({self.name}, {self.assembly_process}, {self.connections})"
    
    def __str__(self):
        return f"Chiplet({self.name}, {self.assembly_process}, {self.connections})"
    


# Define a function to read the layer definitions from a file.
def layer_definition_list_from_file(filename):
    # print("Reading layer definitions from file: " + filename)
    # Read the XML file.
    tree = ET.parse(filename)
    root = tree.getroot()
    # Create a list of layer objects.
    layer_list = []
    # Iterate over the layer definitions.
    for layer_def in root:
        # Create a layer object.
        layer = Layer(name = "", active = False, cost_per_mm2 = 0, defect_density = 0, critical_area_ratio = 0,
                        clustering_factor = 0, litho_percent = 0, mask_cost = 0, stitching_yield = 0, static = False, thickness = 0, material = "")
        attributes = layer_def.attrib
        # Set the layer object attributes.
        layer.set_name(attributes["name"])
        layer.set_active(bool(attributes["active"]))
        layer.set_cost_per_mm2(float(attributes["cost_per_mm2"]))
        layer.set_defect_density(float(attributes["defect_density"]))
        layer.set_critical_area_ratio(float(attributes["critical_area_ratio"]))
        layer.set_clustering_factor(float(attributes["clustering_factor"]))
        layer.set_litho_percent(float(attributes["litho_percent"]))
        layer.set_mask_cost(float(attributes["nre_mask_cost"]))
        layer.set_stitching_yield(float(attributes["stitching_yield"]))
        layer.set_thickness(float(attributes["thickness"]))
        layer.set_material(attributes["material"])

        layer.set_static()
        # Append the layer object to the list.
        layer_list.append(layer)
    # Return the list of layer objects.
    # print("At end of layer_list_from_file")
    return layer_list

class Layer:
    def __init__(self, name = None, active = None, cost_per_mm2 = None, defect_density = None, critical_area_ratio = None,
                 clustering_factor = None, litho_percent = None, mask_cost = None, stitching_yield = None, static = True, thickness = None, material = None) -> None:
        self.name = name
        self.active = active
        self.cost_per_mm2 = cost_per_mm2
        self.defect_density = defect_density
        self.critical_area_ratio = critical_area_ratio
        self.clustering_factor = clustering_factor
        self.litho_percent = litho_percent
        self.mask_cost = mask_cost
        self.stitching_yield = stitching_yield
        self.static = static
        self.thickness = thickness
        self.material = material

    # =========== Get/Set Functions ===========

    def get_name(self) -> str:
        return self.name

    def set_name(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.name = value
            return 0

    def get_active(self) -> bool:
        return self.active

    def set_active(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.active = value
            return 0

    def get_cost_per_mm2(self) -> float:
        return self.cost_per_mm2

    def set_cost_per_mm2(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.cost_per_mm2 = value
            return 0

    def get_defect_density(self) -> float:
        return self.defect_density

    def set_defect_density(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.defect_density = value
            return 0

    def get_critical_area_ratio(self) -> float:
        return self.critical_area_ratio

    def set_critical_area_ratio(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.critical_area_ratio = value
            return 0

    def get_clustering_factor(self) -> float:
        return self.clustering_factor
    
    def set_clustering_factor(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.clustering_factor = value
            return 0
        
    def set_thickness(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.thickness = value
            return 0

    def set_material(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.material = value
            return 0
    
    def get_thickness(self) -> float:
        return self.thickness

    def get_material(self) -> str:
        return self.material

    def get_litho_percent(self) -> float:
        return self.litho_percent
    
    def set_litho_percent(self, value) -> int: 
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.litho_percent = value
            return 0

    def get_mask_cost(self) -> float:
        return self.mask_cost

    def set_mask_cost(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.mask_cost = value
            return 0
    
    def get_stitching_yield(self) -> float:
        return self.stitching_yield

    def set_stitching_yield(self, value) -> int:
        if (self.static):
            print("Error: Cannot change static layer.")
            return 1
        else:
            self.stitching_yield = value
            return 0

    def get_static(self) -> bool:
        return self.static 

    def set_static(self) -> int: # The static variable should act somewhat like a latch, when it is set, it should not get unset.
        if (self.name is None or self.active is None or self.cost_per_mm2 is None or self.defect_density is None or
                     self.critical_area_ratio is None or self.clustering_factor is None or self.litho_percent is None or
                     self.mask_cost is None or self.stitching_yield is None):
            print("Error: Attempt to set layer static without defining all parameters. Exiting...")
        self.static = True
        return 0

def parse_XML_assembly(file):
    # assembly_fname = "configs/thermal-configs/assembly_process_definitions.xml"
    assembly_fname = file
    assembly_process_list = assembly_process_definition_list_from_file(assembly_fname)
    return assembly_process_list

def parse_XML_connection_netlist(file):
    # io_fname = "configs/thermal-configs/netlist.xml"
    connection_fname = file
    connection_list = connection_definition_list_from_file(connection_fname)
    return connection_list

def parse_XML_chiplet_netlist(file, variable_dict):
    chiplet_fname = file
    chiplet_list = chiplet_definiton_list_from_file(chiplet_fname, variable_dict)
    return chiplet_list

def parse_Layer_netlist(file):
    layer_fname = file
    layer_list = layer_definition_list_from_file(layer_fname)
    return layer_list

def parse_variable_dict(fname):
    with open(fname, 'r') as stream:
        try:
            variable_dict = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
    return variable_dict

# dedeepyo : 17-Nov-2024 : Added search_chiplet_by_name function
# Currently, inefficiently iterating over list of chiplets
# Intend to store chiplets in a dictionary for faster with key as chiplet name
# Faster, store chiplets in a Trie data structure
def search_chiplet_by_name(chiplet_name, chiplet_list):
    for chiplet in chiplet_list:
        if chiplet.get_name() == chiplet_name:
            return chiplet
    return None
# dedeepyo : 17-Nov-2024

def parse_all_chiplets(file):

    # first pass assembly processes
    assembly_processes = parse_XML_assembly("configs/thermal-configs/assembly_process_definitions.xml")
    # then pass connection netlist
    connections = parse_XML_connection_netlist("configs/thermal-configs/netlist.xml")
    # then pass layer netlist
    layers = parse_Layer_netlist("configs/thermal-configs/layer_definitions.xml")
    # variable_dict = parse_variable_dict("output/output_vars.yaml")
    # variable_dict = parse_variable_dict("output/output_vars1.yaml")
    variable_dict = parse_variable_dict("output/output_vars2.yaml")
    chiplet_list = parse_XML_chiplet_netlist(file, variable_dict)
    # now we need to radically reconstruct this. First, for each chiplet in the chiplet list, recursively, we need to find the assembly process and connections.
    # this means we go through the chiplet list recursively, and replace the assembly process with the object.
    # first, we need to create a dictionary of assembly processes
    assembly_process_dict = {}
    for assembly_process in assembly_processes:
        assembly_process_dict[assembly_process.get_name()] = assembly_process

    # now we need to traverse the chiplet list and replace the assembly process with the object.
    def traverse_chiplet_list(chiplet_list, parent_chiplet = None):
        for chiplet in chiplet_list:
            try:
                assembly_process = assembly_process_dict[chiplet.get_assembly_process()]
            except:
                assembly_process = parent_chiplet.get_assembly_process()
            chiplet.set_assembly_process(assembly_process)
            traverse_chiplet_list(chiplet.get_child_chiplets(), chiplet)

    traverse_chiplet_list(chiplet_list, None)

    def calc_height(chiplet_list, layers):
        for chiplet in chiplet_list:
            # dedeepyo : 18-Nov-2024 : Checking code for non-existent stackup 
            if(chiplet.get_fake() == False):
                stackup = chiplet.get_stackup()
                height = 0
                stackup_list = stackup.split(",")
                # stackup list example: '1:organic_substrate','6:5nm_global_metal'.
                # The first number before : indicates number of layers, the second part indicates the layer name.
                # We need to find the thickness of each layer and add them up.                
                for stackup in stackup_list:
                    # print("Attempting: ", stackup, "for chip:  ", chiplet.get_name())
                    layer_num, layer_name = stackup.split(":")
                    for layer in layers:
                        if layer.get_name() == layer_name:
                            height += (int(layer_num) * layer.get_thickness())

                height = round(height, 3) #CHECK: 3 decimal places. 
                chiplet.set_height(height)
            # dedeepyo : 18-Nov-2024

            calc_height(chiplet.get_child_chiplets(), layers)


    calc_height(chiplet_list, layers)


    # now go through all connection objects and break them down to tuples of (block0,block1)
    connection_tuples = []
    for connection in connections:
        connection_tuples.append((connection.get_block0(), connection.get_block1()))
    # now we need to go into the chiplet class and add the connections. We will do this recursviely.
    # we need to add connections if the chiplet is in the first or the second tuple position.

    # dedeepyo : 15-Nov-24 : We need to add the chiplet prefix to the connected chiplet name as connections are between 2 chiplets of the same parent.
    # I think we need to add the chiplet prefix to the connection name if the connection is to a memory chiplet.
    def traverse_chiplet_list_connections(chiplet_list, parent_chiplet = None):
        for chiplet in chiplet_list:
            chiplet_type = chiplet.get_chiplet_type()
            chiplet_prefix = chiplet.get_chiplet_prefix()

            if parent_chiplet is not None:
                children_count_dict = count_child_chiplets(parent_chiplet.get_floorplan(), parent_chiplet.get_floorplan_dict())
            
            for connection in connection_tuples:
                connected_chiplet = ""
                if connection[0] == chiplet_type:
                    connected_chiplet = connection[1]
                elif connection[1] == chiplet_type:
                    connected_chiplet = connection[0]

                # if the connected chiplet is a memory chiplet, we need to add the chiplet prefix to the connection name.
                # chiplet.add_connection(chiplet_prefix + connected_chiplet)
                # chiplet_prefix = chiplet_prefix[:-4]
                if(connected_chiplet != ""):
                    if(connected_chiplet == "MEM"):
                        chiplet.add_connection(chiplet.get_name() + "." + connected_chiplet)
                    elif(chiplet_type == "MEM"):
                        chiplet.add_connection(chiplet.get_name()[:-4])
                    else:
                        try:
                            c = children_count_dict[connected_chiplet]
                        except:
                            c = 1

                        if(c > 1):
                            for i in range(c):
                                chiplet.add_connection(chiplet_prefix + connected_chiplet + '#' + str(i))
                        else:
                            chiplet.add_connection(chiplet_prefix + connected_chiplet)

            traverse_chiplet_list_connections(chiplet.get_child_chiplets(), chiplet)
    # dedeepyo : 15-Nov-24

    traverse_chiplet_list_connections(chiplet_list, None)

    return chiplet_list

# dedeepyo : 18-Nov-2024 : Implementing recursive chiplet sizing for fake chiplets
# We update core area and aspect ratio of fake chiplet as per its children
# aspect ratio = width / length
# Assuming that the fake chiplet is a square, we can calculate the width and length of the fake chiplet.
# Assuming the base chiplet is not a "set" (fake chiplet).
# Assuming the topmost chiplet is never a set or a fake chiplet.
# Assuming all chiplets except the base chiplet have a parent.
def recursive_chiplet_sizing(root, parent = None):
    longest_side = 0.0
    for child in root.get_child_chiplets():
        (width, length) = recursive_chiplet_sizing(child, root)
        if(length > longest_side):
            longest_side = length
        if(width > longest_side):
            longest_side = width

    if(root.get_fake() == True):
        # longest_side += parent.get_assembly_process().get_die_separation() * 4
        width = longest_side * int(math.sqrt(len(root.get_floorplan().replace(" ", ""))))
        root.set_core_area(width * width)
        return (width, width)
    else:
        width = math.sqrt(root.get_core_area() * root.get_aspect_ratio())
        return (width, (root.get_core_area() / width))
# dedeepyo : 18-Nov-2024

# dedeepyo : 29-Jan-2025 : Implementing recursive chiplet sizing for fake chiplets
def recursively_copy_chiplet_sizes(fake_chiplet_size_dict, root):
    if(root.get_fake() == True):
        (a, r) = fake_chiplet_size_dict[root.get_chiplet_type()]
        root.set_core_area(a)
        root.set_aspect_ratio(r)
    for child in root.get_child_chiplets():
        recursively_copy_chiplet_sizes(fake_chiplet_size_dict, child)
# dedeepyo : 29-Jan-2025 #

# dedeepyo : 12-Feb-2025 : Removing fake chiplets from chiplet tree.
# Assuming absolute starting / base chiplet is NEVER a fake chiplet. So a fake chiplet is always a child of another chiplet. 
def recursively_remove_fake_chiplets(root):
    real_children_of_fake_child = []
    fake_children_of_root = []
    real_children_of_root = []
    for child in root.get_child_chiplets():
        recursively_remove_fake_chiplets(child)
        if(child.get_fake() == True):
            real_children_of_fake_child.extend(child.get_child_chiplets())
            fake_children_of_root.append(child)
        else:
            real_children_of_root.append(child)
    
    # for fake_child in fake_children_of_root:
        # root.get_child_chiplets().remove(fake_child)
    
    real_children_of_fake_child.extend(real_children_of_root)
    root.set_child_chiplets(real_children_of_fake_child)
# dedeepyo : 12-Feb-2025 #

def recursively_print_chiplets(prefix, root, file = None):
    # print(prefix + str(root) + " Fake: " + str(root.get_fake()) + ", Power : " + str(root.get_power()))
    for child in root.get_child_chiplets():
        recursively_print_chiplets(prefix + " ", child, file = file)
    print(prefix + str(root.get_name()))

def recursively_find_fakes(root, file = None):
    for child in root.get_child_chiplets():
        recursively_find_fakes(child, file = file)
    if(root.get_fake() == True):
        print("Fake chiplet found: " + root.get_name())

if __name__ == "__main__":
    # test code
    # root = parse_all_chiplets("configs/thermal-configs/sip_hbm.xml")
    # root = parse_all_chiplets("configs/thermal-configs/sip_hbm_dray_hbm_4side_64gpu.xml")
    root = parse_all_chiplets("configs/thermal-configs/sip_hbm_dray062325_1gpu_6hbm_2p5D.xml")
    # root = parse_all_chiplets("configs/thermal-configs/sip_hbm_dray_l2_gpu_hbm.xml")
    # root = parse_all_chiplets("configs/thermal-configs/sip_hbm_dray_hbm_top_gpu.xml")
    # f = open("output/chiplet_tree.txt", "w")
    # f.write("############ Before removing fake chiplets ##############\n\n")
    # recursively_print_chiplets("", root[0])
    (w_top, l_top) = recursive_chiplet_sizing(root[0], None)
    recursively_remove_fake_chiplets(root[0])
    # f.write("\n############## After removing fake chiplets ##############\n\n")
    recursively_print_chiplets("", root[0])
    recursively_find_fakes(root[0])
    # f.close()
    # for child in root:
        # print(child.get_child_chiplets()[0].get_power())




