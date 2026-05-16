from .base import ThermalSimulator
import os
import numpy as np
import danka_thermal_api
import time
from thermal_simulators.anemoi_dataframe import DataFrame
from therm_xml_parser import *
import math
from bonding_xml_parser import *
from heatsink_xml_parser import *
import copy

conductivity_values = {
    "Air": 0.025,
    "FR-4": 0.1,
    "Cu-Foil": 400,
    "Si": 105,
    "Aluminium": 205,
    "TIM001": 100,
    "Glass": 1.36,
    "TIM": 100,
    "SnPb 67/37": 36,
    "Epoxy, Silver filled": 1.6,
    "SiO2": 1.1,
    "AlN": 237,
    "EpAg": 1.6,
    "Infill_material": 19,
    "Polymer1": 675,
    "TIM0p5": 1.0 # 5.0 # 1.0 # 0.5 # 100.0 # 
}
# EpAg is Epoxy, Silver filled used in layer_definitions.xml for bonding layers 5nm_HBM2HBM_metal.
anemoi_parameters = {
    "GPU" : "GPU_power",
    "HBM" : "HBM_power",
    "HBM_l" : "HBM_l_power",
    "interposer" : "interposer_power",
    "substrate" : "substrate_power",
    "PCB" : "PCB_power",
    "Power_Source" : "Power_Source_power",
    "GPU_HTC" : "GPU_HTC_power", # Actually HTC but used as a parameter, same for HBM_HTC
    "HBM_HTC" : "HBM_HTC_power",
}
# anemoi_parameter_ID = {
#     "GPU_power" : 67001,
#     "HBM_power" : 67002,
#     "HBM_l_power" : 67003,
#     "interposer_power" : 67004,
#     "substrate_power" : 67005,
#     "PCB_power" : 67006,
#     "Power_Source_power" : 67007
# }
# anemoi_parameter_ID = {}
power_values = {
    "GPU" : 270000.000000,
    "HBM" : 2400.000000,
    "HBM_l" : 1200.000000, 
    "interposer" : 0.0,
    "substrate" : 0.0,
    "PCB" : 0.0,
    "Power_Source" : 0.0,
    "GPU_HTC" : 10000.0, # HTC values in W / (m^2 * K)
    "HBM_HTC" : 10000.0, # HTC values in W / (m^2 * K)
} # power values in mW
#TODO: Send HTC values in kw / (m^2 * K)

def get_key(val,dict):
    for key, value in dict.items():
        if val == value:
            return key
    raise Exception("Key not found")

# dedeepyo : 16-Dec-24 : Maintaining list of projects #
# Current : TechCon_dray2_2p5D_1GPU_6HBM_062325, TechCon_dray1_2p5D_1GPU_6HBM_062325, TechCon_dray2p5D_1GPU_6HBM_062325, TechCon_2p5D_1GPU_6HBM_062325, TechCon_2p5D_1GPU_6HBM_062325, TechCon_iterate1_3D_062125, TechCon_iterate_3D_062125, TechCon_050925_2p5D, TechCon_051025_3D, TechCon_050925_2p5D, TechCon_iteration_3D, TechCon_iteration_3D1, TechCon_iteration_2p5D, TechCon_calibrate_3D, TECHCON_050925_2P5D_iteration, TechCon_2p5D_iteration_062125, TechCon_iteration_2p5D, TechCon_calibrate_3D_062125
# Past : 11-Nov-24 to 12-Feb-25 : Dummy_1122, Dummy, Dummy2_dray_1109, Dummy_121624, Dummy_121824, Dummy_122024, Dummy_010825, Dummy_010925, Dummy1_010925, Dummy2_010925, Dummy_121624, Dummy_012725, Dummy_012825, Dummy_012925, Dummy_013025, Dummy_013125, Dummy2_013125, Dummy3_013125, Dumm_020525, Dummy_020725, Dummy_021125, Dummy1_021125, Dummy2_021125
# 12-Feb-25 to 2-Mar-25 : Dummy_64HBM_top_of_GPU_021225, Dummy1_021225, Dummy_HBM_4side_64GPU_021225, Dummy1_64HBM_top_of_GPU_021225, Dummy_HBM_top_1GPU_021425, Dummy_4HBM_top_64GPU_021425, Dummy_4HBM_64GPU_021525, Dummy_4HBM_1GPU_021525, Dummy_4HBM_64GPU_021825, Dummy_021825_1GPU_4HBM_dray, Dummy_022525_dray1, Dummy_022525_dray2, Dummy_022525_dray3, GPU4x4_6HBM_022725, A100_GPU4x4_6HBM_022725, A100_GPU4x4_6HBM_022725_dray3, A100_GPU_6HBM_top_022725_dray4
# 3-Mar-25 to present : Dual_sided_PCB_A100_4x4GPU_6HBM_top_030325_dray, Dual_sided_PCB_A100_GPU_6HBM_top_030325_dray, Dual_sided_PCB_A100_GPU_6HBM_top_030325_dray2, Dual_sided_PCB_A100_GPU_6HBM_top_030325_dray2, Test_dray2_9Apr25, TechCon_050925_2p5D, TechCon_051025_3D
# dedeepyo : 14-Dec-24

