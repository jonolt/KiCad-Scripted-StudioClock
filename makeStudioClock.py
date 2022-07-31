# run in pcbnew python console
# import sys; sys.path.append("Documents/KiCadStudioClock")
# import makeStudioClock as msc

from __future__ import division  # for float division

import collections
import math
import re

import pcbnew

Modules = {}
Nets = {}
Radius = 42

layer_table = {}
layer_table_rev = {}

# Uncomment to work with the File (run in project directory):
pcb = pcbnew.LoadBoard("StudioClock.kicad_pcb")
pcb.BuildListOfNets()  # needed fo load file
# Work in KiCad Console:
# pcb = pcbnew.GetBoard()


# calc rotation angle (rad) with Position in Clock: float -> float
def calc_rad_angle_from_clock_position(clock_position):
    return -math.pi / 30 * (clock_position % 60) - math.pi


# calc rotation angle (deg) with Position: float -> float
def calc_deg_angle_from_clock_position(clock_position):
    return math.degrees(calc_rad_angle_from_clock_position(clock_position))


# calc the Position(s) with the Radius and an Angle: float, float -> float/float/wxPoint
def calc_x_location_from_clock_position_mm(radius, clock_position):
    return (
        math.sin(calc_rad_angle_from_clock_position(clock_position)) * radius
    )  # +originOffsetXY[0]


def calc_y_location_from_clock_position_mm(radius, clock_position):
    return (
        math.cos(calc_rad_angle_from_clock_position(clock_position)) * radius
    )  # +originOffsetXY[1]


def calc_xy_location_from_clock_position_WxPoint(radius, clock_position):  # noqa
    return pcbnew.wxPointMM(
        calc_x_location_from_clock_position_mm(radius, clock_position),
        calc_y_location_from_clock_position_mm(radius, clock_position),
    )


# calc offset of digit (0,1,2,3)
def calc_dig_location_from_position(digit_position, digit_space, digit_width):
    pos_x = [
        -1.5 - digit_space / digit_width * 2,
        -0.5 - digit_space / digit_width,
        0.5 + digit_space / digit_width,
        1.5 + digit_space / digit_width * 2,
    ][digit_position] * digit_width
    pos_y = 0
    return pcbnew.wxPointMM(
        pos_x, pos_y
    )  # (posX+originOffsetXY[0],posY+originOffsetXY[1])


def radius_from_net_number(number):
    return (
        Radius - 1.2 - (range(15 + 1, 0, -1)[number] * 0.75)
    )  # this can be replaced by a more advanced equation


# add a track and add it: wxPoint, wxPoint, int, int -> Track
def add_track(start_location, stop_location, net_code, layer):
    t = pcbnew.TRACK(pcb)
    pcb.Add(t)
    t.SetStart(start_location)
    t.SetEnd(stop_location)
    t.SetNetCode(net_code)
    t.SetLayer(layer)
    t.SetWidth(300000)
    return t


# add an arc of tracks with the Position Indices of the SecondsLeds:
# float, int, int, int, int -> Track
def add_track_arc(radius, start_ring_position, stop_ring_position, net_code, layer):
    t = None
    if stop_ring_position > start_ring_position:
        for i in range(start_ring_position, stop_ring_position):
            t = add_track(
                calc_xy_location_from_clock_position_WxPoint(radius, i),
                calc_xy_location_from_clock_position_WxPoint(radius, i + 1),
                net_code,
                layer,
            )
    else:
        for i in range(start_ring_position, stop_ring_position, -1):
            t = add_track(
                calc_xy_location_from_clock_position_WxPoint(radius, i),
                calc_xy_location_from_clock_position_WxPoint(radius, i - 1),
                net_code,
                layer,
            )
    return t


# add a full Track ring with the desired Radius: float, int, int
def add_track_ring(radius, net_code, layer):
    add_track_arc(radius, 0, 61, net_code, layer)


# add a via at the Position: wxPoint -> Via
def add_via(position, net):
    v = pcbnew.VIA(pcb)
    pcb.Add(v)
    v.SetPosition(position)
    v.SetWidth(300000)
    v.SetDrill(200000)
    v.SetViaType(pcbnew.VIA_THROUGH)
    v.SetLayerPair(layer_table_rev.get("F.Cu"), layer_table_rev.get("B.Cu"))
    v.SetNetCode(net)
    return v


def get_parent_ref(pad):
    return pad.GetParent().GetReference().encode("utf-8")


