# this file uses click to parse a thermal config, a deepflow config, and a deepflow output file.
# it then performs thermal analysis.

import click
import yaml
import sys
import math
import matplotlib.pyplot as plt
import seaborn as sns
import xml.etree.ElementTree as ET
from thermal_simulators.factory import SimulatorFactory
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
# from rearrange import *
from rearrange import *
from therm_xml_parser import *
import time
from bonding_xml_parser import *
from heatsink_xml_parser import *
import pickle
import os
import subprocess
import re
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

import re
from pathlib import Path
from typing import List, Tuple
import csv

_THERM_REPO_ROOT = Path(__file__).resolve().parent

sns.set()

# how many times*min_dist should we move
MOVE_MULTIPLIER = 1
# how much should we inflate for overlap checking
INFLATION = 1

class Pin():
    def __init__(self,name,parent_name):
        self.name = name
        self.parent_name = parent_name
        self.edge_name = None

    def assign_to_edge(self,edge_name):
        self.edge_name = edge_name

    def is_assigned(self):
        return self.edge_name is not None

# def parse_pin_map(pin_map,gpu_coords):

#     # print("GPU coords received:",gpu_coords)
#     # this is a pin map
#     #   pin_map: [
#     #     "PIXXX
#     #      XIXXX
#     #      XIDIP
#     #      XIXXX
#     #      PIXXX"
#     #   ]
#     # P is pin, D is device, X is air, I is ISOLATOR
#     # lower left corner of the GPU is (gpu_coords[0],gpu_coords[1]).
#     # top right is (gpu_coords[2],gpu_coords[3])
#     # the pin map is a string. We need to parse it and assign coordinates to each pin.
#     pin_coords = []
#     # the pin map could be any size, but has to be odd x odd number. check that first
#     pin_map = pin_map[0].split(' ')
#     for i in range(len(pin_map)):
#         # strip whitespace
#         pin_map[i] = pin_map[i].strip()
#     num_rows = len(pin_map)
#     num_cols = len(pin_map[0])
#     if num_rows % 2 == 0 or num_cols % 2 == 0:
#         raise ValueError("Pin map must be odd x odd")
#     # now parse the pin map
#     die_length = gpu_coords[3] - gpu_coords[1]
#     die_width = gpu_coords[2] - gpu_coords[0]
#     # now subdivide that into num_rows x num_cols
#     # for example, if 3x3 and die_length is 10, I want points at:
#     # 0, 5, 10
#     row_height = die_length / (num_rows-1)
#     col_width = die_width / (num_cols-1)
#     for i in range(num_rows):
#         for j in range(num_cols):
#             if pin_map[i][j] == 'P':
#                 pin_coords.append((gpu_coords[0]+j*col_width,gpu_coords[1]+(num_rows-1-i)*row_height))

#     # I now also want to extract isolator coordinates.
#     # the isolators are thin strips, so we want to merge isolators across columns and rows.
#     isolator_coords = []
#     for i in range(num_rows):
#         for j in range(num_cols):
#             if pin_map[i][j] == 'I':
#                 # check if this is a new isolator
#                 if (i == 0 or pin_map[i-1][j] != 'I') and (j == 0 or pin_map[i][j-1] != 'I'):
#                     # this is the start of a new isolator
#                     start_x = gpu_coords[0]+(j-1)*col_width
#                     start_y = gpu_coords[1]+(num_rows-1-i)*row_height
#                     # now find the end of the isolator
#                     end_x = start_x
#                     end_y = start_y
#                     j_acc = j
#                     while j < num_cols and pin_map[i][j_acc] == 'I':
#                         j_acc += 1
#                         if j_acc == num_cols:
#                             break
#                         end_x += col_width
#                     i_acc = i
#                     while i < num_rows and pin_map[i_acc][j] == 'I':
#                         i_acc += 1
#                         if i_acc == num_rows:
#                             break
#                         end_y -= row_height
#                     # now, remember that isolators are not boxes but lines.
#                     # so we need to ensure that start_x == end_x
#                     # but do we set start_x = end_x or end_x = start_x?
#                     # this depends on whether the isolator is to the left or to the right
#                     middle_x = gpu_coords[0]+(num_cols-1)/2*col_width
#                     if end_x <= middle_x:
#                         # left of gpu
#                         start_x = gpu_coords[0]
#                         end_x = start_x
#                     else:
#                         # right of gpu
#                         end_x = gpu_coords[2]
#                         start_x = end_x
#                     isolator_coords.append((start_x,start_y,end_x,end_y))

#     # print("Isolator coords:",isolator_coords)
#     return pin_coords, isolator_coords

def draw_fig(boxes,out_dir,out_name,limits):
    fig, ax = plt.subplots()
    ax.set_aspect('equal')
    for box in boxes:
        if box.name.endswith("interposer"):
            ax.add_patch(plt.Rectangle((box.start_x, box.start_y), box.width, box.length, fill=True,color='black'))
        elif box.name[:-1].endswith('HBM'):
            ax.add_patch(plt.Rectangle((box.start_x, box.start_y), box.width, box.length, fill=True,color='blue'))
        elif box.name.endswith('wafer'):
            ax.add_patch(plt.Rectangle((box.start_x, box.start_y), box.width, box.length, fill=True,color='green'))
        else:
            ax.add_patch(plt.Rectangle((box.start_x, box.start_y), box.width, box.length, fill=True,color='red'))
        # ax.text(box.start_x+box.width/2,box.start_y+box.length/2,box.name,ha='center',va='center', color='white')
    plt.xlim(limits[0],limits[1])
    plt.ylim(limits[2],limits[3])
    plt.savefig(out_dir+'/'+out_name+'.png')
    plt.close()

# def draw_fig_3D_alt(boxes, out_dir, out_name):
#     fig = plt.figure()
#     ax = fig.add_subplot(111, projection='3d')
    
#     collections = []

#     for box in boxes:
#         x = [box.start_x, box.start_x + box.width, box.start_x + box.width, box.start_x, box.start_x]
#         y = [box.start_y, box.start_y, box.start_y + box.length, box.start_y + box.length, box.start_y]
#         z = [box.start_z] * 5  # base z level
#         z_top = [box.start_z + box.height] * 5  # top z level

#         verts = [list(zip(x, y, z)),
#                 list(zip(x, y, z_top))]

#         # Sides of the box
#         for i in range(4):
#             verts.append([(x[i], y[i], z[i]), (x[i+1], y[i+1], z[i+1]), 
#                         (x[i+1], y[i+1], z_top[i+1]), (x[i], y[i], z_top[i])])

#         # set zpos according to x position
#         # closer means higher zpos

#         zpos = box.start_x

#         if box.name == 'interposer':
#             color = 'black'
#         elif 'HBM' in box.name:
#             color = 'blue'
#         else:
#             color = 'red'


#         poly = Poly3DCollection(verts, facecolors=color, edgecolors='k', alpha=0.7)  # Adjust alpha for better visibility
#         poly.set_sort_zpos(zpos)
#         collections.append((poly, box))

#     for poly, box in collections:
#         ax.add_collection3d(poly)
#         # ax.text(box.start_x + box.width / 2, box.start_y + box.length / 2, box.start_z + box.height / 2, box.name, ha='center', va='center', color='white')

#     ax.set_xlim(-15, 75)
#     ax.set_ylim(-15, 75)
#     ax.set_zlim(0, 90) 
#     plt.savefig(out_dir + '/' + out_name + '3D.png')
#     plt.close()