class AnemoiSim(ThermalSimulator):
    def __init__(self, name = "TechCon_dray4_2p5D_062325_5x5"):
        token = (os.environ.get("ANEMOI_API_TOKEN") or "").strip()
        if not token:
            raise RuntimeError(
                "ANEMOI_API_TOKEN is not set (or is empty). Set it in your shell before initializing AnemoiSim."
            )
        cfg = danka_thermal_api.Configuration(
            host='https://anemoisoftware.com/api',
            api_key={
                'Authorization': token
            },
            api_key_prefix={
                'Authorization': 'Token'
            }
        )
        self.api = danka_thermal_api.ApiClient(configuration=cfg)
        print("Anemoi API client initialized.")
        
        self.papi = danka_thermal_api.ProjectApi(api_client=self.api)
        self.material_list = []
        found = False
        self.name = name
        proj_list = self.list_projects()
        for proj in proj_list:     
            if self.name == proj.name: 
                found = True
                print("Project already exists")
                break
        if not found:
            self.create_project()
        if self.name:
                self.id = self.find_project_id(self.name)
                print(self.id)
        if self.name:
            self.load_material_table()
            if self.material_list == []: # dedeepyo : 12-Feb-25
                self.load_materials() # dedeepyo : 11-Feb-25
            self.load_material_table() # dedeepyo : 13-Feb-2025
        
    def create_project(self):
        data = {
        "name": self.name,
        "world": {
            "ambient": 45,
            "resolution": 0.5,
            "precision": 0.05,
            "iterations": 50000,
            "abs_tol": 0.1,
            "duration": 20,
            "steps": 10,
            "dxmin": "100.000000",
            "dxmax": "100.000000",
            "dymin": "100.000000",
            "dymax": "100.000000",
            "dzmin": "100.000000",
            "dzmax": "100.000000",
            "show_grid": True,
            "show_outline": True,
            "save_internal_temp": True,
            "precondition": True,
            "hc": 16.1,
        },
    }
        self.papi.project_create(data)

    # dedeepyo : 1st November 2024 : Implementing local API caller #
    def api_call(self, activity, args): 
        i = 0
        max_try = 5
        while(i < max_try):
            try:
                self.papi.activity(args)
                i = max_try
            except Exception as e:
                print(e)
            finally:
                print("API caller function")
                i = i + 1
    # dedeepyo : 1st November 2024 #

    # dedeepyo : 7-Feb-25 : Trying to automate material import.
    def load_materials(self):
        material_name_list = list(conductivity_values.keys())
        self.lapi = danka_thermal_api.LibraryApi(api_client=self.api)
        all_libraries = self.lapi.library_list()
        all_materials = self.lapi.library_read(all_libraries[0].id).materials
        for mat in all_materials:
            if mat.name in material_name_list:
                self.papi.project_material_create(self.id, [mat])
        all_material_names = [mat.name for mat in all_materials]
        for key, value in conductivity_values.items():
            if key not in all_material_names:
                mat = danka_thermal_api.Material(name = key, conductivity = str(value), conductivity_y = str(value), conductivity_z = str(value), color = "#456d82", anisotropic = False)
                self.papi.project_material_create(self.id, [mat])
    # dedeepyo : 22-Jun-25

    # dedeepyo : 7-Oct-25 : Updating material conductivities
    def update_materials(self, materials_update_dict):
        materials_name_list = list(materials_update_dict.keys())
        for material_name in materials_name_list:
            mat_id = self.return_material_table_id(material_name)
            if mat_id:
                # new_material = self.papi.project_material_read(self.id, mat_id)
                value = materials_update_dict[material_name]
                mat = danka_thermal_api.Material(name = material_name, conductivity = str(value), conductivity_y = str(value), conductivity_z = str(value), color = "#456d82", anisotropic = False)
                self.papi.project_material_update(self.id, mat_id, mat)
    # dedeepyo : 7-Oct-25

    def delete_materials(self):
        for mat in self.material_list:
         self.papi.project_material_delete(self.id, mat.id)
        print("Deleted Materials successfully")

    def list_projects(self):
        papi = danka_thermal_api.ProjectApi(api_client=self.api)
        list = papi.project_list()
        return list

    def find_project_id(self,name):
        proj_list = self.list_projects()
        for item in proj_list:
            if item.name == name:
                return item.id
        raise Exception("Project not found")

    def load_material_table(self):
        self.material_list = self.papi.project_material_list(self.id)        

    def return_material_table_id(self, material_name):
        for mat in self.material_list:
            if material_name == mat.name:
                return mat.id
        raise Exception(f"Material {material_name} not found")
        return None
    
    def clean_project(self):
        self.papi.project_pcb_delete_all(self.id)
        self.papi.project_source_delete_all(self.id) #
        self.papi.project_box_delete_all(self.id) #
        # self.papi.project_source_delete_all(self.id)
        # for box in self.list_boxes():
        #     self.papi.project_pcb_delete(self.id,box.id)

    def delete_heat_sink(self):
        self.papi.project_heatsink_delete_all(self.id)

    # dedeepyo : 05-Feb-2025
    def delete_plane_power(self):
        power_plane_list = self.papi.project_source_list(self.id)
        if power_plane_list:
                power_plane_list_dict = power_plane_list.to_dict()["result"]
            # if power_plane_list_dict:
                for plane in power_plane_list:
                    plane_dict = plane.to_dict()["result"]
                    # print(plane["name"])
                    # if "_plane_power" in plane["name"]:
                    self.papi.project_source_delete(self.id, plane["id"])
        #     else:
        #         print("No power planes found.")
        # else:
        #     print("No power planes found.")
    # dedeepyo : 05-Feb-2025
        
    # dedeepyo : 18-Dec-24 : TIM deletion #
    def delete_TIM(self):
        project_boxes = self.papi.project_box_list(self.id)
        if project_boxes:    
            project_boxes_dict = project_boxes.to_dict()["result"]
            if project_boxes_dict:
                for box in project_boxes_dict:
                    if "_TIM" in box["name"]:
                        self.papi.project_box_delete(self.id, box["id"])
            else:
                print("No boxes found")
        else:
            print("No boxes found")
    # dedeepyo : 18-Dec-24

    # Moving create_all_bonding to therm.py

        # dedeepyo : 30-Jan-2025 : Bonding layer addition 
    # height : Thickness of the bonding layer; determined based on input from Krutikesh.
    # For Box, both z and dz are in mm. For PCBLayer, thickness is in um. For PCB, z is in mm.
    # height here is in um.
    def calculate_ratio(self, bonding, box):
        radius = bonding.get_diameter() / 2
        n_min_x = max(math.ceil((radius - bonding.get_offset()) / bonding.get_pitch()), 0)
        n_max_x = math.floor((1000 * box.width - bonding.get_offset() - radius) / bonding.get_pitch())
        n_x = n_max_x - n_min_x + 1
        # print("n_min_x : " + str(n_min_x) + " n_max_x : " + str(n_max_x))
        n_min_y = max(math.ceil((radius - bonding.get_offset()) / bonding.get_pitch()), 0)
        n_max_y = math.floor((1000 * box.length - bonding.get_offset() - radius) / bonding.get_pitch())
        n_y = n_max_y - n_min_y + 1
        # print("n_min_y : " + str(n_min_y) + " n_max_y : " + str(n_max_y))
        # print(n_x, n_y, box.width, box.length, radius, bonding.get_offset(), bonding.get_pitch())
        if(n_x <= 0 or n_y <= 0):
            return 0.00
        else:
            if(bonding.get_shape() == "sphere"):
                unit_volume = 4 * math.pi * (radius ** 3) / 3
            elif(bonding.get_shape() == "cylinder"):
                unit_volume = math.pi * (radius ** 2) * bonding.get_height()
            elif(bonding.get_shape() == "cuboid"):
                unit_volume = bonding.get_cross_section_area() * bonding.get_height()
            else:
                raise Exception("Invalid bonding shape")
            
            # print("Unit volume is : " + str(unit_volume))
            material_volume = unit_volume * n_x * n_y
            # print("Material volume is : " + str(material_volume))
            # print("Bonding layer volume is : " + str(1000 * box.width * 1000 * box.length * bonding.get_height()))
            ratio = material_volume / (1000 * box.width * 1000 * box.length * bonding.get_height())
            return ratio

    # dedeepyo : 12-Feb-2025 : Implementing real children finder to avoid creating bonding for fake chiplets.
    def get_real_children_recursive(self, chiplet_list):
        real_children = []
        fake_children = []
        for chiplet in chiplet_list:
            child_chiplets = chiplet.get_child_chiplets()
            for child_chiplet in child_chiplets:
                if(child_chiplet.get_fake() == False):
                    real_children.append(child_chiplet)
                else:
                    fake_children.append(child_chiplet)

        if(fake_children != []):
            real_children.extend(self.get_real_children_recursive(fake_children))

        return real_children
    # dedeepyo : 12-Feb-2025 #

    def create_all_bonding(self, box_list, name_type_dict, bonding_list):
        bondings = {b.get_name():b for b in bonding_list}
        bonding_dict = {}
        for key in name_type_dict:
            x, y = key.split("#")
            if x not in bonding_dict:
                bonding_dict[x] = {}
            if y not in bonding_dict[x]:
                bonding_dict[x][y] = bondings[name_type_dict[key]]

        bm = [box for box in box_list if box.start_z == 0.000000]
        for b in bm:
            chiplet_tree_root = b.chiplet_parent
            self.create_bonding(box_list, chiplet_tree_root, bonding_dict)

    # Assuming bonding only between interposer and GPU or HBM, not between stacked chiplets. # This assumption is no longer valid.
    def create_bonding(self, box_list, base_chiplet, bonding_dict):
        # test1 = [box for box in box_list if "bonding" in box.name]
        # if(len(test1) > 0):
        #     return
        
        # bondings = [b for b in bonding_list if b.get_name() == name]
        # if(bondings is None):
        #     raise Exception("Bonding not found")        
        # bonding = bondings[0]

        
        # base_box = [box for box in box_list if box.name == base][0]
        
        # test_children_of_interposer = self.get_real_children_recursive(intp.chiplet_parent.get_child_chiplets())
        # print("Testing: Real children of interposer are : " + str([t.name for t in test_children_of_interposer]))

        children_of_base = base_chiplet.get_child_chiplets()
        # print(str([x.get_name() for x in children_of_interposer]))
        # z = [x for x in children_of_interposer if x == None]
        # print(str(len(z)))
        # y = [x.get_name() for x in children_of_interposer if x.get_fake() == True]
        # print(str(y))
        for chiplet in children_of_base:
            try:
                bonding = bonding_dict[base_chiplet.get_chiplet_type()].get(chiplet.get_chiplet_type())
            except:
                bonding = None

            if bonding is not None:
                material = bonding.get_material()
                height = bonding.get_height()
                height_mm = height / 1000

                height_mm = round(height_mm, 6)
                box = chiplet.get_box_representation()
                x = round(box.start_x, 6)
                y = round(box.start_y, 6)
                z = round(box.start_z, 6)
                dx = round(box.width, 6)
                dy = round(box.length, 6)

                ratio = 100 * self.calculate_ratio(bonding, box)
                # print("Ratio is : " + str(ratio))   

                pcblayer = danka_thermal_api.PCBLayer(name = f"PCB_Layer_{chiplet.name}_bonding", thickness = str(height), thickness_calc = height, material = self.return_material_table_id(material), material_name = material, fill_material = self.return_material_table_id("Epoxy, Silver filled"), fill_material_name = "Epoxy, Silver filled", ratio = ratio)
                # pcblayer = None
                data = {
                    "name": f"{chiplet.name}_bonding",
                    "x": str(x),
                    "y": str(y),
                    "z": str(z),
                    "dx": str(dx),
                    "dy": str(dy),
                    "index": 57005,
                    "layers" : [pcblayer]
                }
                self.papi.project_pcb_create(self.id, data)
                # print("Creating PCBLayer for box : " + box.name + " with power : " + str(box.power) + " and material : " + material + " at (z : " + str(box.start_z) + ", height :  " + str(height_mm) + ")")
                self.recursively_lift_box(chiplet, box_list, height_mm)

            if(bonding_dict.get(chiplet.get_chiplet_type()) is not None):
                self.create_bonding(box_list, chiplet, bonding_dict)
    
    def recursively_lift_box(self, chiplet, box_list, height):
        box = chiplet.get_box_representation()
        box.start_z = box.start_z + height
        # print("Lifting box " + box.name + " to z : " + str(box.start_z))
        for child in chiplet.get_child_chiplets():
            self.recursively_lift_box(child, box_list, height)
        return
    # dedeepyo : 07-Feb-2025 #

    # dedeepyo : 9-Apr-25 : Load bonding boxes. 
    # A special format is used to define stackup of bonding boxes. They are of the format <layer_count>:<material_name>:<material_ratio>,<fill_material_name>:<fill_material_ratio>
    def load_bonding_boxes(self, bonding_box_list):
        for box in bonding_box_list:
            x = round(box.start_x, 6)
            y = round(box.start_y, 6)
            z = round(box.start_z, 6)
            dx = round(box.width, 6)
            dy = round(box.length, 6)
            # dz = round(box.height, 6)
            height = round(1000 * box.height, 3)
            # print(box.get_box_stackup())
            material_composition = box.get_box_stackup()[2:].split(",", 1)
            material_composition = [m.split(":") for m in material_composition]
            material_name = material_composition[0][0]
            fill_material_name = material_composition[1][0]
            ratio = float(material_composition[0][1])
            # print("Ratio is : " + str(ratio))   

            pcblayer = danka_thermal_api.PCBLayer(name = f"PCB_Layer_{box.name}", thickness = str(height), thickness_calc = height, material = self.return_material_table_id(material_name), material_name = material_name, fill_material = self.return_material_table_id(fill_material_name), fill_material_name = fill_material_name, ratio = ratio)
            # pcblayer = None
            data = {
                "name": f"{box.name}",
                "x": str(x),
                "y": str(y),
                "z": str(z),
                "dx": str(dx),
                "dy": str(dy),
                "index": 57005,
                "layers" : [pcblayer]
            }
            self.papi.project_pcb_create(self.id, data)
    # dedeepyo : 9-Apr-25

    # dedeepyo : 2-Jun-25 : Update power for all boxes.
        # for box in boxes:
        #     if box.power is not None:
        #         power_num = round(box.power * 1000, 6)
        #         if power_num > 0:
        #             power_values[box.chiplet_parent.get_chiplet_type()] = power_num
        #             self.papi.project_parameter_update(self.id, anemoi_parameters[box.chiplet_parent.get_chiplet_type() + "_power"], box.chiplet_parent.get_chiplet_type() + "_power", power_num)
                
    # dedeepyo : 2-Jun-25

    # dedeepyo : 3-Jun-25 : Parameterizing box power.
    # def parameterize_box_power(self, box_list):
    #     for box in box_list:
    #         # dedeepyo : 2-Jun-25 : Parameterizing box power.
    #         # Assuming, all boxes of a particular chiplet_type have same power.
    #         if box.power is None:
    #             box.power = 0.0
    #         box_power_in_mW = round(box.power * 1000, 6)
    #         try:
    #             power_num_in_mW = power_values[box.chiplet_parent.get_chiplet_type()]
    #             # if(power_num_in_mW != box_power_in_mW): # Assuming this asymmetry is never encountered.
    #             #     self.papi.project_parameter_update(self.id, box.chiplet_parent.get_chiplet_type() + "_power", box_power_in_mW)
    #             power_parameter_in_mW = anemoi_parameters[box.chiplet_parent.get_chiplet_type() + "_power"]
    #         except KeyError:
    #             power_num_in_mW = box_power_in_mW
    #             power_parameter_in_mW = None
    #             for key, value in power_values.items():
    #                 if value == power_num_in_mW:
    #                     power_parameter_in_mW = anemoi_parameters[key + "_power"]
    #                     power_values[box.chiplet_parent.get_chiplet_type()] = power_num_in_mW
    #                     anemoi_parameters[box.chiplet_parent.get_chiplet_type() + "_power"] = power_parameter_in_mW
    #             if power_parameter_in_mW is None:
    #                 power_parameter_in_mW = box.chiplet_parent.get_chiplet_type() + "_power"
    #                 # self.papi.project_parameter_create(self.id, power_parameter_in_mW, box.chiplet_parent.get_chiplet_type() + "_power", power_num_in_mW)
    #                 anemoi_parameters[power_parameter_in_mW] = power_parameter_in_mW     
    #                 power_values[box.chiplet_parent.get_chiplet_type()] = power_num_in_mW       
    #         # dedeepyo : 2-Jun-25
    #     print(anemoi_parameters)
    #     print(power_values)
    # dedeepyo : 3-Jun-25

    # dedeepyo : 3-Jun-25 : Power Dictionary update.
    def update_power_dict(self, power_dict, anemoi_parameter_ID = {}):
        anemoi_parameters_list = self.papi.project_parameter_list(self.id)
        for anemoi_param in anemoi_parameters_list:
            anemoi_param_fields = anemoi_param.to_dict()
            anemoi_parameter_ID[anemoi_param_fields["name"]] = anemoi_param_fields["id"]

        for key, value in power_dict.items():
            power_values[key] = round(value * 1000, 6) # Convert to mW
            param_dict = {
                "name": anemoi_parameters[key],
                "description": key + " power in mW",
                "value": power_values[key] # Convert to mW
            }
            self.papi.project_parameter_update(self.id, anemoi_parameter_ID[anemoi_parameters[key]], param_dict)
    
    # def update_power_values(self, boxes, power_values_dict):
    #     for key, value in power_values_dict.items():
    #         power_in_mW = round(value * 1000, 6)
    #         power_values[key] = power_in_mW
    #         self.papi.project_parameter_update(self.id, key, key, power_in_mW)

    def initialize_parameters(self):
        for key, value in power_values.items():
            power_num_in_mW = value
            anemoi_parameters[key] = key + "_power"
            param_dict = {
                "name": anemoi_parameters[key],
                "description": key + " power in mW",
                "value": power_num_in_mW
            }
            self.papi.project_parameter_create(self.id, param_dict)

        anemoi_parameter_ID = {}
        anemoi_parameters_list = self.papi.project_parameter_list(self.id)
        for anemoi_param in anemoi_parameters_list:
            anemoi_param_fields = anemoi_param.to_dict()
            anemoi_parameter_ID[anemoi_param_fields["name"]] = anemoi_param_fields["id"]
        
        return anemoi_parameter_ID
    
    def initialize_power_dict(self, power_dict):
        for key, value in power_dict.items():
            power_values[key] = round(value * 1000, 6) # Convert to mW and round to 6 decimal places
    
    # dedeepyo : 3-Jun-25

    # dedeepyo : 14-Oct-24 : PCB create #
    def load_boxes(self, box_list, layers):
        for box in box_list:
            # dedeepyo : 2-Jun-25 : Parameterizing box power.
            # Assuming, all boxes of a particular chiplet_type have same power.
            # if box.power is None:
            #     box.power = 0.0
            # box_power_in_mW = round(box.power * 1000, 6)
            # try:
            #     power_num_in_mW = power_values[box.chiplet_parent.get_chiplet_type()]
            #     # if(power_num_in_mW != box_power_in_mW): # Assuming this asymmetry is never encountered.
            #     #     self.papi.project_parameter_update(self.id, box.chiplet_parent.get_chiplet_type() + "_power", box_power_in_mW)
            #     power_parameter_in_mW = anemoi_parameters[box.chiplet_parent.get_chiplet_type() + "_power"]
            # except KeyError:
            #     power_num_in_mW = box_power_in_mW
            #     power_parameter_in_mW = None
            #     for key, value in power_values.items():
            #         if value == power_num_in_mW:
            #             power_parameter_in_mW = anemoi_parameters[key + "_power"]
            #             power_values[box.chiplet_parent.get_chiplet_type()] = power_num_in_mW
            #             anemoi_parameters[box.chiplet_parent.get_chiplet_type() + "_power"] = power_parameter_in_mW
            #     if power_parameter_in_mW is None:
            #         power_parameter_in_mW = box.chiplet_parent.get_chiplet_type() + "_power"
            #         self.papi.project_parameter_create(self.id, power_parameter_in_mW, box.chiplet_parent.get_chiplet_type() + "_power", power_num_in_mW)
            #         anemoi_parameters[power_parameter_in_mW] = power_parameter_in_mW     
            #         power_values[box.chiplet_parent.get_chiplet_type()] = power_num_in_mW       
            # dedeepyo : 2-Jun-25
            # dedeepyo : 28-Jan-2025 : Adding multiple power planes to the HBM.
            # Create a box if single layer stackup of single material.
            if box.power is not None:
                if(box.chiplet_parent.get_chiplet_type()[0:5] == "HBM_l"):
                    power_parameter_in_mW = anemoi_parameters["HBM_l"]
                else:
                    try:
                        power_parameter_in_mW = anemoi_parameters[box.chiplet_parent.get_chiplet_type()]
                    except KeyError:
                        print("KeyError: " + box.chiplet_parent.get_chiplet_type())
                        power_parameter_in_mW = 0.00

            stackup = box.get_box_stackup()
            stackup_list = stackup.split(",")
            mId = None
            if(len(stackup_list) == 1):
                _, layer_name = stackup_list[0].split(":")
                for layer in layers:
                    if(layer.get_name() == layer_name):
                        m = layer.get_material() # Assuming there is no layer without a material.
                        m_mat_list = m.split(',')
                        if(len(m_mat_list) > 1):
                            if(len(m_mat_list) > 2):
                                raise Exception("More than two materials found for a single layer")
                            else:
                                height = round(1000 * box.height, 3)
                                primary_material, primary_ratio = m_mat_list[0].split(':')
                                secondary_material, secondary_ratio = m_mat_list[1].split(':')
                                
                                total_ratio = float(primary_ratio) + float(secondary_ratio)
                                if(total_ratio != 1.00):
                                    raise Exception("Total Ratio of materials is not 100%")
                                                                    
                                ratio = 100 * float(primary_ratio)
                                pcblayer = danka_thermal_api.PCBLayer(name = f"PCB_Layer_{box.name}", thickness = str(height), thickness_calc = height, material = self.return_material_table_id(primary_material), material_name = primary_material, fill_material = self.return_material_table_id(secondary_material), fill_material_name = secondary_material, ratio = ratio)
                                data = {
                                    "name": box.name,
                                    "x": str(round(box.start_x, 6)),
                                    "y": str(round(box.start_y, 6)),
                                    "z": str(round(box.start_z, 6)),
                                    "dx": str(round(box.width, 6)),
                                    "dy": str(round(box.length, 6)),
                                    "index": 57005,
                                    "layers" : [pcblayer]
                                }
                                self.papi.project_pcb_create(self.id, data)

                                # dedeepyo : 2-Jun-25 : Creating power plane for the newly created PCB.
                                power_num = round(box.power * 1000, 2)
                                if power_num > 0:
                                    heat_source_data = {}
                                    heat_source_data["name"] = box.name + "_plane_power"
                                    heat_source_data["x"] = round(box.start_x, 6)
                                    heat_source_data["y"] = round(box.start_y, 6)
                                    heat_source_data["z"] = round(box.start_z + box.height/2, 6)
                                    heat_source_data["dx"] = round(box.width, 6)
                                    heat_source_data["dy"] = round(box.length, 6)
                                    heat_source_data["dz"] = 0.1
                                    heat_source_data["hc"] = box.ambient_conduct
                                    heat_source_data["index"] = 57005
                                    # heat_source_data["power"] = round(box.power * 1000, 6)
                                    heat_source_data["power"] = power_parameter_in_mW
                                    heat_source_data["plane"] = "XY"
                                    heat_source_data["color"] = "#000"
                                    self.papi.project_source_create(self.id, heat_source_data)
                                # dedeepyo : 2-Jun-25
                        else:                            
                            mId = self.return_material_table_id(m_mat_list[0].split(':')[0])
                            if mId is None:
                                raise Exception("Material is None")
                                
                            data = {
                                "name": box.name,
                                "x": round(box.start_x, 6),
                                "y": round(box.start_y, 6),
                                "z": round(box.start_z, 6),
                                "dx": round(box.width, 6),
                                "dy": round(box.length, 6),
                                "dz": round(box.height, 6),
                                "index": 57005,
                                "material" : mId,
                                "power" : power_parameter_in_mW,
                                "mesh_minx": 0.00,
                                "mesh_maxx": 0.00,
                                "mesh_miny": 0.00,
                                "mesh_maxy": 0.00,
                                "mesh_minz": 0.00,
                                "mesh_maxz": 0.00
                                # "power" : round(box.power * 1000, 2)
                            }
                            print("Creating box : " + box.name + " with power : " + str(box.power) + " and material : " + m + " at (z : " + str(data["z"]) + ", dz :  " + str(data["dz"]) + ")")
                            # temp_box = danka_thermal_api.Box(data)
                            self.papi.project_box_create(self.id, data)
                # print("Creating box : " + box.name + " with power : " + str(box.power) + " and material : " + m + " at (z : " + str(data["z"]) + ", dz :  " + str(data["dz"]) + ")")
            # dedeepyo : 30-Jan-2025
            else:
                power_num = round(box.power * 1000, 2)
                if power_num > 0:
                    heat_source_data = {}
                    heat_source_data["name"] = box.name + "_plane_power"
                    heat_source_data["x"] = round(box.start_x, 6)
                    heat_source_data["y"] = round(box.start_y, 6)
                    heat_source_data["z"] = round(box.start_z + box.height/2, 6)
                    heat_source_data["dx"] = round(box.width, 6)
                    heat_source_data["dy"] = round(box.length, 6)
                    heat_source_data["dz"] = 0.1
                    heat_source_data["hc"] = box.ambient_conduct
                    heat_source_data["index"] = 57005
                    # heat_source_data["power"] = round(box.power * 1000, 6)
                    heat_source_data["power"] = power_parameter_in_mW
                    heat_source_data["plane"] = "XY"
                    heat_source_data["color"] = "#000"
                    self.papi.project_source_create(self.id, heat_source_data)

                data = {}
                data["name"] = box.name
                data["x"] = round(box.start_x, 6)
                data["y"] = round(box.start_y, 6)
                data["z"] = round(box.start_z, 6)
                data["dx"] = round(box.width, 6)
                data["dy"] = round(box.length, 6)
                data["index"] = 57005

                if box.ambient_conduct != 0:
                    data["hc"] = box.ambient_conduct

                i = 0
                pcblayers = []
                for stackup_iter in stackup_list:
                    layer_num, layer_name = stackup_iter.split(":")                   

                    t = 0.00
                    m = ""
                    mId = -1
                    for layer in layers:
                        if(layer.get_name() == layer_name):
                            t = int(layer_num) * layer.get_thickness() * 1000
                            t = round(t, 2)
                            m = layer.get_material()
                            m_mat_list = m.split(',')
                            if(len(m_mat_list) > 1):
                                if(len(m_mat_list) > 2):
                                    raise Exception("More than two materials found for a single layer")
                                else:
                                    primary_material, primary_ratio = m_mat_list[0].split(':')
                                    secondary_material, secondary_ratio = m_mat_list[1].split(':')
                                    
                                    total_ratio = float(primary_ratio) + float(secondary_ratio)
                                    if(total_ratio != 1.00):
                                        raise Exception("Total Ratio of materials is not 100%")
                                    
                                    ratio = 100 * float(primary_ratio)
                                    pcblayer = danka_thermal_api.PCBLayer(name=f"PCB_Layer_{i}", thickness=str(t), thickness_calc=t, material=self.return_material_table_id(primary_material), material_name=primary_material, fill_material=self.return_material_table_id(secondary_material), fill_material_name=secondary_material, ratio=ratio)
                            else:
                                mId = self.return_material_table_id(m)
                                if mId is None:
                                    raise Exception("Material is None")
                                pcblayer = danka_thermal_api.PCBLayer(name=f"PCB_Layer_{i}", thickness=str(t), thickness_calc=t, material=mId, material_name=m, fill_material=mId, fill_material_name=m)

                    pcblayers.insert(0, pcblayer)
                    # print("Creating PCBLayer for box : " + box.name + " with power : " + str(box.power) + " and material : " + m + " at (z : " + str(data["z"]) + ", t :  " + str(t) + ")")
                    i = i + 1
                    
                data["layers"] = pcblayers
                self.papi.project_pcb_create(self.id,data)
    # END # dedeepyo : 14-Oct-24 : PCB create #
    
    def max_z_bounds(self,box_list):
         z = round(max(box.start_z for box in box_list), 6)
         dz = round(max(box.start_z + box.height for box in box_list), 6)
         return z,dz
    
    def isStacked(self, box, box_list, other_box_list):
        """
        This function checks if a given box is stacked on top of another box in the box_list.
        
        Parameters:
        - box: The box to check for stacking
        - box_list: List of all boxes to compare against
        - other_box_list: A list of boxes to exclude from the stacking check
        
        Returns:
        - The box that the given box is stacked on, if any
        - An empty list if no stacking is found
        
        The function checks for:
        1. Overlap in x and y dimensions
        2. The z-coordinate of the other box matching the top of the given box
        3. The other box not being in the other_box_list
        4. The other box not being the same as the given box or named "interposer"
        """
        excluded_types = ["interposer", "substrate", "PCB", "Power_Source"]
        for other_box in box_list:
            if other_box == box or other_box.chiplet_parent.get_chiplet_type() in excluded_types:
                continue
            x_overlap = box.start_x < other_box.start_x + other_box.width and other_box.start_x < box.start_x + box.width
            y_overlap = box.start_y < other_box.start_y + other_box.length and other_box.start_y < box.start_y + box.length
            z_stacked = other_box.start_z == box.start_z + box.height
            if (x_overlap and y_overlap and z_stacked) and other_box not in other_box_list:
                return other_box
        return []
    
    # dedeepyo : 1-Jan-25 : Implementing TIM creation for all chiplets at the top
    def create_TIM_to_heatsink(self, box_list, material = "TIM0p5", min_TIM_height = 0.1):
        m = self.return_material_table_id(material)
        z_min = max([box.end_z for box in box_list])
        # print("z_min is : " + str(z_min))
        z = z_min + min_TIM_height
        # print("z is : " + str(z))
        for box in box_list:
            # dedeepyo : 12-Feb-25 : A fake chiplet always has child chiplets; that is the purpose why it is made. Also, a box here is never fake.
            if(box.chiplet_parent.get_child_chiplets() == []):
                tim_height = z - box.end_z
                # print("TIM height is : " + str(tim_height))
                if(tim_height != 0):
                    tim_data = {
                        "name": str(box.name) + "_TIM",
                        "x": str(round(box.start_x, 6)),
                        "y": str(round(box.start_y, 6)),
                        "z": str(round(box.end_z, 6)),
                        "dx": str(round(box.width, 6)),
                        "dy": str(round(box.length, 6)),
                        "dz": str(round(tim_height, 6)),
                        "index": 57005,
                        "material": m,
                        "mesh_minx": 0.00,
                        "mesh_maxx": 0.00,
                        "mesh_miny": 0.00,
                        "mesh_maxy": 0.00,
                        "mesh_minz": 0.00,
                        "mesh_maxz": 0.00
                    }
                    self.papi.project_box_create(self.id, tim_data)
                    # print(tim_data["name"] + " starts from z : " + tim_data["z"] + " and has height : " + tim_data["dz"])
                else:
                    print("The top of PCB " + box.name + " is at the same level as the bottom of heat sink!")
    # dedeepyo : 1-Jan-25 

    # dedeepyo : 9-Apr-25 : Load TIM boxes.
    def load_TIM_boxes(self, box_list):
        for box in box_list:
            m = self.return_material_table_id(box.get_box_stackup().split(":")[1])
            tim_data = {
                "name": str(box.name),
                "x": str(round(box.start_x, 6)),
                "y": str(round(box.start_y, 6)),
                "z": str(round(box.start_z, 6)),
                "dx": str(round(box.width, 6)),
                "dy": str(round(box.length, 6)),
                "dz": str(round(box.height, 6)),
                "index": 57005,
                "material": m,
                "mesh_minx": 0.00,
                "mesh_maxx": 0.00,
                "mesh_miny": 0.00,
                "mesh_maxy": 0.00,
                "mesh_minz": 0.00,
                "mesh_maxz": 0.00
            }
            self.papi.project_box_create(self.id, tim_data)
    # dedeepyo : 9-Apr-25

    # dedeepyo : 1-Jan-25 : Implementing updation of power numbers for all chiplets
    def update_power_plane(self, box_list):
        power_box_dict = {box.name + "_plane_power" : box.power for box in box_list}
        power_plane_list = self.papi.project_source_list(self.id)
        if power_plane_list:
            power_plane_list_dict = power_plane_list.to_dict()["result"]
            if power_plane_list_dict:
                for plane in power_plane_list_dict:
                    if plane.name in power_box_dict:
                        power_num = round(power_box_dict[plane.name]*1000, 2)
                        if power_num != plane["power"]:
                            heat_source_data = {}
                            heat_source_data["name"] = plane["name"]
                            heat_source_data["x"] = plane["x"]
                            heat_source_data["y"] = plane["y"]
                            heat_source_data["z"] = plane["z"]
                            heat_source_data["dx"] = plane["dx"]
                            heat_source_data["dy"] = plane["dy"]
                            heat_source_data["dz"] = plane["dz"]
                            heat_source_data["hc"] = plane["hc"]
                            heat_source_data["index"] = plane["index"]
                            heat_source_data["power"] = power_num
                            heat_source_data["plane"] = plane["plane"]
                            heat_source_data["color"] = plane["color"]
                            self.papi.project_source_update(self.id, plane['id'], heat_source_data)
            else:
                print("No heat sources / power planes found.")
        else:
            print("No heat sources / power planes found.")
    # dedeepyo : 1-Jan-25

    def fill_gaps(self, box_list, hs_z, material = "Epoxy, Silver filled"):
        intp_list = [b for b in box_list if b.chiplet_parent.get_chiplet_type() == "interposer" or b.chiplet_parent.get_chiplet_type() == "substrate"]
        intp = intp_list[0]
        for i in intp_list:
            if(i.end_z > intp.end_z):
                intp = i
        
        mId = self.return_material_table_id(material)
        if mId is None:
            raise Exception("Material is None")
        
        data = {
            "name": "Gap_filler",
            "x": round(intp.start_x, 6),
            "y": round(intp.start_y, 6),
            "z": round(intp.end_z, 6),
            "dx": round(intp.width, 6),
            "dy": round(intp.length, 6),
            "dz": round(hs_z - intp.end_z, 6),
            "index": 1000000, # 10000000
            "material" : mId,
            "mesh_minx": 0.00,
            "mesh_maxx": 0.00,
            "mesh_miny": 0.00,
            "mesh_maxy": 0.00,
            "mesh_minz": 0.00,
            "mesh_maxz": 0.00
        }
        self.papi.project_box_create(self.id, data)

    # Assuming same scale factor in x and y directions.
    def create_heat_sink(self, box_list, heatsink_list, heatsink_name, min_TIM_height = 0.01, scale_factor_x = 0, scale_factor_y = 0, area_scale_factor = 0):
        # dedeepyo : 7-Feb-2025 : Heatsink object creation.
        heatsinks = [h for h in heatsink_list if h.get_name() == heatsink_name]
        if(heatsinks is None):
            raise Exception("Heatsink not found")
        
        excluded_types = ["interposer", "substrate", "PCB", "Power_Source"]
        box_list_min = [box for box in box_list if box.chiplet_parent.get_chiplet_type() not in excluded_types]
        x_min = min([box.start_x for box in box_list_min])
        x_max = max([box.end_x for box in box_list_min])
        y_min = min([box.start_y for box in box_list_min])
        y_max = max([box.end_y for box in box_list_min])
            
        if(area_scale_factor != 0):
            dimension_scale_factor = math.sqrt(area_scale_factor)
            dx = dimension_scale_factor * (x_max - x_min)
            dy = dimension_scale_factor * (y_max - y_min)
        elif(scale_factor_x == 0):
            if(scale_factor_y == 0):
                dy = heatsinks[0].get_base_length()
            else:
                dy = scale_factor_y * (y_max- y_min)
            dx = heatsinks[0].get_base_width()
        elif(scale_factor_y == 0):
            dy = heatsinks[0].get_base_length()
            dx = scale_factor_x * (x_max - x_min)
        else:
            dx = scale_factor_x * (x_max - x_min)
            dy = scale_factor_y * (y_max- y_min)

        x = (x_max + x_min - dx) / 2
        y = (y_max + y_min - dy) / 2
        z_min = max([box.end_z for box in box_list_min])
        # print(str([box.end_z for box in box_list_min]))
        # print(str([box.name for box in box_list_min if box.end_z == z_min]))
        # print("z_min is : " + str(z_min))
        z = z_min + min_TIM_height
        # print("z is : " + str(z))
        # x = 0
        # dedeepyo : 31-Oct-2024 : Implementing checker for all top chiplets touching heat_sink

        # dedeepyo : 7-Feb-2025 : Heatsink object creation.
        fin_height = heatsinks[0].get_fin_height()
        fin_thickness = heatsinks[0].get_fin_thickness()
        material = heatsinks[0].get_material()
        fin_number = heatsinks[0].get_fin_count()
        hc = heatsinks[0].get_hc()
        fin_offset = heatsinks[0].get_fin_offset()
        dz = heatsinks[0].get_base_thickness()
        bind_to_ambient = heatsinks[0].get_bind_to_ambient()

        if(fin_number == 0):
            fin_number = int(dx / (2 * fin_thickness))
        # dedeepyo : 7-Feb-2025

        # dedeepyo : 18-Dec-24 : Implementing TIM creation for all chiplets at the top ## Uncomment
        # m  = self.return_material_table_id("TIM")
        # for box in box_list:
        #     if(box.chiplet_parent.get_child_chiplets() == []):
        #         tim_height = z - box.end_z
        #         if(tim_height != 0):
        #             tim_data = {
        #                 "name": str(box.name) + "_TIM",
        #                 "x": str(round(box.start_x, 2)),
        #                 "y": str(round(box.start_y, 2)),
        #                 "z": str(round(box.end_z, 2)),
        #                 "dx": str(round(box.width, 2)),
        #                 "dy": str(round(box.length, 2)),
        #                 "dz": str(round(tim_height, 2)),
        #                 "index": 57005,
        #                 "material": m
        #             }
        #             self.papi.project_box_create(self.id, tim_data)
        #         else:
        #             print("The top of PCB " + box.name + " is at the same level as the bottom of heat sink!")
        # dedeepyo : 18-Dec-24 ## Uncomment
        
        # dedeepyo : 31-Oct-2024
        # y = 0
        # z = 2.0
        # dx = 65
        # dy = 65

        data = {
            "name": f"HS_top",
            "index": 0,
            "material": self.return_material_table_id(material),  # Cu-Foil
            "x": str(round(x, 6)),
            "y": str(round(y, 6)),
            "base_dx": str(round(dx, 6)),
            "base_dy": str(round(dy, 6)),
            "z": str(round(z, 6)),
            "base_dz": str(round(dz, 6)),
            "fin_height": str(fin_height),
            "fin_thickness": str(fin_thickness),
            "fin_count": str(fin_number),
            "fin_axis": "Y",
            "hc": str(hc),
            "bound": bind_to_ambient,
            "mesh_minx": 0.00,
            "mesh_maxx": 0.00,
            "mesh_miny": 0.00,
            "mesh_maxy": 0.00,
            "mesh_minz": 0.00,
            "mesh_maxz": 0.00
        }
        # print(data)
        self.papi.project_heatsink_create(self.id, data) # Uncomment
        # print(data["name"] + " starts at z : " + data["z"] + " and has height : " + data["base_dz"])
        self.fill_gaps(box_list, z_min, material = "Infill_material") # "TIM", "AlN")

        ## TODO: This creates multiple heat sinks. We want 1 heatsink only. Probably have to simplify this heavily.
        # print("Heat Sink:-->",material)
        # other_box_list =[]
        # z = float('-inf')
        # dz = float('-inf')
        # for box in box_list:
        #     if box.name == "interposer":
        #         interposer = box
        #         other_box = self.isStacked(interposer,box_listther_box_list)
        #         if other_box.start_z > z and other_box.height > dz:
        #             z = round(other_box.start_z,2)
        #             dz = round(other_box.height,2)
        
        # #Creating Heatsink for components just above the interposer
        # if interposer:
        #     x = round(interposer.start_x, 2)
        #     y = round(interposer.start_y, 2)
        #     dx = round(interposer.width, 2)
        #     dy = round(interposer.length, 2)
        #     data = {
        #         "name": "HS",
        #         "index": 0,
        #         "material": self.return_material_table_id(material),  # Cu-Foil
        #         "x": str(x),
        #         "y": str(y),
        #         "base_dx": str(dx),
        #         "base_dy": str(dy),
        #         "z": str(z),
        #         "base_dz": str(dz),
        #         "fin_height": "5",
        #         "fin_thickness": "0.3",
        #         "fin_count": "40",
        #         "fin_axis": "Y",
        #         "hc": "300"
        #     }
        #     self.papi.project_heatsink_create(self.id, data)

        # #Create Heatsink for stacked components
        # for box in box_list:
        #     if box.name == "interposer":
        #         continue
        #     stack_box = self.isStacked(box,box_list,other_box_list)
        #     if stack_box:
        #         other_box_list.append(stack_box)
        #         x = round(stack_box.start_x, 2)
        #         y = round(stack_box.start_y, 2)
        #         dx = round(stack_box.width, 2)
        #         dy = round(stack_box.length, 2)
        #         z = round(stack_box.start_z,2)
        #         dz = round(stack_box.height,2)
        #         data = {
        #             "name": f"HS_{stack_box.name}",
        #             "index": 0,
        #             "material": self.return_material_table_id(material),  # Cu-Foil
        #             "x": str(x),
        #             "y": str(y),
        #             "base_dx": str(dx),
        #             "base_dy": str(dy),
        #             "z": str(z),
        #             "base_dz": str(dz),
        #             "fin_height": "5",
        #             "fin_thickness": "2",
        #             "fin_count": "60",
        #             "fin_axis": "Y",
        #             "hc": "500"
        #         }
        #         self.papi.project_heatsink_create(self.id, data)
                
        # print("Successfully created HeatSink")

    # dedeepyo : 9-Apr-25 : Load heatsink_obj which is a dict.
    def load_heatsink(self, box_list, heatsink_obj, min_TIM_height):
        data = {
            "name": heatsink_obj["name"],
            "index": heatsink_obj["index"],
            "x": heatsink_obj["x"],
            "y": heatsink_obj["y"],
            "base_dx": heatsink_obj["base_dx"],
            "base_dy": heatsink_obj["base_dy"],
            "z": heatsink_obj["z"],
            "base_dz": heatsink_obj["base_dz"],
            "fin_height": heatsink_obj["fin_height"],
            "fin_thickness": heatsink_obj["fin_thickness"],
            "fin_count": heatsink_obj["fin_count"],
            "fin_axis": heatsink_obj["fin_axis"],
            "hc": heatsink_obj["hc"],
            "bound": heatsink_obj["bound"],
            "material": self.return_material_table_id(heatsink_obj["material"]),  # Cu-Foil
            "mesh_minx": 0.00,
            "mesh_maxx": 0.00,
            "mesh_miny": 0.00,
            "mesh_maxy": 0.00,
            "mesh_minz": 0.00,
            "mesh_maxz": 0.00
        }
        self.papi.project_heatsink_create(self.id, data) # Uncomment
        self.fill_gaps(box_list, float(heatsink_obj["z"]) - min_TIM_height, material = "Infill_material") # "AlN") # "TIM")
        # self.fill_spreader_gaps(box_list, heatsink_obj["x"], heatsink_obj["y"], heatsink_obj["base_dx"], heatsink_obj["base_dy"], float(heatsink_obj["z"]) - min_TIM_height) #TODO: Comment out for heat spreader same area as die.
    # dedeepyo : 9-Apr-25

    def fill_spreader_gaps(self, box_list, start_x, start_y, base_dx, base_dy, hs_z, material = "Epoxy, Silver filled"):
        intp_list = [b for b in box_list if b.chiplet_parent.get_chiplet_type() == "interposer" or b.chiplet_parent.get_chiplet_type() == "substrate" or b.chiplet_parent.get_chiplet_type() == "Power_Source"]
        intp = intp_list[0]
        for i in intp_list:
            if(i.end_z > intp.end_z):
                intp = i
        
        mId = self.return_material_table_id(material)
        if mId is None:
            raise Exception("Material is None")
        
        data = {
            "name": "Gap_filler_spreader",
            "x": round(float(start_x), 6),
            "y": round(float(start_y), 6),
            "z": round(intp.start_z, 6),
            "dx": round(float(base_dx), 6),
            "dy": round(float(base_dy), 6),
            "dz": round(hs_z - intp.start_z, 6),
            "index": 10000000,
            "material" : mId,
            "mesh_minx": 0.00,
            "mesh_maxx": 0.00,
            "mesh_miny": 0.00,
            "mesh_maxy": 0.00,
            "mesh_minz": 0.00,
            "mesh_maxz": 0.00
        }
        self.papi.project_box_create(self.id, data)

    # dedeepyo : 21-Jun-25 : Load heatsink_obj which is a dict.
    def load_multiple_heatsinks(self, box_list, heatsink_obj_list):
        for heatsink_obj in heatsink_obj_list:
            data = {
                "name": heatsink_obj["name"],
                "index": heatsink_obj["index"],
                "x": heatsink_obj["x"],
                "y": heatsink_obj["y"],
                "base_dx": heatsink_obj["base_dx"],
                "base_dy": heatsink_obj["base_dy"],
                "z": heatsink_obj["z"],
                "base_dz": heatsink_obj["base_dz"],
                "fin_height": heatsink_obj["fin_height"],
                "fin_thickness": heatsink_obj["fin_thickness"],
                "fin_count": heatsink_obj["fin_count"],
                "fin_axis": heatsink_obj["fin_axis"],
                "hc": anemoi_parameters[heatsink_obj["hc"]],
                "bound": heatsink_obj["bound"],
                "material": self.return_material_table_id(heatsink_obj["material"]),  # Cu-Foil
                "mesh_minx": 0.00,
                "mesh_maxx": 0.00,
                "mesh_miny": 0.00,
                "mesh_maxy": 0.00,
                "mesh_minz": 0.00,
                "mesh_maxz": 0.00
            }
            self.papi.project_heatsink_create(self.id, data) # Uncomment

        # self.fill_gaps(box_list, float(heatsink_obj["z"]), material = "Infill_material") # "AlN") # "TIM")
    # dedeepyo : 21-Jun-25

    # dedeepyo : 3-Mar-2025 : Heatsink object creation.
    def create_heat_sink_bottom(self, box_list, heatsink_list, heatsink_name, min_TIM_height = 0.01, area_scale_factor = 1, scale_factor_x = 0, scale_factor_y = 0):
        heatsinks = [h for h in heatsink_list if h.get_name() == heatsink_name]
        if(heatsinks is None):
            raise Exception("Heatsink not found")
        
        excluded_types = ["interposer", "substrate", "PCB"]
        box_list_min = [box for box in box_list if box.chiplet_parent.get_chiplet_type() not in excluded_types]
        x_min = min([box.start_x for box in box_list_min])
        x_max = max([box.end_x for box in box_list_min])
        y_min = min([box.start_y for box in box_list_min])
        y_max = max([box.end_y for box in box_list_min])
            
        if(area_scale_factor != 0):
            dimension_scale_factor = math.sqrt(area_scale_factor)
            dx = dimension_scale_factor * (x_max - x_min)
            dy = dimension_scale_factor * (y_max - y_min)
        elif(scale_factor_x == 0):
            if(scale_factor_y == 0):
                dy = heatsinks[0].get_base_length()
            else:
                dy = scale_factor_y * (y_max- y_min)
            dx = heatsinks[0].get_base_width()
        elif(scale_factor_y == 0):
            dy = heatsinks[0].get_base_length()
            dx = scale_factor_x * (x_max - x_min)
        else:
            dx = scale_factor_x * (x_max - x_min)
            dy = scale_factor_y * (y_max- y_min)

        x = (x_max + x_min - dx) / 2
        y = (y_max + y_min - dy) / 2
        z_min = min([box.start_z for box in box_list])
        z = z_min - min_TIM_height

        fin_height = (-1) * heatsinks[0].get_fin_height()
        fin_thickness = heatsinks[0].get_fin_thickness()
        material = heatsinks[0].get_material()
        fin_number = heatsinks[0].get_fin_count()
        hc = heatsinks[0].get_hc()
        fin_offset = heatsinks[0].get_fin_offset()
        dz = (-1) * heatsinks[0].get_base_thickness()
        bind_to_ambient = heatsinks[0].get_bind_to_ambient()

        if(fin_number == 0):
            fin_number = int(dx / (2 * fin_thickness))

        data = {
            "name": f"HS_bottom",
            "index": 0,
            "material": self.return_material_table_id(material),  # Cu-Foil
            "x": str(round(x, 6)),
            "y": str(round(y, 6)),
            "base_dx": str(round(dx, 6)),
            "base_dy": str(round(dy, 6)),
            "z": str(round(z, 6)),
            "base_dz": str(round(dz, 6)),
            "fin_height": str(fin_height),
            "fin_thickness": str(fin_thickness),
            "fin_count": str(fin_number),
            "fin_axis": "Y",
            "hc": str(hc),
            "bound": bind_to_ambient,
            "mesh_minx": 0.00,
            "mesh_maxx": 0.00,
            "mesh_miny": 0.00,
            "mesh_maxy": 0.00,
            "mesh_minz": 0.00,
            "mesh_maxz": 0.00
        }
        self.papi.project_heatsink_create(self.id, data) # Uncomment

        mId = self.return_material_table_id("TIM0p5")
        if mId is None:
            raise Exception("Material is None")

        box_data = {
            "name": "Bottom_TIM",
            "x": str(round(x, 6)),
            "y": str(round(y, 6)),
            "z": str(round(z, 6)),
            "dx": str(round(dx, 6)),
            "dy": str(round(dy, 6)),
            "dz": str(min_TIM_height),
            "index": 57005,
            # "index": 10000000,
            "material" : mId,
            "mesh_minx": 0.00,
            "mesh_maxx": 0.00,
            "mesh_miny": 0.00,
            "mesh_maxy": 0.00,
            "mesh_minz": 0.00,
            "mesh_maxz": 0.00
        }
        self.papi.project_box_create(self.id, box_data)
    # dedeepyo : 3-Mar-25 #

    def solve(self):
        self.papi.project_solve_list(self.id)
        while(True):
            task = self.papi.project_task_list(self.id)
            if task.task == None:
                break
            time.sleep(2)
        return
    
    def calculate_voxel_resolution_and_max_sizes(self, box_list):
        excluded_types = ["interposer", "substrate", "PCB", "Power_Source"]
        box_list_min = [box for box in box_list if box.chiplet_parent.get_chiplet_type() not in excluded_types]
        max_x = max(box.start_x + box.width for box in box_list_min)
        max_y = max(box.start_y + box.length for box in box_list_min)
        max_z = max(box.start_z + box.height for box in box_list_min)
        #print("INTERPOSER SIZES",max_x,max_y,max_z)
        base_box = max(box_list_min, key=lambda box: box.width * box.length * box.height)
        voxel_res_x = base_box.width / 100.0
        voxel_res_y = base_box.length / 100.0
        voxel_res_z = base_box.height / 50.0
        # voxel_res_x = base_box.width / 10.0
        # voxel_res_y = base_box.length / 10.0
        # voxel_res_z = base_box.height / 5.0 
        #voxel_res_z = 0.65
        voxel_res = [voxel_res_x, voxel_res_y, voxel_res_z]
        #print(voxel_res)
        max_sizes = [max_x, max_y, max_z]
        return voxel_res, max_sizes

    def solution_to_temp_map_3D(self, boxes):
        voxel_res, max_sizes = self.calculate_voxel_resolution_and_max_sizes(boxes)
        no_soln_x = []
        no_soln_y = []
        no_soln_z = []
        x_voxels = round(float(max_sizes[0] / voxel_res[0])) 
        y_voxels = round(float(max_sizes[1] / voxel_res[1])) 
        z_voxels = round(float(max_sizes[2] / voxel_res[2])) 
        temp_map = np.full((x_voxels, y_voxels , z_voxels), -1)  # Initialize with -1
        #print("Z range",voxel_res[2] / 2, max_sizes[2], voxel_res[2])
        z_range = np.arange(voxel_res[2] / 2, max_sizes[2], voxel_res[2])
        #print(voxel_res[2] / 2, max_sizes[2], voxel_res[2])
        #print("X coords:", voxel_res[0] , max_sizes[0], voxel_res[0])
        #print("Y coords:",voxel_res[1] , max_sizes[1], voxel_res[1])
        for z in z_range:
            
            #print(f"Z value {z}")
            solutions = self.papi.project_solution_plane_list(self.id, plane="xy", coordinate=z)
            #print("SOLUTIONS:",solutions)
            if not solutions:
                #print(f"No solution for {item}")
                continue

            data = solutions.to_dict()["result"]
            data_arr=[]
            if not data:
                continue
            for voxel in data:
                data_arr.append((voxel['temp'],voxel['x0'],voxel['y0'], voxel['dx'], voxel['dy']))

            for x in np.arange(voxel_res[0]/2 , max_sizes[0], voxel_res[0]):
                
                for y in np.arange(voxel_res[1]/2 , max_sizes[1], voxel_res[1]):
                    #print(f"BEGINNING OF {x,y} LOOP!!!!!!")
                    temp_sum = 0
                    num_solutions = 0
                    for item in data_arr:
                        #print("1ST CONDITION:",solution[0],solution[1], x - voxel_res[0], x + voxel_res[0])
                        #print("2ND CONDITION:", solution[0],solution[2], y - voxel_res[1],  y + voxel_res[1])
                        # if item[1] > x - voxel_res[0] and item[1] <= x + voxel_res[0] and item[2] > y - voxel_res[1]  and item[2] <= y + voxel_res[1] :
                        if item[1] + item[3] > x and item[1] <= x and item[2] + item[4] > y  and item[2] <= y :
                            temp_sum += item[0]
                            num_solutions += 1
                    #print(f"END OF {x,y} LOOP!!!!")
                    norm_x = int(x / voxel_res[0])
                    norm_y = int(y / voxel_res[1])
                    norm_z = int(z / voxel_res[2])
                    #print(f"norm_x : {norm_x}, norm_y:{norm_y}, norm_z:{norm_z}")
                    #print(f"TEMP SUM {temp_sum} and NUM SOLNS {num_solutions}")
                    if num_solutions != 0:
                        temp_avg = temp_sum / num_solutions
                        temp_map[norm_x, norm_y, norm_z] = temp_avg
                        #all_coords.append([norm_x, norm_y])
                        #all_temps.append(temp_avg)
                    else:
                        pass
                        # average temperature is undefined, grab temperature of last voxel
                         #print("No solutions found for voxel at x = " + str(x) + ", y = " + str(y) + ", z = " + str(z))
                        #if (norm_y-1 >= 0):
                         #   temp_map[norm_x,norm_y,norm_z] = temp_map[norm_x,norm_y-1,norm_z]
                        #else:
                          #  temp_map[norm_x,norm_y,norm_z] = temp_map[norm_x-1,norm_y,norm_z]
                        #print("No solutions found for voxel at x = " + str(x) + ", y = " + str(y) + ", z = " + str(z))
                   
        return temp_map            
    
    # dedeepyo : 3-Nov-2024 : Implementing mapping of temperature values from Anemoi Voxels to our own voxels.
    # Assumption : Each Anemoi Voxel is larger than our own voxel
    # Code works faster if our voxels are much more in number than Anemoi Voxels.
    # Sampling : We are picking (sampling) values at points (within Anemoi Voxels). The points chosen are midpoints of our own voxels.
    # Resolution : We are taking 1x1x1 points (within our voxel) from Anemoi Voxels and averaging the temperature values.
    # anemoi_voxel_start_x <= (n + 1/2) * voxel_res => n >= (anemoi_voxel_start_x / voxel_res) - 0.5 => start_x_n = ceil[(anemoi_voxel_start_x / voxel_res) - 0.5]
    # anemoi_voxel_end_x >= (n + 1/2) * voxel_res => n <= (anemoi_voxel_end_x / voxel_res) - 0.5 => end_x_n = floor[(anemoi_voxel_end_x / voxel_res) - 0.5]
    # Anemoi Voxel Count:  621906

    def solution_to_temp_map_3D_dray(self, boxes):
        voxel_res, max_sizes = self.calculate_voxel_resolution_and_max_sizes(boxes)
        x_voxels = round(float(max_sizes[0] / voxel_res[0])) 
        y_voxels = round(float(max_sizes[1] / voxel_res[1])) 
        z_voxels = round(float(max_sizes[2] / voxel_res[2])) 
        temp_map = np.full((x_voxels, y_voxels , z_voxels), 0.00)  # dedeepyo: Initialize with 0 : Easier to add values
        solutions_check = np.full((x_voxels, y_voxels, z_voxels), 0)

        # anemoi_voxel_count = 0        
        norm_z_range = np.arange(0, z_voxels, 1)
        z_coord = voxel_res[2] / 2
        for z in norm_z_range:
            solutions = self.papi.project_solution_plane_list(self.id, plane="xy", coordinate=z_coord)
            z_coord += voxel_res[2]
            if not solutions:
                print("No solution at z = " + str(z_coord))
            else:
                data = solutions.to_dict()["result"]
                if not data:
                    print("No data.")
                else:
                    for voxel in data:
                        start_x_n = math.ceil((voxel['x0'] / voxel_res[0]) - 0.5)
                        start_y_n = math.ceil((voxel['y0'] / voxel_res[1]) - 0.5)
                        end_x_n = math.floor(((voxel['x0'] + voxel['dx']) / voxel_res[0]) - 0.5) + 1
                        end_y_n = math.floor(((voxel['y0'] + voxel['dy']) / voxel_res[1]) - 0.5) + 1
                        # print(start_x_n, end_x_n, start_y_n, end_y_n)
                        if((start_x_n == end_x_n) or (start_y_n == end_y_n)):
                            print("Anemoi Voxel does not include midpoint of any of our voxels for sampling resolution.")
                        else:
                            temp_map[start_x_n:end_x_n, start_y_n:end_y_n, z] += voxel['temp']                        
                            solutions_check[start_x_n:end_x_n, start_y_n:end_y_n, z] += 1

        solutions_check[solutions_check == 0] = -1
        temp_map = np.divide(temp_map, solutions_check)
        temp_map[temp_map == 0.00] = -1
        return temp_map

    # dedeepyo : 3-Nov-2024

    # dedeepyo : 3-Nov-2024 : Implementing mapping of temperature values from Anemoi Voxels to our own voxels.
    # Sampling : We are picking (sampling) values at points (within Anemoi Voxels). The points chosen are midpoints of our own voxels.
    # Resolution : We are taking 3x3x3 points (within our voxel) from Anemoi Voxels and averaging the temperature values.
    # Matrices : We are creating 27 3D matrices of our own voxels and filling the temperature values.
    # Each matrix corresponds to (start, mid, end) of our own voxels. Start is (1 / 6) from boundary, end is (5 / 6) from boundary.
    # We do this for all 3 dimensions.
    # anemoi_voxel_start_x <= (n + 1/2) * voxel_res => n >= (anemoi_voxel_start_x / voxel_res) - 0.5 => start_x_n = ceil[(anemoi_voxel_start_x / voxel_res) - 0.5]
    # anemoi_voxel_start_x <= (n + 1/2 - 1/3) * voxel_res => n >= (anemoi_voxel_start_x / voxel_res) - (1/6) => start_x_n = ceil[(anemoi_voxel_start_x / voxel_res) - 1/6]
    # anemoi_voxel_start_x <= (n + 1/2 + 1/3) * voxel_res => n >= (anemoi_voxel_start_x / voxel_res) - 0.5 => start_x_n = ceil[(anemoi_voxel_start_x / voxel_res) - 5/6]
    # anemoi_voxel_end_x >= (n + 1/2) * voxel_res => n <= (anemoi_voxel_end_x / voxel_res) - 0.5 => end_x_n = box[(anemoi_voxel_end_x / voxel_res) - 0.5]
    # anemoi_voxel_end_x >= (n + 1/2 - 1/3) * voxel_res => n <= (anemoi_voxel_end_x / voxel_res) - 0.5 => end_x_n = box[(anemoi_voxel_end_x / voxel_res) - 1/6]
    # anemoi_voxel_end_x >= (n + 1/2 + 1/3) * voxel_res => n <= (anemoi_voxel_end_x / voxel_res) - 0.5 => end_x_n = box[(anemoi_voxel_end_x / voxel_res) - 5/6]
    # We create one jumbo matrix of all sampled points. We then extract 27 matrices from this jumbo matrix.
    # Simplify : voxel_res = voxel_res / 3 : anemoi_voxel_start_x <= (n + 1/2) * voxel_res & anemoi_voxel_end_x >= (n + 1/2) * voxel_res
    # => n >= (anemoi_voxel_start_x / voxel_res) - 0.5 & n <= (anemoi_voxel_end_x / voxel_res) - 0.5
    # => start_x_n = ceil[(anemoi_voxel_start_x / voxel_res) - 0.5] & end_x_n = floor[(anemoi_voxel_end_x / voxel_res) - 0.5]
    def solution_to_temp_map_3D_dray_3x3x3(self, boxes):
        voxel_res, max_sizes = self.calculate_voxel_resolution_and_max_sizes(boxes)
        voxel_res = [voxel_res[0] / 3, voxel_res[1] / 3, voxel_res[2] / 3]
        x_voxels = round(float(max_sizes[0] / voxel_res[0])) 
        y_voxels = round(float(max_sizes[1] / voxel_res[1])) 
        z_voxels = round(float(max_sizes[2] / voxel_res[2])) 
        jumbo_temp_maps = np.full((x_voxels, y_voxels, z_voxels), 0.00)  # dedeepyo: Initialize with 0 : Easier to add values
        solutions_check = np.full((x_voxels, y_voxels, z_voxels), 0)
        
        # f = open("temp_map_dray_121724.txt", "w")

        norm_z_range = np.arange(0, z_voxels, 1)
        z_coord = voxel_res[2] / 2
        for z in norm_z_range:
            start_time = time.time()
            solutions = self.papi.project_solution_plane_list(self.id, plane="xy", coordinate=z_coord)
            end_time = time.time()
            # f.write("Each iteration time: " + str(end_time - start_time) + "\n")
            z_coord += voxel_res[2]
            if not solutions:
                print("No solution at z = " + str(z_coord))
            else:
                data = solutions.to_dict()["result"]
                if not data:
                    print("No data.")
                    # f.write("No data.\n")
                else:
                    for voxel in data:
                        start_x_n = math.ceil((voxel['x0'] / voxel_res[0]) - 0.5)
                        start_y_n = math.ceil((voxel['y0'] / voxel_res[1]) - 0.5)
                        end_x_n = math.floor(((voxel['x0'] + voxel['dx']) / voxel_res[0]) - 0.5) + 1
                        end_y_n = math.floor(((voxel['y0'] + voxel['dy']) / voxel_res[1]) - 0.5) + 1
                        if(start_x_n == end_x_n):
                            if(start_y_n == end_y_n):
                                # print("Anemoi Voxel does not include any of our sampling points within any of our voxels.") #
                                jumbo_temp_maps[start_x_n, start_y_n, z] += voxel['temp']                        
                                solutions_check[start_x_n, start_y_n, z] += 1
                            else:
                                jumbo_temp_maps[start_x_n, start_y_n:end_y_n, z] += voxel['temp']                        
                                solutions_check[start_x_n, start_y_n:end_y_n, z] += 1
                                # print("Anemoi Voxel does not include any of our sampling points within any of our voxels.") #
                        elif(start_y_n == end_y_n):
                            # print("Anemoi Voxel does not include any of our sampling points within any of our voxels.") #
                            jumbo_temp_maps[start_x_n:end_x_n, start_y_n, z] += voxel['temp']                        
                            solutions_check[start_x_n:end_x_n, start_y_n, z] += 1
                        else:
                            jumbo_temp_maps[start_x_n:end_x_n, start_y_n:end_y_n, z] += voxel['temp']                        
                            solutions_check[start_x_n:end_x_n, start_y_n:end_y_n, z] += 1

        # f.close()
        
        solutions_check[solutions_check == 0] = -1
        jumbo_temp_maps = np.divide(jumbo_temp_maps, solutions_check)

        solutions_check_bool = jumbo_temp_maps > 0.00
        solutions_check = solutions_check_bool.astype(int)
        reduced_solutions_check = solutions_check[0:-2:3, 0:-2:3, 0:-2:3] + solutions_check[1:-1:3, 0:-2:3, 0:-2:3] + solutions_check[2::3, 0:-2:3, 0:-2:3] + solutions_check[0:-2:3, 1:-1:3, 0:-2:3] + solutions_check[1:-1:3, 1:-1:3, 0:-2:3] + solutions_check[2::3, 1:-1:3, 0:-2:3] + solutions_check[0:-2:3, 2::3, 0:-2:3] + solutions_check[1:-1:3, 2::3, 0:-2:3] + solutions_check[2::3, 2::3, 0:-2:3] + solutions_check[0:-2:3, 0:-2:3, 1:-1:3] + solutions_check[1:-1:3, 0:-2:3, 1:-1:3] + solutions_check[2::3, 0:-2:3, 1:-1:3] + solutions_check[0:-2:3, 1:-1:3, 1:-1:3] + solutions_check[1:-1:3, 1:-1:3, 1:-1:3] + solutions_check[2::3, 1:-1:3, 1:-1:3] + solutions_check[0:-2:3, 2::3, 1:-1:3] + solutions_check[1:-1:3, 2::3, 1:-1:3] + solutions_check[2::3, 2::3, 1:-1:3] + solutions_check[0:-2:3, 0:-2:3, 2::3] + solutions_check[1:-1:3, 0:-2:3, 2::3] + solutions_check[2::3, 0:-2:3, 2::3] + solutions_check[0:-2:3, 1:-1:3, 2::3] + solutions_check[1:-1:3, 1:-1:3, 2::3] + solutions_check[2::3, 1:-1:3, 2::3] + solutions_check[0:-2:3, 2::3, 2::3] + solutions_check[1:-1:3, 2::3, 2::3] + solutions_check[2::3, 2::3, 2::3]
        reduced_solutions_check[reduced_solutions_check == 0] = -1

        temp_map = np.divide((jumbo_temp_maps[0:-2:3, 0:-2:3, 0:-2:3] + jumbo_temp_maps[1:-1:3, 0:-2:3, 0:-2:3] + jumbo_temp_maps[2::3, 0:-2:3, 0:-2:3] + jumbo_temp_maps[0:-2:3, 1:-1:3, 0:-2:3] + jumbo_temp_maps[1:-1:3, 1:-1:3, 0:-2:3] + jumbo_temp_maps[2::3, 1:-1:3, 0:-2:3] + jumbo_temp_maps[0:-2:3, 2::3, 0:-2:3] + jumbo_temp_maps[1:-1:3, 2::3, 0:-2:3] + jumbo_temp_maps[2::3, 2::3, 0:-2:3] + jumbo_temp_maps[0:-2:3, 0:-2:3, 1:-1:3] + jumbo_temp_maps[1:-1:3, 0:-2:3, 1:-1:3] + jumbo_temp_maps[2::3, 0:-2:3, 1:-1:3] + jumbo_temp_maps[0:-2:3, 1:-1:3, 1:-1:3] + jumbo_temp_maps[1:-1:3, 1:-1:3, 1:-1:3] + jumbo_temp_maps[2::3, 1:-1:3, 1:-1:3] + jumbo_temp_maps[0:-2:3, 2::3, 1:-1:3] + jumbo_temp_maps[1:-1:3, 2::3, 1:-1:3] + jumbo_temp_maps[2::3, 2::3, 1:-1:3] + jumbo_temp_maps[0:-2:3, 0:-2:3, 2::3] + jumbo_temp_maps[1:-1:3, 0:-2:3, 2::3] + jumbo_temp_maps[2::3, 0:-2:3, 2::3] + jumbo_temp_maps[0:-2:3, 1:-1:3, 2::3] + jumbo_temp_maps[1:-1:3, 1:-1:3, 2::3] + jumbo_temp_maps[2::3, 1:-1:3, 2::3] + jumbo_temp_maps[0:-2:3, 2::3, 2::3] + jumbo_temp_maps[1:-1:3, 2::3, 2::3] + jumbo_temp_maps[2::3, 2::3, 2::3]), reduced_solutions_check)
        temp_map[temp_map == 0] = -1
        return temp_map

    # dedeepyo : 3-Nov-2024

    def solution_to_temp_map_2D(self, boxes):
        voxel_res, max_sizes = self.calculate_voxel_resolution_and_max_sizes(boxes)
        no_soln_x = []
        no_soln_y = []
        #print(round(float(max_sizes[0]/voxel_res[0])))
        x_voxels = float(max_sizes[0] / voxel_res[0]) 
        y_voxels = float(max_sizes[1] / voxel_res[1]) 
        z_voxels = float(max_sizes[2] / voxel_res[2]) 
        temp_map = np.full((round(x_voxels), round(y_voxels)), -1)  # Initialize with -1
        #print(f"shape of temp map {temp_map.shape}")
        #z_range = np.arange(voxel_res[2] / 2, max_sizes[2], voxel_res[2])
        
        #print(voxel_res[2] / 2, max_sizes[2], voxel_res[2])
        #print("X coords:", voxel_res[0] , max_sizes[0], voxel_res[0])
        #print("Y coords:",voxel_res[1] , max_sizes[1], voxel_res[1])
        #for z in z_range:
        solutions = self.papi.project_solution_plane_list(self.id, plane="xy", coordinate=1.2)
         #solutions2 = self.papi.project_solution_plane_list(self.id, plane="xy", coordinate=z+0.1*z)
         #solutions3 = self.papi.project_solution_plane_list(self.id, plane="xy", coordinate=z-0.1*z)
            #print("SOLUTIONS:",solutions)
        #if not solutions:
                #print(f"No solution for {item}")
         #       continue

        data = solutions.to_dict()["result"]
        #print("DATA",data)
         #data += solutions2.to_dict()["result"]
         #data += solutions3.to_dict()["result"]
        #if not data:
          #continue
        data_arr = [(voxel['temp'], voxel['x0'], voxel['y0'], voxel["dx"], voxel["dy"]) for voxel in data]
        # print(data_arr)
        for x in np.arange(voxel_res[0]/2 , max_sizes[0], voxel_res[0]):
            for y in np.arange(voxel_res[1]/2 , max_sizes[1], voxel_res[1]):
                for item in data_arr:
                    x0 = item[1]
                    y0 = item[2]
                    dx = item[3]
                    dy = item[4]
                    if x >= x0 and x < x0 + dx and y >= y0 and y < y0 + dy:
                        temp_map[int(x / voxel_res[0]), int(y / voxel_res[1])] = item[0]
                        no_soln_x.append(x)
                        no_soln_y.append(y)

                    #print(f"BEGINNING OF {x,y} LOOP!!!!!!")
                    # temp_sum = 0
                    # num_solutions = 0
                    # for solution in data_arr:
                    #     #print("1ST CONDITION:",solution[0],solution[1], x - voxel_res[0], x + voxel_res[0])
                    #     #print("2ND CONDITION:", solution[0],solution[2], y - voxel_res[1],  y + voxel_res[1])
                    #     if solution[1] >= x - voxel_res[0] and solution[1]< x + voxel_res[0] and \
                    #     solution[2] >= y - voxel_res[1]  and solution[2] < y + voxel_res[1] :
                    #         temp_sum += solution[0]
                    #         num_solutions += 1
                    #print(f"END OF {x,y} LOOP!!!!")
                    #print(temp_sum,num_solutions)
                    # norm_x = int(x / voxel_res[0])
                    # norm_y = int(y / voxel_res[1])
                    #norm_z = int(z / voxel_res[2])
                    #print(f"TEMP SUM {temp_sum} and NUM SOLNS {num_solutions}")
                    # if num_solutions != 0:
                    #     temp_avg = temp_sum / num_solutions
                    #     temp_map[norm_x, norm_y] = temp_avg
                        #all_coords.append([norm_x, norm_y])
                        #all_temps.append(temp_avg)
                       #temp_map[norm_x,norm_y] = 999
                        # average temperature is undefined, grab temperature of last voxel
                    # no_soln_x.append(norm_x)
                    # no_soln_y.append(norm_y)
                        #print("No solutions found for voxel at x = " + str(x) + ", y = " + str(y) + ", z = " + str(0.65))
                        
                    #     norm_x = int(x/voxel_res[0])
                    #     norm_y = int(y/voxel_res[1])
                    #    # norm_z = int(z/voxel_res[2])
                    #     if(norm_y-1 >= 0):
                    #         temp_map[norm_x,norm_y] = temp_map[norm_x,norm_y-1]
                    #     else:
                    #         try:
                    #             temp_map[norm_x,norm_y] = temp_map[norm_x-1,norm_y]
                    #         except:
                    #             # print("No solutions found for voxel at x = " + str(x) + ", y = " + str(y) + ", z = " + str(item))
                    #             pass
                    #print("TEMP MAP IS :", temp_map)
        #all_coords = np.array(all_coords)
        #all_temps = np.array(all_temps)

        #if len(all_coords) == 0:
         #   return temp_map
        #print("COUNT VALUES:",count, count1)
        #grid_x, grid_y = np.mgrid[0:x_voxels, 0:y_voxels]
        #temp_map = griddata(all_coords, all_temps, (grid_x, grid_y), method='cubic', fill_value=-1)
        
        # Nearest 8 neighbors (4 direct neighbors + 4 diagonal neighbors)
        # neighbor_offsets = [
        #     (-1,  0), ( 1,  0), # left, right
        #     ( 0, -1), ( 0,  1), # top, bottom
        #     (-1, -1), (-1,  1), # top-left, top-right
        #     ( 1, -1), ( 1,  1)  # bottom-left, bottom-right
        # ]

        # for x in range(round(x_voxels)):
        #     for y in range(round(y_voxels)):
        #         if temp_map[x, y] == -1:
        #             neighbors = []
        #             for dx, dy in neighbor_offsets:
        #                 nx, ny = x + dx, y + dy
        #                 if 0 <= nx < round(x_voxels) and 0 <= ny < round(y_voxels):
        #                     if temp_map[nx, ny] != -1:
        #                         neighbors.append(temp_map[nx, ny])
        #             if neighbors:
        #                 temp_map[x, y] = sum(neighbors) / len(neighbors)

        
        
        
        # import matplotlib.pyplot as plt
        # plt.scatter(no_soln_x,no_soln_y,c='red',marker='x')
        # plt.title('Points with no Solution')
        # plt.xlabel('X coordinate')
        # plt.ylabel('Y Coordinate')
        # plt.savefig("output/noSolns.png")
        # plt.clf()
        
        # print(temp_map)
        return temp_map
    
       #self.create_project_from_scratch()
       
    def delete_project(self,id):
        print("Deleting existing Project")
        self.papi.project_delete(id)

    def retrieve_conductivity(self, box, voxel_start_z, voxel_end_z, layers):

        def determine_layer_prop(layers_info, start_z, voxel_start_z, voxel_end_z):
            conductivity = 0
            current_z = start_z  # Overall start_z for PCB
            for t, c in layers_info:
                layer_start_z = current_z
                layer_end_z = layer_start_z + t
                current_z = layer_end_z
                # Check for overlap with the voxel
                overlap_start_z = max(layer_start_z, voxel_start_z)
                overlap_end_z = min(layer_end_z, voxel_end_z)
                if overlap_start_z < overlap_end_z:  # There's an overlap
                    overlap_proportion = (overlap_end_z - overlap_start_z) / (voxel_end_z - voxel_start_z)
                    conductivity += overlap_proportion * c
            return conductivity

        voxel_conductivity = 0
        
        layers_info = []
        stackup_list = box.get_box_stackup().split(",")
        for stackup_iter in stackup_list:
            layer_num, layer_name = stackup_iter.split(":")
            
            t = 0
            c = 0
            for layer in layers:
                if(layer.get_name() == layer_name):
                    t = int(layer_num) * layer.get_thickness()
                    m = layer.get_material()
                    m_mat_list = m.split(",")
                    if(len(m_mat_list) > 1):
                        if(len(m_mat_list) > 2):
                            raise Exception("More than two materials found for a single layer")
                        else:
                            primary_material, primary_ratio = m_mat_list[0].split(':')
                            secondary_material, secondary_ratio = m_mat_list[1].split(':')

                            total_ratio = float(primary_ratio) + float(secondary_ratio)
                            if(total_ratio != 1.00):
                                raise Exception("Total Ratio of materials is not 100%")
                            
                            c = (float(primary_ratio) * conductivity_values[primary_material] + float(secondary_ratio) * conductivity_values[secondary_material]) / total_ratio
                    else:
                        c = conductivity_values[m]
            
            layers_info.insert(0, (t, c))

        voxel_conductivity = determine_layer_prop(layers_info, box.start_z, voxel_start_z, voxel_end_z)
        return voxel_conductivity

    # dedeepyo : 3-Nov-2024 : Implementing dictionary of layer names, conductivity and heights
    def create_layer_height_map(self, layers):
        pcblayer_height_conductivities = {}
        for layer in layers:
            m = layer.get_material()
            m_mat_list = m.split(",")
            temp_conductivity = 0
            if(len(m_mat_list) > 1):
                if(len(m_mat_list) > 2):
                    raise Exception("More than two materials found for a single layer")
                else:
                    primary_material, primary_ratio = m_mat_list[0].split(':')
                    secondary_material, secondary_ratio = m_mat_list[1].split(':')

                    total_ratio = float(primary_ratio) + float(secondary_ratio)
                    if(total_ratio != 1.00):
                        raise Exception("Total Ratio of materials is not 100%")
                    
                    temp_conductivity = (float(primary_ratio) * conductivity_values[primary_material] + float(secondary_ratio) * conductivity_values[secondary_material]) / total_ratio
            else:
                temp_conductivity = conductivity_values[m]
            pcblayer_height_conductivities[layer.get_name()] = (layer.get_thickness(), layer.get_material(), temp_conductivity)
        return pcblayer_height_conductivities
    # dedeepyo : 3-Nov-2024

    def serialize(self,box_list, layers):
        # For serialization - we will create a data frame, and then convert list of objects to that data frame
        # objects may overlap. in that case, only the last one will be used
        # remember that we are using a voxel resolution, so we will need to convert the objects to the voxel resolution
        voxel_res, max_sizes = self.calculate_voxel_resolution_and_max_sizes(box_list)
        x_voxels = round(max_sizes[0] / voxel_res[0])
        y_voxels = round(max_sizes[1] / voxel_res[1])
        z_voxels = round(max_sizes[2] / voxel_res[2])

        power_map = np.full((x_voxels, y_voxels, z_voxels), -1)
        conductivity_map = np.full((x_voxels, y_voxels, z_voxels), -1)
        
        for x in range(x_voxels):
            for y in range(y_voxels):
                for z in range(z_voxels):
                    # calculate the coordinates of the voxel in the original coordinate system
                    start_x = x * voxel_res[0]
                    start_y = y * voxel_res[1]
                    start_z = z * voxel_res[2]
                    end_x = start_x + voxel_res[0]
                    end_y = start_y + voxel_res[1]
                    end_z = start_z + voxel_res[2]
                    
                    # find the chosen_pcb that contains the voxel
                    chosen_pcb = None
                    chosen_pcb_list = []
                    for obj in box_list:
                        if start_x >= obj.start_x and start_y >= obj.start_y and start_z >= obj.start_z and \
                        end_x <= obj.start_x + obj.width and end_y <= obj.start_y + obj.length and end_z <= obj.start_z + obj.height:
                            chosen_pcb = obj
                            chosen_pcb_list.append(chosen_pcb)
                    
                    # if an chosen_pcb is found, assign its power and conductivity to the voxel
                    if chosen_pcb is not None:
                        # TODO: improve this to be proportional for voxels within multiple objects
                        # power_map[x, y, z] = chosen_pcb.power # BIG ISSUE HERE!!! SHOULD BE PROPORTIONAL!
                        conductivity_map[x, y, z] = self.retrieve_conductivity(chosen_pcb, start_z, end_z, layers)

                        # dedeepyo : 30-Oct-2024 : Implementing adjustment as per volume
                        power_map[x, y, z] = 0
                        for chosen_pcb in chosen_pcb_list:
                            x_overlap = max(0, min(chosen_pcb.start_x + chosen_pcb.width, end_x) - max(chosen_pcb.start_x, start_x)) / voxel_res[0]
                            y_overlap = max(0, min(chosen_pcb.start_y + chosen_pcb.length, end_y) - max(chosen_pcb.start_y, start_y)) / voxel_res[1]
                            z_overlap = max(0, min(chosen_pcb.start_z + chosen_pcb.height, end_z) - max(chosen_pcb.start_z, start_z)) / voxel_res[2]
                            scale_factor = x_overlap * y_overlap * z_overlap
                            if (scale_factor!=0):
                                power_map[x, y, z] = power_map[x, y, z] + scale_factor * chosen_pcb.power
                        
                        # power_map[x, y, z] = chosen_pcb.power
                        # dedeepyo : 30-Oct-2024
                        
        df = DataFrame(voxel_res, power_map=power_map, conductivity_map=conductivity_map)
        return df

    # dedeepyo : 2-Nov-24 : Implementing mapping of power and conductivity values from PCB to voxels
    # Assume : Anemoi voxels and PCBs are larger than our voxels : Works otherwise too but understanding is difficult
    # 1st : voxels inside cuboid : excluding faces : only in 1 PCB : 1
    # 2nd : voxels at faces : excluding edges : shared between 2 PCBs : 6 = 3C1 * 2
    # 3rd : voxels at edges : excluding corners : shared between 3 PCBs : 12 = 3C2 * 2^2
    # 4th : voxels at corners : shared between 4 PCBs : 8 = 2^3
    # Discretization : We are dividing the spatial volume encompassed by an Anemoi Voxel into our own voxel cuboids. 
    def serialize_dray(self, box_list, layers):
        voxel_res, max_sizes = self.calculate_voxel_resolution_and_max_sizes(box_list)
        x_voxels = round(max_sizes[0] / voxel_res[0])
        y_voxels = round(max_sizes[1] / voxel_res[1])
        z_voxels = round(max_sizes[2] / voxel_res[2])

        power_map = np.full(((x_voxels + 1), (y_voxels + 1), (z_voxels + 1)), 0.00) # dedeepyo : 2-Nov-24 : Initializing power to 0 for additive contribution of PCBs sharing a voxel
        conductivity_map = np.full(((x_voxels + 1), (y_voxels + 1), (z_voxels + 1)), 0.00) # dedeepyo : 3-Nov-24 : Initializing conductivity to 0 for additive contribution of PCBs sharing a voxel
        pcblayer_height_conductivities = self.create_layer_height_map(layers) # dedeepyo : 3-Nov-24 : Creating dictionary of layer names, thickness and conductivity
        
        excluded_types = ["interposer", "substrate", "PCB", "Power_Source"]
        box_list_min = [box for box in box_list if box.chiplet_parent.get_chiplet_type() not in excluded_types]

        for box in box_list_min:
            # frac_start_x = box.start_x / voxel_res[0]
            # frac_start_y = box.start_y / voxel_res[1]
            # frac_start_z = box.start_z / voxel_res[2]
            # frac_end_x = box.end_x / voxel_res[0]
            # frac_end_y = box.end_y / voxel_res[1]
            # frac_end_z = box.end_z / voxel_res[2]
            # start_z_n = math.ceil(frac_start_z)
            # end_z_n = math.floor(frac_end_z) + 1
            # start_y_n = math.ceil(frac_start_y)
            # end_y_n = math.floor(frac_end_y) + 1
            # start_x_n = math.ceil(frac_start_x)
            # end_x_n = math.floor(frac_end_x) + 1
            # start_x_n_internal = math.ceil(frac_start_x)
            # start_y_n_internal = math.ceil(frac_start_y)
            # start_z_n_internal = math.ceil(frac_start_z)
            # overlap_start_x_n = start_x_n_internal - frac_start_x
            # overlap_start_y_n = start_y_n_internal - frac_start_y
            # overlap_start_z_n = start_z_n_internal - frac_start_z
            # overlap_end_x_n = frac_end_x - end_x_n
            # overlap_end_y_n = frac_end_y - end_y_n
            # overlap_end_z_n = frac_end_z - end_z_n

            start_x_n = int(box.start_x // voxel_res[0])
            start_y_n = int(box.start_y // voxel_res[1])
            start_z_n = int(box.start_z // voxel_res[2])
            end_x_n = int((box.end_x - 1e-12) // voxel_res[0])
            end_y_n = int((box.end_y - 1e-12) // voxel_res[1])
            end_z_n = int((box.end_z - 1e-12) // voxel_res[2])
            overlap_start_x_n = (start_x_n + 1) * voxel_res[0] - box.start_x
            overlap_start_y_n = (start_y_n + 1) * voxel_res[1] - box.start_y
            overlap_start_z_n = (start_z_n + 1) * voxel_res[2] - box.start_z
            overlap_end_x_n = box.end_x - end_x_n * voxel_res[0]
            overlap_end_y_n = box.end_y - end_y_n * voxel_res[1]
            overlap_end_z_n = box.end_z - end_z_n * voxel_res[2]
            start_x_n_internal = int(box.start_x // voxel_res[0])
            start_y_n_internal = int(box.start_y // voxel_res[1])
            start_z_n_internal = int(box.start_z // voxel_res[2])
            
            # print("Box named : " + box.name + " has start_x_n : " + str(start_x_n) + " and end_x_n : " + str(end_x_n) + " and start_y_n : " + str(start_y_n) + " and end_y_n : " + str(end_y_n) + " and start_z_n : " + str(start_z_n) + " and end_z_n : " + str(end_z_n))
            # print("Box named : " + box.name + " has start_x : " + str(box.start_x) + " and end_x : " + str(box.end_x) + " and start_y : " + str(box.start_y) + " and end_y : " + str(box.end_y) + " and start_z : " + str(box.start_z) + " and end_z : " + str(box.end_z))
            
            power_map[start_x_n_internal:(end_x_n + 1), start_y_n_internal:(end_y_n + 1), start_z_n_internal:(end_z_n + 1)] += box.power
            power_map[start_x_n, start_y_n_internal:(end_y_n + 1), start_z_n_internal:(end_z_n + 1)] += overlap_start_x_n * box.power
            power_map[end_x_n, start_y_n_internal:(end_y_n + 1), start_z_n_internal:(end_z_n + 1)] += overlap_end_x_n * box.power
            power_map[start_x_n_internal:(end_x_n + 1), start_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_start_y_n * box.power
            power_map[start_x_n_internal:(end_x_n + 1), end_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_end_y_n * box.power
            power_map[start_x_n_internal:(end_x_n + 1), start_y_n_internal:(end_y_n + 1), start_z_n] += overlap_start_z_n * box.power
            power_map[start_x_n_internal:(end_x_n + 1), start_y_n_internal:(end_y_n + 1), end_z_n] += overlap_end_z_n * box.power
            power_map[start_x_n_internal:(end_x_n + 1), start_y_n, start_z_n] += overlap_start_y_n * overlap_start_z_n * box.power
            power_map[start_x_n_internal:(end_x_n + 1), start_y_n, end_z_n] += overlap_start_y_n * overlap_end_z_n * box.power
            power_map[start_x_n_internal:(end_x_n + 1), end_y_n, start_z_n] += overlap_end_y_n * overlap_start_z_n * box.power
            power_map[start_x_n_internal:(end_x_n + 1), end_y_n, end_z_n] += overlap_end_y_n * overlap_end_z_n * box.power
            power_map[start_x_n, start_y_n_internal:(end_y_n + 1), start_z_n] += overlap_start_x_n * overlap_start_z_n * box.power
            power_map[start_x_n, start_y_n_internal:(end_y_n + 1), end_z_n] += overlap_start_x_n * overlap_end_z_n * box.power
            power_map[end_x_n, start_y_n_internal:(end_y_n + 1), start_z_n] += overlap_end_x_n * overlap_start_z_n * box.power
            power_map[end_x_n, start_y_n_internal:(end_y_n + 1), end_z_n] += overlap_end_x_n * overlap_end_z_n * box.power
            power_map[start_x_n, start_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_start_x_n * overlap_start_y_n * box.power
            power_map[start_x_n, end_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_start_x_n * overlap_end_y_n * box.power
            power_map[end_x_n, start_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_end_x_n * overlap_start_y_n * box.power
            power_map[end_x_n, end_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_end_x_n * overlap_end_y_n * box.power
            power_map[start_x_n, start_y_n, start_z_n] += overlap_start_x_n * overlap_start_y_n * overlap_start_z_n * box.power
            power_map[start_x_n, start_y_n, end_z_n] += overlap_start_x_n * overlap_start_y_n * overlap_end_z_n * box.power
            power_map[start_x_n, end_y_n, start_z_n] += overlap_start_x_n * overlap_end_y_n * overlap_start_z_n * box.power
            power_map[start_x_n, end_y_n, end_z_n] += overlap_start_x_n * overlap_end_y_n * overlap_end_z_n * box.power
            power_map[end_x_n, start_y_n, start_z_n] += overlap_end_x_n * overlap_start_y_n * overlap_start_z_n * box.power
            power_map[end_x_n, start_y_n, end_z_n] += overlap_end_x_n * overlap_start_y_n * overlap_end_z_n * box.power
            power_map[end_x_n, end_y_n, start_z_n] += overlap_end_x_n * overlap_end_y_n * overlap_start_z_n * box.power
            power_map[end_x_n, end_y_n, end_z_n] += overlap_end_x_n * overlap_end_y_n * overlap_end_z_n * box.power

            pcblayer_start_z = box.start_z
            stackup_list = box.get_box_stackup().split(",")
            for stackup_iter in stackup_list:
                layer_num, layer_name = stackup_iter.split(":")
                pcblayer_end_z = pcblayer_start_z + int(layer_num) * pcblayer_height_conductivities[layer_name][0] 
                start_z_n = int(pcblayer_start_z // voxel_res[2])
                end_z_n = int(pcblayer_end_z // voxel_res[2])
                start_z_n_internal = int(pcblayer_start_z // voxel_res[2])
                overlap_start_z_n = (start_z_n + 1) * voxel_res[2] - pcblayer_start_z
                overlap_end_z_n = pcblayer_end_z - end_z_n  * voxel_res[2]     
                # frac_start_z = pcblayer_start_z / voxel_res[2]
                # frac_end_z = pcblayer_end_z / voxel_res[2]
                pcblayer_start_z = pcblayer_end_z
                temp_conductivity = pcblayer_height_conductivities[layer_name][2]

                # start_z_n = math.floor(frac_start_z)
                # end_z_n = math.ceil(frac_end_z) - 1
                # start_z_n_internal = math.ceil(frac_start_z)
                # overlap_start_z_n = start_z_n_internal - frac_start_z
                # overlap_end_z_n = frac_end_z - end_z_n
                
                
                conductivity_map[start_x_n_internal:(end_x_n + 1), start_y_n_internal:(end_y_n + 1), start_z_n_internal:(end_z_n + 1)] += temp_conductivity
                conductivity_map[start_x_n, start_y_n_internal:(end_y_n + 1), start_z_n_internal:(end_z_n + 1)] += overlap_start_x_n * temp_conductivity
                conductivity_map[end_x_n, start_y_n_internal:(end_y_n + 1), start_z_n_internal:(end_z_n + 1)] += overlap_end_x_n * temp_conductivity
                conductivity_map[start_x_n_internal:(end_x_n + 1), start_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_start_y_n * temp_conductivity
                conductivity_map[start_x_n_internal:(end_x_n + 1), end_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_end_y_n * temp_conductivity
                conductivity_map[start_x_n_internal:(end_x_n + 1), start_y_n_internal:(end_y_n + 1), start_z_n] += overlap_start_z_n * temp_conductivity
                conductivity_map[start_x_n_internal:(end_x_n + 1), start_y_n_internal:(end_y_n + 1), end_z_n] += overlap_end_z_n * temp_conductivity
                conductivity_map[start_x_n_internal:(end_x_n + 1), start_y_n, start_z_n] += overlap_start_y_n * overlap_start_z_n * temp_conductivity
                conductivity_map[start_x_n_internal:(end_x_n + 1), start_y_n, end_z_n] += overlap_start_y_n * overlap_end_z_n * temp_conductivity
                conductivity_map[start_x_n_internal:(end_x_n + 1), end_y_n, start_z_n] += overlap_end_y_n * overlap_start_z_n * temp_conductivity
                conductivity_map[start_x_n_internal:(end_x_n + 1), end_y_n, end_z_n] += overlap_end_y_n * overlap_end_z_n * temp_conductivity
                conductivity_map[start_x_n, start_y_n_internal:(end_y_n + 1), start_z_n] += overlap_start_x_n * overlap_start_z_n * temp_conductivity
                conductivity_map[start_x_n, start_y_n_internal:(end_y_n + 1), end_z_n] += overlap_start_x_n * overlap_end_z_n * temp_conductivity
                conductivity_map[end_x_n, start_y_n_internal:(end_y_n + 1), start_z_n] += overlap_end_x_n * overlap_start_z_n * temp_conductivity
                conductivity_map[end_x_n, start_y_n_internal:(end_y_n + 1), end_z_n] += overlap_end_x_n * overlap_end_z_n * temp_conductivity
                conductivity_map[start_x_n, start_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_start_x_n * overlap_start_y_n * temp_conductivity
                conductivity_map[start_x_n, end_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_start_x_n * overlap_end_y_n * temp_conductivity
                conductivity_map[end_x_n, start_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_end_x_n * overlap_start_y_n * temp_conductivity
                conductivity_map[end_x_n, end_y_n, start_z_n_internal:(end_z_n + 1)] += overlap_end_x_n * overlap_end_y_n * temp_conductivity
                conductivity_map[start_x_n, start_y_n, start_z_n] += overlap_start_x_n * overlap_start_y_n * overlap_start_z_n * temp_conductivity
                conductivity_map[start_x_n, start_y_n, end_z_n] += overlap_start_x_n * overlap_start_y_n * overlap_end_z_n * temp_conductivity
                conductivity_map[start_x_n, end_y_n, start_z_n] += overlap_start_x_n * overlap_end_y_n * overlap_start_z_n * temp_conductivity
                conductivity_map[start_x_n, end_y_n, end_z_n] += overlap_start_x_n * overlap_end_y_n * overlap_end_z_n * temp_conductivity
                conductivity_map[end_x_n, start_y_n, start_z_n] += overlap_end_x_n * overlap_start_y_n * overlap_start_z_n * temp_conductivity
                conductivity_map[end_x_n, start_y_n, end_z_n] += overlap_end_x_n * overlap_start_y_n * overlap_end_z_n * temp_conductivity
                conductivity_map[end_x_n, end_y_n, start_z_n] += overlap_end_x_n * overlap_end_y_n * overlap_start_z_n * temp_conductivity
                conductivity_map[end_x_n, end_y_n, end_z_n] += overlap_end_x_n * overlap_end_y_n * overlap_end_z_n * temp_conductivity

        power_map[power_map == 0.00] = -1.00
        conductivity_map[conductivity_map == 0.00] = -1.00
                    
        df = DataFrame(voxel_res, power_map=power_map[:x_voxels, :y_voxels, :z_voxels], conductivity_map=conductivity_map[:x_voxels, :y_voxels, :z_voxels])
        return df
    # dedeepyo : 2-Nov-24

    # dedeepyo : 17-Oct-24 : Implementing chiplet temperature retrieval #
    def overlap(self, x1, y1, dx1, dy1, x2, y2, dx2, dy2):
        if((x1 > x2 + dx2) or (x2 > x1 + dx1)):
            return False
        elif((y1 > y2 + dy2) or (y2 > y1 + dy1)):
            return False
        else:
            return True
    
    def chiplets_temperature(self, temp_map_3D, box_list):
        voxel_res, max_sizes = self.calculate_voxel_resolution_and_max_sizes(box_list)
        # f = open("output_techcon_051325_3D.txt", "w")
        f = open("output_chiplets_temperature_031026.txt", "w")
        f.write("Mean temperature of entire system is {}\n".format(np.mean(temp_map_3D[temp_map_3D > 0])))
        # f.write(str(temp_map_3D.shape))
        # f.write(str(temp_map_3D))
        GPU_peak_temperature = 0.0
        HBM_peak_temperature = 0.0
        GPU_min_peak_temperature = 1000.0
        HBM_min_peak_temperature = 1000.0
        GPU_temperatures_list = []
        HBM_temperatures_list = []
        for box in box_list:
            # temperature_sum = 0
            # max_temperature = 0
            # voxel_count = 0
            start_z_n = math.floor(box.start_z / voxel_res[2])
            end_z_n = math.ceil(box.end_z / voxel_res[2]) # - 1
            start_y_n = math.floor(box.start_y / voxel_res[1])
            end_y_n = math.ceil(box.end_y / voxel_res[1]) # - 1
            start_x_n = math.floor(box.start_x / voxel_res[0])
            end_x_n = math.ceil(box.end_x / voxel_res[0]) #- 1
            # count_voxels = (end_x_n - start_x_n) * (end_y_n - start_y_n) * (end_z_n - start_z_n)            
            # f.write("start_z_n is " + str(start_z_n) + " and end_z_n is " + str(end_z_n) + " and start_y_n is " + str(start_y_n) + " and end_y_n is " + str(end_y_n) + " and start_x_n is " + str(start_x_n) + " and end_x_n is " + str(end_x_n))
            # f.write(box.name)
            temps = temp_map_3D[start_x_n:end_x_n, start_y_n:end_y_n, start_z_n:end_z_n]
            # print(f"Box {box.name} has temps shape {temps.shape}")
            temps = temps[temps > 0]
            # print(f"Box {box.name} has positive temps shape {temps.shape}")
            temp_avg = np.mean(temps)
            # temps = temps[temps > temp_avg]
            # print(f"{box.name} has {temps.size} voxels.")
            max_temperature = np.max(temps)
            # f.write(str(temps))
            
            if(box.chiplet_parent.get_chiplet_type() == "GPU"):
                GPU_peak_temperature = max(GPU_peak_temperature, max_temperature)
                GPU_min_peak_temperature = min(GPU_min_peak_temperature, max_temperature)
                GPU_temperatures_list.append(max_temperature)
            elif(box.chiplet_parent.get_chiplet_type() == "HBM"):
                HBM_peak_temperature = max(HBM_peak_temperature, max_temperature)
                HBM_min_peak_temperature = min(HBM_min_peak_temperature, max_temperature)
            elif(box.chiplet_parent.get_chiplet_type()[0:5] == "HBM_l"):
                HBM_peak_temperature = max(HBM_peak_temperature, max_temperature)

            temp_avg = np.mean(temps) #
            max_temps = np.max(temps) #
            # print(max_temps) #
            f.write("Mean temperature of " + box.name + " chiplet is " + str(temp_avg) + " and its maximum temperature is " + str(max_temperature))
            f.write("\n")
            # z = voxel_res[2] * (n + 1)
            # while(z < box.end_z):
                # solutions = self.papi.project_solution_plane_list(self.id, plane="xy", coordinate=z)
                # if solutions:
                #     data = solutions.to_dict()["result"]
                #     if data:
                #         for voxel in data:
                #             if(self.overlap(voxel['x0'], voxel['y0'], voxel['dx'], voxel['dy'], box.start_x, box.start_y, box.width, box.length)):
                                # temperature_sum = temperature_sum  + voxel['temp']
                                # voxel_count = voxel_count + 1
                                # if(voxel['temp'] > max_temperature):
                                #     max_temperature = voxel['temp']

                # z = z + voxel_res[2]
            # temp_avg = temperature_sum / voxel_count 
        # print(0)
        f.close()
        return (GPU_peak_temperature, HBM_peak_temperature, GPU_min_peak_temperature, HBM_min_peak_temperature, GPU_temperatures_list, HBM_temperatures_list)
    # dedeepyo : 17-oct-24 #

    # dedeepyo : 8-Jan-25 : Implementing chiplet temperature on Anemoi voxels instead of local voxels #
    def check_overlap_dray(self, box1, box2_start_x, box2_start_y, box2_start_z, box2_end_x, box2_end_y, box2_end_z):
    # Check z-axis overlap first since boxes without common z are not overlapping at all
        if box1.end_z < box2_start_z or box2_end_z < box1.start_z:
            return False
        # Check x-axis overlap first since boxes are sorted by x
        if box1.end_x < box2_start_x or box2_end_x < box1.start_x:
            return False
        # Only check y-axis if x overlaps
        if box1.end_y < box2_start_y or box2_end_y < box1.start_y:
            return False
        return True

    def chiplets_temperature_from_all_Anemoi_voxels(self, box_list):
        max_pages = 300
        page = 1
        number = 20000

        # f = open("output_test_030425_dray2.txt", "w")
        all_temps = []
        all_x0 = []
        all_y0 = []
        all_z0 = []
        all_x1 = []
        all_y1 = []
        all_z1 = []
        while page <= max_pages:
            start_time = time.time()
            result = self.papi.project_solution_boxes_list(self.id, page = page, number = number) 
            end_time = time.time()
            print("Time taken to retrieve solution boxes : " + str(end_time - start_time))
            max_pages = result.pages
            page = page + 1 

            if not result:
                print("No solution found")
            else:
                data = result.to_dict()["boxes"]
                if not data:
                    print("No solution found")
                else:
                    for voxel in data:
                        all_temps.append(voxel['temp'])
                        all_x0.append(voxel['x0'])
                        all_y0.append(voxel['y0'])
                        all_z0.append(voxel['z0'])
                        all_x1.append(voxel['x1'])
                        all_y1.append(voxel['y1'])
                        all_z1.append(voxel['z1'])
                    
                    # f.write("\nTemperatures of Anemoi voxels are : \n")
                    # f.write(str(all_temps))
                    # f.write("\nx0 of Anemoi voxels are : \n")
                    # f.write(str(all_x0))
                    # f.write("\ny0 of Anemoi voxels are : \n")
                    # f.write(str(all_y0))
                    # f.write("\nz0 of Anemoi voxels are : \n")
                    # f.write(str(all_z0))
                    # f.write("\nx1 of Anemoi voxels are : \n")
                    # f.write(str(all_x1))
                    # f.write("\ny1 of Anemoi voxels are : \n")
                    # f.write(str(all_y1))
                    # f.write("\nz1 of Anemoi voxels are : \n")
                    # f.write(str(all_z1))
                    # print(len(all_temps))
                    # print(self.check_order(all_temps))
                    # print(self.check_order(all_x0))
                    # print(self.check_order(all_y0))
                    # print(self.check_order(all_z0))
                    # print(self.check_order(all_x1))
                    # print(self.check_order(all_y1))
                    # print(self.check_order(all_z1))
        # f.close()
        all_x0_mm = [1000 * float(i) for i in all_x0]
        all_y0_mm = [1000 * float(i) for i in all_y0]
        all_z0_mm = [1000 * float(i) for i in all_z0]
        all_x1_mm = [1000 * float(i) for i in all_x1]
        all_y1_mm = [1000 * float(i) for i in all_y1]
        all_z1_mm = [1000 * float(i) for i in all_z1]
        all_temps_new = [float(i) for i in all_temps]
        
        iter_count = len(all_temps_new)
        print(iter_count)

        box_temperatures_total = {box.name : 0.00 for box in box_list}
        box_temperatures_count = {box.name : 0 for box in box_list}
        box_temperatures_max = {box.name : -1000000.00 for box in box_list}

        i = 0
        while(i < iter_count):
            for box in box_list:
                if(self.check_overlap_dray(box, all_x0_mm[i], all_y0_mm[i], all_z0_mm[i], all_x1_mm[i], all_y1_mm[i], all_z1_mm[i])):
                    box_temperatures_total[box.name] = box_temperatures_total[box.name] + all_temps_new[i]
                    box_temperatures_count[box.name] = box_temperatures_count[box.name] + 1
                    if(all_temps_new[i] > box_temperatures_max[box.name]):
                        box_temperatures_max[box.name] = all_temps_new[i]
            i = i + 1

        for box in box_list:
            if(box_temperatures_count[box.name] > 0):
                box_temperatures_total[box.name] = box_temperatures_total[box.name] / box_temperatures_count[box.name]
            else:
                print("Box : " + box.name + " has no temperature data")

            print("Mean temperature of " + box.name + " chiplet is " + str(box_temperatures_total[box.name]) + " and its maximum temperature is " + str(box_temperatures_max[box.name]))

    def local_temperature_from_all_Anemoi_voxels(self, box_list):
        voxel_res, max_sizes = self.calculate_voxel_resolution_and_max_sizes(box_list)
        voxel_res = [voxel_res[0] / 3, voxel_res[1] / 3, voxel_res[2] / 3]
        x_voxels = math.ceil(float(max_sizes[0] / voxel_res[0])) 
        y_voxels = math.ceil(float(max_sizes[1] / voxel_res[1])) 
        z_voxels = math.ceil(float(max_sizes[2] / voxel_res[2])) 
        jumbo_temp_maps = np.full((x_voxels, y_voxels, z_voxels), 0.00)  # dedeepyo: Initialize with 0 : Easier to add values
        solutions_check = np.full((x_voxels, y_voxels, z_voxels), 0)
        
        # f = open("temp_map_dray_121724.txt", "w")

        # norm_z_range = np.arange(0, z_voxels, 1)
        # z_coord = voxel_res[2] / 2

        max_pages = 300
        # max_pages = 10
        page = 1
        number = 20000

        # f = open("output_test_030425_dray2.txt", "w")
        # all_temps = []
        # all_x0 = []
        # all_y0 = []
        # all_z0 = []
        # all_x1 = []
        # all_y1 = []
        # all_z1 = []
        while page <= max_pages:
            start_time = time.time()
            result = self.papi.project_solution_boxes_list(self.id, page = page, number = number) 
            end_time = time.time()
            # print("Time taken to retrieve solution boxes : " + str(end_time - start_time))
            max_pages = result.pages
            page = page + 1 

            if not result:
                print("No solution found")
            else:
                data = result.to_dict()["boxes"]
                if not data:
                    print("No solution found")
                else:
                    for voxel in data:
                        start_x_n = int((1000 * float(voxel['x0'])) // voxel_res[0])
                        start_y_n = int((1000 * float(voxel['y0'])) // voxel_res[1])
                        end_x_n = int((1000 * float(voxel['x1']) - 1e-12) // voxel_res[0]) + 1
                        end_y_n = int((1000 * float(voxel['y1']) - 1e-12) // voxel_res[1]) + 1
                        start_z_n = int((1000 * float(voxel['z0'])) // voxel_res[2])
                        end_z_n = int((1000 * float(voxel['z1']) - 1e-12) // voxel_res[2]) + 1
                        if(start_x_n == end_x_n):
                            if(start_y_n == end_y_n):
                                if(start_z_n == end_z_n):
                                    # print("Anemoi Voxel does not include any of our sampling points within any of our voxels.") #
                                    # jumbo_temp_maps[start_x_n, start_y_n, start_z_n] += float(voxel['temp'])                        
                                    # solutions_check[start_x_n, start_y_n, start_z_n] += 1
                                    jumbo_temp_maps[end_x_n - 1, end_y_n - 1, end_z_n - 1] += float(voxel['temp'])                        
                                    solutions_check[end_x_n - 1, end_y_n - 1, end_z_n - 1] += 1
                                else:
                                    # jumbo_temp_maps[start_x_n, start_y_n, start_z_n:end_z_n] += float(voxel['temp'])
                                    # solutions_check[start_x_n, start_y_n, start_z_n:end_z_n] += 1
                                    jumbo_temp_maps[end_x_n - 1, end_y_n - 1, start_z_n:end_z_n] += float(voxel['temp'])
                                    solutions_check[end_x_n - 1, end_y_n - 1, start_z_n:end_z_n] += 1
                            elif(start_z_n == end_z_n):
                                # jumbo_temp_maps[start_x_n, start_y_n:end_y_n, start_z_n] += float(voxel['temp'])                        
                                # solutions_check[start_x_n, start_y_n:end_y_n, start_z_n] += 1
                                jumbo_temp_maps[end_x_n - 1, start_y_n:end_y_n, end_z_n - 1] += float(voxel['temp'])                        
                                solutions_check[end_x_n - 1, start_y_n:end_y_n, end_z_n - 1] += 1
                                # print("Anemoi Voxel does not include any of our sampling points within any of our voxels.") #
                            else:
                                # jumbo_temp_maps[start_x_n, start_y_n:end_y_n, start_z_n:end_z_n] += float(voxel['temp'])                        
                                # solutions_check[start_x_n, start_y_n:end_y_n, start_z_n:end_z_n] += 1
                                # jumbo_temp_maps[start_x_n, start_y_n:end_y_n, start_z_n:end_z_n] += float(voxel['temp'])                        
                                # solutions_check[start_x_n, start_y_n:end_y_n, start_z_n:end_z_n] += 1
                                jumbo_temp_maps[end_x_n - 1, start_y_n:end_y_n, start_z_n:end_z_n] += float(voxel['temp'])                        
                                solutions_check[end_x_n - 1, start_y_n:end_y_n, start_z_n:end_z_n] += 1
                        elif(start_y_n == end_y_n):
                            if(start_z_n == end_z_n):
                                # print("Anemoi Voxel does not include any of our sampling points within any of our voxels.") #
                                # jumbo_temp_maps[start_x_n:end_x_n, start_y_n, start_z_n] += float(voxel['temp'])                        
                                # solutions_check[start_x_n:end_x_n, start_y_n, start_z_n] += 1
                                jumbo_temp_maps[start_x_n:end_x_n, end_y_n - 1, end_z_n - 1] += float(voxel['temp'])                        
                                solutions_check[start_x_n:end_x_n, end_y_n - 1, end_z_n - 1] += 1
                            else:
                                # jumbo_temp_maps[start_x_n:end_x_n, start_y_n, start_z_n:end_z_n] += float(voxel['temp'])
                                # solutions_check[start_x_n:end_x_n, start_y_n, start_z_n:end_z_n] += 1
                                jumbo_temp_maps[start_x_n:end_x_n, end_y_n - 1, start_z_n:end_z_n] += float(voxel['temp'])
                                solutions_check[start_x_n:end_x_n, end_y_n - 1, start_z_n:end_z_n] += 1
                        elif(start_z_n == end_z_n):
                            # print("Anemoi Voxel does not include any of our sampling points within any of our voxels.") #
                            # jumbo_temp_maps[start_x_n:end_x_n, start_y_n:end_y_n, start_z_n] += float(voxel['temp'])                        
                            # solutions_check[start_x_n:end_x_n, start_y_n:end_y_n, start_z_n] += 1
                            jumbo_temp_maps[start_x_n:end_x_n, start_y_n:end_y_n, end_z_n - 1] += float(voxel['temp'])                        
                            solutions_check[start_x_n:end_x_n, start_y_n:end_y_n, end_z_n - 1] += 1
                        else:
                            # jumbo_temp_maps[start_x_n:end_x_n, start_y_n:end_y_n, start_z_n:end_z_n] += float(voxel['temp'])                        
                            # solutions_check[start_x_n:end_x_n, start_y_n:end_y_n, start_z_n:end_z_n] += 1
                            jumbo_temp_maps[start_x_n:end_x_n, start_y_n:end_y_n, start_z_n:end_z_n] += float(voxel['temp'])                        
                            solutions_check[start_x_n:end_x_n, start_y_n:end_y_n, start_z_n:end_z_n] += 1

        solutions_check[solutions_check == 0] = -1
        jumbo_temp_maps = np.divide(jumbo_temp_maps, solutions_check)

        solutions_check_bool = jumbo_temp_maps > 0.00
        solutions_check = solutions_check_bool.astype(int)
        reduced_solutions_check = solutions_check[0:-2:3, 0:-2:3, 0:-2:3] + solutions_check[1:-1:3, 0:-2:3, 0:-2:3] + solutions_check[2::3, 0:-2:3, 0:-2:3] + solutions_check[0:-2:3, 1:-1:3, 0:-2:3] + solutions_check[1:-1:3, 1:-1:3, 0:-2:3] + solutions_check[2::3, 1:-1:3, 0:-2:3] + solutions_check[0:-2:3, 2::3, 0:-2:3] + solutions_check[1:-1:3, 2::3, 0:-2:3] + solutions_check[2::3, 2::3, 0:-2:3] + solutions_check[0:-2:3, 0:-2:3, 1:-1:3] + solutions_check[1:-1:3, 0:-2:3, 1:-1:3] + solutions_check[2::3, 0:-2:3, 1:-1:3] + solutions_check[0:-2:3, 1:-1:3, 1:-1:3] + solutions_check[1:-1:3, 1:-1:3, 1:-1:3] + solutions_check[2::3, 1:-1:3, 1:-1:3] + solutions_check[0:-2:3, 2::3, 1:-1:3] + solutions_check[1:-1:3, 2::3, 1:-1:3] + solutions_check[2::3, 2::3, 1:-1:3] + solutions_check[0:-2:3, 0:-2:3, 2::3] + solutions_check[1:-1:3, 0:-2:3, 2::3] + solutions_check[2::3, 0:-2:3, 2::3] + solutions_check[0:-2:3, 1:-1:3, 2::3] + solutions_check[1:-1:3, 1:-1:3, 2::3] + solutions_check[2::3, 1:-1:3, 2::3] + solutions_check[0:-2:3, 2::3, 2::3] + solutions_check[1:-1:3, 2::3, 2::3] + solutions_check[2::3, 2::3, 2::3]
        reduced_solutions_check[reduced_solutions_check == 0] = -1

        temp_map = np.divide((jumbo_temp_maps[0:-2:3, 0:-2:3, 0:-2:3] + jumbo_temp_maps[1:-1:3, 0:-2:3, 0:-2:3] + jumbo_temp_maps[2::3, 0:-2:3, 0:-2:3] + jumbo_temp_maps[0:-2:3, 1:-1:3, 0:-2:3] + jumbo_temp_maps[1:-1:3, 1:-1:3, 0:-2:3] + jumbo_temp_maps[2::3, 1:-1:3, 0:-2:3] + jumbo_temp_maps[0:-2:3, 2::3, 0:-2:3] + jumbo_temp_maps[1:-1:3, 2::3, 0:-2:3] + jumbo_temp_maps[2::3, 2::3, 0:-2:3] + jumbo_temp_maps[0:-2:3, 0:-2:3, 1:-1:3] + jumbo_temp_maps[1:-1:3, 0:-2:3, 1:-1:3] + jumbo_temp_maps[2::3, 0:-2:3, 1:-1:3] + jumbo_temp_maps[0:-2:3, 1:-1:3, 1:-1:3] + jumbo_temp_maps[1:-1:3, 1:-1:3, 1:-1:3] + jumbo_temp_maps[2::3, 1:-1:3, 1:-1:3] + jumbo_temp_maps[0:-2:3, 2::3, 1:-1:3] + jumbo_temp_maps[1:-1:3, 2::3, 1:-1:3] + jumbo_temp_maps[2::3, 2::3, 1:-1:3] + jumbo_temp_maps[0:-2:3, 0:-2:3, 2::3] + jumbo_temp_maps[1:-1:3, 0:-2:3, 2::3] + jumbo_temp_maps[2::3, 0:-2:3, 2::3] + jumbo_temp_maps[0:-2:3, 1:-1:3, 2::3] + jumbo_temp_maps[1:-1:3, 1:-1:3, 2::3] + jumbo_temp_maps[2::3, 1:-1:3, 2::3] + jumbo_temp_maps[0:-2:3, 2::3, 2::3] + jumbo_temp_maps[1:-1:3, 2::3, 2::3] + jumbo_temp_maps[2::3, 2::3, 2::3]), reduced_solutions_check)
        temp_map[temp_map == 0] = -1

        # f = open("output_test_dray1_0402", "w")
        # f.write(str(temp_map))
        # f.close()

        return temp_map
    # dedeepyo : 06-Mar-25 #

                        # all_temps.append(voxel['temp'])
                        # all_x0.append(voxel['x0'])
                        # all_y0.append(voxel['y0'])
                        # all_z0.append(voxel['z0'])
                        # all_x1.append(voxel['x1'])
                        # all_y1.append(voxel['y1'])
                        # all_z1.append(voxel['z1'])
                    
                    # f.write("\nTemperatures of Anemoi voxels are : \n")
                    # f.write(str(all_temps))
                    # f.write("\nx0 of Anemoi voxels are : \n")
                    # f.write(str(all_x0))
                    # f.write("\ny0 of Anemoi voxels are : \n")
                    # f.write(str(all_y0))
                    # f.write("\nz0 of Anemoi voxels are : \n")
                    # f.write(str(all_z0))
                    # f.write("\nx1 of Anemoi voxels are : \n")
                    # f.write(str(all_x1))
                    # f.write("\ny1 of Anemoi voxels are : \n")
                    # f.write(str(all_y1))
                    # f.write("\nz1 of Anemoi voxels are : \n")
                    # f.write(str(all_z1))
                    # print(len(all_temps))
                    # print(self.check_order(all_temps))
                    # print(self.check_order(all_x0))
                    # print(self.check_order(all_y0))
                    # print(self.check_order(all_z0))
                    # print(self.check_order(all_x1))
                    # print(self.check_order(all_y1))
                    # print(self.check_order(all_z1))
        # f.close()

        # all_x0_mm = [1000 * float(i) for i in all_x0]
        # all_y0_mm = [1000 * float(i) for i in all_y0]
        # all_z0_mm = [1000 * float(i) for i in all_z0]
        # all_x1_mm = [1000 * float(i) for i in all_x1]
        # all_y1_mm = [1000 * float(i) for i in all_y1]
        # all_z1_mm = [1000 * float(i) for i in all_z1]
        # all_temps_new = [float(i) for i in all_temps]
        
        # iter_count = len(all_temps_new)
        # print(iter_count)

        # box_temperatures_total = {box.name : 0.00 for box in box_list}
        # box_temperatures_count = {box.name : 0 for box in box_list}
        # box_temperatures_max = {box.name : -1000000.00 for box in box_list}

        # i = 0
        # while(i < iter_count):
        #     for box in box_list:
        #         if(self.check_overlap_dray(box, all_x0_mm[i], all_y0_mm[i], all_z0_mm[i], all_x1_mm[i], all_y1_mm[i], all_z1_mm[i])):
        #             box_temperatures_total[box.name] = box_temperatures_total[box.name] + all_temps_new[i]
        #             box_temperatures_count[box.name] = box_temperatures_count[box.name] + 1
        #             if(all_temps_new[i] > box_temperatures_max[box.name]):
        #                 box_temperatures_max[box.name] = all_temps_new[i]
        #     i = i + 1

        # for box in box_list:
        #     if(box_temperatures_count[box.name] > 0):
        #         box_temperatures_total[box.name] = box_temperatures_total[box.name] / box_temperatures_count[box.name]
        #     else:
        #         print("Box : " + box.name + " has no temperature data")

        #     print("Mean temperature of " + box.name + " chiplet is " + str(box_temperatures_total[box.name]) + " and its maximum temperature is " + str(box_temperatures_max[box.name]))

    
    def check_order(self, lst):
        if all(lst[i] <= lst[i + 1] for i in range(len(lst) - 1)):
            return 'ascending'
        elif all(lst[i] >= lst[i + 1] for i in range(len(lst) - 1)):
            return 'descending'
        else:
            return 'neither'
    # dedeepyo : 8-Jan-25 #

    # dedeepyo : 13-Jan-25 : Reading Anemoi voxels and mapping to local chiplet boxes 
    def chiplets_temperature_from_all_Anemoi_voxels_to_local_boxes(self, box_list):
        f = open("output_test_012825.txt", "r")
        # data = f.read()
        line0 = f.readline()
        line1 = f.readline()
        line2 = f.readline()
        line3 = f.readline()
        line4 = f.readline()
        line5 = f.readline()
        line6 = f.readline()
        line7 = f.readline()
        line8 = f.readline()
        line9 = f.readline()
        line10 = f.readline()
        line11 = f.readline()
        line12 = f.readline()
        line13 = f.readline()
        line14 = f.readline()
        f.close()
        # lines = data.split('\n')
        # print(len(lines))
        # print(line0)
        # print(line1)
        # print(line2)
        # print(line13)
        # print(line14)
        # print(line15)

        dict_keys = ["Temperatures", "x0", "y0", "z0", "x1", "y1", "z1"]
        dict_values_orig = [line2, line4, line6, line8, line10, line12, line14]
        dict_values = []
        for line_orig in dict_values_orig:
            line = line_orig.replace('[', '').replace(']', '').replace(',', '').replace('\'', '').split(' ')
            dict_values.append(line)
            # print(line[0])
            # print(len(line))
        data_dict = dict(zip(dict_keys, dict_values))
        '''
        data_all = data.replace(']', '[').split('[')
        data_dict = {}
        dict_key = ""
        for line in data_all:
            if(line == ''):
                print("Empty line")
            elif(line[0] == '\''):
                data_dict[dict_key] = line.replace('\'', '').replace(',', '').split(' ')
                print(len(data_dict[dict_key]))
            else:
                dict_key = line.split(' ')[0]

        # f = open("output_test_011325_try2.txt", "w")
        # f.write(str(data_dict))
        # f.close()    
        '''

        all_temps = data_dict['Temperatures']
        all_x0 = data_dict['x0']
        all_y0 = data_dict['y0']
        all_z0 = data_dict['z0']
        all_x1 = data_dict['x1']
        all_y1 = data_dict['y1']
        all_z1 = data_dict['z1']
        all_temps = [float(i) for i in all_temps]
        all_x0 = [float(i) for i in all_x0]
        all_y0 = [float(i) for i in all_y0]
        all_z0 = [float(i) for i in all_z0]
        all_x1 = [float(i) for i in all_x1]
        all_y1 = [float(i) for i in all_y1]
        all_z1 = [float(i) for i in all_z1]
        print(len(all_temps))
        print(str(all_temps[0]))
        print(str(all_temps[-1]))
        print(max(all_temps))
        print(min(all_temps))
        print(max(all_z0))
        '''
        all_x0_sorted = np.argsort(all_x0)
        all_y0_sorted = np.argsort(all_y0)
        all_z0_sorted = np.argsort(all_z0)
        all_x1_sorted = np.argsort(all_x1)
        all_y1_sorted = np.argsort(all_y1)
        all_z1_sorted = np.argsort(all_z1)
        all_x0_sorted_vals = [all_x0[i] for i in all_x0_sorted]
        all_y0_sorted_vals = [all_y0[i] for i in all_y0_sorted]
        all_z0_sorted_vals = [all_z0[i] for i in all_z0_sorted]
        all_x1_sorted_vals = [all_x1[i] for i in all_x1_sorted]
        all_y1_sorted_vals = [all_y1[i] for i in all_y1_sorted]
        all_z1_sorted_vals = [all_z1[i] for i in all_z1_sorted]
        print(all_x1_sorted_vals[-1])
        '''
        # f = open("output_test_011325_try3.txt", "w")
        # f.write(str(all_x0_sorted_vals))
        # f.write('\n')
        # f.write(str(all_y0_sorted_vals))
        # f.write('\n')
        # f.write(str(all_z0_sorted_vals))
        # f.write('\n')
        # f.write(str(all_x1_sorted_vals))
        # f.write('\n')
        # f.write(str(all_y1_sorted_vals))
        # f.write('\n')
        # f.write(str(all_z1_sorted_vals))
        # f.write('\n')
        # f.close()

        '''
        f = open("output_test_012825_1.txt", "w")
        c = len(all_temps)
        for box in box_list:
            i = 0
            max_temp = -1000000
            sum_temp = 0.00
            count_temp = 0
            while(i < c):
                overlap = True
                if all_x1[i] < box.start_x or all_x0[i] > box.end_x:
                    overlap = False
                if all_y1[i] < box.start_y or all_y0[i] > box.end_y:
                    overlap = False
                if all_z1[i] < box.start_z or all_z0[i] > box.end_z:
                    overlap = False
                if(overlap == True):
                    sum_temp = sum_temp + all_temps[i]
                    count_temp = count_temp + 1
                    if(max_temp < all_temps[i]):
                        max_temp = all_temps[i]
                i = i + 1

            if(count_temp != 0):
                mean_temp = sum_temp / count_temp
            f.write("Mean temperature of " + box.name + " chiplet is " + str(mean_temp) + " and its maximum temperature is " + str(max_temp))
            f.write('\n')
        f.close()
        '''
    # dedeepyo : 29-Jan-25 #

    # dedeepyo : 1-Jan-25 : Implementing chiplet temperature on Anemoi voxels instead of local voxels #
    def chiplets_temperature_from_Anemoi_voxels(self, box_list):
        voxel_res, max_sizes = self.calculate_voxel_resolution_and_max_sizes(box_list)
        voxel_res = [voxel_res[0] / 3, voxel_res[1] / 3, voxel_res[2] / 3]        
        # f = open("temp_map_dray_121724.txt", "w")        
        for box in box_list:
            temperature_sum = 0.00
            max_temperature = 0.00
            temperature_count = 0
            z_coord = box.start_z
            while(z_coord <= box.end_z):
                solutions = self.papi.project_solution_plane_list(self.id, plane="xy", coordinate=z_coord)
                z_coord += voxel_res[2]
                if not solutions:
                    # f.write("No solution at z = " + str(z_coord) + " for " + box.name)
                    print("No solution at z = " + str(z_coord) + " for " + box.name)
                else:
                    data = solutions.to_dict()["result"]
                    if not data:
                        # f.write("No data.\n")
                        print("No data.\n")
                    else:
                        for voxel in data:
                            temperature_sum += voxel['temp']
                            temperature_count += 1
                            if(voxel['temp'] > max_temperature):
                                max_temperature = voxel['temp']
            
            if(temperature_count != 0):
                temperature_avg = temperature_sum / temperature_count
            print("Mean temperature of " + box.name + " chiplet is " + str(temperature_avg) + " and its maximum temperature is " + str(max_temperature))
    # dedeepyo : 1-Jan-25 #

    # dedeepyo : 14-Feb-25 : Creating a hard-coded box #
    def create_hard_coded_box(self):
        mId = self.return_material_table_id("TIM") # Epoxy, Silver filled # AlN
        if mId is None:
            raise Exception("Material is None")

        data = {
            "name": "Gap_filler",
            "x": "0.00",
            "y": "0.00",
            "z": "1.55",
            "dx": "228.149074",
            "dy": "192.85636",
            "dz": "1.02",
            # "index": 57005,
            "index": 10000000,
            "material" : mId,
            "mesh_minx": 0.00,
            "mesh_maxx": 0.00,
            "mesh_miny": 0.00,
            "mesh_maxy": 0.00,
            "mesh_minz": 0.00,
            "mesh_maxz": 0.00
        }
        self.papi.project_box_create(self.id, data)
    # dedeepyo : 14-Feb-25 #

    def simulate(self, box_list, bonding_box_list, TIM_box_list, heatsink_obj, heatsink_list, heatsink_name, bonding_list, bonding_name_type_dict, layers, anemoi_parameter_ID, power_dict = {}, suffix="", is_repeat = False, min_TIM_height = 0.01, materials_update_dict = {}):
        # print("Boxes : " + str(box_list))
        # print("Heatsink list : " + str(heatsink_list))
        # print("Heatsink name : " + str(heatsink_name))
        # print("Bonding list : " + str(bonding_list))
        # print("Bonding name type dict : " + str(bonding_name_type_dict))
        # print("Suffix : " + str(suffix))
        # print("Is repeat : " + str(is_repeat))
        # print("Min TIM height : " + str(min_TIM_height))

        # print("Type of box_list : " + str(type(box_list)))
        # print("Type of box_list[0] : " + str(type(box_list[0])))
        # print("Type of heatsink_list : " + str(type(heatsink_list)))
        # print("Type of heatsink_list[0] : " + str(type(heatsink_list[0])))
        # print("Type of bonding_list : " + str(type(bonding_list)))
        # print("Type of bonding_list[0] : " + str(type(bonding_list[0])))
        # print("Type of bonding_name_type_dict : " + str(type(bonding_name_type_dict)))
        # print("Type of suffix : " + str(type(suffix)))
        # print("Type of is_repeat : " + str(type(is_repeat)))
        # print("Type of min_TIM_height : " + str(type(min_TIM_height)))

        print("Initiating Anemoi simulation")
        print("Cleaning project...")
        # print(self.material_list)
        # self.delete_plane_power() #
        # self.clean_project() #
        # self.delete_TIM() #
        # self.delete_heat_sink() #
        print("Setting up simulation environment...")
        # dedeepyo : 16-Oct-24 #
        # layers = parse_Layer_netlist("configs/thermal-configs/layer_definitions.xml")        
        # dedeepyo : 16-Oct-24 #
        
        # dedeepyo : 1-Jan-25 : Implementing repeat simulation #
        if is_repeat:
            if(materials_update_dict):
                self.update_materials(materials_update_dict) #
                print("Materials updated.")
                return None, None, None, None, None
            # self.update_power_plane(box_list) # 
            # self.create_hard_coded_box()
            # self.update_power_values(boxes = box_list)
            # self.parameterize_box_power(box_list)
            # print(anemoi_parameter_ID)
            # anemoi_parameter_ID = self.initialize_parameters() #
            # print(anemoi_parameter_ID)
            self.update_power_dict(power_dict, anemoi_parameter_ID) #
            # anemoi_parameters_list = self.papi.project_parameter_list(self.id)
            # print("Anemoi parameters list retrieved.")
            # for anemoi_param in anemoi_parameters_list:
                # anemoi_param_fields = anemoi_param.to_dict()
                # print(anemoi_param_fields)
            
            # param_dict = {
            #     "name" : "power",
            #     "description" : "Total power of the PCB",
            #     "value" : "0.00"
            # }
            # self.papi.project_parameter_create(self.id, param_dict) #
            # print(heatsink_list)
            # return None, None, None, None, None
            if(len(heatsink_list) > 0):
                self.load_multiple_heatsinks(box_list, heatsink_list) #
            print("Repeating.")
        else:
            anemoi_to_local_map_start_time = time.time()
            print("Starting Anemoi PCB building at " + str(anemoi_to_local_map_start_time))
            # self.create_bonding(box_list, material = "Cu-Foil", height = 0.5, ratio = 0.7) #
            # self.create_bonding(box_list, name = bonding_name, bonding_list = bonding_list, base = "interposer") #
            # self.create_all_bonding(box_list, name_type_dict = bonding_name_type_dict, bonding_list = bonding_list) #
            # wire_thickness = 0.1, wire_height = 0.1, wire_length = 0.1 #
            # self.create_bonding(box_list, material = "Cu-Foil", height = 0.01, wire_thickness = 0.1, wire_height = 0.1, wire_length = 0.1)
            self.load_bonding_boxes(bonding_box_list) #
            self.initialize_power_dict(power_dict) #
            anemoi_parameter_ID = self.initialize_parameters() #
            self.load_boxes(box_list, layers) #
            self.load_TIM_boxes(TIM_box_list) #
            anemoi_to_local_map_end_time = time.time()
            print("Ending Anemoi PCB building at " + str(anemoi_to_local_map_end_time))
            print("Time taken for Anemoi PCB building is " + str(anemoi_to_local_map_end_time - anemoi_to_local_map_start_time))
            self.load_heatsink(box_list, heatsink_obj, min_TIM_height = min_TIM_height) #
            if(len(heatsink_list) > 0):
                self.load_multiple_heatsinks(box_list, heatsink_list) #
            # self.create_TIM_to_heatsink(box_list, material = "TIM", min_TIM_height = min_TIM_height) #
            # self.create_heat_sink(box_list, "Cu-Foil", fin_thickness = 1, fin_height = 20, dz = 3, min_TIM_height = 0.01, scale_factor = 1) #
            # self.create_heat_sink(box_list, min_TIM_height = 0.01, scale_factor = 1, heatsink_list = heatsink_list, heatsink_name = "heatsink_water_free_convection") #
            # self.create_heat_sink(box_list, min_TIM_height = 0.01, scale_factor = 4, heatsink_list = heatsink_list, heatsink_name = heatsink_name) #
            # self.create_heat_sink(box_list, min_TIM_height = 0.01, heatsink_list = heatsink_list, heatsink_name = heatsink_name, scale_factor_x = 5.76, scale_factor_y = 3.16) #
            # self.create_heat_sink(box_list, min_TIM_height = min_TIM_height, heatsink_list = heatsink_list, heatsink_name = heatsink_name, area_scale_factor = 1) #
            # self.create_heat_sink_bottom(box_list, heatsink_list = heatsink_list, heatsink_name = heatsink_name, min_TIM_height = min_TIM_height, area_scale_factor = 1) #
            # self.create_heat_sink(box_list,"Cu-Foil")
            # self.create_hard_coded_box()
            print("First Iteration.")
            # return #TODO: Comment out later.
        # dedeepyo : 1-Jan-25 #

        # exit(0)
        print("Boxes loaded. Solving...") #
        solution_start_time = time.time()
        self.solve() #
        solution_end_time = time.time()
        print("Time taken for solving is " + str(solution_end_time - solution_start_time))
        print("Serializing...") #
        # df = self.serialize(box_list, layers) #
        # all_boxes = copy.deepcopy(box_list)
        # all_boxes.extend(bonding_box_list).extend(TIM_box_list)
        # df = self.serialize_dray(all_boxes, layers) #
        # temp_map = self.solution_to_temp_map_2D(box_list) ##
        df = self.serialize_dray(box_list, layers) #
        print("Mapping Anemoi solution to DeepFlow temperature map...") #
        # temp_map_3D = self.solution_to_temp_map_3D(box_list) #
        # temp_map_3D = self.solution_to_temp_map_3D_dray(box_list) #
        anemoi_to_local_map_start_time = time.time()
        print("Starting mapping of Anemoi solution to DeepFlow temperature map at " + str(anemoi_to_local_map_start_time))
        # temp_map_3D = self.solution_to_temp_map_3D_dray_3x3x3(box_list) #
        temp_map_3D = self.local_temperature_from_all_Anemoi_voxels(box_list) #
        anemoi_to_local_map_end_time = time.time()
        print("Ending mapping of Anemoi solution to DeepFlow temperature map at " + str(anemoi_to_local_map_end_time))
        print("Time taken for mapping of Anemoi solution to DeepFlow temperature map is " + str(anemoi_to_local_map_end_time - anemoi_to_local_map_start_time))
        # print(temp_map.shape)
        # df.load_temperature_map(temp_map) ##
        # df.visualize_power(fname="dataframes_2D/P.png")
        # df.visualize_temp_2D(fname=f"result_example/T{suffix}.png") ##
        print("Loading temperature map...") #
        df.load_temperature_map(temp_map_3D) #
        print("Plotting temperature map...") #
        # df.visualize_temp_3D(fname=f"result_example/T{suffix}_3D.png") #
        # df.visualize_temp_3D_dray(fname=f"result_example/T{suffix}_3D.png") #
        voxel_res, max_sizes = self.calculate_voxel_resolution_and_max_sizes(box_list)
        dx = voxel_res[0]
        dy = voxel_res[1]
        dz = voxel_res[2]
        # df.visualize_temp_3D_dray2(dx = dx, dy = dy, dz = dz, fname=f"result_example/T{suffix}_3D_fast.png") # This works!!
        # df.visualize_temp_3D_dray3(dx = dx, dy = dy, dz = dz, fname=f"result_example/T{suffix}_3D_2.png") #
        print("Finding chiplets' temperature") #
        GPU_peak_temperature, HBM_peak_temperature, GPU_min_peak_temperature, HBM_min_peak_temperature, GPU_temperatures_list, HBM_temperatures_list = self.chiplets_temperature(temp_map_3D, box_list) #
        # self.chiplets_temperature_from_all_Anemoi_voxels(box_list) #
        # self.chiplets_temperature_from_all_Anemoi_voxels_to_local_boxes(box_list) #

        return GPU_peak_temperature, HBM_peak_temperature, GPU_min_peak_temperature, HBM_min_peak_temperature, anemoi_parameter_ID