def set_position_second_ring(modules_seconds, radius_seconds):
    for key, value in modules_seconds.items():
        _, i = regex_split_annotation(key)
        value.SetOrientation((calc_deg_angle_from_clock_position(i - 1) - 90) * 10)
        value.SetPosition(
            calc_xy_location_from_clock_position_WxPoint(radius_seconds, i - 1)
        )
        print(
            "Placed: Second %s at %s with rot %s"
            % (
                key,
                str(value.GetPosition()),
                str(value.GetOrientation()),
            )
        )


def set_position_hour_ring(modules_hours, radius_hours):
    for key, value in modules_hours.items():
        _, i = regex_split_annotation(key)
        value.SetOrientation(
            (calc_deg_angle_from_clock_position((i - 61) * 5) - 90) * 10
        )
        value.SetPosition(
            calc_xy_location_from_clock_position_WxPoint(radius_hours, (i - 61) * 5)
        )
        print(
            "Placed: Hour %s at %s with rot %s"
            % (
                key,
                str(value.GetPosition()),
                str(value.GetOrientation()),
            )
        )


def set_position_digits(modules_digits, digit_space, digit_width, revers=True):
    for key, value in modules_digits.items():
        _, i = regex_split_annotation(key)
        value.SetPosition(
            calc_dig_location_from_position(i - 1, digit_space, digit_width)
        )
        if revers:
            value.SetOrientation(2700)
        print("Placed: Digit %d at %s" % (i, str(value.GetPosition())))


def set_separation_modules(modules_sep, digit_high):
    for key, module in modules_sep.items():
        _, i = regex_split_annotation(key)  # TODO fix one must be plus
        sign = 1 if key == "D73" else -1
        module.SetPosition(pcbnew.wxPointMM(0, sign * digit_high * 0.4))
        module.SetOrientation(2700)
        print("Placed: Seperator %s at %s" % (key, str(module.GetPosition())))


def set_connector_modules(modules_con, digit_high):
    for key, module in modules_con.items():
        _, i = regex_split_annotation(key)
        sign = -1 if key == "J1" else 1
        module.SetPosition(pcbnew.wxPointMM(0, sign * digit_high * 1.5))
        module.SetOrientation(2700)
        # module.Se # TODO change front to back side
        print("Placed: Connector %s at %s" % (key, str(module.GetPosition())))


def set_dimension(length):
    corners = [[-1, -1], [-1, 1], [1, 1], [1, -1]]
    print("Setting Board Dimensions too:" + str(length) + "x" + str(length))
    tmp_print = []
    for i in range(4):
        seg = pcbnew.DRAWSEGMENT(pcb)
        pcb.Add(seg)
        seg.SetStart(
            pcbnew.wxPointMM(corners[i][0] * length / 2, corners[i][1] * length / 2)
        )
        seg.SetEnd(
            pcbnew.wxPointMM(
                corners[(i + 1) % 4][0] * length / 2,
                corners[(i + 1) % 4][1] * length / 2,
            )
        )
        seg.SetLayer(layer_table_rev.get("Edge.Cuts"))
        tmp_print.append(seg.GetStart())
    print("Board Corners:" + str(tmp_print))


def u_connect(location1, location2, offset, net_code):
    location_a = pcbnew.wxPointMM(
        location1[0] / 1000000.0, location1[1] / 1000000.0 + offset
    )
    location_b = pcbnew.wxPointMM(
        location2[0] / 1000000.0, location2[1] / 1000000.0 + offset
    )
    add_track(location1, location_a, net_code, layer_table_rev.get("F.Cu"))
    add_via(location_a, net_code)
    add_track(location_a, location_b, net_code, layer_table_rev.get("B.Cu"))
    add_via(location_b, net_code)
    add_track(location_b, location2, net_code, layer_table_rev.get("F.Cu"))
    if math.fabs(location_a[0]) <= math.fabs(location_b[0]):
        return location_b
    else:
        return location_a


# Input: eq1radiusPolygon: Equation1, radius of the circle represented by the Polygon
# 		eq2slope: Equation2, Slope of the beam intersecting the circle
def get_ring_intersection(eq_1_radius_polygon, eq_2_slope, left_neg_1_right_1):
    m = eq_2_slope
    r = eq_1_radius_polygon
    alpha = math.pi / 60
    epsilon = math.tan(m) % (alpha * 2)
    b = math.cos(alpha) * r
    d = b / math.cos(alpha - epsilon)
    ring_x_point = math.cos(math.tan(m)) * d * left_neg_1_right_1
    ring_y_point = math.sin(math.tan(m)) * d * left_neg_1_right_1
    return pcbnew.wxPointMM(ring_x_point, ring_y_point)


