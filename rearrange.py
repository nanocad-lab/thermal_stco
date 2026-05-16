from sortedcontainers import SortedList
import sys
import random
# deep copy
import copy

conductivity_values = {
    "Air": 0.025,
    "FR-4": 0.1,
    "Cu-Foil": 400,
    "Si": 105,
    "Aluminium": 205,
    "TIM001": 100,
    "Glass": 1.36
}
random.seed(0)

class Box():

    def __init__(self, start_x, start_y, start_z, width, length, height, power, stackup, ambient_conduct, name):
        self._start_x = start_x
        self._start_y = start_y
        self._start_z = start_z
        self._width = width
        self._length = length
        self._height = height
        self._end_x = start_x + width
        self._end_y = start_y + length 
        self._end_z = start_z + height
        self.center_2d = (start_x + width/2, start_y + length/2)
        self.power = power
        # self.conductivity = conductivity_values[material]
        self.name = name
        self.chiplet_parent = None
        self.ambient_conduct = ambient_conduct
        self.stackup = stackup

    @property 
    def start_x(self):
        return self._start_x

    @start_x.setter
    def start_x(self, value):
        self._start_x = value
        self._end_x = value + self._width

    @property
    def start_y(self):
        return self._start_y 

    @start_y.setter
    def start_y(self, value):
        self._start_y = value
        self._end_y = value + self._length

    @property
    def start_z(self):
        return self._start_z

    @start_z.setter
    def start_z(self, value):
        self._start_z = value
        self._end_z = value + self._height

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, value):
        self._width = value
        self._end_x = self._start_x + value

    @property
    def length(self):
        return self._length

    @length.setter
    def length(self, value):
        self._length = value
        self._end_y = self._start_y + value

    @property
    def height(self):
        return self._height

    @height.setter
    def height(self, value):
        self._height = value
        self._end_z = self._start_z + value

    @property
    def end_x(self):
        return self._end_x

    @property
    def end_y(self):
        return self._end_y

    @property
    def end_z(self):
        return self._end_z

    def assign_chiplet_parent(self, parent):
        self.chiplet_parent = parent

    def get_2d_coords(self):
        return (self.start_x, self.start_y, self.end_x, self.end_y)
    
    def get_2d_center(self):
        return (self.center_2d[0], self.center_2d[1])
    
    def rotate(self):
        self._width, self._length = self._length, self._width
        self._end_x = self._start_x + self._width
        self._end_y = self._start_y + self._length

    def __str__(self):
        # add print for all 3d coords
        return "Box: " + self.name + " at (" + str(round(self.start_x, 3)) + "," + str(round(self.start_y, 3)) + "," + str(round(self.start_z, 3)) + ") with width " + str(round(self.width, 3)) + " and length " + str(round(self.length, 3)) + " and height " + str(round(self.height, 3))
    
    def __repr__(self):
        return self.__str__()
    
    def unlock(self):
        self.locked = False
    
    def lock(self):
        self.locked = True

    def set_parent_side(self,side):
        self.parent_side = side
    
    # dedeepyo : 16-Oct-24 : Implementing stackup value retrieval #
    def get_box_stackup(self):
        return self.stackup
    # dedeepyo : 16-oct-24 #

    # dedeepyo : 13-Nov-2024 : Implementing box name without prefix #
    def get_box_type(self) -> str:
        return self.name.split(".")[-1]
    # dedeepyo : 13-Nov-2024 #

def find_parent(boxes,name):
    for box in boxes:
        if box.name == name:
            return box
    return None

def check_overlap(box1, box2):
    # Check z-axis overlap first since boxes without common z are not overlapping at all
    if box1.end_z < box2.start_z or box2.end_z < box1.start_z:
        return False
    # Check x-axis overlap first since boxes are sorted by x
    if box1.end_x < box2.start_x or box2.end_x < box1.start_x:
        return False
    # Only check y-axis if x overlaps
    if box1.end_y < box2.start_y or box2.end_y < box1.start_y:
        return False
    return True


