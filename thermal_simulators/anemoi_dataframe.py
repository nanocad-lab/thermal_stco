import matplotlib.pyplot as plt
import seaborn as sns

sns.set()
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


# this file includes functions that take in a formatted input or output data frame
# for input data frames, we will visualize, in seperate 3D images, the initial power and conductivity
# for output data frames, we will visualize, in one 3D image, the output temperature


class DataFrame():
    def __init__(self, voxel_res, power_map = None, conductivity_map = None, temperature_map = None):
        self.voxel_res = voxel_res
        self.power_map = power_map
        self.conductivity_map = conductivity_map
        self.temperature_map = temperature_map
        if self.temperature_map is not None and len(self.temperature_map.shape) == 3:
            self.determine_allow_map()
    
    def determine_allow_map(self,threshold = -1):
        # determine allow map from power map
        data = self.temperature_map
        # self.allow_map = np.zeros((data.shape[0], data.shape[1], data.shape[2]))
        self.allow_map = np.zeros((data.shape[0], data.shape[1], data.shape[2]))
        self.allow_map[data > threshold] = 1

    def load_temperature_map(self, temperature_map):
        self.temperature_map = temperature_map
        self.determine_allow_map()
        
    def visualize_temp_2D(self, fname=None):
     data = self.temperature_map
     print(f"Temp map shape: {data.shape}")
     color = np.zeros((data.shape[0], data.shape[1], 4), dtype=np.float32)  # Initialize a transparent color array
     max_val = np.max(data)
     min_val = np.min(data[data != -1])
     print("Min val: ", min_val, "Max val: ", max_val)
     color_incr = (data - min_val) / (max_val - min_val)
     color[:, :, 2] = 1 - color_incr  # Blue channel decreases as color_incr increases
     color[:, :, 0] = color_incr  # Red channel increases as color_incr increases
     color[:, :, 3] = np.isfinite(data)  # Alpha channel based on valid data points

     plt.rcParams['figure.figsize'] = [12, 8]
     plt.imshow(color, origin='lower')
     plt.xlabel('X Coordinate')
     plt.ylabel('Y Coordinate')
     plt.title('Temperature Map')
     

     if fname:
        plt.savefig(fname)
     else:
        plt.show()
        
    def visualize_temp_3D(self, fname = None):
        data = self.temperature_map
        
        # Ensure data is correctly initialized and allow_map is properly set
        if data is None or data.size == 0:
            raise ValueError("Temperature map data is not initialized properly.")
        
        color = np.zeros((data.shape[0], data.shape[1], data.shape[2], 4), dtype=np.float32)
        
        # max_val = np.max(data)
        # min_val = np.min(data[data != -1])

        max_val = 90
        min_val = 60

        print("Min val: ", min_val, "Max val: ", max_val)
        
        color_incr = (data - min_val) / (max_val - min_val)
        color[:, :, :, 2] = 1 - color_incr  # Blue decreases as color increases
        color[:, :, :, 0] = color_incr      # Red increases as color increases
        
        # Set alpha channel to 1 where data is valid
        color[:, :, :, 3] = self.allow_map[:, :, :] 
        
        plt.rcParams['figure.figsize'] = [12, 8]
        x, y, z = np.indices((data.shape[0]+1, data.shape[1]+1, data.shape[2]+1))
        
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')
        # ax.set_box_aspect([1, 1, 1])
        # ax.set_xlim(0, 63.25)
        # ax.set_ylim(0, 63.25)
        # ax.set_zlim(0, 5)
        ax.view_init(elev=20, azim=30)
        # Ensure edgecolors are set for better visibility of the voxel structure
        # my voxel boundaries are white and are blocking my view. Please disable.
        # ax.voxels(x, y, z, self.allow_map, facecolors=color)
        ax.voxels(x, y, z, self.allow_map, facecolors=color, edgecolors=color)
        
        if fname:
            plt.savefig(fname)
        else:
            plt.show()

    def visualize_temp_3D_dray(self, fname=None):
        data = self.temperature_map

        if data is None or data.size == 0:
            raise ValueError("Temperature map data is not initialized properly.")

        allow_map = self.allow_map
        shape = data.shape

        # max_val = np.max(data)
        # min_val = np.min(data[data != -1])

        max_val = 90
        min_val = 60

        print("Min val: ", min_val, "Max val: ", max_val)

        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        for x in range(shape[0]):
            for y in range(shape[1]):
                for z in range(shape[2]):
                    if allow_map[x, y, z] > 0:
                        val = data[x, y, z]
                        norm_val = (val - min_val) / (max_val - min_val + 1e-8)  # Normalize
                        red = norm_val
                        blue = 1 - norm_val
                        color = (red, 0.0, blue, 0.8)  # RGBA
                        
                        # Define cube corners
                        cube_x = [x, x+1, x+1, x, x]
                        cube_y = [y, y, y+1, y+1, y]
                        cube_z = [z] * 5
                        cube_z_top = [z+1] * 5
                        
                        verts = [list(zip(cube_x, cube_y, cube_z)),
                                list(zip(cube_x, cube_y, cube_z_top))]

                        for i in range(4):
                            verts.append([
                                (cube_x[i], cube_y[i], cube_z[i]),
                                (cube_x[i+1], cube_y[i+1], cube_z[i+1]),
                                (cube_x[i+1], cube_y[i+1], cube_z_top[i+1]),
                                (cube_x[i], cube_y[i], cube_z_top[i])
                            ])

                        poly = Poly3DCollection(verts, facecolors=color, edgecolors='k', linewidths=0.3)
                        poly.set_sort_zpos(x)  # or use z
                        ax.add_collection3d(poly)

        ax.set_xlim(0, shape[0])
        ax.set_ylim(0, shape[1])
        ax.set_zlim(0, shape[2])

        ax.view_init(elev=20, azim=30)
        ax.dist = 1

        if fname:
            plt.savefig(fname)
            plt.close()
        else:
            plt.show()

    def visualize_temp_3D_dray2(self, dx = 1, dy = 1, dz = 1, fname=None):
        data = self.temperature_map
        if data is None or data.size == 0:
            raise ValueError("Temperature map data is not initialized properly.")

        color = np.zeros((data.shape[0], data.shape[1], data.shape[2], 4), dtype=np.float32)
        max_val = np.max(data)
        min_val = np.min(data[data != -1])
        # max_val = 90
        # min_val = 60
        print("Min val: ", min_val, "Max val: ", max_val)

        color_incr = (data - min_val) / (max_val - min_val)
        color[:, :, :, 2] = 1 - color_incr  # Blue decreases
        color[:, :, :, 0] = color_incr      # Red increases
        color[:, :, :, 3] = self.allow_map[:, :, :]

        if not np.any(self.allow_map):
            raise ValueError("allow_map has no valid voxels to display.")

        shape = data.shape
        x, y, z = np.indices((shape[0]+1, shape[1]+1, shape[2]+1), dtype=np.float32)
        x = x * dx
        y = y * dy
        z = z * dz

        plt.rcParams['figure.figsize'] = [12, 8]
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')
        ax.set_box_aspect([dx * shape[0], dy * shape[1], dz * shape[2]])
        ax.view_init(elev=20, azim=30)
        ax.voxels(x, y, z, self.allow_map, facecolors=color, edgecolors=color)

        if fname:
            plt.savefig(fname)
        else:
            plt.show()

    def visualize_temp_3D_dray3(self, dx = 1, dy = 1, dz = 1, fname=None):
        data = self.temperature_map
        if data is None or data.size == 0:
            raise ValueError("Temperature map data is not initialized properly.")
        
        allow_mask = self.allow_map.astype(bool)
        indices = np.argwhere(allow_mask)
        if indices.size == 0:
            print("No voxels to render.")
            return

        min_val = 60
        max_val = 90
        print("Min val: ", min_val, "Max val: ", max_val)
        norm_temp = (data[allow_mask] - min_val) / (max_val - min_val)
        norm_temp = np.clip(norm_temp, 0, 1)

        colors = np.zeros((indices.shape[0], 4), dtype=np.float32)
        colors[:, 0] = norm_temp              # Red
        colors[:, 2] = 1 - norm_temp          # Blue
        colors[:, 3] = 1.0                    # Alpha

        x = indices[:, 0] * dx
        y = indices[:, 1] * dy
        z = indices[:, 2] * dz

        filled = {}
        facecolors = {}

        for i in range(indices.shape[0]):
            coord = (x[i], y[i], z[i])
            key = (x[i], y[i], z[i])
            filled[key] = True
            facecolors[key] = colors[i]

        plt.rcParams['figure.figsize'] = [12, 8]
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')
        ax.set_box_aspect([dx * data.shape[0], dy * data.shape[1], dz * data.shape[2]])
        ax.view_init(elev=20, azim=30)
        ax.voxels(filled, facecolors=facecolors, edgecolors='none')

        if fname:
            plt.savefig(fname)
        else:
            plt.show()