def get_ring_intersection_by_position(eq_1_radius_polygon, position):
    m = math.atan(position * math.pi / 30 - math.pi / 2)
    return get_ring_intersection(
        eq_1_radius_polygon, m, 1
    )  # (position-30)/math.fabs(position-30))


def set_digits_connections(modules_digits, modules_separation_leds):

    print(
        "Connecting Digits %s and Separation LEDs %s with Nets"
        % (
            str(
                map(lambda x: x.GetReference().encode("utf8"), modules_digits.values())
            ),
            str(
                list(
                    map(  # TODO do this as list comprehension
                        lambda x: x.GetReference().encode("utf8"),
                        modules_separation_leds.values(),
                    )
                )
            ),
        )
    )
    pads_lists = [list()] * 4
    for i, key in enumerate(modules_digits):
        pads_lists[i] = [None] * 10
        for pad in modules_digits[key].Pads():
            pads_lists[i][int(pad.GetPadName()) - 1] = pad
        pads_lists[i].pop(2)
        pads_lists[i].pop(6)
    outer_location = 0
    list_left_vias = [list()] * 8
    list_right_vias = [list()] * 8
    for i in range(8):
        list_left_vias[i] = u_connect(
            pads_lists[0][i].GetPosition(),
            pads_lists[1][i].GetPosition(),
            [6, 5, 4, 3, -3, -4, -5, -6][i] * 1.4,
            pads_lists[0][i].GetNetCode(),
        )
        list_right_vias[i] = u_connect(
            pads_lists[2][i].GetPosition(),
            pads_lists[3][i].GetPosition(),
            [3, 4, 5, 6, -6, -5, -4, -3][i] * 1.4,
            pads_lists[2][i].GetNetCode(),
        )
        if list_left_vias[i][0] < outer_location:
            outer_location = list_left_vias[i][0]
    # Left Side
    for i in range(8):
        t = add_track(
            list_left_vias[i],
            pcbnew.wxPoint(outer_location, list_left_vias[i][1]),
            pads_lists[0][i].GetNetCode(),
            layer_table_rev.get("B.Cu"),
        )
        if i not in [5 - 1 - 1, 6 - 1 - 1]:
            add_via(t.GetEnd(), pads_lists[0][i].GetNetCode())
        m = list_left_vias[i][1] / outer_location
        r = radius_from_net_number(
            regex_split_annotation(pads_lists[0][i].GetNetname())[1]
        )
        t2 = add_track(
            t.GetEnd(),
            get_ring_intersection(r, m, -1),
            pads_lists[0][i].GetNetCode(),
            layer_table_rev.get("F.Cu"),
        )
        if i == 6 - 1 - 1:
            t2.SetLayer(layer_table_rev.get("B.Cu"))
            continue
        add_via(t2.GetEnd(), pads_lists[0][i].GetNetCode())
    # Right Side
    for i in range(8):
        if i == 1 - 1:
            continue
        t = add_track(
            list_right_vias[i],
            pcbnew.wxPoint(-outer_location, list_right_vias[i][1]),
            pads_lists[2][i].GetNetCode(),
            layer_table_rev.get("B.Cu"),
        )
        if i not in [1 - 1, 10 - 1 - 1]:
            add_via(t.GetEnd(), pads_lists[2][i].GetNetCode())
        m = list_right_vias[i][1] / -outer_location
        r = radius_from_net_number(
            regex_split_annotation(pads_lists[2][i].GetNetname())[1]
        )
        t2 = add_track(
            t.GetEnd(),
            get_ring_intersection(r, m, 1),
            pads_lists[2][i].GetNetCode(),
            layer_table_rev.get("F.Cu"),
        )
        if i == 1:
            led_pads = []
            led_modules_keys = modules_separation_leds.keys()
            for key in led_modules_keys:
                for pad in modules_separation_leds[key].Pads():
                    if pad.GetNetCode() == pads_lists[2][i - 1].GetNetCode():
                        led_pads.append(pad)
            t3 = add_track(
                pcbnew.wxPoint(
                    pads_lists[2][0].GetPosition()[0], list_right_vias[i - 1][1]
                ),
                pcbnew.wxPoint(led_pads[0].GetPosition()[0], list_right_vias[i - 1][1]),
                pads_lists[2][i - 1].GetNetCode(),
                layer_table_rev.get("B.Cu"),
            )
            t4 = add_track(
                t3.GetEnd(),
                pcbnew.wxPoint(
                    led_pads[1].GetPosition()[0], led_pads[1].GetPosition()[1] - 2000000
                ),
                pads_lists[2][i - 1].GetNetCode(),
                layer_table_rev.get("B.Cu"),
            )
            add_via(t4.GetEnd(), pads_lists[2][i - 1].GetNetCode())
            add_track(
                t4.GetEnd(),
                led_pads[1].GetPosition(),
                pads_lists[2][i - 1].GetNetCode(),
                layer_table_rev.get("F.Cu"),
            )
            v1 = add_via(
                pcbnew.wxPoint(t3.GetEnd()[0] + 1500000, t3.GetEnd()[1]),
                pads_lists[2][i - 1].GetNetCode(),
            )
            t5 = add_track(
                v1.GetPosition(),
                t3.GetEnd(),
                pads_lists[2][i - 1].GetNetCode(),
                layer_table_rev.get("F.Cu"),
            )
            add_track(
                t5.GetEnd(),
                led_pads[0].GetPosition(),
                pads_lists[2][i - 1].GetNetCode(),
                layer_table_rev.get("F.Cu"),
            )
            con_pos = list(modules["J1"].Pads())[15].GetPosition()
            add_track(
                con_pos,
                pcbnew.wxPoint(con_pos[0], list_right_vias[i - 1][1]),
                pads_lists[2][i - 1].GetNetCode(),
                layer_table_rev.get("B.Cu"),
            )
        else:
            add_via(t2.GetEnd(), pads_lists[0][i].GetNetCode())