def draw_fig_3D_zoom(boxes, out_dir, out_name, limits):
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    
    collections = []

    for box in boxes:
        x = [box.start_x, box.start_x + box.width, box.start_x + box.width, box.start_x, box.start_x]
        y = [box.start_y, box.start_y, box.start_y + box.length, box.start_y + box.length, box.start_y]
        z = [box.start_z] * 5  # base z level
        z_top = [box.start_z + box.height] * 5  # top z level

        verts = [list(zip(x, y, z)),
                 list(zip(x, y, z_top))]

        # Sides of the box
        for i in range(4):
            verts.append([(x[i], y[i], z[i]), (x[i+1], y[i+1], z[i+1]), 
                          (x[i+1], y[i+1], z_top[i+1]), (x[i], y[i], z_top[i])])

        zpos = box.start_x

        if box.name.endswith('interposer'):
            color = 'black'
        elif box.name[:-1].endswith('HBM'):
            color = 'blue'
        elif box.name.endswith('wafer'):
            color = 'green'
        else:
            color = 'red'

        poly = Poly3DCollection(verts, facecolors=color, edgecolors='k', alpha=0.7)
        poly.set_sort_zpos(zpos)
        collections.append((poly, box))

    for poly, box in collections:
        ax.add_collection3d(poly)
        # Uncomment to add labels
        # ax.text(box.start_x + box.width / 2, box.start_y + box.length / 2, box.start_z + box.height / 2, box.name, ha='center', va='center', color='white')

    ax.set_xlim(limits[0], limits[1])
    ax.set_ylim(limits[0], limits[1])
    ax.set_zlim(limits[0], int(limits[1]//2))  

    ax.view_init(elev=20, azim=30)  # Adjust the viewing angle
    ax.dist = 1  # Decrease this value to zoom in

    plt.savefig(out_dir + '/' + out_name + '3D.png')
    plt.close()

def determine_draw_lim(boxes):
    # find the min and max x and y
    min_x = 100000
    max_x = -100000
    min_y = 100000
    max_y = -100000
    for box in boxes:
        if box.start_x < min_x:
            min_x = box.start_x
        if box.start_x + box.width > max_x:
            max_x = box.start_x + box.width
        if box.start_y < min_y:
            min_y = box.start_y
        if box.start_y + box.length > max_y:
            max_y = box.start_y + box.length

    return min_x-5,max_x+5,min_y-5,max_y+5


# dedeepyo : 25-Feb-2025 : Implementing power source representation.
def recursively_lift_box(chiplet, box_list, height):
    box = chiplet.get_box_representation()
    box.start_z = box.start_z + height
    # print("Lifting box " + box.name + " to z : " + str(box.start_z))
    for child in chiplet.get_child_chiplets():
        recursively_lift_box(child, box_list, height)
    return

def create_power_source_backside(boxes, efficiency = 0.9):
    # ps = Box(x_coord,y_coord,z_coord,width,length,height,power,stackup,0,"Power Source")
    # recursively_lift_box(boxes[0].chiplet_parent, boxes, ps.height)
    # boxes.append(ps)
    total_power = 0
    for box in boxes:
        total_power += box.power
    
    ps = [box for box in boxes if box.chiplet_parent.get_chiplet_type() == "Power_Source"][0] # Assuming only one power source. For now, it is at bottom. backside power delivery.
    ps.power = (1 - efficiency) * total_power / efficiency
    ps.chiplet_parent.set_power(ps.power)
    # print("Power source power : " + str(ps.power))
# dedeepyo : 25-Feb-2025 #

# dedeepyo : 30-Jan-2025 : Bonding layer addition 
# height : Thickness of the bonding layer; determined based on input from Krutikesh.
# For Box, both z and dz are in mm. For PCBLayer, thickness is in um. For PCB, z is in mm.
# height here is in um.
def calculate_ratio(bonding, box):
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
def get_real_children_recursive(chiplet_list):
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
        real_children.extend(get_real_children_recursive(fake_children))

    return real_children
# dedeepyo : 12-Feb-2025 #

def create_all_bonding(box_list, name_type_dict, bonding_list):
    bonding_box_list = []

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
        create_bonding(box_list, chiplet_tree_root, bonding_dict, bonding_box_list)
    
    return bonding_box_list

# Assuming bonding only between interposer and GPU or HBM, not between stacked chiplets. # This assumption is no longer valid.
def create_bonding(box_list, base_chiplet, bonding_dict, bonding_box_list):
    children_of_base = base_chiplet.get_child_chiplets()
    for chiplet in children_of_base:
        try:
            bonding = bonding_dict[base_chiplet.get_chiplet_type()].get(chiplet.get_chiplet_type())
        except:
            bonding = None

        # dedeepyo : 03-Dec-2025 : Testing bonding for GPU on top.
        # print(f"Bonding for {base_chiplet.get_chiplet_type()} with {chiplet.get_chiplet_type()} above it.")
        # dedeepyo : 03-Dec-2025

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

            ratio = 100 * calculate_ratio(bonding, box)
            bonding_box = Box(x, y, z, dx, dy, height_mm, 0.0, f"1:{material}:{ratio},Epoxy, Silver filled:{100 - ratio}", 0.0, f"{chiplet.name}_bonding")
            recursively_lift_box(chiplet, box_list, height_mm)
            bonding_box_list.append(bonding_box)

        # if(bonding_dict.get(chiplet.get_chiplet_type()) is not None):
        #     create_bonding(box_list, chiplet, bonding_dict, bonding_box_list)

        create_bonding(box_list, chiplet, bonding_dict, bonding_box_list)

def recursively_lift_box(chiplet, box_list, height):
    box = chiplet.get_box_representation()
    box.start_z = box.start_z + height
    # print("Lifting box " + box.name + " to z : " + str(box.start_z))
    for child in chiplet.get_child_chiplets():
        recursively_lift_box(child, box_list, height)
    return

# dedeepyo : 9-Apr-25 : Copying over TIM creation.
def create_TIM_to_heatsink(box_list, material = "TIM0p5", min_TIM_height = 0.1, system_type = None):
    TIM_boxes = []
    z_min = max([box.end_z for box in box_list])
    z = z_min
    # top_box = [b for b in box_list if b.end_z == z_min][0]
    # print("Highest box is : " + top_box.name + " which ends at z : " + str(z_min))
    # print("The bottom of heat sink is at z : " + str(z))
    if system_type != "3D_1GPU_top":
        for box in box_list:
            # dedeepyo : 12-Feb-25 : A fake chiplet always has child chiplets; that is the purpose why it is made. Also, a box here is never fake.
            if(box.chiplet_parent.get_child_chiplets() == []):
                tim_height = z - box.end_z
                # if(tim_height != 0):
                if(tim_height > 0.0001):
                    # print("TIM height is : " + str(tim_height) + " for box " + box.name + " which ends at z : " + str(box.end_z))
                    tim_box = Box(box.start_x, box.start_y, box.end_z, box.width, box.length, tim_height, 0.0, f"1:{material}", 0.0, f"{box.name}_TIM")
                    TIM_boxes.append(tim_box)
                    # print(tim_data["name"] + " starts from z : " + tim_data["z"] + " and has height : " + tim_data["dz"])
                # else:
                #     print("The top of PCB " + box.name + " is at the same level as the bottom of heat sink!")
        
    intp_list = [b for b in box_list if b.chiplet_parent.get_chiplet_type() == "interposer" or b.chiplet_parent.get_chiplet_type() == "substrate"]
    intp = intp_list[0]
    for i in intp_list:
        if(i.end_z > intp.end_z):
            intp = i

    tim_box = Box(intp.start_x, intp.start_y, z_min, intp.width, intp.length, min_TIM_height, 0.0, f"1:{material}", 0.0, f"{intp.name}_TIM")
    TIM_boxes.append(tim_box)
    return TIM_boxes

# dedeepyo : 21-Jun-25 : Creating multiple heat sinks for a chiplet tree.
def calculate_GPU_HBM_HTC(box_list, power_dict, hc):
    # Assumption that we already have temperature data with default HTC hc. We use those temperatures to calculate the individual HTC for GPU and HBM.
    GPU_HTC = 15236.73003 # hc
    HBM_HTC = 2729.690335 # hc
    return GPU_HTC, HBM_HTC

def create_multiple_heat_sinks(box_list, heatsink_list, heatsink_name, power_dict, min_TIM_height = 0.01): # , scale_factor_x = 0, scale_factor_y = 0, area_scale_factor = 0):
    # dedeepyo : 7-Feb-2025 : Heatsink object creation.
    heatsinks = [h for h in heatsink_list if h.get_name() == heatsink_name]
    if(heatsinks is None):
        raise Exception("Heatsink not found")
    
    fin_height = heatsinks[0].get_fin_height()
    fin_thickness = heatsinks[0].get_fin_thickness()
    material = heatsinks[0].get_material()
    fin_number = heatsinks[0].get_fin_count()
    hc = heatsinks[0].get_hc()
    fin_offset = heatsinks[0].get_fin_offset()
    dz = heatsinks[0].get_base_thickness()
    bind_to_ambient = heatsinks[0].get_bind_to_ambient()

    if(fin_number == 0):
        if(fin_thickness > 0):
            fin_number = int(dx / (2 * fin_thickness))
    
    excluded_types = ["interposer", "substrate", "PCB", "Power_Source"]
    box_list_min = [box for box in box_list if box.chiplet_parent.get_chiplet_type() not in excluded_types]
    z_min = max([box.end_z for box in box_list_min])
    z = z_min + min_TIM_height
    
    # x_min = min([box.start_x for box in box_list_min])
    # x_max = max([box.end_x for box in box_list_min])
    # y_min = min([box.start_y for box in box_list_min])
    # y_max = max([box.end_y for box in box_list_min])
        
    # if(area_scale_factor != 0):
    #     dimension_scale_factor = math.sqrt(area_scale_factor)
    #     dx = dimension_scale_factor * (x_max - x_min)
    #     dy = dimension_scale_factor * (y_max - y_min)
    # elif(scale_factor_x == 0):
    #     if(scale_factor_y == 0):
    #         dy = heatsinks[0].get_base_length()
    #     else:
    #         dy = scale_factor_y * (y_max- y_min)
    #     dx = heatsinks[0].get_base_width()
    # elif(scale_factor_y == 0):
    #     dy = heatsinks[0].get_base_length()
    #     dx = scale_factor_x * (x_max - x_min)
    # else:
    #     dx = scale_factor_x * (x_max - x_min)
    #     dy = scale_factor_y * (y_max- y_min)

    # x = (x_max + x_min - dx) / 2
    # y = (y_max + y_min - dy) / 2

    GPU_HTC = hc
    HBM_HTC = hc
    GPU_HTC, HBM_HTC = calculate_GPU_HBM_HTC(box_list, power_dict, hc)

    HTC_dict = {
        "GPU_HTC": GPU_HTC / 1000,  # Convert to kW/m^2-K
        "HBM_HTC": HBM_HTC / 1000
    }
    power_dict.update(HTC_dict)
    heatsink_data_list = []
    chiplet_HTC = {
        "GPU": "GPU_HTC",
        "HBM": "HBM_HTC"
    }
    box_list_top = []
    for box in box_list:
        if(box.chiplet_parent.get_child_chiplets() == []):
            box_list_top.append(box)
    for box in box_list_top:
        chiplet_type = box.chiplet_parent.get_chiplet_type()[0:3]
        hc = chiplet_HTC.get(chiplet_type, None)
        if(hc is not None):
            # print(f"HTC is {hc} for chiplet type {chiplet_type}")
            x = box.start_x
            y = box.start_y
            dx = box.width
            dy = box.length
            heatsink_data = {
                "name": f"HS_top_{box.name}",
                "index": 0,
                "material": material,  # Cu-Foil
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
                "bound": bind_to_ambient
            }
            heatsink_data_list.append(heatsink_data)
    
    return heatsink_data_list, power_dict
# dedeepyo : 21-Jun-25

def create_heat_sink(box_list, heatsink_list, heatsink_name, min_TIM_height = 0.01, scale_factor_x = 0, scale_factor_y = 0, area_scale_factor = 0):
    # dedeepyo : 7-Feb-2025 : Heatsink object creation.
    heatsinks = [h for h in heatsink_list if h.get_name() == heatsink_name]
    if(heatsinks is None):
        raise Exception("Heatsink not found")
    
    # excluded_types = ["interposer", "substrate", "PCB", "Power_Source"]
    excluded_types = []
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
        if(fin_thickness > 0):
            fin_number = int(dx / (2 * fin_thickness))

    heatsink_data = {
        "name": f"HS_top",
        "index": 0, # 10000000, # 
        # "material": self.return_material_table_id(material),  # Cu-Foil
        "material": material,  # Cu-Foil
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
        "bound": bind_to_ambient
    }
    return heatsink_data
# dedeepyo : 09-Apr-2025 #

# dedeepyo : 03-Dec-2025 : Implementing DFS.
def find_deepest_node(chiplet_tree):
    if not chiplet_tree or len(chiplet_tree) == 0:
        return None
    
    root = chiplet_tree[0]
    deepest_node = root
    max_depth = 0
    
    def traverse(node, depth):
        nonlocal deepest_node, max_depth
        if depth > max_depth:
            max_depth = depth
            deepest_node = node
        
        for child in node.get_child_chiplets():
            traverse(child, depth + 1)
    
    traverse(root, 0)
    return deepest_node
# dedeepyo : 03-Dec-2025

@click.command("standalone")
@click.option('--therm_conf', help='The thermal config file')
# @click.option('--deep_conf', help='The deepflow config file')
@click.option('--out_dir', help='The output directory')
# @click.option('--simtype', default="Anemoi", help='The simulator type')
@click.option('--heatsink_conf', help='The heatsink config file')
@click.option('--bonding_conf', help='The bonding config file')
@click.option('--heatsink', help='The heatsink name')
# @click.option('--bonding', help='The bonding name')
@click.option('--project_name', help='The project name')
@click.option('--is_repeat', default = False, help='Is this a repeat run?')
@click.option('--hbm_stack_height', default = 1, help='Number of dies per HBM stack')
@click.option('--system_type', default = "2p5D", help='The system type')
@click.option('--dummy_si', default = False, help='Does 3D have dummy Si?')
@click.option('--tim_cond_list', default = [10.0], multiple = True, help='The TIM conductivity list')
@click.option('--infill_cond_list', default = [1.6], multiple = True, help='The infill conductivity list')
@click.option('--underfill_cond_list', default = [1.6], multiple = True, help='The underfill conductivity list')
def therm(therm_conf, heatsink_conf, bonding_conf, heatsink, out_dir, project_name, simtype = "Anemoi", is_repeat = False, hbm_stack_height = 1, system_type = "2p5D", dummy_si = False, tim_cond_list = (5, 10, 50), infill_cond_list = (1.6, 19), underfill_cond_list = (1.6, 19)):

    simulator = SimulatorFactory.get_simulator(type = simtype, name = project_name)

    chiplet_tree = parse_all_chiplets(therm_conf)
    (w_top, l_top) = recursive_chiplet_sizing(chiplet_tree[0], None)

    # first chip at 0,0
    next_level_assignements = []
    # traverse chiplet tree. Handle each level separately.D

    def generate_placements_from_floorplan(floorplan, floorplan_dict, chiplet_tree):
        # if floorplan or floorplan_dict = "", then check if the chiplet_tree has only 1 element.
        # if it does, then assign it to the center of the floorplan.
        # if it has more, then exception
        if floorplan == "" or floorplan_dict == "":
            if len(chiplet_tree) == 1:
                grid = [[chiplet_tree[0]]]
                return grid, []
            else:
                raise ValueError("Chiplet tree has more than 1 element with no floorplan definitions")
            
        # if floorplan and floorplan_dict are not empty, then we need to parse them.
        # first, parse the floorplan
        # example floorplan (in XML):
        # floorplan="
        #     HXH
        #     XDX
        #     HXH"
        # example floorplan dict:
        # floorplan_dict="
        # D:(GPU)*
        # H:(HBM0,HBM1,HBM2,HBM3)
        # "
        # first, parse the floorplan dict
        # I want a python dict that goes D:GPU, H:(HBM0,HBM1,HBM2,HBM3)
        # because GPU has an * after it, I want to remove it and instead consider the GPU a fixed chiplet.
        fixed_chiplets = []
        # print("Before split", floorplan_dict)
        floorplan_dict = floorplan_dict.split(' ')
        # now eliminate all substrings that are empty whitespace
        floorplan_dict = [x for x in floorplan_dict if x != ""]
        # now split by :
        floorplan_dict = [x.split(':') for x in floorplan_dict]
        # print("After split", floorplan_dict)
        # now split by *
        # handle asterisk
        for i in range(len(floorplan_dict)):
            if floorplan_dict[i][1][-1] == '*':
                floorplan_dict[i][1] = floorplan_dict[i][1][:-1]
                fix_name = floorplan_dict[i][1]
                # remove "(" and ")" from fix name
                fix_name = fix_name.split('(')[1]
                fix_name = fix_name.split(')')[0]
                fixed_chiplets.append(fix_name)
        # floorplan_dict = {x[0]:x[1] for x in floorplan_dict}  
        # we want to do the above line while checking that x[1] is a list
        # if its a string or not a list, basically not in parentheses, then we want to error out
        for i in range(len(floorplan_dict)):
            if floorplan_dict[i][1][0] != '(':
                raise ValueError("Floorplan dict must have values in parentheses")
            floorplan_dict[i][1] = floorplan_dict[i][1][1:-1]
            floorplan_dict[i][1] = floorplan_dict[i][1].split(',')
        floorplan_dict = {x[0]:x[1] for x in floorplan_dict}

        # ensure the values in the dict exist in the chiplet tree
        for key in floorplan_dict:
            # if key is a single string
            if len(floorplan_dict[key]) == 1:
                # if floorplan_dict[key][0] not in chiplet_tree:
                #     print("Chiplet tree:",chiplet_tree)
                #     raise ValueError("Chiplet {} not found in chiplet tree".format(floorplan_dict[key][0]))
                found = False
                for chiplet in chiplet_tree:
                    if chiplet.get_chiplet_type() == floorplan_dict[key][0]:
                        found = True
                        break
                if not found:
                    raise ValueError("Chiplet {} not found in chiplet tree".format(floorplan_dict[key][0]))
            else:
                for chiplet in floorplan_dict[key]:
                    # if chiplet not in chiplet_tree:
                    #     raise ValueError("Chiplet {} not found in chiplet tree".format(chiplet))
                    for chiplet_tree_chiplet in chiplet_tree:
                        if chiplet_tree_chiplet.get_chiplet_type() == chiplet:
                            found = True
                            break
                    if not found:
                        raise ValueError("Chiplet {} not found in chiplet tree".format(chiplet))


    
        # now parse the floorplan
        # print("Pre split", floorplan)
        # floorplan = floorplan.split('\n')
        # floorplan = [x.strip() for x in floorplan] # dedeepyo : 27-Feb-25
        # floorplan = [x for x in floorplan if x != ""] # dedeepyo : 27-Feb-25
        # floorplan = [list(x) for x in floorplan] # dedeepyo : 27-Feb-25
        # print("After processing", floorplan)
        # floorplan is now a flat list. We need to ensure it is a square.
        # floorpl_len = len(floorplan) # dedeepyo : 27-Feb-25
        # check that it is a square number
        # like literally. Is it 4,9,16,..
        # if math.sqrt(floorpl_len) != int(math.sqrt(floorpl_len)): # dedeepyo : 27-Feb-25
        #     raise ValueError("Floorplan must be a square") # dedeepyo : 27-Feb-25
        # now format it into a square
        # floorplan = [floorplan[i:i+int(math.sqrt(floorpl_len))] for i in range(0,floorpl_len,int(math.sqrt(floorpl_len)))] # dedeepyo : 27-Feb-25

        # dedeepyo : 27-Feb-25 : Fixing the floorplan parsing. Adding rectangular floorplanning.
        floorplan = floorplan.strip("\n").strip().split(' ')
        floorplan = [x for x in floorplan if x != ""]
        floorplan = [list(x) for x in floorplan]
        r = len(floorplan)
        for i in range(r):
            floorplan[i] = [list(x) for x in floorplan[i]]
        # print("Floorplan:",floorplan)
        # print(len(floorplan),len(floorplan[0]))
        # dedeepyo : 27-Feb-25 #
        # # ensure floorplan is an odd square.
        # if len(floorplan) % 2 == 0 or len(floorplan[0]) % 2 == 0:
        #     raise ValueError("Floorplan must be an odd square")
            

        # create a grid with the same dimensions as the floorplan
        grid = [[None for i in range(len(floorplan[0]))] for j in range(len(floorplan))]
        # now, for each element in the floorplan, assign the corresponding chiplet
        # print floorplan and grid shapes
        # print("Floorplan shape:",len(floorplan),len(floorplan[0]))
        # print("Grid shape:",len(grid),len(grid[0]))
        # print("Floorplan:",floorplan)
        # print("Floorplan dict:",floorplan_dict)
        # print(grid)
        for i in range(len(floorplan)):
            for j in range(len(floorplan[0])):
                if floorplan[i][j][0] == 'X':
                    grid[i][j] = None
                else:
                    # print("Checking",floorplan[i][j][0])
                    # try to find an appropriate assignment within the floorplan dict
                    if floorplan[i][j][0] not in floorplan_dict:
                        raise ValueError("Chiplet {} not found in floorplan dict".format(floorplan[i][j][0]))
                    # else, we need to find the first chiplet in the chiplet tree that matches the floorplan dict
                    chosen_chiplet = None
                    for chiplet in chiplet_tree:
                        # print("Checking",chiplet.get_chiplet_type())
                        # print("In",floorplan_dict[floorplan[i][j][0]])
                        if chiplet.get_chiplet_type() in floorplan_dict[floorplan[i][j][0]] and not chiplet.is_assigned_floorplan():
                            chosen_chiplet = chiplet
                            chiplet.set_assigned_floorplan(True)
                            break

                    if chosen_chiplet is None:
                        raise ValueError("Chiplet defined by {} not found in chiplet tree".format(floorplan[i][j][0]))
                    grid[i][j] = chosen_chiplet

                    # grid[i][j] = floorplan_dict[floorplan[i][j][0]][0]
                    # print("Assigned",grid[i][j])

        return grid, fixed_chiplets

    # dedeepyo : 17-Dec-2024 : Implementing copy of placement recursion.
    def copy_placements_recursive(boxes,parent,chiplet_tree, min_dist = 0.0):
        return
    # dedeepyo : 17-Dec-2024

    # dedeepyo : 28-Jan-2025 : Implementing recursive fake chiplet sizing.
    # Assuming any level has either all fake chiplets or all real chiplets.
    # Assuming the base chiplet is never fake.
    def determine_sizing_recursive(boxes,parent,chiplet_tree, min_dist = 0.0, fake_chiplet_size_dict = {}):
        if len(chiplet_tree) == 0:
            return
        
        if not parent:
            grid = [[chiplet_tree[0]]]
            x_coord = 0
            y_coord = 0
            z_coord = 0
            stackup = chiplet_tree[0].get_stackup()
            material = "Si"
            power = chiplet_tree[0].get_power()
            area = chiplet_tree[0].get_core_area()
            aspect_ratio = chiplet_tree[0].get_aspect_ratio()
            height = chiplet_tree[0].get_height()
            width = math.sqrt(area*aspect_ratio)
            length = area/width
            box = Box(x_coord,y_coord,z_coord,width,length,height,power,stackup,0,chiplet_tree[0].get_name())
            box.assign_chiplet_parent(chiplet_tree[0])
            boxes.append(box)
            determine_sizing_recursive(boxes,box,chiplet_tree[0].get_child_chiplets(), box.chiplet_parent.assembly_process.get_die_separation(), fake_chiplet_size_dict)
        else:
            grid, fixed_chiplets = generate_placements_from_floorplan(parent.chiplet_parent.floorplan,parent.chiplet_parent.floorplan_dict,chiplet_tree)
            parent_coords = parent.get_2d_coords()
            parent_width = parent.width
            parent_length = parent.length
            num_rows = len(grid)
            num_cols = len(grid[0])
            # Assuming fake chiplets are only iterated over once.
            fake_chiplet_dict = {}
            largest_width = 0
            largest_length = 0
            for i in range(num_rows):
                for j in range(num_cols):
                    if grid[i][j] is not None:
                        chiplet = grid[i][j]
                        chiplet_area = chiplet.get_core_area()
                        chiplet_aspect_ratio = chiplet.get_aspect_ratio()
                        chiplet_width = math.sqrt(chiplet_area*chiplet_aspect_ratio)
                        chiplet_length = chiplet_area/chiplet_width
                        # dedeepyo : 28-Jan-2025 : Implementing fake chiplet addition to dictionary.
                        chiplet.set_assigned_floorplan(False)
                        if((chiplet.get_fake() == True) and (fake_chiplet_dict.get(chiplet.get_chiplet_type()) == None)):
                            fake_chiplet_dict[chiplet.get_chiplet_type()] = 0
                        # dedeepyo : 28-Jan-2025 #
                        if chiplet_width > largest_width:
                            largest_width = chiplet_width
                        if chiplet_length > largest_length:
                            largest_length = chiplet_length

            side_length = largest_length
            side_length += min_dist #
            # side_length += min_dist * (1 + INFLATION)
            side_width = largest_width
            side_width += min_dist #
            # side_width += min_dist * (1 + INFLATION)
            grid_length = side_length*num_rows
            grid_width = side_width*num_cols
            grid_x = parent_coords[0] + parent_width/2 - grid_width/2
            grid_y = parent_coords[1] + parent_length/2 - grid_length/2

            children_boxes = []         
            for i in range(num_rows):
                for j in range(num_cols):
                    if grid[i][j] is not None:
                        chiplet = grid[i][j]
                        if(chiplet.get_fake() == True):
                            if(fake_chiplet_dict[chiplet.get_chiplet_type()] == 1):
                                continue
                        x_coord = grid_x + j*side_length + side_length/2
                        y_coord = grid_y + i*side_length + side_length/2
                        z_coord = parent.start_z + parent.height
                        stackup = chiplet.get_stackup()
                        material = "Si"
                        power = chiplet.get_power()
                        aspect_ratio = chiplet.get_aspect_ratio()
                        height = chiplet.get_height()
                        area = chiplet.get_core_area()
                        width = math.sqrt(area*aspect_ratio)
                        length = area/width
                        
                        x_coord = x_coord - width/2
                        y_coord = y_coord - length/2                        
                        box = Box(x_coord,y_coord,z_coord,width,length,height,power,stackup,0,chiplet.get_name())
                        box.assign_chiplet_parent(chiplet)
                        chiplet.set_box_representation(box)
                        min_dist_for_children = 0.0
                        if(chiplet.get_fake() == True):
                            min_dist_for_children = parent.chiplet_parent.assembly_process.get_die_separation()
                            fake_chiplet_dict[chiplet.get_chiplet_type()] = 1
                        else:
                            min_dist_for_children = chiplet.assembly_process.get_die_separation()
                            boxes.append(box)                        
                        children_boxes.append(box)
                        determine_sizing_recursive(boxes,box,chiplet.get_child_chiplets(), min_dist_for_children, fake_chiplet_size_dict)

            def move_box(box, x, y):
                box.start_x += x #
                box.start_y += y #
                for chiplet in box.chiplet_parent.get_child_chiplets(): #
                    if chiplet.get_box_representation(): #
                        move_box(chiplet.get_box_representation(), x, y) #

            # parent_center = parent.get_2d_center()
            box_destination_pairs = []
            for box in children_boxes:
                if box.chiplet_parent.get_chiplet_type() in fixed_chiplets:
                    continue
                curr_conn = box.chiplet_parent.connections
                coordinates = box.get_2d_center()
                connection_coords = []
                for conn in curr_conn:
                    conn_type = conn.split(".")[-1].split("#")[0]
                    # conn_type = ''.join([i for i in conn_type if not i.isdigit()])
                    # conn_type = conn_type.split("#")[0]
                    # print("Connection type:", conn_type)
                    if conn_type in fixed_chiplets:
                        for fixed_box in boxes:
                            if fixed_box.name == conn:
                                connection_coords.append(fixed_box.get_2d_center())
                avg_x = 0
                avg_y = 0
                for coord in connection_coords:
                    avg_x += coord[0]
                    avg_y += coord[1]
                if len(connection_coords) == 0:
                    continue
                else:
                    avg_x = avg_x / len(connection_coords)
                    avg_y = avg_y / len(connection_coords)
                box_destination_pairs.append((box,(avg_x,avg_y)))

            # f = open("box_movement_log.txt", "a")
            i = 0
            old_boxes = box_destination_pairs.copy()
            N = 1010
            while (True):
                i += 1
                if i > N:
                    break
                if i % 10 == 0:
                    # TODO: Fix this low priority
                    same = True
                    for j in range(len(box_destination_pairs)):
                        new_box = box_destination_pairs[j]
                        old_box = old_boxes[j]
                        def is_equal(box1, box2):
                            bound = min_dist
                            return abs(box1[0] - box2[0]) < bound and abs(box1[1] - box2[1]) < bound

                        if not is_equal(new_box[1], old_box[1]):
                            same = False
                            break
                    if not same:
                        break
                old_boxes = box_destination_pairs.copy()

                for box, coordinates in box_destination_pairs:
                    curr_x, curr_y = box.get_2d_center()
                    dist_x = curr_x - coordinates[0]
                    dist_y = curr_y - coordinates[1]
                    multiplier_x = 1
                    multiplier_y = 1
                    if abs(dist_x) > abs(dist_y):
                        # multiplier_x = 1
                        multiplier_y = abs(dist_y) / abs(dist_x)
                    elif abs(dist_x) < abs(dist_y):
                        multiplier_x = abs(dist_x) / abs(dist_y)
                    #     multiplier_y = 1
                    # else:   
                    #     multiplier_x = 1
                    #     multiplier_y = 1

                    delta_x = -min_dist*multiplier_x if dist_x > 0 else min_dist*multiplier_x
                    delta_y = -min_dist*multiplier_y if dist_y > 0 else min_dist*multiplier_y
                    if abs(dist_x) < min_dist:
                        delta_x = 0
                    if abs(dist_y) < min_dist:
                        delta_y = 0
                    
                    # line = "Moving box " + box.name + " from (" + str(curr_x) + "," + str(curr_y) + ") to (" + str(coordinates[0]) + "," + str(coordinates[1]) + " by dist_x of " + str(dist_x) + "and dist_y of " + str(dist_y) + ") with deltas (" + str(delta_x) + "," + str(delta_y) + ")\n"
                    # f.write(line)
                    # f.close()

                    overlap_count = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    move_box(box,0,delta_y)
                    overlap_count_new = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    if overlap_count_new > overlap_count:
                        move_box(box,0,-delta_y)
                    
                    # f.write("overlap_count of " + str(box.name) + " is " + str(overlap_count) + "\n")
                    # f.write("overlap_count_new of " + str(box.name) + " after y-movement and before x-movement is " + str(overlap_count_new) + "\n")
                    move_box(box,delta_x,0)
                    overlap_count_new = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    if overlap_count_new > overlap_count:
                        move_box(box,-delta_x,0)
                    # f.write("overlap_count_new of " + str(box.name) + " after y-movement and after x-movement is " + str(overlap_count_new) + "\n")

            # f.close()
            if(parent.chiplet_parent.get_fake() == True):
                fakes = [c for c in children_boxes if c.chiplet_parent.get_fake() == True]
                if(len(fakes) == 0):
                    min_x = min([c.start_x for c in children_boxes])
                    max_x = max([c.end_x for c in children_boxes])
                    min_y = min([c.start_y for c in children_boxes])
                    max_y = max([c.end_y for c in children_boxes])
                    # parent.start_x = min_x
                    # parent.start_x -= min_dist * INFLATION
                    # parent.start_y = min_y
                    # parent.start_y -= min_dist * INFLATION
                    parent.width = max_x - min_x
                    parent.length = max_y - min_y
                    parent.width += 2 * min_dist * INFLATION
                    parent.length += 2 * min_dist * INFLATION
                    # for cbox in children_boxes:
                        # print("Child box:", cbox.name, "Width:", cbox.width, "Length:", cbox.length, "Start X:", cbox.start_x, "Start Y:", cbox.start_y, "End X:", cbox.end_x, "End Y:", cbox.end_y)
                elif(len(fakes) == len(children_boxes)):
                    # Assuming all fakes are of same type.
                    c  = fakes[0]
                    parent.width = num_cols * c.width 
                    parent.length = num_rows * c.length
                    parent.width += 2 * min_dist * INFLATION
                    parent.length += 2 * min_dist * INFLATION
                else:
                    # TODO : Handle this case
                    print("#TODO : Handle this case")
                
                parent.chiplet_parent.set_core_area(parent.width * parent.length)
                parent.chiplet_parent.set_aspect_ratio(parent.width / parent.length)
                fake_chiplet_size_dict[parent.chiplet_parent.get_chiplet_type()] = (parent.chiplet_parent.get_core_area(), parent.chiplet_parent.get_aspect_ratio())
    # dedeepyo : 28-Jan-2025 #

    def determine_placements_recursive(boxes,parent,chiplet_tree, min_dist = 0.0):
        # parent argument is a Box() class argument that references the original Chiplet() class.
        # if chiplet_tree is empty, return
        if len(chiplet_tree) == 0:
            return

        # dedeepyo : 18-Nov-2024 : This is the recursive function that will determine the placements of the chiplets.
        # We will start with the root chiplet and then recursively determine the placements of the child chiplets.
        # We will use a grid based approach to determine the placements of the chiplets.
        # The grid will be projected onto the parent chiplet.
        # The grid will have a side length of the largest chiplet in the grid.
        # The grid will be centered on the center of the parent chiplet.
        # The grid will have a minimum distance between chiplets based on the assembly process.
        # We will also handle overlaps by moving the chiplets towards the center of mass of their connections.
        # We will also handle fixed chiplets by not moving them at all.
        # We assume the first (or root) chiplet in the XML chiplet tree is not a fake chiplet.
        # We assume the definition of any referenced xml tag (eg. interposer, GPU, HBM, etc.) is present within the definition of the XML chiplet tree which references it.
        # We assume the XML chiplet tree is a tree and not a graph. This means there are no cycles in the XML chiplet tree.
        # We assume the XML chiplet tree is a valid tree. This means there is only one root chiplet and all other chiplets have exactly one parent.
        # We assume the XML chiplet tree is a valid tree. This means there are no disconnected components in the XML chiplet tree.
        # We assume the XML chiplet tree is a valid tree. This means there are no two chiplets in the chiplet XML tree with the exact same parameters. 
        # If there are duplicate definitions for the same chiplet, they must differ in atleast one parameter.
        # We assume "set" of chiplets has an area.
        # We assume the first chiplet at the base of all the chiplets is not a "set".
        # We assume the fake chiplet has an empty stackup string.
        # dedeepyo : 18-Nov-2024

        # this is only the case for the root chiplet (interposer)
        if not parent:
            # print("Parse start")
            # we are starting. Assume coordinates are 0,0
            # just assign the first chiplet to the center
            # this is interposer or PCB so we don't need to get fancy at all.
            grid = [[chiplet_tree[0]]]
            x_coord = 0
            y_coord = 0
            z_coord = 0
            # we need to make a box
            # we dont know exact material. Do a rough guess based on stackup.
            stackup = chiplet_tree[0].get_stackup()
            # stackup example:
            #         stackup="1:5nm_active,2:5nm_advanced_metal,2:5nm_intermediate_metal,2:5nm_global_metal"
            # actually just assume Si.
            material = "Si"
            power = chiplet_tree[0].get_power()
            area = chiplet_tree[0].get_core_area()
            aspect_ratio = chiplet_tree[0].get_aspect_ratio()
            height = chiplet_tree[0].get_height()
            width = math.sqrt(area*aspect_ratio)
            length = area/width
            box = Box(x_coord,y_coord,z_coord,width,length,height,power,stackup,0,chiplet_tree[0].get_name())
            box.assign_chiplet_parent(chiplet_tree[0])
            boxes.append(box)
            determine_placements_recursive(boxes,box,chiplet_tree[0].get_child_chiplets(), box.chiplet_parent.assembly_process.get_die_separation())
        else:
            grid, fixed_chiplets = generate_placements_from_floorplan(parent.chiplet_parent.floorplan,parent.chiplet_parent.floorplan_dict,chiplet_tree)
            parent_coords = parent.get_2d_coords()
            # now, we need to determine the grid based on the parent chiplet
            # the grid is projected onto the parent chiplet
            parent_width = parent.width
            parent_length = parent.length

            # how many rows/columns in grid?
            num_rows = len(grid)
            # num_cols = num_rows
            num_cols = len(grid[0])

            # the grid coordinate box size will be based on the largest chiplet dimensions in the grid
            # we need to find the largest width and largest length separately. The larger one of the two will define side length
            largest_width = 0
            largest_length = 0
            for i in range(num_rows):
                for j in range(num_cols):
                    if grid[i][j] is not None:
                        chiplet = grid[i][j]
                        chiplet_area = chiplet.get_core_area()
                        chiplet_aspect_ratio = chiplet.get_aspect_ratio()
                        chiplet_width = math.sqrt(chiplet_area * chiplet_aspect_ratio)
                        chiplet_length = chiplet_area/chiplet_width
                        if chiplet_width > largest_width:
                            largest_width = chiplet_width
                        if chiplet_length > largest_length:
                            largest_length = chiplet_length

            # now, we need to determine the side length of the grid box
            # we will use the larger of the two
            side_length = largest_length
            # side_length += min_dist * (1 + INFLATION) #
            side_length += min_dist #
            # dedeepyo : 29-Jan-2025 : Sizing length and width of grid separately.
            side_width = largest_width
            side_width += min_dist #
            # side_width += min_dist * (1 + INFLATION)
            # dedeepyo : 29-Jan-2025 #
            # print("Side length:",side_length)
            # now, we need to determine the x and y coordinates of the grid box
            # the grid box will be centered on the parent chiplet
            # the grid box will have a side length of side_length
            grid_length = side_length*num_rows
            grid_width = side_width*num_cols
            # the grid will be centered on the center of the parent chiplet
            grid_x = parent_coords[0] + parent_width/2 - grid_width/2
            grid_y = parent_coords[1] + parent_length/2 - grid_length/2
            # now, we need to assign coordinates to each chiplet in the grid
            # we assign them to the center of the grid subbox
            # print("Parent:",parent.name)
            # print("Grid:",grid)
            children_boxes = []         
            for i in range(num_rows):
                for j in range(num_cols):
                    if grid[i][j] is not None:
                        chiplet = grid[i][j]
                        x_coord = grid_x + j*side_width + side_width/2
                        y_coord = grid_y + i*side_length + side_length/2
                        # parent z + parent height
                        z_coord = parent.start_z + parent.height

                        # we dont know exact material. Do a rough guess based on stackup.
                        stackup = chiplet.get_stackup()
                        # stackup example:
                        #         stackup="1:5nm_active,2:5nm_advanced_metal,2:5nm_intermediate_metal,2:5nm_global_metal"
                        # actually just assume Si.
                        material = "Si"
                        power = chiplet.get_power()
                        aspect_ratio = chiplet.get_aspect_ratio()
                        height = chiplet.get_height()
                        area = chiplet.get_core_area()
                        width = math.sqrt(area*aspect_ratio)
                        length = area/width
                        
                        # we need to adjust the box so that it is centered on the grid point.
                        x_coord = x_coord - width/2
                        y_coord = y_coord - length/2                        
                        box = Box(x_coord,y_coord,z_coord,width,length,height,power,stackup,0,chiplet.get_name())
                        box.assign_chiplet_parent(chiplet)
                        chiplet.set_box_representation(box)

                        # dedeepyo : 18-Nov-2024 : Implementing checker and side calculation for fake chiplet.
                        # If the chiplet is a fake chiplet, we need to remove it from the list of boxes.
                        # We update the min_dist for the current chiplet and pass it for its children sitting on top of it unless the current one is a fake chiplet.
                        min_dist_for_children = 0.0
                        if(chiplet.get_fake() == True):
                            # print("Fake chiplet found: ",chiplet.get_name())
                            min_dist_for_children = parent.chiplet_parent.assembly_process.get_die_separation()
                        else:
                            min_dist_for_children = chiplet.assembly_process.get_die_separation()
                            boxes.append(box)
                        # dedeepyo : 18-Nov-2024
                        # print("Created box: ",box.name)
                        children_boxes.append(box)
                        determine_placements_recursive(boxes,box,chiplet.get_child_chiplets(), min_dist_for_children)

            # dedeepyo : 17-Dec-2024 : Implementing copy of placement recursion.
            # determined_placements = {}
            # if(determined_placements.get(grid[i][j].get_chiplet_type()) == None):
            #     determined_placements[grid[i][j].get_chiplet_type()] = box
            # else:
            #     # print("Copying placements for: ",box.name)
            #     copy_placements_recursive(boxes,box,chiplet.get_child_chiplets(), min_dist_for_children, determined_placements[grid[i][j].get_chiplet_type()])
                # print("Copied placements for: ",box.name)
            # dedeepyo : 17-Dec-2024
                    
            def move_box(box, x, y):
                box.start_x += x #
                box.start_y += y #
                # box.end_x += x
                # box.end_y += y
                for chiplet in box.chiplet_parent.get_child_chiplets(): #
                    if chiplet.get_box_representation(): #
                        move_box(chiplet.get_box_representation(), x, y) #

            # dedeepyo : 17-Dec-2024 : Implementing copying placements.            
            # if(reference_box != None):
            #     del_x = reference_box.start_x - parent.start_x
            #     del_y = reference_box.start_y - parent.start_y
            #     move_box(parent, del_x, del_y)
            #     return
            # dedeepyo : 17-Dec-2024
            
            # shrinking step
            # print("FIX:",fixed_chiplets)
            parent_center = parent.get_2d_center()
            box_destination_pairs = []
            for box in children_boxes:
                # print(box.name,":",box.chiplet_parent.connections)
                if box.chiplet_parent.get_chiplet_type() in fixed_chiplets:
                    continue
                curr_conn = box.chiplet_parent.connections
                coordinates = box.get_2d_center()
                # This list is a list of coordinates of boxes that this current box should move towards.
                connection_coords = []
                for conn in curr_conn:
                    conn_type = conn.split(".")[-1]
                    # conn_type = ''.join([i for i in conn_type if not i.isdigit()])
                    conn_type = conn_type.split("#")[0]
                    if conn_type in fixed_chiplets:
                        for fixed_box in boxes:
                            if fixed_box.name == conn:
                                connection_coords.append(fixed_box.get_2d_center())
                # average out to get the "center of mass"
                # print("Box:",box.name,"Connections:",connection_coords)
                avg_x = 0
                avg_y = 0
                for coord in connection_coords:
                    avg_x += coord[0]
                    avg_y += coord[1]
                if len(connection_coords) == 0:
                    # dedeepyo : 26-Jan-2025 : Implementing movement of fake chiplets towards each other to reduce space wastage till they abut (distance between neighbours is more than minimum die separation).
                    # Spreading out real chiplets away from each other till they do not overlap.
                    # Before computing the dimensions of the parent box of the parent chiplet, we need to move the current chiplets, which may be fake, closer to each other.
                    # Assuming either current chiplets are not fake chiplets or all are fake chiplets and none of the grid[i][j] are None or fixed. Otherwise, we have area wastage.
                    # if(box.chiplet_parent.get_fake() == True):
                    #     avg_x = parent_center[0]
                    #     avg_y = parent_center[1]
                    # dedeepyo : 26-Jan-2025 #
                    # else:
                    #     continue
                    continue
                else:
                    avg_x = avg_x / len(connection_coords)
                    avg_y = avg_y / len(connection_coords)
                box_destination_pairs.append((box,(avg_x,avg_y)))

            # f = open("box_placement_movement_log.txt", "a")
            # now, we need to greedily move the box towards the center of mass while respecting overlaps
            i = 0
            old_boxes = box_destination_pairs.copy()
            N = 1010
            # dedeepyo : 27-Jan-2025 : Assigning a higher number of steps for fake chiplets.
            # Assuming either all chiplets in the current set are fake chiplets or none of them are fake chiplets. Else, wastage of iterations.
            # if(children_boxes[0].chiplet_parent.get_fake() == True):
            #     N = 1500
            # dedeepyo : 27-Jan-2025 #
            while (True):
                i += 1
                # number of steps
                if i > N:
                    break
                # THIS EARLY EXIT STUFF DOES NOT WORK
                if i % 10 == 0:
                    # TODO: Fix this low priority
                    same = True
                    for j in range(len(box_destination_pairs)):
                        new_box = box_destination_pairs[j]
                        old_box = old_boxes[j]
                        def is_equal(box1, box2):
                            bound = min_dist
                            return abs(box1[0] - box2[0]) < bound and abs(box1[1] - box2[1]) < bound

                        if not is_equal(new_box[1], old_box[1]):
                            same = False
                            break
                    if not same:
                        # print("early exit")
                        break
                old_boxes = box_destination_pairs.copy()

                for box, coordinates in box_destination_pairs:
                    curr_x, curr_y = box.get_2d_center()
                    dist_x = curr_x - coordinates[0]
                    dist_y = curr_y - coordinates[1]
                    # attempt to greedily reduce dist x and dist y by the min dist
                    # we only want to move the box min_dist at a time
                    # multiplier = 1

                    multiplier_x = 1
                    multiplier_y = 1

                    # dedeepyo : 18-Feb-25 : Implementing a more efficient way to move the boxes, to ensure dist_x / dist_y remains constant.
                    if abs(dist_x) > abs(dist_y):
                    #     multiplier_x = 1
                        multiplier_y = abs(dist_y) / abs(dist_x)
                    elif abs(dist_x) < abs(dist_y):
                        multiplier_x = abs(dist_x) / abs(dist_y)
                    #     multiplier_y = 1
                    # else:   
                    #     multiplier_x = 1
                    #     multiplier_y = 1
                    # dedeepyo : 18-Feb-25 #

                    delta_x = -min_dist*multiplier_x if dist_x > 0 else min_dist*multiplier_x
                    delta_y = -min_dist*multiplier_y if dist_y > 0 else min_dist*multiplier_y
                    if abs(dist_x) < min_dist:
                        delta_x = 0
                    if abs(dist_y) < min_dist:
                        delta_y = 0
                    
                    # dedeepyo : 18-Dec-2024 : Implementing overlap check with only current box.
                    # overlap_count = check_all_overlaps_3d(boxes, box, min_dist*INFLATION)
                    # move_box(box,0,delta_y)
                    # overlap_count_new = check_all_overlaps_3d(boxes, box, min_dist*INFLATION)
                    # if overlap_count_new > overlap_count:
                    #     move_box(box,0,-delta_y)
                    # move_box(box,delta_x,0)
                    # overlap_count_new = check_all_overlaps_3d(boxes, box, min_dist*INFLATION)
                    # if overlap_count_new > overlap_count:
                    #     move_box(box,-delta_x,0)
                    # dedeepyo : 27-Jan-2025 #

                    overlaps = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    move_box(box,0,delta_y)
                    overlaps_new = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    if overlaps_new > overlaps:
                        move_box(box,0,-delta_y)

                    # f.write("overlap_count of " + str(box.name) + " is " + str(overlaps) + "\n")
                    # f.write("overlap_count_new of " + str(box.name) + " after y-movement and before x-movement is " + str(overlaps_new) + "\n")
                    move_box(box,delta_x,0)
                    overlaps_new = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    if overlaps_new > overlaps:
                        move_box(box,-delta_x,0)

                    # f.write("overlap_count_new of " + str(box.name) + " after y-movement and before x-movement is " + str(overlaps_new) + "\n")
                    
            # dedeepyo : 10-Oct-25 : Implementing dummy Si. #TODO: Comment for 2.5D or anything other than 3D. Uncommen`t for 3D.`
            if(system_type == "3D_1GPU" or system_type == "3D_waferscale" or system_type == "3D_1GPU_top"):
                dummy_Si_height = 0.63 # in mm # 0.62 for 8-high, 0.63 for 16-high.
                min_x = min([c.start_x for c in children_boxes]) - min_dist
                max_x = max([c.end_x for c in children_boxes]) + min_dist
                min_y = min([c.start_y for c in children_boxes]) - min_dist
                max_y = max([c.end_y for c in children_boxes]) + min_dist
                if(parent.start_x < min_x):
                    if(parent.start_y < min_y):
                        if(parent.end_x > max_x):
                            if(parent.end_y > max_y):
                                box = Box(parent.start_x, parent.start_y, parent.end_z, min_x - parent.start_x, parent.length, dummy_Si_height, 0.0, "1:dummySi_HBM", 0, parent.name + ".Dummy_Si_above_1")
                                chiplet = Chiplet(name = parent.name + ".Dummy_Si_above_1", core_area = box.width * box.length, aspect_ratio = box.width / box.length, assembly_process = parent.chiplet_parent.get_assembly_process(), stackup = "1:dummySi_HBM", height = dummy_Si_height)
                                r = parent.chiplet_parent.add_child_chiplet(chiplet)
                                boxes.append(box)
                                box.assign_chiplet_parent(chiplet)
                                chiplet.set_box_representation(box)
                                
                                box = Box(max_x, parent.start_y, parent.end_z, parent.end_x - max_x, parent.length, dummy_Si_height, 0.0, "1:dummySi_HBM", 0, parent.name + ".Dummy_Si_above_2")
                                chiplet = Chiplet(name = parent.name + ".Dummy_Si_above_2", core_area = box.width * box.length, aspect_ratio = box.width / box.length, assembly_process = parent.chiplet_parent.get_assembly_process(), stackup = "1:dummySi_HBM", height = dummy_Si_height)
                                r = parent.chiplet_parent.add_child_chiplet(chiplet)
                                boxes.append(box)
                                box.assign_chiplet_parent(chiplet)
                                chiplet.set_box_representation(box)
                                
                                box = Box(min_x, parent.start_y, parent.end_z, max_x - min_x, min_y - parent.start_y, dummy_Si_height, 0.0, "1:dummySi_HBM", 0, parent.name + ".Dummy_Si_above_3")
                                chiplet = Chiplet(name = parent.name + ".Dummy_Si_above_3", core_area = box.width * box.length, aspect_ratio = box.width / box.length, assembly_process = parent.chiplet_parent.get_assembly_process(), stackup = "1:dummySi_HBM", height = dummy_Si_height)
                                r = parent.chiplet_parent.add_child_chiplet(chiplet)
                                boxes.append(box)
                                box.assign_chiplet_parent(chiplet)
                                chiplet.set_box_representation(box)
                                
                                box = Box(min_x, max_y, parent.end_z, max_x - min_x, parent.end_y - max_y, dummy_Si_height, 0.0, "1:dummySi_HBM", 0, parent.name + ".Dummy_Si_above_4")
                                chiplet = Chiplet(name = parent.name + ".Dummy_Si_above_4", core_area = box.width * box.length, aspect_ratio = box.width / box.length, assembly_process = parent.chiplet_parent.get_assembly_process(), stackup = "1:dummySi_HBM", height = dummy_Si_height)
                                r = parent.chiplet_parent.add_child_chiplet(chiplet)
                                boxes.append(box)
                                box.assign_chiplet_parent(chiplet)
                                chiplet.set_box_representation(box)
                            #TODO: Other cases not handled. 
            # dedeepyo : 10-Oct-25 #

            # f.close()
            # dedeepyo : 26-Jan-2025 : Implementing set sizing based on child chiplet dimensions.
            # Assuming all the minimum possible dimensions of the present set of chiplets are already known / calculated.
            # if(parent.chiplet_parent.get_fake() == True):
            #     min_x = min([c.start_x for c in children_boxes])
            #     max_x = max([c.end_x for c in children_boxes])
            #     min_y = min([c.start_y for c in children_boxes])
            #     max_y = max([c.end_y for c in children_boxes])
            #     parent.start_x = min_x
            #     parent.start_y = min_y
            #     parent.width = max_x - min_x
            #     parent.length = max_y - min_y
            #     parent.chiplet_parent.set_core_area(parent.width * parent.length)
            #     parent.chiplet_parent.set_aspect_ratio(parent.width / parent.length)
            # dedeepyo : 26-Jan-2025

    # dedeepyo : 28-Jan-2025 : Assigning recursive fake chiplet sizing.
    fake_chiplet_size_dict = {}
    start_time = time.time()
    print("Starting sizing at ", start_time)
    boxes_unique = []
    determine_sizing_recursive(boxes_unique, None, chiplet_tree, 0.0, fake_chiplet_size_dict)
    end_time = time.time()
    print("Sizing done at ", end_time)
    print("Time taken: ", end_time - start_time)
    # time.sleep(5)
    # dedeepyo : 29-Jan-2025
    # print(fake_chiplet_size_dict)
    # fake_chiplet_size_dict = {
    #     'set_primary' : (1420.092338, 0.4578712122),
    #     'set_secondary' : (5680.369353, 0.4578712122)
    # }
    # for box in boxes_unique:
    #     print(box.name + " " + str(box.start_z) + " " + str(box.end_z) + " " + str(box.height) + " " + str(box.width) + " " + str(box.length) + " " + str(box.start_x) + " " + str(box.start_y))
    # return #TODO: Comment out later.
    # dedeepyo : 29-Jan-2025 : Sizing fake chiplets.
    recursively_copy_chiplet_sizes(fake_chiplet_size_dict, chiplet_tree[0])
    # dedeepyo : 29-Jan-2025 #

    start_time = time.time()
    print("Starting placement at ", start_time)
    boxes = []
    determine_placements_recursive(boxes, None, chiplet_tree, 0.0)
    end_time = time.time()
    print("Placement done at ", end_time)
    print("Time taken: ", end_time - start_time)

    # dedeepyo : 18-Nov-2024 : Implementing checker for fake chiplet.
    # If the chiplet is a fake chiplet, we need to remove it from the list of boxes.
    # We create and delete a box for the chiplet that is actually a fake chiplet.
    # temp_box_names = [b.name for b in boxes if b.chiplet_parent.get_fake() == True]
    # for box_name in temp_box_names:
    #     for box in boxes:
    #         if box.name == box_name:
    #             if(box.chiplet_parent.get_fake() == True):
    #                 boxes.remove(box)
                    # print("Removed fake chiplet box: ", box.name + " for chiplet: " + box.chiplet_parent.get_name())
    # for box in boxes:
    #     print(box.name + " " + str(box.start_z) + " " + str(box.end_z) + " " + str(box.height) + " " + str(box.width) + " " + str(box.length) + " " + str(box.start_x) + " " + str(box.start_y) + " " + str(box.end_x) + " " + str(box.end_y))
    # dedeepyo : 18-Nov-2024

    # dedeepyo : 29-Jan-2025 : Testing dimensions.
    # print(min([c.start_x for c in boxes if c.name != "interposer" or c.name != "Power_Source"]),max([c.end_x for c in boxes if c.name != "interposer" or c.name != "Power_Source"]))
    # print(min([c.start_y for c in boxes if c.name != "interposer" or c.name != "Power_Source"]),max([c.end_y for c in boxes if c.name != "interposer" or c.name != "Power_Source"]))
    # dedeepyo : 29-Jan-2025 #

    # now, draw everything
    limits = determine_draw_lim(boxes)
    draw_fig(boxes,out_dir,"post",limits)
    draw_fig_3D_zoom(boxes,out_dir,"post",limits)
    print("Placement finished, plots generated")
    # print(str(boxes))
    # return #TODO: Comment out later.

    # for box in boxes:
    #     if(box.chiplet_parent.get_chiplet_type() == "GPU" or box.chiplet_parent.get_chiplet_type() == "HBM_l1"):
    #         print("Created : ", box.name + " at (" + str(box.start_x) + "," + str(box.start_y) + "," + str(box.start_z) + ") with width " + str(box.width) + " and length " + str(box.length) + " and height " + str(box.height))

    # return #TODO: Comment out later.

    layers = parse_Layer_netlist("configs/thermal-configs/layer_definitions.xml")
    heatsink_list = heatsink_definition_list_from_file(heatsink_conf)
    bonding_list = bonding_definition_list_from_file(bonding_conf)
    heatsink_name = heatsink
    bonding_name_type_dict = {"GPU#HBM_l4": "bonding_Cu_pillar", "HBM_l4#GPU": "bonding_Cu_pillar", "GPU#HBM_l12": "bonding_Cu_pillar", "HBM_l12#GPU": "bonding_Cu_pillar", "GPU#HBM_l16": "bonding_Cu_pillar", "HBM_l16#GPU": "bonding_Cu_pillar", "GPU#HBM_l8": "bonding_Cu_pillar", "HBM_l8#GPU": "bonding_Cu_pillar", "GPU#HBM": "bonding_Cu_pillar", "HBM#GPU": "bonding_Cu_pillar", "GPU#interposer": "bonding_Cu_pillar", "interposer#GPU": "bonding_Cu_pillar", "interposer#HBM": "bonding_Cu_pillar", "HBM#interposer": "bonding_Cu_pillar", "interposer#PCB": "bonding_bga_ball", "PCB#interposer": "bonding_bga_ball", "interposer#substrate": "bonding_bga_ball", "substrate#interposer": "bonding_bga_ball", "substrate#Power_Source": "bonding_bga_ball", "Power_Source#substrate": "bonding_bga_ball", "interposer#Power_Source": "bonding_bga_ball", "Power_Source#interposer": "bonding_bga_ball", "GPU#substrate": "bonding_Cu_pillar", "substrate#GPU": "bonding_Cu_pillar", "substrate#HBM": "bonding_Cu_pillar", "HBM#substrate": "bonding_Cu_pillar", "GPU#PCB": "bonding_Cu_pillar", "PCB#GPU": "bonding_Cu_pillar", "PCB#HBM": "bonding_Cu_pillar", "HBM#PCB": "bonding_Cu_pillar", "PCB#Power_Source": "bonding_bga_ball", "Power_Source#PCB": "bonding_bga_ball"}
    # bonding_name = bonding_name_type_dict
    recursively_remove_fake_chiplets(chiplet_tree[0])
    # recursively_find_fakes(chiplet_tree[0])
    is_repeat = is_repeat # False
    min_TIM_height = 0.1 # 0.02 # 0.1 # 0.01, 0.02, 0.05, 0.1
    suffix = ""
    
    # print(str(boxes))
    # print("After creating bonding, TIM and heatsink:")
    # for box in boxes:
    #     print(box.name + " " + str(box.start_z) + " " + str(box.end_z) + " " + str(box.height) + " " + str(box.width) + " " + str(box.length) + " " + str(box.start_x) + " " + str(box.start_y) + " " + str(box.end_x) + " " + str(box.end_y))

    # dedeepyo : 01-Dec-25 : Implementing GPU on top.
    # Box(x_coord,y_coord,z_coord,width,length,height,power,"1:5nm_GPU_active_3D,20:5nm_GPU_metal",0,"Power_Source.substrate.HBM.GPU")
    # dedeepyo : 03-Dec-25 : Implementing GPU on top.
    if(system_type == "3D_1GPU_top"):
        # <chip name="GPU"
            # bb_area="$core_area"
            # bb_cost=""
            # bb_quality=""
            # bb_power=""
            # aspect_ratio="0.787"
            # x_location=""
            # y_location=""
        
            # core_area="0.0"
            # fraction_memory="0.0"
            # fraction_logic="1.0"
            # fraction_analog="0.0"
            # gate_flop_ratio="1.0"
            # reticle_share="1.0"
            # buried="False"
            # assembly_process="silicon_individual_bonding"
            # test_process="KGD_free_test"
            # stackup="1:5nm_GPU_active_3D,20:5nm_GPU_metal"
            # wafer_process="process_1"
            # v_rail="5,1.8"
            # reg_eff="1.0,0.9"
            # reg_type="none,side"
            # core_voltage="1.0"
            # power="$core_power"
            # quantity="1000000"
            # fake="False"

            # floorplan=""
            # floorplan_dict=""></chip>
        deepest_node = find_deepest_node(chiplet_tree)
        deepest_node_box = deepest_node.get_box_representation()
        z_coord = deepest_node_box.start_z + deepest_node_box.height

        GPU_stackup = "1:5nm_GPU_active_3D,20:5nm_GPU_metal"
        height = 0
        stackup_list = GPU_stackup.split(",")
        for stackup in stackup_list:
            layer_num, layer_name = stackup.split(":")
            for layer in layers:
                if layer.get_name() == layer_name:
                    height += (int(layer_num) * layer.get_thickness())

        height = round(height, 3) #CHECK: 3 decimal places. 
        
        GPU_chiplet = Chiplet(name=deepest_node.get_name() + ".GPU", core_area=826.2, aspect_ratio= 0.787, fraction_memory=0.0, fraction_logic=1.0, fraction_analog=0.0, assembly_process="silicon_individual_bonding", stackup=stackup, power=270.0, floorplan="", floorplan_dict="", fake=False, height=height)
        width = math.sqrt(GPU_chiplet.get_core_area() * GPU_chiplet.get_aspect_ratio())
        length = GPU_chiplet.get_core_area() / width
        GPU_box = Box(0.0,0.0,z_coord,width,length,GPU_chiplet.get_height(),GPU_chiplet.get_power(),GPU_chiplet.get_stackup(),0,GPU_chiplet.get_name())
        GPU_box.assign_chiplet_parent(GPU_chiplet)
        GPU_chiplet.set_box_representation(GPU_box)
        boxes.append(GPU_box) #TODO

        deepest_node.add_child_chiplet(GPU_chiplet)
    # dedeepyo : 01-Dec-25 #

    bonding_box_list = create_all_bonding(box_list = boxes, name_type_dict = bonding_name_type_dict, bonding_list = bonding_list) #        
    TIM_boxes = create_TIM_to_heatsink(box_list = boxes, material = "TIM0p5", min_TIM_height = min_TIM_height, system_type = system_type)
    
    # dedeepyo : 19-Feb-2026 : Implementing area scale factor.
    # area_scale_factor = 1.761 #TODO: Check each time for the area scale factor. Comment out in general.
    # area_scale_factor *= 2 #TODO: Comment out in general.
    area_scale_factor = 1 #TODO: Uncomment in general.
    # dedeepyo : 19-Feb-2026
    
    heatsink_obj = create_heat_sink(box_list = boxes, heatsink_list = heatsink_list, heatsink_name = heatsink_name, min_TIM_height = min_TIM_height, scale_factor_x = 0, scale_factor_y = 0, area_scale_factor = area_scale_factor)
    # create_power_source_backside(boxes) # TODO: Uncomment in general. dedeepyo : 08-Mar-26
    power_dict = initialize_power_dict_values(boxes)

    # print("After creating bonding, TIM and heatsink:")
    # for box in boxes:
    #     print(box.name + " " + str(box.start_z) + " " + str(box.end_z) + " " + str(box.height) + " " + str(box.width) + " " + str(box.length) + " " + str(box.start_x) + " " + str(box.start_y) + " " + str(box.end_x) + " " + str(box.end_y))
    
    # print(str(boxes))    
    # return #TODO: Comment out later.

    # dedeepyo : 21-Jun-25 : Implmenting multiple heatsinks. 
    # heatsink_list till now stored definitions of heatsinks. From now on, it will store the actual heatsink objects used with coordinates.
    multiple_heatsinks = False # True if multiple heatsinks are used, False if only one heatsink is used.
    if not multiple_heatsinks:
        heatsink_list = []
    else:
        heatsink_list_new, power_dict_new = create_multiple_heat_sinks(box_list = boxes, heatsink_list = heatsink_list, heatsink_name = heatsink_name, min_TIM_height = min_TIM_height, power_dict = power_dict) # , scale_factor_x = 0, scale_factor_y = 0, area_scale_factor = 1)
        heatsink_list = heatsink_list_new
        power_dict = power_dict_new
    # dedeepyo : 21-Jun-25

    # dedeepyo : 01-Dec-25 #
    # Below is only Anemoi, above is tool-agnostic.
    # dedeepyo : 01-Dec-25 #
    data = {
                'boxes' : boxes,
                'heatsink_list' : heatsink_list,
                'heatsink_name' : heatsink_name,
                'bonding_box_list' : bonding_box_list,
                'heatsink_obj' : heatsink_obj,
                'TIM_boxes' : TIM_boxes,
                'suffix' : suffix,
                'is_repeat' : is_repeat,
                'min_TIM_height' : min_TIM_height,
                'layers' : layers
    }
    with open('data_dray1_051425.pkl', 'wb') as f:
        pickle.dump(data, f)

    # return
    # GPU_peak_temperature_list = []
    # HBM_peak_temperature_list = []
    GPU_time_frac_idle_list = []
    GPU_min_peak_temperature_list = []
    HBM_min_peak_temperature_list = []
    
    # box_temperatures = {box.name : [] for box in boxes}
    # print(box_temperatures)
    # results = simulator.simulate(boxes, bonding_box_list, TIM_boxes, heatsink_obj = heatsink_obj, heatsink_list = heatsink_list, heatsink_name = heatsink_name, bonding_list = bonding_list, bonding_name_type_dict = bonding_name_type_dict, is_repeat = is_repeat,  min_TIM_height = min_TIM_height, layers = layers) #
    anemoi_parameter_ID = {} # Uncomment
    # anemoi_parameter_ID = {'interposer_power': 1949, 'substrate_power': 1950, 'PCB_power': 1951, 'GPU_power': 1946, 'Power_Source_power': 1952, 'HBM_power': 1947, 'GPU_HTC_power': 1953, 'HBM_l_power': 1948, 'HBM_HTC_power': 1954}
    # print("Power dict initialized: ", power_dict)

    if(is_repeat == False):
        simulation_start_time = time.time()
        print("Starting simulation at ", simulation_start_time)
        
        is_repeat = is_repeat # False # False # True if the simulation is repeated with different powers, False if only one simulation is run.
        results = simulator.simulate(boxes, bonding_box_list, TIM_boxes, heatsink_obj = heatsink_obj, heatsink_list = heatsink_list, heatsink_name = heatsink_name, bonding_list = bonding_list, bonding_name_type_dict = bonding_name_type_dict, is_repeat = is_repeat,  min_TIM_height = min_TIM_height, power_dict = power_dict, anemoi_parameter_ID = anemoi_parameter_ID, layers = layers) #
        
        simulation_end_time = time.time()
        print("Simulation finished at ", simulation_end_time)
        print("Time taken for simulation: ", simulation_end_time - simulation_start_time)
        return #TODO: Comment out later

    temperature_dict = defaultdict(lambda : defaultdict(list)) # temperature_dict[GPU_power][HBM_power] = [GPU_peak_temperature, HBM_peak_temperature, GPU_min_peak_temperature, HBM_min_peak_temperature]
    
    # GPU_peak_temperature, HBM_peak_temperature, GPU_min_peak_temperature, HBM_min_peak_temperature, anemoi_parameter_ID = results # 87.534, 87.15 # results #TODO: Uncomment.
    # temperature_dict[power_dict["GPU"]][5 * power_dict["HBM"]] = results[0:4] #TODO: Uncomment
    # print(f"GPU_peak_temperature: {GPU_peak_temperature} C, HBM_peak_temperature: {HBM_peak_temperature} C, GPU_min_peak_temperature: {GPU_min_peak_temperature} C, HBM_min_peak_temperature: {HBM_min_peak_temperature} C")
    # return

    if os.path.exists("dray_ECTC1.txt"):
        os.remove("dray_ECTC1.txt")
    if os.path.exists("dray_ECTC2.txt"):
        os.remove("dray_ECTC2.txt") 
    if os.path.exists("dray_ECTC3.txt"):
        os.remove("dray_ECTC3.txt")

    for TIM_cond in tim_cond_list: # [10]: # [5, 10]: tim_cond_list = (5, 10, 50)
        for infill_cond in infill_cond_list: # [19]: # tim_cond_list = (1.6, 19)
            for underfill_cond in underfill_cond_list: # [19]: underfill_cond_list = (1.6, 19)
                materials_update_dict = {
                    "TIM0p5": TIM_cond,
                    "Infill_material": infill_cond,
                    "EpAg": underfill_cond
                }
                results = simulator.simulate(boxes, bonding_box_list, TIM_boxes, materials_update_dict = materials_update_dict, heatsink_obj = heatsink_obj, heatsink_list = heatsink_list, heatsink_name = heatsink_name, bonding_list = bonding_list, bonding_name_type_dict = bonding_name_type_dict, is_repeat = is_repeat,  min_TIM_height = min_TIM_height, power_dict = power_dict, anemoi_parameter_ID = anemoi_parameter_ID, layers = layers)

                f = open("dray_ECTC1.txt", "w")
                factor_per_die = hbm_stack_height + 2
                if(hbm_stack_height == 8):
                    col2_values = [5.0, 5.6, 6.8024] # For 8-high HBM stack
                elif(hbm_stack_height == 16):
                    col2_values = [9.0, 9.4, 10.1218] # For 16-high HBM stack
                else:
                    col2_values = [5.0, 5.6, 6.8024]
                # GPU_power = 50.0 # 380.0 # 200.0 # 270.0
                # for HBM_power in [5.0, 5.6, 6.8024]: # [5.6]: # 
                #     power_dict["HBM"] = 2 * HBM_power / 10 # power in W
                #     power_dict["HBM_l"] = HBM_power / 10 # power in W
                # for HBM_power in [9.0, 9.4, 10.1218]: # [5.6]: # For 16-high HBM stack #TODO: Comment for 8-high HBM stack
                #     power_dict["HBM"] = 2 * HBM_power / 18 # power in W # For 16-high HBM stack #TODO: Comment for 8-high HBM stack
                #     power_dict["HBM_l"] = HBM_power / 18 # power in W # For 16-high HBM stack #TODO: Comment for 8-high HBM stack
                for HBM_power in col2_values: # [5.6]:
                    power_dict["HBM"] = 2 * HBM_power / factor_per_die # power in W
                    power_dict["HBM_l"] = HBM_power / factor_per_die # power in W
                    for GPU_power in [320.0, 270.0, 220.0, 170.0, 120.0, 70.0]: # [320.0, 270.0]:
                        power_dict["GPU"] = GPU_power # power in W
                        # power_dict["Power_Source"] = update_power_source_backside(boxes, power_dict) # power in W
                        results = simulator.simulate(boxes, bonding_box_list, TIM_boxes, heatsink_obj = heatsink_obj, heatsink_list = heatsink_list, heatsink_name = heatsink_name, bonding_list = bonding_list, bonding_name_type_dict = bonding_name_type_dict, is_repeat = is_repeat,  min_TIM_height = min_TIM_height, power_dict = power_dict, anemoi_parameter_ID = anemoi_parameter_ID, layers = layers)
                        temperature_dict[GPU_power][HBM_power] = results[0:6] # results[0:4]
                        anemoi_parameter_ID = results[-1]
                        f.write(f"{GPU_power} {HBM_power} {temperature_dict[GPU_power][HBM_power][0]} {temperature_dict[GPU_power][HBM_power][1]}\n")
                        # f.write(f"temperature_dict[{GPU_power}][{HBM_power}] = {temperature_dict[GPU_power][HBM_power]}\n")

                f.close()

                # f = open("dray_ECTC2.txt", "a")
                f = open("calibration_data.csv", "a") #TODO: Uncomment for calibration data.
                # f = open("calibration_data_largerHeatSpreader.csv", "a") #TODO: Comment out for calibration data.
                # f = open("calibration_data_2xHeatSpreader.csv", "a") #TODO: Comment out for calibration data.
                filename = "dray_ECTC1.txt"
                data = read_data(filename)
                # infill_cond_mark = 1 if infill_cond == 1.6 else infill_cond
                # underfill_cond_mark = 1 if underfill_cond == 1.6 else underfill_cond
                
                # key = f"{system_name}_{hbm_stack_height}_{7}_{TIM_cond}_{infill_cond}_{underfill_cond}"

                # f.write(f"\nif((TIM_cond == {TIM_cond}) and (infill_cond == {infill_cond_mark}) and (underfill_cond == {underfill_cond_mark})):\n") #TODO: Uncomment for non-3D
                # f.write(f"\nif((TIM_cond == {TIM_cond}) and (infill_cond == {infill_cond_mark}) and (underfill_cond == {underfill_cond_mark}) and (dummy_Si == True))):\n") #TODO: Comment for non-3D
                HTC = float(heatsink_obj.get("hc")) / 1000.0 # in kW/(m^2 * K)
                interpolate_and_report(data, col2_values, f, system_name = system_type, HTC = HTC, TIM_conductivity = TIM_cond, infill_conductivity = infill_cond, underfill_conductivity = underfill_cond, HBM_stack_height = hbm_stack_height, dummy_Si = dummy_si)
                f.close()

    # project_root = Path(__file__).resolve().parent
    # source_path = project_root / "dray_ECTC2.txt"
    # destination_path = project_root / "dray_ECTC3.txt"

    # if not source_path.exists():
    #     raise FileNotFoundError(f"Source file not found: {source_path}")

    # convert(source_path, destination_path, hbm_stack_height = hbm_stack_height)
    # print(f"Converted {source_path.name} → {destination_path.name}")
    
    return

    # GPU_peak_temperature_list.append(GPU_peak_temperature)
    # HBM_peak_temperature_list.append(HBM_peak_temperature)
    # GPU_min_peak_temperature_list.append(GPU_min_peak_temperature)
    # HBM_min_peak_temperature_list.append(HBM_min_peak_temperature)
    # print(results)
    # with open(out_dir + '/therm_out.txt', 'w') as f:
       #     f.write('This is a placeholder for the thermal output\n')
    # get_temperatures_from_results(file = "output_techcon_051325_3D.txt")

    # dedeepyo : 19-Jun-2025 : Implementing GPU thermal throttling powers.
    f = open("dray_temperature_dict_2p5D_waferscale.txt", "w")
    GPU_power = 50.0 # 380.0 # 200.0 # 270.0
    while(GPU_power > 20.0):
        GPU_power -= 10.0
        power_dict["GPU"] = GPU_power # power in W
        for HBM_power in [5.0, 5.6, 6.8024]: # [5.6]: # 
            power_dict["HBM"] = 2 * HBM_power / 10 # power in W
            power_dict["HBM_l"] = HBM_power / 10 # power in W
            power_dict["Power_Source"] = update_power_source_backside(boxes, power_dict) # power in W
            results = simulator.simulate(boxes, bonding_box_list, TIM_boxes, heatsink_obj = heatsink_obj, heatsink_list = heatsink_list, heatsink_name = heatsink_name, bonding_list = bonding_list, bonding_name_type_dict = bonding_name_type_dict, is_repeat = is_repeat,  min_TIM_height = min_TIM_height, power_dict = power_dict, anemoi_parameter_ID = anemoi_parameter_ID, layers = layers)
            temperature_dict[GPU_power][HBM_power] = results[0:4]
            anemoi_parameter_ID = results[-1]
            f.write(f"temperature_dict[{GPU_power}][{HBM_power}] = {temperature_dict[GPU_power][HBM_power]}\n")

            # GPU_peak_temperature, HBM_peak_temperature, GPU_min_peak_temperature, HBM_min_peak_temperature, anemoi_parameter_ID = results # 0.00, 0.00 # 
            # GPU_peak_temperature_list.append(GPU_peak_temperature)
            # HBM_peak_temperature_list.append(HBM_peak_temperature)
            # GPU_min_peak_temperature_list.append(GPU_min_peak_temperature)
            # HBM_min_peak_temperature_list.append(HBM_min_peak_temperature)
        
    # print(f"GPU_power_list: {GPU_power_list}")
    # print(f"GPU_peak_temperatures: {GPU_peak_temperature_list}")
    # print(f"HBM_peak_temperatures: {HBM_peak_temperature_list}")
    # print(f"GPU_min_peak_temperatures: {GPU_min_peak_temperature_list}")
    # print(f"HBM_min_peak_temperatures: {HBM_min_peak_temperature_list}")

    # with open('dray_temperature_dict_2p5D_waferscale.txt', 'w') as f:
    #     f.write(f"temperature_dict: {temperature_dict}")
    f.close()
    return
    # dedeepyo : 19-Jun-2025

    # dedeepyo : 4-Jun-25 : Implementing iterations with thermal and performance.
    current_GPU_peak_temperature = GPU_peak_temperature
    current_HBM_peak_temperature = HBM_peak_temperature
    current_GPU_min_peak_temperature = GPU_min_peak_temperature
    current_HBM_min_peak_temperature = HBM_min_peak_temperature

    old_GPU_peak_temperature = 0.00 # 0
    old_HBM_peak_temperature = 0.00 # 0
    old_GPU_min_peak_temperature = 0.00 # 0
    old_HBM_min_peak_temperature = 0.00 # 0

    GPU_count_sqrt = int(math.sqrt(get_GPU_count(boxes)))
    kp1 = GPU_count_sqrt
    kp2 = GPU_count_sqrt
    run_file_path = "local_DeepFlow/DeepFlow/scripts/run.sh"
    with open(run_file_path, "r") as f:
        content = f.read()

    content = re.sub(r"--kp1\s+\d+", f"--kp1 {kp1}", content)
    content = re.sub(r"--kp2\s+\d+", f"--kp2 {kp2}", content)

    new_content = content # .replace("--kp1 7 --kp2 7 --m", f"--kp1 {kp1} --kp2 {kp2} --m")
    with open(run_file_path, "w") as f:
        f.write(new_content)

    runtimes = []
    file_path = "local_DeepFlow/DeepFlow/configs/new-configs/testing_thermal_A100.yaml"
    with open(file_path, "r") as f:
        lines = f.readlines()

    i = 0
    while(abs(old_HBM_peak_temperature - current_HBM_peak_temperature) > 1):
        HBM_bandwidth, HBM_latency = HBM_throttled_performance(bandwidth = 7944, latency = 100e-9, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth = 7944 for 3D, 1986 for 2.5D
        HBM_power_Watt = HBM_throttled_power(bandwidth_throttled = HBM_bandwidth, HBM_power = 5, bandwidth_reference = 7944, HBM_peak_temperature = current_HBM_peak_temperature) # bandwidth_reference = 7944 for 3D, 1986 for 2.5D
        HBM_latency *= 1e9
        print(f"HBM latency is {HBM_latency:.1f} ns, HBM bandwidth is {HBM_bandwidth} GB/s, HBM power is {HBM_power_Watt} W")
        for idx in [32, 39]:
            if "bandwidth:" in lines[idx]:
                parts = lines[idx].split("bandwidth:")
                lines[idx] = f"{parts[0]}bandwidth: {HBM_bandwidth} GB\n"
            elif "latency:" in lines[idx]:
                parts = lines[idx].split("latency:")
                lines[idx] = f"{parts[0]}latency: {HBM_latency:.1f}e-9\n"

        #TODO: Run DeepFlow. GPU_time_frac_idle depends on DeepFlow.
        os.chdir("local_DeepFlow/DeepFlow/scripts")
        # deepflow_result = subprocess.run(['csh', '-c', combined_command], capture_output = True, text = True)
        deepflow_result = subprocess.run(['./buildRun.sh'], capture_output = True, text = True)
        if deepflow_result.returncode == 0:
            a = deepflow_result.stdout.split()
            runtimes.append(float(a[0]))
            GPU_time_frac_idle = float(a[1])
            GPU_time_frac_idle_list.append(GPU_time_frac_idle)
        else:
            print(f"Error: Command failed with return code {deepflow_result.returncode}")
            print(deepflow_result.stderr)
            os.chdir(str(_THERM_REPO_ROOT))
            return
        os.chdir(str(_THERM_REPO_ROOT))
        # DeepFlow ran.

        GPU_power_throttled = GPU_throttling(GPU_power = 270.0, GPU_time_frac_idle = GPU_time_frac_idle, GPU_idle_power = 42)
        GPU_power = GPU_power_throttled # power in W
        HBM_power = HBM_power_Watt # power in W
        power_dict["GPU"] = GPU_power # power in W
        power_dict["HBM"] = 2 * HBM_power / 10 # power in W
        power_dict["HBM_l"] = HBM_power / 10 # power in W
        old_GPU_peak_temperature = current_GPU_peak_temperature
        old_HBM_peak_temperature = current_HBM_peak_temperature
        old_GPU_min_peak_temperature = current_GPU_min_peak_temperature
        old_HBM_min_peak_temperature = current_HBM_min_peak_temperature
        power_dict["Power_Source"] = update_power_source_backside(boxes, power_dict) # power in W

        results = simulator.simulate(boxes, bonding_box_list, TIM_boxes, heatsink_obj = heatsink_obj, heatsink_list = heatsink_list, heatsink_name = heatsink_name, bonding_list = bonding_list, bonding_name_type_dict = bonding_name_type_dict, is_repeat = is_repeat,  min_TIM_height = min_TIM_height, power_dict = power_dict, anemoi_parameter_ID = anemoi_parameter_ID, layers = layers)
        GPU_peak_temperature, HBM_peak_temperature, GPU_min_peak_temperature, HBM_min_peak_temperature, anemoi_parameter_ID = results # 0.00, 0.00 # 
        GPU_peak_temperature_list.append(GPU_peak_temperature)
        HBM_peak_temperature_list.append(HBM_peak_temperature)
        current_GPU_peak_temperature = GPU_peak_temperature
        current_HBM_peak_temperature = HBM_peak_temperature
        current_GPU_min_peak_temperature = GPU_min_peak_temperature
        current_HBM_min_peak_temperature = HBM_min_peak_temperature
        
        i += 1
        if i > 10: # 11 iterations
            print("Reached maximum iterations. Exiting.")
            break

    simulation_end_time = time.time()
    print("Simulation finished at ", simulation_end_time)
    print("Time taken for simulation: ", simulation_end_time - simulation_start_time)
    print(f"Runtimes: {runtimes}")
    print(f"GPU_peak_temperatures: {GPU_peak_temperature_list}")
    print(f"HBM_peak_temperatures: {HBM_peak_temperature_list}")
    print(f"GPU_time_frac_idle_list: {GPU_time_frac_idle_list}")

    # dedeepyo : 4-Jun-25

        # for box in boxes:
        #     # dedeepyo : 2-Jun-25 : Parameterizing box power.
        #     # Assuming, all boxes of a particular chiplet_type have same power.
        #     if box.power is None:
        #         box.power = 0.0
        #     box_power_in_mW = round(box.power * 1000, 6)
        #     try:
        #         power_num_in_mW = power_values[box.chiplet.get_chiplet_type()]
        #         # if(power_num_in_mW != box_power_in_mW): # Assuming this asymmetry is never encountered.
        #         #     self.papi.project_parameter_update(self.id, box.chiplet.get_chiplet_type() + "_power", box_power_in_mW)
        #         power_parameter_in_mW = anemoi_parameters[box.chiplet.get_chiplet_type() + "_power"]
        #     except KeyError:
        #         power_num_in_mW = box_power_in_mW
        #         power_parameter_in_mW = None
        #         for key, value in power_values.items():
        #             if value == power_num_in_mW:
        #                 power_parameter_in_mW = anemoi_parameters[key + "_power"]
        #                 power_values[box.chiplet.get_chiplet_type()] = power_num_in_mW
        #                 anemoi_parameters[box.chiplet.get_chiplet_type() + "_power"] = power_parameter_in_mW
        #         if power_parameter_in_mW is None:
        #             power_parameter_in_mW = box.chiplet.get_chiplet_type() + "_power"
        #             self.papi.project_parameter_create(self.id, power_parameter_in_mW, box.chiplet.get_chiplet_type() + "_power", power_num_in_mW)
        #             anemoi_parameters[power_parameter_in_mW] = power_parameter_in_mW     
        #             power_values[box.chiplet.get_chiplet_type()] = power_num_in_mW       
        #     # dedeepyo : 2-Jun-25

# def get_temperatures_from_results(file):
#     f = open(file, 'r')
#     lines = f.readlines()
#     f.close()
#     temperatures = {}

# dedeepyo : 4-Jun-25 : Implementing helper functions for iterations.
def get_GPU_count(boxes):
    GPU_count = 0
    for box in boxes:
        if box.chiplet_parent.get_chiplet_type() == "GPU":
            GPU_count += 1
    return GPU_count

def GPU_throttling(GPU_power = 275, GPU_time_frac_idle = 0.2, GPU_idle_power = 47):
  GPU_power_throttled = GPU_power * (1 - GPU_time_frac_idle) + GPU_idle_power * GPU_time_frac_idle
  return GPU_power_throttled

# def HBM_throttled_performance(bandwidth, latency, HBM_peak_temperature = 74):
#     if((HBM_peak_temperature > 85)):
#         bandwidth *= 0.732
#         latency *= 1.714
#     elif((HBM_peak_temperature > 75) and (HBM_peak_temperature <= 85)):
#         bandwidth *= 0.912
#         latency *= 1.238
    
#     return bandwidth, latency

def HBM_throttled_performance(bandwidth, latency, HBM_peak_temperature = 74):
    if((HBM_peak_temperature > 74)):
        bandwidth *= (2.82 - 0.018 * HBM_peak_temperature) # Linear interpolation between (75, 0.912) and (85, 0.732)
    if((HBM_peak_temperature > 85)):
        # bandwidth *= 0.732
        latency *= 1.714
    elif((HBM_peak_temperature > 75) and (HBM_peak_temperature <= 85)):
        # bandwidth *= 0.912
        latency *= 1.238
    
    return bandwidth, latency

def HBM_throttled_power(bandwidth_throttled, HBM_power, bandwidth_reference = 1986, HBM_peak_temperature = 74):
    refresh_energy = 0.12 * HBM_power
    non_refresh_energy = HBM_power - refresh_energy
    if(bandwidth_throttled < bandwidth_reference):
        non_refresh_energy *= (bandwidth_throttled / bandwidth_reference)
    if(HBM_peak_temperature > 85):
        refresh_energy *= 4.004
    elif(HBM_peak_temperature > 75 and HBM_peak_temperature <= 85):
        refresh_energy *= 2.0
    return refresh_energy + non_refresh_energy
    
def update_power_source_backside(boxes, power_dict, efficiency = 0.9):
    total_power = 0
    for box in boxes:
        if(box.chiplet_parent.get_chiplet_type() != "Power_Source"):
            if(box.chiplet_parent.get_chiplet_type()[0:5] == "HBM_l"):
                box.power = power_dict["HBM_l"]
            elif(box.chiplet_parent.get_chiplet_type() == "HBM"):
                box.power = power_dict["HBM"]
            elif(box.chiplet_parent.get_chiplet_type() == "GPU"):
                box.power = power_dict["GPU"]
            elif(box.power > 0.00):
                print(f"Chiplet type: {box.chiplet_parent.get_chiplet_type()} has power {box.power}W\n")

            total_power += box.power
    
    ps = [box for box in boxes if box.chiplet_parent.get_chiplet_type() == "Power_Source"][0] # Assuming only one power source. For now, it is at bottom. backside power delivery.
    ps.power = (1 - efficiency) * total_power / efficiency
    ps.chiplet_parent.set_power(ps.power)
    return ps.power

def initialize_power_dict_values(boxes):
    power_dict = {}
    for box in boxes: # Assuming all boxes of a particular type have same power.
        if(box.chiplet_parent.get_chiplet_type() == "GPU"):
            power_dict["GPU"] = box.power
        elif(box.chiplet_parent.get_chiplet_type() == "HBM"):
            power_dict["HBM"] = box.power
        elif(box.chiplet_parent.get_chiplet_type()[0:5] == "HBM_l"):
            power_dict["HBM_l"] = box.power
        # elif(box.chiplet_parent.get_chiplet_type() == "Power_Source"):
        #     power_dict["Power_Source"] = box.power
    return power_dict

# dedeepyo : 4-Jun-25

def read_data(filename):
    data = []
    with open(filename, 'r') as f:
        for line in f:
            if line.strip():
                parts = line.strip().split()
                if len(parts) == 4:
                    data.append([float(x) for x in parts])
    return np.array(data)

def interpolate_and_report(data, col2_values, file_handle, system_name, HTC, TIM_conductivity, infill_conductivity, underfill_conductivity, HBM_stack_height, dummy_Si):
    slope_intercept_dict = {}
    for val in col2_values:
        slope_intercept_dict[val] = {'peak_GPU_temp': (0.0, 0.0), 'peak_HBM_temp': (0.0, 0.0)}
        mask = np.isclose(data[:,1], val)
        subset = data[mask]
        if subset.shape[0] < 2:
            continue  # Need at least 2 points for regression
        x = subset[:,0].reshape(-1, 1)
        for col_idx, col_name in zip([2,3], ['peak_GPU_temp', 'peak_HBM_temp']):
            y = subset[:,col_idx]
            model = LinearRegression()
            model.fit(x, y)
            y_pred = model.predict(x)
            r2 = r2_score(y, y_pred)
            slope_intercept_dict[val][col_name] = (f"{model.coef_[0]:.3f}", f"{model.intercept_:.2f}")
            # file_handle.write(f"Interpolation for col={val}, {col_name}:")
            # file_handle.write(f"  Slope: {model.coef_[0]:.6f}, Intercept: {model.intercept_:.6f}, R^2: {r2:.6f}\n")

    # "system_name,HBM_power(W),HTC(W/(m2K)),TIM_conductivity(W/(mK)),infill_conductivity(W/(mK)),underfill_conductivity(W/(mK)),HBM_stack_height,dummy_Si"

    for key1 in slope_intercept_dict:
        file_handle.write(f"{system_name},{key1},{HTC},{TIM_conductivity},{infill_conductivity},{underfill_conductivity},{HBM_stack_height},{dummy_Si},{slope_intercept_dict[key1]['peak_GPU_temp'][0]},{slope_intercept_dict[key1]['peak_GPU_temp'][1]},{slope_intercept_dict[key1]['peak_HBM_temp'][0]},{slope_intercept_dict[key1]['peak_HBM_temp'][1]}\n")
    #     # print(f"{slope_intercept_dict[key1]['peak_GPU_temp'][0]}, {slope_intercept_dict[key1]['peak_HBM_temp'][0]}")
    #     # print(f"{slope_intercept_dict[key1]['peak_GPU_temp'][1]}, {slope_intercept_dict[key1]['peak_HBM_temp'][1]}")
    #     # print("calibrate_GPU")
    #     file_handle.write(f"calibrate_GPU :: {key1} : ({slope_intercept_dict[key1]['peak_GPU_temp'][0]}, {slope_intercept_dict[key1]['peak_GPU_temp'][1]})\n")
    #     # print("calibrate_HBM")
    #     file_handle.write(f"calibrate_HBM :: {key1} : ({slope_intercept_dict[key1]['peak_HBM_temp'][0]}, {slope_intercept_dict[key1]['peak_HBM_temp'][1]})\n")

def write_calibration_to_csv(
    system_name,
    HBM_power,
    HTC,
    TIM_cond,
    infill_cond,
    underfill_cond,
    HBM_stack_height,
    dummy_Si,
    calibrate_GPU_slope,
    calibrate_GPU_intercept,
    calibrate_HBM_slope,
    calibrate_HBM_intercept,
    csv_file_path="calibration_data.csv"
):
    """
    Write calibration data to CSV file.
    
    Args:
        system_name: Name of the system (e.g., "2p5D_1GPU")
        HBM_power: HBM power in Watts
        HTC: Heat Transfer Coefficient in W/(m^2*K)
        TIM_cond: TIM conductivity in W/(m*K)
        infill_cond: Infill conductivity in W/(m*K)
        underfill_cond: Underfill conductivity in W/(m*K)
        HBM_stack_height: HBM stack height (number of dies)
        dummy_Si: Boolean indicating if dummy Si is present
        calibrate_GPU_slope: GPU calibration slope
        calibrate_GPU_intercept: GPU calibration intercept
        calibrate_HBM_slope: HBM calibration slope
        calibrate_HBM_intercept: HBM calibration intercept
        csv_file_path: Path to the CSV file (default: "calibration_data.csv")
    """
    # Ensure dummy_Si is a boolean and convert to string for CSV
    dummy_Si_str = str(bool(dummy_Si))
    
    # Prepare the row data
    row_data = [
        system_name,
        str(HBM_power),
        str(HTC),
        str(TIM_cond),
        str(infill_cond),
        str(underfill_cond),
        str(HBM_stack_height),
        dummy_Si_str,
        str(calibrate_GPU_slope),
        str(calibrate_GPU_intercept),
        str(calibrate_HBM_slope),
        str(calibrate_HBM_intercept)
    ]
    
    # Check if file exists to determine if we need to write header
    file_exists = os.path.exists(csv_file_path)
    
    # Open file in append mode
    with open(csv_file_path, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header if file doesn't exist
        if not file_exists:
            header = [
                "system_name",
                "HBM_power(W)",
                "HTC(W/(m2K))",
                "TIM_conductivity(W/(mK))",
                "infill_conductivity(W/(mK))",
                "underfill_conductivity(W/(mK))",
                "HBM_stack_height",
                "dummy_Si",
                "calibrate_GPU_slope",
                "calibrate_GPU_intercept",
                "calibrate_HBM_slope",
                "calibrate_HBM_intercept"
            ]
            writer.writerow(header)
        
        # Write the data row
        writer.writerow(row_data)

def parse_calibration_block(block: str) -> Tuple[str, List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Extract condition line and calibration tuples for GPU and HBM from a text block."""
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Empty calibration block encountered")

    condition_with_suffix = lines[0]
    colon_index = condition_with_suffix.find(":")
    if colon_index == -1:
        raise ValueError(f"Condition line missing ':' separator: {condition_with_suffix!r}")
    condition_line = condition_with_suffix[: colon_index + 1]

    gpu_entries: List[Tuple[str, str]] = []
    hbm_entries: List[Tuple[str, str]] = []
    entry_pattern = re.compile(r"calibrate_(GPU|HBM) :: ([^:]+) : \(([^)]+)\)")

    for line in lines[1:]:
        match = entry_pattern.search(line)
        if not match:
            continue
        target, setpoint, values = match.groups()
        if target.upper() == "GPU":
            gpu_entries.append((setpoint.strip(), values.strip()))
        else:
            hbm_entries.append((setpoint.strip(), values.strip()))

    if not gpu_entries and not hbm_entries:
        raise ValueError(f"No calibration entries found for block starting: {condition_line}")

    return condition_line, gpu_entries, hbm_entries

def format_condition_block(condition: str, entries: List[Tuple[str, str]]) -> List[str]:
    """Render a condition block without a calibrate header."""
    if not entries:
        return []

    # output = [condition, '    temperature_dict["2p5D_1GPU"] = {']
    output = [condition, '    temperature_dict["3D_1GPU"] = {']
    for index, (setpoint, values) in enumerate(entries):
        trailing = "," if index < len(entries) - 1 else ""
        output.append(f"        {setpoint} : ({values}){trailing}")
    output.append("    }")
    output.append("")
    return output

def convert(source: Path, destination: Path, hbm_stack_height = 1) -> None:
    raw_text = source.read_text()
    blocks = [block.strip() for block in raw_text.split("\n\n") if block.strip()]

    gpu_sections: List[List[str]] = []
    hbm_sections: List[List[str]] = []

    for block in blocks:
        condition, gpu_entries, hbm_entries = parse_calibration_block(block)
        gpu_block = format_condition_block(condition, gpu_entries)
        if gpu_block:
            gpu_sections.append(gpu_block)
        hbm_block = format_condition_block(condition, hbm_entries)
        if hbm_block:
            hbm_sections.append(hbm_block)

    output_lines: List[str] = []
    output_lines.append("hbm_stack_height = {}".format(hbm_stack_height))

    if gpu_sections:
        output_lines.append("calibrate_GPU")
        for block in gpu_sections:
            output_lines.extend(block)

    if hbm_sections:
        if output_lines and output_lines[-1] != "":
            output_lines.append("")
        output_lines.append("calibrate_HBM")
        for block in hbm_sections:
            output_lines.extend(block)

    while output_lines and output_lines[-1] == "":
        output_lines.pop()

    destination.write_text("\n".join(output_lines) + "\n")

if __name__ == '__main__':
    therm()

# 
# new_bandwidth = input("Enter the new bandwidth value (GB): ")



# # Update line 33 and line 40 (0-based index: 32 and 39)
# for idx in [32, 39]:
#     if "bandwidth:" in lines[idx]:
#         # Replace the value after 'bandwidth:'
#         parts = lines[idx].split("bandwidth:")
#         lines[idx] = f"{parts[0]}bandwidth: {new_bandwidth} GB\n"

# with open(file_path, "w") as f:
#     f.writelines(lines)

# print("Bandwidth values updated successfully.")