# GEORGE KARFAKIS NOV 19. THIS IS THE OLD CHECK_ALL_OVERLAPS WITH THE DEEPCOPY THAT TOOK 25 MINS

# def check_all_overlaps(boxes,inflation=0):
#     sort_boxes = copy.deepcopy(boxes)
#     sort_boxes.sort(key=lambda box: box.start_x)
#     active = SortedList(key=lambda box: box.end_y)  # Sort active boxes by end_y
#     overlaps = []
#     if inflation > 0:
#         for box in sort_boxes:
#             box.start_x -= inflation
#             box.start_y -= inflation
#             box.width += 2*inflation
#             box.length += 2*inflation

#     for box in sort_boxes:
#         # Remove boxes that are left of the current box's start_x
#         while active and active[0].end_x <= box.start_x:
#             active.pop(0)

#         # Check for overlaps with active boxes
#         for active_box in active:
#             if active_box.end_y > box.start_y:  # There is a vertical overlap
#                 if check_overlap(box, active_box):
#                     overlaps.append((box, active_box))

#         # Add current box to active boxes
#         active.add(box)

#     return overlaps

def check_all_overlaps(boxes, inflation=0):
    sort_boxes = sorted(boxes, key=lambda box: box.start_x)  # Sort boxes by start_x
    active = SortedList(key=lambda box: box.end_y)  # Sort active boxes by end_y
    overlaps = []

    for box in sort_boxes:
        # Adjust the box dimensions for inflation if needed
        if inflation > 0:
            original_start_x, original_start_y, original_width, original_length = (
                box.start_x,
                box.start_y,
                box.width,
                box.length,
            )
            box.start_x -= inflation
            box.start_y -= inflation
            box.width += 2 * inflation
            box.length += 2 * inflation

        # Remove boxes that are left of the current box's start_x
        while active and active[0].end_x <= box.start_x:
            active.pop(0)

        # Check for overlaps with active boxes
        for active_box in active:
            if active_box.end_y > box.start_y:  # There is a vertical overlap
                if check_overlap(box, active_box):
                    overlaps.append((box, active_box))

        # Add current box to active boxes
        active.add(box)

        # Revert the box dimensions after overlap check
        if inflation > 0:
            box.start_x = original_start_x
            box.start_y = original_start_y
            box.width = original_width
            box.length = original_length

    return overlaps

# dedeepyo : 18-Dec-24 : Implementing 3D overlap check for only one box with all other boxes #
def check_all_overlaps_3d(boxes, current_box, inflation = 0):
    overlap_count = 0
    if inflation > 0:
        original_start_x, original_start_y, original_width, original_length = (
            current_box.start_x,
            current_box.start_y,
            current_box.width,
            current_box.length,
        )
        current_box.start_x -= inflation
        current_box.start_y -= inflation
        current_box.width += 2 * inflation
        current_box.length += 2 * inflation
    
    for box in boxes:
        if check_overlap(current_box, box):
            overlap_count += 1
    
    if inflation > 0:
        current_box.start_x = original_start_x
        current_box.start_y = original_start_y
        current_box.width = original_width
        current_box.length = original_length

    return overlap_count
# dedeepyo : 18-Dec-24

def flip_box(box, dist_res):
    # symetrically flip across parent coord point
    box.start_x = box.parent_pin_coords[0] + dist_res
    # box.end_x = box.start_x + box.width