def set_cathode_tracks(nets_cathode):
    for key, value in nets_cathode.items():
        prefix, num = regex_split_annotation(key)
        if key == "k15":
            continue
        r = radius_from_net_number(num)
        print("Adding Net:", str(key), "with radius", str(r))
        add_track_ring(r, value[0].GetNetCode(), layer_table_rev.get("B.Cu"))
        for pad in value:
            module_ref = regex_split_annotation(pad.GetParent().GetReference())
            if module_ref[0] == "D" and module_ref[1] <= 60:
                corner_location = calc_xy_location_from_clock_position_WxPoint(
                    r, module_ref[1] - 1
                )
                add_track(
                    pad.GetPosition(),
                    corner_location,
                    pad.GetNetCode(),
                    layer_table_rev.get("F.Cu"),
                )
                add_via(corner_location, pad.GetNetCode())
            elif module_ref[0] == "D" and module_ref[1] <= 72:
                radius = math.sqrt(
                    (
                        math.pow(pad.GetPosition()[0], 2)
                        + math.pow(pad.GetPosition()[1], 2)
                    )
                ) / math.pow(10, 6)
                pos = module_ref[1] % 61 * 5
                t1 = add_track_arc(
                    radius, pos, pos + 2, pad.GetNetCode(), layer_table_rev.get("F.Cu")
                )
                t3 = add_track(
                    get_ring_intersection_by_position(radius, pos + 2.5),
                    get_ring_intersection_by_position(radius - 4, pos + 2.5),
                    pad.GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )
                t4 = add_track(
                    t3.GetEnd(),
                    get_ring_intersection_by_position(
                        radius_from_net_number(num), pos + 2.5
                    ),
                    pad.GetNetCode(),
                    layer_table_rev.get("F.Cu"),
                )
                t2 = add_track(
                    t1.GetEnd(),
                    t3.GetStart(),
                    pad.GetNetCode(),
                    layer_table_rev.get("F.Cu"),
                )
                add_via(t2.GetEnd(), pad.GetNetCode())
                add_via(t3.GetEnd(), pad.GetNetCode())
                if module_ref[1] not in [61, 71, 72]:
                    add_via(t4.GetEnd(), pad.GetNetCode())
            elif module_ref[0] == "J":
                # (origin to layerSwitch): vertical track segment to change layer
                via_point_y = pad.GetParent().GetPosition()[1] / 1000000.0 - 4.0
                via_point_x = pad.GetPosition()[0] / 1000000.0
                add_track(
                    pad.GetPosition(),
                    pcbnew.wxPointMM(via_point_x, via_point_y),
                    pad.GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )
                add_via(pcbnew.wxPointMM(via_point_x, via_point_y), pad.GetNetCode())
                # (layerSwitch to Ring) equation with slope
                angle_rad = (
                    int(pad.GetPadName()) - 8 - 0.5
                ) / 30 * math.pi - math.pi / 2
                m = math.tan(angle_rad)
                # (pad to Intersection):
                # calculate intersection of y = x*m and y=constant=Y-Position of Pad
                intersection_x = pad.GetPosition()[0] / 1000000.0
                intersection_y = intersection_x * m
                add_track(
                    pcbnew.wxPointMM(via_point_x, via_point_y),
                    pcbnew.wxPointMM(intersection_x, intersection_y),
                    pad.GetNetCode(),
                    layer_table_rev.get("F.Cu"),
                )
                # (intersection to ring):
                # math.cos(math.pi/60) adjust the length to polygon
                ring_x_point = math.cos(angle_rad) * r * math.cos(math.pi / 60)
                ring_y_point = math.sin(angle_rad) * r * math.cos(math.pi / 60)
                add_track(
                    pcbnew.wxPointMM(intersection_x, intersection_y),
                    pcbnew.wxPointMM(ring_x_point, ring_y_point),
                    pad.GetNetCode(),
                    layer_table_rev.get("F.Cu"),
                )
                add_via(pcbnew.wxPointMM(ring_x_point, ring_y_point), pad.GetNetCode())


