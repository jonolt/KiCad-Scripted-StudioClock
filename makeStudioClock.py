# run in pcbnew python console
# import sys; sys.path.append("Documents/KiCadStudioClock")
# import makeStudioClock as msc

from __future__ import division  # for float division

import collections
import math
import re

import numpy as np
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
    if number < 15:
        f = 16 - number  # range(15 + 1, 0, -1)[number]
    else:
        f = 17
    return (
        Radius - 1.2 - (16 - number) * 0.75
    )  # this can be replaced by a more advanced equation


# add a track and add it: wxPoint, wxPoint, int, int -> Track
def add_track(start_location, stop_location, net_code, layer):
    """

    :param start_location:
    :param stop_location:
    :param net_code:
    :param layer:
    :return:
    """
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
    """rig position in parts of 60 part

    Note: not natural number position will start/end on the exact circle

    :param radius:
    :param start_ring_position:
    :param stop_ring_position:
    :param net_code:
    :param layer:
    :return:
    """
    t_start = None
    t_stop = None

    start_frac, _start_int = np.modf(start_ring_position)
    stop_frac, _stop_int = np.modf(stop_ring_position)
    if stop_ring_position > start_ring_position:
        if start_frac:
            _start_int += 1
        for clock_pos in np.arange(_start_int, _stop_int):
            t_stop = add_track(
                calc_xy_location_from_clock_position_WxPoint(radius, clock_pos),
                calc_xy_location_from_clock_position_WxPoint(radius, clock_pos + 1),
                net_code,
                layer,
            )
            if t_start is None:
                t_start = t_stop
    else:
        if stop_frac:
            _stop_int -= 1
        for clock_pos in np.arange(_start_int, _stop_int, -1):
            t_stop = add_track(
                calc_xy_location_from_clock_position_WxPoint(radius, clock_pos),
                calc_xy_location_from_clock_position_WxPoint(radius, clock_pos - 1),
                net_code,
                layer,
            )
            if t_start is None:
                t_start = t_stop
    if start_frac:
        t_start = add_track(
            get_ring_intersection_by_position(radius, start_ring_position),
            t_start.GetStart(),
            net_code,
            layer,
        )
    if stop_frac:
        t_stop = add_track(
            t_stop.GetEnd(),
            get_ring_intersection_by_position(radius, stop_ring_position),
            net_code,
            layer,
        )
    return t_start, t_stop


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


def digit_u_connect(pad_a, pad_b, distance):
    """connect two pads with a U shaped track via combination.

    The horizontal lines are on the bottom and the vertical lines are on the top layer.

    :param pad_a: one pad to connect
    :param pad_b: other pad to connect
    :param distance: distance of the horizontal line to the pad
    :return: via further away from the center
    """
    net_code = pad_a.GetNetCode()
    assert net_code == pad_b.GetNetCode()  # simple consistency check
    pad_a_loc = pad_a.GetPosition()
    pad_b_loc = pad_b.GetPosition()
    via_a_loc = pcbnew.wxPointMM(
        pad_a_loc[0] / 1000000.0, pad_a_loc[1] / 1000000.0 + distance
    )
    via_b_loc = pcbnew.wxPointMM(
        pad_b_loc[0] / 1000000.0, pad_b_loc[1] / 1000000.0 + distance
    )
    add_track(pad_a_loc, via_a_loc, net_code, layer_table_rev.get("F.Cu"))
    via_a = add_via(via_a_loc, net_code)
    add_track(via_a_loc, via_b_loc, net_code, layer_table_rev.get("B.Cu"))
    via_b = add_via(via_b_loc, net_code)
    add_track(via_b_loc, pad_b_loc, net_code, layer_table_rev.get("F.Cu"))
    if math.fabs(via_a_loc[0]) <= math.fabs(via_b_loc[0]):
        return via_b
    else:
        return via_a


# Input: eq1radiusPolygon: Equation1, radius of the circle represented by the Polygon
# 		eq2slope: Equation2, Slope of the beam intersecting the circle
def get_ring_intersection(eq_1_radius_polygon, eq_2_slope, left_neg_1_right_1):
    """

    :param eq_1_radius_polygon:
    :param eq_2_slope:
    :param left_neg_1_right_1:
    :return:
    """
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
    """

    :param eq_1_radius_polygon:
    :param position:
    :return:
    """
    m = math.atan(position * math.pi / 30 - math.pi / 2)
    return get_ring_intersection(
        eq_1_radius_polygon, m, 1
    )  # (position-30)/math.fabs(position-30))


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


def regex_split_annotation(str_):
    a, i = re.match(r"([/A-Za-z]*)(\d*)", str_).groups()
    return a, int(i)