def rearrange_boxes(boxes, dist_res):

    # this will be complicated.
    # first, rearrange boxes that have been placed incorrectly.

    dram_boxes = [box for box in boxes if box.name.startswith("DRAM")]
    for box in dram_boxes:
        # print("BOX: ", box.name, "PARENT: ", box.parent, "PARENT PIN COORDS: ", box.parent_pin_coords)
        # first, check if any boxes are not positioned correctly in respect to their parent GPU.
        # this means, if the DRAM is to the top or bottom of the GPU, I need to rotate it.
        if box.parent != None and box.parent_pin_coords != None:
            # we need to check DRAM center and compare it to parent center
            parent_pin_coords = box.parent_pin_coords
            parent = find_parent(boxes, box.parent)
            if not parent:
                print("Error: Parent box not found.")
                print("Box: ", box.name)
                print("Parent: ", box.parent)
                print("Boxes:", boxes)
                sys.exit(1)
            # print("Comparing DRAM center", box.center_2d, "to parent center", parent.center_2d)
            # parent pin coords are at edge of GPU. Lets figure out which edge.
            if parent_pin_coords[0] == parent.start_x and parent_pin_coords[1] == parent.start_y:
                # bottom left, do nothing
                box.set_parent_side("right")
            elif parent_pin_coords[0] == parent.start_x and parent_pin_coords[1] == parent.end_y:
                # top left, do nothing
                box.set_parent_side("right")
            elif parent_pin_coords[0] == parent.end_x and parent_pin_coords[1] == parent.start_y:
                # bottom right, flip
                flip_box(box)
                box.set_parent_side("left")
            elif parent_pin_coords[0] == parent.end_x and parent_pin_coords[1] == parent.end_y:
                # top right, flip
                flip_box(box)
                box.set_parent_side("left")
            elif parent_pin_coords[1] == parent.start_y:
                # pin is on the bottom of parent
                box.rotate()
                # now clamp to parent
                box.start_y = parent.start_y - box.length - dist_res
                box.end_y = box.start_y + box.length
                box.set_parent_side("top")
            elif parent_pin_coords[1] == parent.end_y:
                # pin is on the top of parent
                box.rotate()
                # now clamp to parent
                box.start_y = parent.end_y + dist_res
                box.end_y = box.start_y + box.length
                box.set_parent_side("bottom")
            elif parent_pin_coords[0] == parent.start_x:
                # pin is on left of parent
                box.set_parent_side("right")
            elif parent_pin_coords[0] == parent.end_x:
                # pin is on the right of parent
                flip_box(box)
                box.set_parent_side("left")

    # get a static copy of boxes that does not change (deep copy)
    pre_boxes = copy.deepcopy(boxes)
    # now check overlap and move DRAMs only
    # first check overlap
    i = 0
    while True:
        i +=1
        overlaps = check_all_overlaps(boxes)
        if i > 100000:
            print("Fatal error: Boxes overlap, and this cannot be resolved automatically. Problem boxes listed below:")
            print(overlaps)
            # sys.exit(1)
            return pre_boxes,boxes
        if not overlaps:
            break

        # Now we have a list of overlapping boxes. We need to move them.
        # if any overlaps don't involve a DRAM, fail with error.
        for box1, box2 in overlaps:
            if not box1.name.startswith("DRAM") and not box2.name.startswith("DRAM"):
                print("Fatal error: Boxes overlap, and this cannot be resolved automatically. Problem boxes listed below:")
                print(overlaps)
                # sys.exit(1)
                return pre_boxes,boxes
            
        for box in boxes:
            box.unlock()

        for overlap in overlaps:
            # we can only move DRAMs to fix these.
            # first pick which box to move.
            # if one of them is not DRAM, pick the other.
            box1, box2 = overlap
            # if either of them is not DRAM, quit with error
            if not box1.name.startswith("DRAM") or not box2.name.startswith("DRAM"):
                print("Fatal error: Unimplemented, DRAM overlaps with non-DRAM")
                print(overlaps)
                # sys.exit(1)
                return pre_boxes,boxes
            
            if box1.locked or box2.locked:
                continue

            # now check if box1 and box2 are in the same row or column. This happens if their start x or their start y are the same.
            # if they are in the same row, move the one with the higher start_x to the right.
            # if they are in the same column, move the one with the higher start_y to the top.
            if box1.start_x == box2.start_x:
                if box1.start_y > box2.start_y:
                    # move box1 top OR box2 bottom, randomly.
                    if random.choice([0,1]) == 0:
                        box1.start_y = box1.start_y + dist_res
                        # box1.end_y = box1.start_y + box1.length
                        box1.lock()
                    else:
                        box2.start_y = box2.start_y - dist_res
                        # box2.end_y = box2.start_y + box2.length
                        box2.lock()
                else:
                    # move box2 top OR box1 bottom, randomly.
                    if random.choice([0,1]) == 0:
                        box1.start_y = box1.start_y - dist_res
                        # box1.end_y = box1.start_y + box1.length
                        box1.lock()
                    else:
                        box2.start_y = box2.start_y + dist_res
                        # box2.end_y = box2.start_y + box2.length
                        box2.lock()
            elif box1.start_y == box2.start_y:
                if box1.start_x < box2.start_x:
                    # move box1 right OR box2 left, randomly.
                    if random.choice([0,1]) == 0:
                        box1.start_x = box1.start_x + dist_res
                        # box1.end_x = box1.start_x + box1.width
                        box1.lock()
                    else:
                        box2.start_x = box2.start_x - dist_res
                        # box2.end_x = box2.start_x + box2.width
                        box2.lock()
                else:
                    # move box2 right OR box1 left, randomly.
                    if random.choice([0,1]) == 0:
                        box1.start_x = box1.start_x - dist_res
                        # box1.end_x = box1.start_x + box1.width
                        box1.lock()
                    else:
                        box2.start_x = box2.start_x + dist_res
                        # box2.end_x = box2.start_x + box2.width
                        box2.lock()
            else:
                # if they are not in the same row or column, move them away from each other pseudorandomly, and then snap back so that the one moved is close to parent.
                # first, we know that both of these boxes are DRAMs, so they have a parent.
                # furthermore, their start_x or end_x or start_y or end_y must differ by dist_res from a side of the parent.
                # this needs to remain true for both boxes.
                # the other "free" dimension can be moved pseudo-randomly.
                box1_parent = find_parent(boxes, box1.parent)
                box2_parent = find_parent(boxes, box2.parent)
                if not box1_parent or not box2_parent:
                    print("Error: Parent box not found.")
                    sys.exit(1)

                box1_side = box1.parent_side
                box2_side = box2.parent_side
                if not box1_side or not box2_side:
                    print("Error: Parent side not found.")
                    sys.exit(1)

                # randomly choose 1 to move
                box_chosen = random.choice([box1, box2])
                box_chosen_side = box1_side if box_chosen == box1 else box2_side
                box_chosen_parent = box1_parent if box_chosen == box1 else box2_parent
                if box_chosen_side == "top" or box_chosen_side == "bottom":
                    # we cannot move chosen box up or down. Move it randomly left or right
                    # set the greedy prefered direction. Move the box closer to center of parent.
                    if box_chosen.center_2d[0] < box_chosen_parent.center_2d[0]:
                        greedy_add = dist_res
                    else:
                        greedy_add = -dist_res
                    ungreedy_add = -greedy_add 
                    if random.choices([True, False], weights=[0.8, 0.2])[0]:
                        box_chosen.start_x = box_chosen.start_x + greedy_add
                        # box_chosen.end_x = box_chosen.start_x + box_chosen.width
                        box_chosen.lock()
                    else:
                        box_chosen.start_x = box_chosen.start_x + ungreedy_add
                        # box_chosen.end_x = box_chosen.start_x + box_chosen.width
                        box_chosen.lock()
                else:
                    # we cannot move chosen box left or right. Move it randomly up or down
                    # set the greedy prefered direction. Move the box closer to center of parent.
                    if box_chosen.center_2d[1] < box_chosen_parent.center_2d[1]:
                        greedy_add = dist_res
                    else:
                        greedy_add = -dist_res
                    ungreedy_add = -greedy_add
                    if random.choices([True, False], weights=[0.8, 0.2])[0]:
                        box_chosen.start_y = box_chosen.start_y + greedy_add
                        # box_chosen.end_y = box_chosen.start_y + box_chosen.length
                        box_chosen.lock()
                    else:
                        box_chosen.start_y = box_chosen.start_y + ungreedy_add
                        # box_chosen.end_y = box_chosen.start_y + box_chosen.length
                        box_chosen.lock()
                        
    return pre_boxes, boxes