def add_track_with_intersection(circle_position, target_pad_position, net_code):
    m = circle_position[1] / circle_position[0]
    t = add_track(
        circle_position,
        pcbnew.wxPoint(target_pad_position[0], target_pad_position[0] * m),
        net_code,
        layer_table_rev.get("F.Cu"),
    )
    add_via(t.GetEnd(), net_code)
    add_track(t.GetEnd(), target_pad_position, net_code, layer_table_rev.get("B.Cu"))


def set_anode_tracks(nets_anode):
    for key, value in nets_anode.items():
        print("Adding Net:", str(key))
        print(
            list(
                map(
                    lambda x: (
                        x.GetParent().GetReference().encode("utf8"),
                        x.GetPadName(),
                    ),
                    value,
                )
            )
        )
        prefix, num = regex_split_annotation(key)
        if num <= 3:
            ring_pos = None
            con_pad_pos = value[15].GetPosition()
            radius = math.sqrt(
                (
                    math.pow(value[0].GetPosition()[0], 2)
                    + math.pow(value[0].GetPosition()[1], 2)
                )
            ) / math.pow(10, 6)
            for i in range(len(value) - 2):
                add_track(
                    value[i].GetPosition(),
                    value[i + 1].GetPosition(),
                    value[i].GetNetCode(),
                    layer_table_rev.get("F.Cu"),
                )
            if num == 1:
                ring_pos = get_ring_intersection_by_position(radius, 28.5)
            if num == 2:
                ring_pos = get_ring_intersection_by_position(radius, 31.5)
            if num == 0:
                t1 = add_track(
                    value[14].GetPosition(),
                    get_ring_intersection_by_position(radius, 14.5),
                    value[0].GetNetCode(),
                    layer_table_rev.get("F.Cu"),
                )
                add_via(t1.GetEnd(), value[0].GetNetCode())
                add_track(
                    t1.GetEnd(),
                    get_ring_intersection_by_position(radius + 3, 16),
                    value[0].GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )
                t3 = add_track_arc(
                    radius + 3,
                    16,
                    24,
                    value[0].GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )
                t4 = add_track(
                    t3.GetEnd(),
                    get_ring_intersection_by_position(radius - 2, 26.5),
                    value[0].GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )
                v2 = add_via(t4.GetEnd(), value[0].GetNetCode())
                ring_pos = v2.GetPosition()
            if num == 3:
                # t1 Not Needed as Track already there
                v1 = add_via(
                    get_ring_intersection_by_position(radius, 45.5),
                    value[0].GetNetCode(),
                )
                add_track(
                    v1.GetPosition(),
                    get_ring_intersection_by_position(radius + 3, 44),
                    value[0].GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )
                t3 = add_track_arc(
                    radius + 3,
                    44,
                    36,
                    value[0].GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )
                t4 = add_track(
                    t3.GetEnd(),
                    get_ring_intersection_by_position(radius - 2, 33.5),
                    value[0].GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )
                v2 = add_via(t4.GetEnd(), value[0].GetNetCode())
                ring_pos = v2.GetPosition()
            add_track_with_intersection(ring_pos, con_pad_pos, value[0].GetNetCode())
        elif num == 4:
            radius = math.sqrt(
                (
                    math.pow(value[0].GetPosition()[0], 2)
                    + math.pow(value[0].GetPosition()[1], 2)
                )
            ) / math.pow(10, 6)
            add_track_ring(radius, value[0].GetNetCode(), layer_table_rev.get("F.Cu"))
            for i in range(2):
                v1 = add_via(
                    get_ring_intersection_by_position(radius, [24.5, 35.5][i]),
                    value[0].GetNetCode(),
                )
                t1 = add_track(
                    v1.GetPosition(),
                    get_ring_intersection_by_position(radius - 6, [24.5, 35.5][i]),
                    value[0].GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )
                v2 = add_via(t1.GetEnd(), value[0].GetNetCode())
                add_track_with_intersection(
                    v2.GetPosition(),
                    value[[13, 12][i]].GetPosition(),
                    value[0].GetNetCode(),
                )
        elif num in [50, 51, 60, 61]:  # TODO: Sort Values?
            add_track(
                value[2].GetPosition(),
                value[1].GetPosition(),
                value[0].GetNetCode(),
                layer_table_rev.get("F.Cu"),
            )
            v = add_via(
                pcbnew.wxPoint(
                    value[2].GetPosition()[0], value[2].GetPosition()[1] - 3000000
                ),
                value[0].GetNetCode(),
            )
            add_track(
                v.GetEnd(),
                value[0].GetPosition(),
                value[0].GetNetCode(),
                layer_table_rev.get("B.Cu"),
            )
        elif num in [11, 21]:
            t1 = add_track(
                value[0].GetPosition(),
                pcbnew.wxPoint(value[1].GetPosition()[0], value[0].GetPosition()[1]),
                value[0].GetNetCode(),
                layer_table_rev.get("F.Cu"),
            )
            v1 = add_via(t1.GetEnd(), value[0].GetNetCode())
            add_track(
                v1.GetPosition(),
                value[1].GetPosition(),
                value[0].GetNetCode(),
                layer_table_rev.get("B.Cu"),
            )