if __name__ == "__main__":

    pcb_dimension_length = 100
    radius_seconds = Radius
    radius_hours = Radius * 1.1

    digit_space = 3
    # only change when digit footprint changes
    digit_width = 10
    digit_high = 10
    digit_orientation = 2700

    # note assumes dict are ordered, which they are in python3.9

    # collect layer names
    for num in range(51):
        print(num)
        layer_table[num] = pcb.GetLayerName(num)
        layer_table_rev[pcb.GetLayerName(num)] = num
        # print("{} {}".format(i, pcb.GetLayerName(i)))

    # delete old, existing tracks and drawings
    print(f"deleting {len(list(pcb.GetTracks()))} tracks")
    for track in pcb.GetTracks():
        pcb.Delete(track)
    print(f"deleting {len(list(pcb.GetDrawings()))} drawings")
    for d in pcb.GetDrawings():
        pcb.Remove(d)

    # collect and sort modules into groups (second, hour, digit, seperator, connector)
    modules = {mod.GetReference(): mod for mod in sorted(pcb.GetModules())}
    modules_seconds = {k: modules[k] for k in ["D" + str(i) for i in range(1, 60 + 1)]}
    modules_hours = {k: modules[k] for k in ["D" + str(i) for i in range(61, 72 + 1)]}
    modules_digit = {k: modules[k] for k in ["U" + str(i) for i in range(1, 4 + 1)]}
    modules_separation = {k: modules[k] for k in ["D" + str(i) for i in [73, 74]]}
    modules_connector = {k: modules[k] for k in ["J" + str(i) for i in [1, 2]]}

    # collect and sort nets into groups (anode, cathode)
    nets = collections.defaultdict(list)
    for mod in modules.values():
        for pad in mod.Pads():
            nets[pad.GetShortNetname()].append(pad)
    nets_cathode = {k: v for k, v in nets.items() if k.startswith("k")}
    nets_anode = {k: v for k, v in nets.items() if k.startswith("a")}

    # position the second modules in a circle
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

    # position the hour modules in a circle
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

    # position the digit and digit seperator modules (4x7seg, 2xled)
    for key, value in modules_digit.items():
        _, i = regex_split_annotation(key)
        value.SetPosition(
            calc_dig_location_from_position(i - 1, digit_space, digit_width)
        )
        if digit_orientation is not None:  # else do nothing
            value.SetOrientation(digit_orientation)
        print("Placed: Digit %d at %s" % (i, str(value.GetPosition())))

    for key, module in modules_separation.items():
        _, i = regex_split_annotation(key)  # TODO fix one must be plus
        sign = 1 if key == "D73" else -1
        module.SetPosition(pcbnew.wxPointMM(0, sign * digit_high * 0.4))
        module.SetOrientation(2700)
        print("Placed: Seperator %s at %s" % (key, str(module.GetPosition())))

    # position the two connector modules on the back of the clock
    for key, module in modules_connector.items():
        _, i = regex_split_annotation(key)
        sign = -1 if key == "J1" else 1
        module.SetPosition(pcbnew.wxPointMM(0, sign * digit_high * 1.5))
        module.SetOrientation(2700)
        # module.Se # TODO change front to back side
        print("Placed: Connector %s at %s" % (key, str(module.GetPosition())))

    # set the pcb size
    _pcb_corners = [[-1, -1], [-1, 1], [1, 1], [1, -1]]
    print(
        "Setting Board Dimensions too:"
        + str(pcb_dimension_length)
        + "x"
        + str(pcb_dimension_length)
    )
    tmp_print = []
    for i in range(4):
        seg = pcbnew.DRAWSEGMENT(pcb)
        pcb.Add(seg)
        seg.SetStart(
            pcbnew.wxPointMM(
                _pcb_corners[i][0] * pcb_dimension_length / 2,
                _pcb_corners[i][1] * pcb_dimension_length / 2,
            )
        )
        seg.SetEnd(
            pcbnew.wxPointMM(
                _pcb_corners[(i + 1) % 4][0] * pcb_dimension_length / 2,
                _pcb_corners[(i + 1) % 4][1] * pcb_dimension_length / 2,
            )
        )
        seg.SetLayer(layer_table_rev.get("Edge.Cuts"))
        tmp_print.append(seg.GetStart())
    print("Board Corners:" + str(tmp_print))

    # draw the cathode tracks of the digit (using modules as base for drawing)
    print(
        f"Connecting Digits {[x.GetReference() for x in modules_digit.values()]} "
        f"and Separation LEDs {[x.GetReference() for x in modules_separation.values()]}"
        f" with Nets"
    )
    net_norm_distance_dict = dict(
        k0=-3,
        k1=3,
        k2=-4,
        k3=4,
        k4=-5,
        k5=5,
        k6=-6,
        k7=6,
        k8=-3,
        k9=-4,
        k10=4,
        k11=-5,
        k12=5,
        k13=-6,
        k14=6,
        k15=3,
    )
    pads_dict = collections.defaultdict(dict)
    for i, key in enumerate(modules_digit):
        for pad in modules_digit[key].Pads():
            pads_dict[i][int(pad.GetPadName())] = pad
        pads_dict[i].pop(3)
        pads_dict[i].pop(8)
    outer_location = 0

    net_digit_via_dict = dict()
    for i in pads_dict[0].keys():
        net_short_name = pads_dict[0][i].GetNet().GetShortNetname()
        net_digit_via_dict[net_short_name] = digit_u_connect(
            pads_dict[0][i],
            pads_dict[1][i],
            net_norm_distance_dict[net_short_name] * 1.4,
        )
        net_short_name = pads_dict[2][i].GetNet().GetShortNetname()
        net_digit_via_dict[net_short_name] = digit_u_connect(
            pads_dict[2][i],
            pads_dict[3][i],
            net_norm_distance_dict[net_short_name] * 1.4,
        )

    outer_location = max(v.GetPosition().x for v in net_digit_via_dict.values())
    for net_name, via in net_digit_via_dict.items():
        net_side = np.sign(via.GetPosition().x)
        if abs(via.GetPosition().x) < outer_location:
            t = add_track(
                via.GetPosition(),
                pcbnew.wxPoint(
                    int(outer_location * net_side),
                    via.GetPosition().y,
                ),
                via.GetNetCode(),
                layer_table_rev.get("B.Cu"),
            )
            via = add_via(t.GetEnd(), t.GetNetCode())
            net_digit_via_dict[net_name] = via
        num = regex_split_annotation(net_name)[1]
        if net_name == "k15":
            num = -1
        r = radius_from_net_number(num)
        m = via.GetPosition().y / outer_location * net_side
        t = add_track(
            via.GetPosition(),
            get_ring_intersection(r, m, int(np.sign(via.GetPosition().x))),
            via.GetNetCode(),
            layer_table_rev.get("F.Cu"),
        )
        add_via(t.GetEnd(), t.GetNetCode())

    # draw the cathode tracks connecting the separation leds to k15
    k15_vias = [
        track
        for track in pcb.GetTracks()
        if isinstance(track, pcbnew.VIA) and track.GetNet().GetShortNetname() == "k15"
    ]
    k15_via = (
        k15_vias[0]
        if k15_vias[0].GetPosition().x < k15_vias[1].GetPosition().x
        else k15_vias[1]
    )
    k15_led_pads = [
        pad
        for pad in pcb.GetPads()
        if pad.GetNet().GetShortNetname() == "k15"
        and pad.GetParent().GetReference().startswith("D")
    ]
    t = add_track(
        k15_via.GetPosition(),
        pcbnew.wxPoint(1270000, k15_via.GetPosition().y),
        k15_via.GetNetCode(),
        layer_table_rev.get("B.Cu"),
    )
    t = add_track(
        t.GetEnd(),
        pcbnew.wxPoint(
            t.GetEnd().x, max([pad.GetPosition().y for pad in k15_led_pads])
        ),
        t.GetNetCode(),
        t.GetLayer(),
    )
    for pad_ in k15_led_pads:
        v = add_via(pcbnew.wxPoint(t.GetEnd().x, pad_.GetPosition().y), t.GetNetCode())
        add_track(
            pad_.GetPosition(),
            v.GetPosition(),
            t.GetNetCode(),
            layer_table_rev.get("F.Cu"),
        )

    # draw the cathode tracks of ring leds (iterating over all nets)
    for key, value in nets_cathode.items():
        prefix, num = regex_split_annotation(key)
        if key == "k15":
            num = -1
        r = radius_from_net_number(num)
        print("Adding Net:", str(key), "with radius", str(r))
        add_track_ring(r, value[0].GetNetCode(), layer_table_rev.get("B.Cu"))
        for pad in value:
            module_ref = regex_split_annotation(pad.GetParent().GetReference())
            if module_ref[0] == "D" and module_ref[1] <= 60:  # seconds
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
            elif module_ref[0] == "D" and module_ref[1] <= 72:  # hours
                radius = math.sqrt(
                    (
                        math.pow(pad.GetPosition()[0], 2)
                        + math.pow(pad.GetPosition()[1], 2)
                    )
                ) / math.pow(10, 6)
                pos = module_ref[1] % 61 * 5
                t1 = add_track_arc(
                    radius, pos, pos + 2, pad.GetNetCode(), layer_table_rev.get("F.Cu")
                )[1]
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
            elif module_ref[0] == "J":  # connectors
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

    # draw the anode tracks (iterating over all nets)
    for key, value in nets_anode.items():
        print("Adding Net:", str(key))
        prefix, num = regex_split_annotation(key)
        if num <= 3:  # 4 segments of the LED ring
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
            if num == 0:
                t_start, t_stop = add_track_arc(
                    radius_from_net_number(15),
                    13.5,
                    26.5,
                    value[-1].GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )

                t0 = add_track(
                    get_ring_intersection_by_position(radius, 13.5),
                    t_start.GetStart(),
                    value[-1].GetNetCode(),
                    layer_table_rev.get("F.Cu"),
                )
                add_via(t0.GetEnd(), t0.GetNetCode())

                v = add_via(t_stop.GetEnd(), t_stop.GetNetCode())
                ring_pos = v.GetPosition()
            if num == 1:
                ring_pos = get_ring_intersection_by_position(radius, 28.5)
            if num == 2:
                ring_pos = get_ring_intersection_by_position(radius, 31.5)
            if num == 3:
                t_start, t_stop = add_track_arc(
                    radius_from_net_number(15),
                    46.5,
                    33.5,
                    value[-1].GetNetCode(),
                    layer_table_rev.get("B.Cu"),
                )

                t0 = add_track(
                    get_ring_intersection_by_position(radius, 46.5),
                    t_start.GetStart(),
                    value[-1].GetNetCode(),
                    layer_table_rev.get("F.Cu"),
                )
                add_via(t0.GetEnd(), t0.GetNetCode())

                v = add_via(t_stop.GetEnd(), t_stop.GetNetCode())
                ring_pos = v.GetPosition()
            add_track_with_intersection(ring_pos, con_pad_pos, value[0].GetNetCode())
        elif num == 4:
            radius = math.sqrt(
                (
                    math.pow(value[0].GetPosition()[0], 2)
                    + math.pow(value[0].GetPosition()[1], 2)
                )
            ) / math.pow(10, 6)
            inner_radius = radius_from_net_number(-2)
            add_track_ring(radius, value[0].GetNetCode(), layer_table_rev.get("F.Cu"))
            t = add_track(
                get_ring_intersection_by_position(radius, 29.5),
                calc_xy_location_from_clock_position_WxPoint(inner_radius, 29.5),
                value[-1].GetNetCode(),
                layer_table_rev.get("F.Cu"),
            )
            v = add_via(t.GetEnd(), t.GetNetCode())
            t_start, t_stop = add_track_arc(
                inner_radius, 36, 24, t.GetNetCode(), layer_table_rev.get("B.Cu")
            )

            def distance(wx1, wx2):
                return np.sqrt(np.square(wx1.x - wx2.x) + np.square(wx1.y - wx2.y))

            for pad in modules_connector["J2"].Pads():
                if not pad.GetNet().GetShortNetname() == "a4":
                    continue
                dist1 = distance(pad.GetPosition(), t_start.GetStart())
                dist2 = distance(pad.GetPosition(), t_stop.GetEnd())
                if dist1 < dist2:
                    t_pos = t_start.GetStart()
                else:
                    t_pos = t_stop.GetEnd()
                add_via(t_pos, pad.GetNetCode())
                add_track_with_intersection(t_pos, pad.GetPosition(), pad.GetNetCode())
        elif num in [50, 51, 60, 61]:  # TODO: Sort Values?
            pad_connector = next(
                pad_
                for pad_ in value
                if pad_.GetParent().GetReference().startswith("J")
            )
            value.remove(pad_connector)
            add_track(
                value[0].GetPosition(),
                value[1].GetPosition(),
                value[0].GetNetCode(),
                layer_table_rev.get("F.Cu"),
            )
            if value[0].GetPosition().y > 0:
                pad_digit = value[0]
            else:
                pad_digit = value[1]
            # digit_u_connect(pad_digit, pad_connector, -2)
            v = add_via(
                pcbnew.wxPoint(
                    pad_digit.GetPosition()[0], pad_digit.GetPosition()[1] - 3000000
                ),
                pad_digit.GetNetCode(),
            )
            t = add_track(
                v.GetEnd(),
                pcbnew.wxPoint(
                    pad_connector.GetPosition().x,
                    v.GetPosition().y
                    + abs(pad_connector.GetPosition().x - v.GetPosition().x),
                ),
                value[0].GetNetCode(),
                layer_table_rev.get("B.Cu"),
            )
            add_track(
                t.GetEnd(), pad_connector.GetPosition(), t.GetNetCode(), t.GetLayer()
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

    pcb.Save("autogen.kicad_pcb")