def regex_split_annotation(str_):
    a, i = re.match(r"([/A-Za-z]*)(\d*)", str_).groups()
    return a, int(i)


if __name__ == "__main__":

    # note assumes dict are ordered, which they are in python3.9

    # find layer names
    for num in range(51):
        print(num)
        layer_table[num] = pcb.GetLayerName(num)
        layer_table_rev[pcb.GetLayerName(num)] = num
        # print("{} {}".format(i, pcb.GetLayerName(i)))
    # Delete Old Tracks
    print(f"deleting {len(list(pcb.GetTracks()))} tracks")
    for track in pcb.GetTracks():
        pcb.Delete(track)
    print(f"deleting {len(list(pcb.GetDrawings()))} drawings")
    for d in pcb.GetDrawings():
        pcb.Remove(d)

    # get and sort modules
    modules = {mod.GetReference(): mod for mod in sorted(pcb.GetModules())}
    modules_seconds = {k: modules[k] for k in ["D" + str(i) for i in range(1, 60 + 1)]}
    modules_hours = {k: modules[k] for k in ["D" + str(i) for i in range(61, 72 + 1)]}
    modules_digit = {k: modules[k] for k in ["U" + str(i) for i in range(1, 4 + 1)]}
    modules_separation = {k: modules[k] for k in ["D" + str(i) for i in [73, 74]]}
    modules_connector = {k: modules[k] for k in ["J" + str(i) for i in [1, 2]]}

    # get and sort nets
    nets = collections.defaultdict(list)
    for mod in modules.values():
        for pad in mod.Pads():
            nets[pad.GetShortNetname()].append(pad)
    nets_cathode = {k: v for k, v in nets.items() if k.startswith("k")}
    nets_anode = {k: v for k, v in nets.items() if k.startswith("a")}

    set_position_second_ring(modules_seconds, Radius)
    set_position_hour_ring(modules_hours, Radius * 1.1)
    set_position_digits(modules_digit, 3, 9.8)
    set_separation_modules(modules_separation, 10)
    set_connector_modules(modules_connector, 10)
    set_dimension(100)
    set_digits_connections(modules_digit, modules_separation)
    set_cathode_tracks(nets_cathode)
    set_anode_tracks(nets_anode)

    pcb.Save("autogen.kicad_pcb")
