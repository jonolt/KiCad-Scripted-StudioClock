#!/usr/bin/env python
# -*- coding: utf-8 -*-
# I started this script with a structure in mind, but din't hold on to it so it istn't consistent.
# Some functions won't sort the Lists. You migth get strange results when the list shufled for some reason

# run in pcbew python console
# import sys; sys.path.append("Documents/KiCadStudioClock"); import makeStudioClock as msc;

from __future__ import division  # for float division
import pcbnew
import collections
import itertools
import math


Modules = {}
Nets = {}
Radius = 42

layertable = {}
layertableRev = {}

# Uncomment to work with the File (run in project directory):
pcb = pcbnew.LoadBoard("StudioClock.kicad_pcb")
pcb.BuildListOfNets() #neded fo load file
# Work in KiCad Console:
# pcb = pcbnew.GetBoard()




# calc rotation angle (rad) with Position in Clock: float -> float
def calcRadAngleFromClockPosition(clockPosition):
    return -math.pi / 30 * (clockPosition % 60) - math.pi


# calc ratation angle (deg) with Position: float -> float
def calcDegAngleFromClockPosition(clockPosition):
    return math.degrees(calcRadAngleFromClockPosition(clockPosition))


# calc the Position(s) with the Radius and an Angle: float, float -> float/float/wxPoint
def calcXLocationFromClockPositionMM(radius, clockPosition):
    return (
        math.sin(calcRadAngleFromClockPosition(clockPosition)) * radius
    )  # +originOffsetXY[0]


def calcYLocationFromClockPositionMM(radius, clockPosition):
    return (
        math.cos(calcRadAngleFromClockPosition(clockPosition)) * radius
    )  # +originOffsetXY[1]


def calcXYLocationFromClockPositionWxPoint(radius, clockPosition):
    return pcbnew.wxPointMM(
        calcXLocationFromClockPositionMM(radius, clockPosition),
        calcYLocationFromClockPositionMM(radius, clockPosition),
    )


# calc ofset of gigit (0,1,2,3)
def calcDigLocationFromPosition(digitPosition, digitSpace, digitWidth, digitHigth):
    posX = [
        -1.5 - digitSpace / digitWidth * 2,
        -0.5 - digitSpace / digitWidth,
        0.5 + digitSpace / digitWidth,
        1.5 + digitSpace / digitWidth * 2,
    ][digitPosition] * digitWidth
    posY = 0
    return pcbnew.wxPointMM(
        posX, posY
    )  # (posX+originOffsetXY[0],posY+originOffsetXY[1])


def radiusFromNetNumber(number):
    return (
        Radius - 1.2 - (range(15 + 1, 0, -1)[number] * 0.75)
    )  # this can be replaced by a more advanced equation


# add a track and add it: wxPoint, wxPoint, int, int -> Track
def addTrack(startLocation, stopLocation, netCode, layer):
    t = pcbnew.TRACK(pcb)
    pcb.Add(t)
    t.SetStart(startLocation)
    t.SetEnd(stopLocation)
    t.SetNetCode(netCode)
    t.SetLayer(layer)
    t.SetWidth(300000)
    return t


# add an arc of tracks with the Position Idices of the SecondsLeds: float, int, int, int, int -> Track
def addTrackArc(radius, startRingPosition, stopRingPosition, netCode, layer):
    t = None
    if stopRingPosition > startRingPosition:
        for i in range(startRingPosition, stopRingPosition):
            t = addTrack(
                calcXYLocationFromClockPositionWxPoint(radius, i),
                calcXYLocationFromClockPositionWxPoint(radius, i + 1),
                netCode,
                layer,
            )
    else:
        for i in range(startRingPosition, stopRingPosition, -1):
            t = addTrack(
                calcXYLocationFromClockPositionWxPoint(radius, i),
                calcXYLocationFromClockPositionWxPoint(radius, i - 1),
                netCode,
                layer,
            )
    return t


# add a full Track ring with the desired Radius: float, int, int
def addTrackRing(radius, netCode, layer):
    addTrackArc(radius, 0, 61, netCode, layer)


# add a via at the Position: wxPoint -> Via
def addVia(position, net):
    v = pcbnew.VIA(pcb)
    pcb.Add(v)
    v.SetPosition(position)
    v.SetWidth(300000)
    v.SetDrill(200000)
    v.SetViaType(pcbnew.VIA_THROUGH)
    v.SetLayerPair(layertableRev.get("F.Cu"), layertableRev.get("B.Cu"))
    v.SetNetCode(net)
    return v


def split_string(string_):

    # TODO replace with regex
    ref = ""
    num = ""
    for s in string_:
        if s.isdigit():
            num.join(s)
        else:
            ref.join(s)
    return ref, num


def getParentRef(pad):
    return split_string(pad.GetParent().GetReference().encode("utf-8"))


def findNets(modules):
    nets = {}
    for mod in modules.values():
        for pad in mod.Pads():
            netname = pad.GetShortNetname().encode("utf-8")
            # print "Found Net:", netname
            if split_string(netname) not in nets.keys():
                nets.update({split_string(netname): []})
            nets.get(split_string(netname)).append(pad)
    # Order The Dictionary
    nets = collections.OrderedDict(sorted(nets.items(), key=lambda t: t[0]))
    for code, num in nets.keys():
        print("Found Net: %s%s with %d pads" % (code, num, len(nets.get((code, num)))))
    return nets


def getSecondModules(modules_dict):
    odict = collections.OrderedDict()
    for key, value in modules_dict.items():
        if key[0] == "D" and key[1] in range(1, 60 + 1):
            odict.update({key: value})
    return odict


def getHourModules(modules_dict):
    odict = collections.OrderedDict()
    for key, value in modules_dict.items():
        if key[0] == "D" and key[1] in range(61, 72 + 1):
            odict.update({key: value})
    return odict


def getDigitModules(modules_dict):
    odict = collections.OrderedDict()
    for key, value in modules_dict.items():
        if key[0] == "U" and key[1] in range(1, 4 + 1):
            odict.update({key: value})
    return odict


def getSeparationModules(modules_dict):
    odict = collections.OrderedDict()
    for key, value in modules_dict.items():
        if key[0] == "D" and key[1] in [73, 74]:
            odict.update({key: value})
    return odict


def getConnectorModules(modules_dict):
    odict = collections.OrderedDict()
    for key, value in modules_dict.items():
        if key[0] == "J":
            odict.update({key: value})
    return odict


def getCathodeNets(nets_dict):
    odict = collections.OrderedDict()
    for key, value in nets_dict.items():
        if key[0] == "k":
            odict.update({key: value})
    return odict


def getAnodeNets(nets_dict):
    odict = collections.OrderedDict()
    for key, value in nets_dict.items():
        if key[0] == "a":
            odict.update({key: value})
    return odict


def setPositionSecondRing(modulesSeconds, radiusSeconds):
    for key, value in modulesSeconds.items():
        _, i = regex_split_annotation(key)
        value.SetOrientation((calcDegAngleFromClockPosition(i - 1) - 90) * 10)
        value.SetPosition(
            calcXYLocationFromClockPositionWxPoint(radiusSeconds, i - 1)
        )
        print(
            "Placed: Second %s at %s with rot %s"
            % (
                key,
                str(value.GetPosition()),
                str(value.GetOrientation()),
            )
        )


def setPositionHourRing(modulesHours, radiusHours):
    for key, value in modulesHours.items():
        _, i = regex_split_annotation(key)
        value.SetOrientation(
            (calcDegAngleFromClockPosition((i - 61) * 5) - 90) * 10
        )
        value.SetPosition(
            calcXYLocationFromClockPositionWxPoint(radiusHours, (i - 61) * 5)
        )
        print(
            "Placed: Hour %s at %s with rot %s"
            % (
                key,
                str(value.GetPosition()),
                str(value.GetOrientation()),
            )
        )


def setPositionDigits(modulesDigits, digitSpace, digitWidth, digitHigth, revers=True):
    for key, value in modulesDigits.items():
        _, i = regex_split_annotation(key)
        value.SetPosition(
            calcDigLocationFromPosition(i - 1, digitSpace, digitWidth, digitHigth)
        )
        if revers:
            value.SetOrientation(2700)
        print("Placed: Digit %d at %s" % (i, str(value.GetPosition())))


def setSeparationModules(modulesSep, digitHigth):
    for key, module in modulesSep.items():
        _, i = regex_split_annotation(key)  # TODO fix one must be plus
        sign = 1 if key=="D73" else -1
        module.SetPosition(pcbnew.wxPointMM(0, sign * digitHigth * 0.4))
        module.SetOrientation(2700)
        print("Placed: Seperator %s at %s" % (key, str(module.GetPosition())))


def setConnectorModules(modulesCon, digitHigth):
    for key, module in modulesCon.items():
        _, i = regex_split_annotation(key)
        sign = -1 if key=="J1" else 1
        module.SetPosition(pcbnew.wxPointMM(0, sign * digitHigth * 1.5))
        module.SetOrientation(2700)
        #module.Se # TODO change front to back side
        print("Placed: Connector %s at %s" % (key, str(module.GetPosition())))



def setDimension(length):
    corners = [[-1, -1], [-1, 1], [1, 1], [1, -1]]
    print("Setting Board Dimensions too:" + str(length) + "x" + str(length))
    tmpPrint = []
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
        seg.SetLayer(layertableRev.get("Edge.Cuts"))
        tmpPrint.append(seg.GetStart())
    print("Board Corners:" + str(tmpPrint))


def uConnect(location1, location2, offset, netCode):
    locationA = pcbnew.wxPointMM(
        location1[0] / 1000000.0, location1[1] / 1000000.0 + offset
    )
    locationB = pcbnew.wxPointMM(
        location2[0] / 1000000.0, location2[1] / 1000000.0 + offset
    )
    addTrack(location1, locationA, netCode, layertableRev.get("F.Cu"))
    addVia(locationA, netCode)
    addTrack(locationA, locationB, netCode, layertableRev.get("B.Cu"))
    addVia(locationB, netCode)
    addTrack(locationB, location2, netCode, layertableRev.get("F.Cu"))
    if math.fabs(locationA[0]) <= math.fabs(locationB[0]):
        return locationB
    else:
        return locationA


# Input: eq1radiusPolygon: Equation1, radius of the circle represented by the Polygon
# 		eq2slope: Equation2, Slope of the beam intersecting the circle
def getRingIntersection(eq1radiusPolygon, eq2slope, leftneg1rigth1):
    m = eq2slope  # listLeftVias[i][1]/outerLocation
    r = eq1radiusPolygon  # radiusFromNetNumber(splitString(padsLists[0][i].GetNetname().encode('utf-8'))[1], 15, Radius)
    alpha = math.pi / 60
    epsilon = math.tan(m) % (alpha * 2)
    b = math.cos(alpha) * r
    d = b / math.cos(alpha - epsilon)
    ringXPoint = math.cos(math.tan(m)) * d * leftneg1rigth1
    ringYpoint = math.sin(math.tan(m)) * d * leftneg1rigth1
    return pcbnew.wxPointMM(ringXPoint, ringYpoint)


def getRingIntersectionByPosition(eq1radiusPolygon, position):
    m = math.atan(position * math.pi / 30 - math.pi / 2)
    return getRingIntersection(
        eq1radiusPolygon, m, 1
    )  # (position-30)/math.fabs(position-30))


def setDigitsConections(modulesDigits, modulesSeperationLeds):

    print(
        "Connecting Digits %s and Separatrion LEDs %s with Nets"
        % (
            str(map(lambda x: x.GetReference().encode("utf8"), modulesDigits.values())),
            str(
                list(map(  # TODO do this as list comprehension
                    lambda x: x.GetReference().encode("utf8"),
                    modulesSeperationLeds.values(),
                ))
            ),
        )
    )
    padsLists = [None] * (4)
    for i, key in enumerate(modulesDigits):
        padsLists[i] = [None] * 10
        for pad in modulesDigits[key].Pads():
            padsLists[i][int(pad.GetPadName()) - 1] = pad
        padsLists[i].pop(2)
        padsLists[i].pop(6)
    outerLocation = 0
    listLeftVias = [None] * (8)
    listRigthVias = [None] * (8)
    for i in range(8):
        listLeftVias[i] = uConnect(
            padsLists[0][i].GetPosition(),
            padsLists[1][i].GetPosition(),
            [6, 5, 4, 3, -3, -4, -5, -6][i] * 1.4,
            padsLists[0][i].GetNetCode(),
        )
        listRigthVias[i] = uConnect(
            padsLists[2][i].GetPosition(),
            padsLists[3][i].GetPosition(),
            [3, 4, 5, 6, -6, -5, -4, -3][i] * 1.4,
            padsLists[2][i].GetNetCode(),
        )
        if listLeftVias[i][0] < outerLocation:
            outerLocation = listLeftVias[i][0]
    # Left Side
    for i in range(8):
        t = addTrack(
            listLeftVias[i],
            pcbnew.wxPoint(outerLocation, listLeftVias[i][1]),
            padsLists[0][i].GetNetCode(),
            layertableRev.get("B.Cu"),
        )
        if i not in [5 - 1 - 1, 6 - 1 - 1]:
            addVia(t.GetEnd(), padsLists[0][i].GetNetCode())
        m = listLeftVias[i][1] / outerLocation
        r = radiusFromNetNumber(
            regex_split_annotation(padsLists[0][i].GetNetname())[1]
        )
        t2 = addTrack(
            t.GetEnd(),
            getRingIntersection(r, m, -1),
            padsLists[0][i].GetNetCode(),
            layertableRev.get("F.Cu"),
        )
        if i == 6 - 1 - 1:
            t2.SetLayer(layertableRev.get("B.Cu"))
            continue
        addVia(t2.GetEnd(), padsLists[0][i].GetNetCode())
    # Rigth Side
    for i in range(8):
        if i == 1 - 1:
            continue
        t = addTrack(
            listRigthVias[i],
            pcbnew.wxPoint(-outerLocation, listRigthVias[i][1]),
            padsLists[2][i].GetNetCode(),
            layertableRev.get("B.Cu"),
        )
        if i not in [1 - 1, 10 - 1 - 1]:
            addVia(t.GetEnd(), padsLists[2][i].GetNetCode())
        m = listRigthVias[i][1] / -outerLocation
        r = radiusFromNetNumber(
            regex_split_annotation(padsLists[2][i].GetNetname())[1]
        )
        t2 = addTrack(
            t.GetEnd(),
            getRingIntersection(r, m, 1),
            padsLists[2][i].GetNetCode(),
            layertableRev.get("F.Cu"),
        )
        if i == 1:
            start = (padsLists[3][0].GetPosition()[0], listRigthVias[i])
            ledPads = []
            ledModulesKeys = modulesSeperationLeds.keys()
            for key in ledModulesKeys:
                for pad in modulesSeperationLeds[key].Pads():
                    if pad.GetNetCode() == padsLists[2][i - 1].GetNetCode():
                        ledPads.append(pad)
            t3 = addTrack(
                pcbnew.wxPoint(
                    padsLists[2][0].GetPosition()[0], listRigthVias[i - 1][1]
                ),
                pcbnew.wxPoint(ledPads[0].GetPosition()[0], listRigthVias[i - 1][1]),
                padsLists[2][i - 1].GetNetCode(),
                layertableRev.get("B.Cu"),
            )
            t4 = addTrack(
                t3.GetEnd(),
                pcbnew.wxPoint(
                    ledPads[1].GetPosition()[0], ledPads[1].GetPosition()[1] - 2000000
                ),
                padsLists[2][i - 1].GetNetCode(),
                layertableRev.get("B.Cu"),
            )
            addVia(t4.GetEnd(), padsLists[2][i - 1].GetNetCode())
            addTrack(
                t4.GetEnd(),
                ledPads[1].GetPosition(),
                padsLists[2][i - 1].GetNetCode(),
                layertableRev.get("F.Cu"),
            )
            v1 = addVia(
                pcbnew.wxPoint(t3.GetEnd()[0] + 1500000, t3.GetEnd()[1]),
                padsLists[2][i - 1].GetNetCode(),
            )
            t5 = addTrack(
                v1.GetPosition(),
                t3.GetEnd(),
                padsLists[2][i - 1].GetNetCode(),
                layertableRev.get("F.Cu"),
            )
            addTrack(
                t5.GetEnd(),
                ledPads[0].GetPosition(),
                padsLists[2][i - 1].GetNetCode(),
                layertableRev.get("F.Cu"),
            )
            conPos = list(modules["J1"].Pads())[15].GetPosition()
            t6 = addTrack(
                conPos,
                pcbnew.wxPoint(conPos[0], listRigthVias[i - 1][1]),
                padsLists[2][i - 1].GetNetCode(),
                layertableRev.get("B.Cu"),
            )
        else:
            addVia(t2.GetEnd(), padsLists[0][i].GetNetCode())


def setCathodeTraks(netsCathode, maxRadius):
    for key, value in netsCathode.items():
        prefix, num = regex_split_annotation(key)
        if key == "k15":
            continue
        r = radiusFromNetNumber(num)
        print("Adding Net:", str(key), "with radius", str(r))
        addTrackRing(r, value[0].GetNetCode(), layertableRev.get("B.Cu"))
        for pad in value:
            moduleRef = regex_split_annotation(pad.GetParent().GetReference())
            if moduleRef[0] == "D" and moduleRef[1] <= 60:
                cornerLocation = calcXYLocationFromClockPositionWxPoint(
                    r, moduleRef[1] - 1
                )
                addTrack(
                    pad.GetPosition(),
                    cornerLocation,
                    pad.GetNetCode(),
                    layertableRev.get("F.Cu"),
                )
                addVia(cornerLocation, pad.GetNetCode())
            elif moduleRef[0] == "D" and moduleRef[1] <= 72:
                radius = math.sqrt(
                    (
                        math.pow(pad.GetPosition()[0], 2)
                        + math.pow(pad.GetPosition()[1], 2)
                    )
                ) / math.pow(10, 6)
                pos = moduleRef[1] % 61 * 5
                t1 = addTrackArc(
                    radius, pos, pos + 2, pad.GetNetCode(), layertableRev.get("F.Cu")
                )
                t3 = addTrack(
                    getRingIntersectionByPosition(radius, pos + 2.5),
                    getRingIntersectionByPosition(radius - 4, pos + 2.5),
                    pad.GetNetCode(),
                    layertableRev.get("B.Cu"),
                )
                t4 = addTrack(
                    t3.GetEnd(),
                    getRingIntersectionByPosition(
                        radiusFromNetNumber(num), pos + 2.5
                    ),
                    pad.GetNetCode(),
                    layertableRev.get("F.Cu"),
                )
                t2 = addTrack(
                    t1.GetEnd(),
                    t3.GetStart(),
                    pad.GetNetCode(),
                    layertableRev.get("F.Cu"),
                )
                addVia(t2.GetEnd(), pad.GetNetCode())
                addVia(t3.GetEnd(), pad.GetNetCode())
                if moduleRef[1] not in [61, 71, 72]:
                    addVia(t4.GetEnd(), pad.GetNetCode())
            elif moduleRef[0] == "J":
                # (origin to layerSwitch): vertical track segment to change layer
                viaPointY = pad.GetParent().GetPosition()[1] / 1000000.0 - 4.0
                viaPointX = pad.GetPosition()[0] / 1000000.0
                addTrack(
                    pad.GetPosition(),
                    pcbnew.wxPointMM(viaPointX, viaPointY),
                    pad.GetNetCode(),
                    layertableRev.get("B.Cu"),
                )
                addVia(pcbnew.wxPointMM(viaPointX, viaPointY), pad.GetNetCode())
                # (layerSwitch to Ring) eqution with slope
                angleRad = (
                    int(pad.GetPadName()) - 8 - 0.5
                ) / 30 * math.pi - math.pi / 2
                m = math.tan(angleRad)
                # (pad to Intersection): calculate intersection of y = x*m and y=constant=Y-Position of Pad
                intersectionX = pad.GetPosition()[0] / 1000000.0
                intersectionY = intersectionX * m
                addTrack(
                    pcbnew.wxPointMM(viaPointX, viaPointY),
                    pcbnew.wxPointMM(intersectionX, intersectionY),
                    pad.GetNetCode(),
                    layertableRev.get("F.Cu"),
                )
                # (intersection to ring): math.cos(math.pi/60) adjust the length to polygon
                ringXPoint = math.cos(angleRad) * r * math.cos(math.pi / 60)
                ringYpoint = math.sin(angleRad) * r * math.cos(math.pi / 60)
                addTrack(
                    pcbnew.wxPointMM(intersectionX, intersectionY),
                    pcbnew.wxPointMM(ringXPoint, ringYpoint),
                    pad.GetNetCode(),
                    layertableRev.get("F.Cu"),
                )
                addVia(pcbnew.wxPointMM(ringXPoint, ringYpoint), pad.GetNetCode())


def addTrackWithIntersection(circlePosition, targetPadPosition, netCode):
    m = circlePosition[1] / circlePosition[0]
    t = addTrack(
        circlePosition,
        pcbnew.wxPoint(targetPadPosition[0], targetPadPosition[0] * m),
        netCode,
        layertableRev.get("F.Cu"),
    )
    addVia(t.GetEnd(), netCode)
    addTrack(t.GetEnd(), targetPadPosition, netCode, layertableRev.get("B.Cu"))


def setAnodeTracks(netsAnode):
    for key, value in netsAnode.items():
        print("Adding Net:", str(key))
        print(
            list(map(
                lambda x: (x.GetParent().GetReference().encode("utf8"), x.GetPadName()),
                value,
            )
        ))
        prefix, num = regex_split_annotation(key)
        if num <= 3:
            conPadPos = None
            ringPos = None
            conPadPos = value[15].GetPosition()
            radius = math.sqrt(
                (
                    math.pow(value[0].GetPosition()[0], 2)
                    + math.pow(value[0].GetPosition()[1], 2)
                )
            ) / math.pow(10, 6)
            for i in range(len(value) - 2):
                t = addTrack(
                    value[i].GetPosition(),
                    value[i + 1].GetPosition(),
                    value[i].GetNetCode(),
                    layertableRev.get("F.Cu"),
                )
            if num == 1:
                ringPos = getRingIntersectionByPosition(radius, 28.5)
            if num == 2:
                ringPos = getRingIntersectionByPosition(radius, 31.5)
            if num == 0:
                t1 = addTrack(
                    value[14].GetPosition(),
                    getRingIntersectionByPosition(radius, 14.5),
                    value[0].GetNetCode(),
                    layertableRev.get("F.Cu"),
                )
                v1 = addVia(t1.GetEnd(), value[0].GetNetCode())
                t2 = addTrack(
                    t1.GetEnd(),
                    getRingIntersectionByPosition(radius + 3, 16),
                    value[0].GetNetCode(),
                    layertableRev.get("B.Cu"),
                )
                t3 = addTrackArc(
                    radius + 3, 16, 24, value[0].GetNetCode(), layertableRev.get("B.Cu")
                )
                t4 = addTrack(
                    t3.GetEnd(),
                    getRingIntersectionByPosition(radius - 2, 26.5),
                    value[0].GetNetCode(),
                    layertableRev.get("B.Cu"),
                )
                v2 = addVia(t4.GetEnd(), value[0].GetNetCode())
                ringPos = v2.GetPosition()
            if num == 3:
                # t1 Not Needed as Track already there
                v1 = addVia(
                    getRingIntersectionByPosition(radius, 45.5), value[0].GetNetCode()
                )
                t2 = addTrack(
                    v1.GetPosition(),
                    getRingIntersectionByPosition(radius + 3, 44),
                    value[0].GetNetCode(),
                    layertableRev.get("B.Cu"),
                )
                t3 = addTrackArc(
                    radius + 3, 44, 36, value[0].GetNetCode(), layertableRev.get("B.Cu")
                )
                t4 = addTrack(
                    t3.GetEnd(),
                    getRingIntersectionByPosition(radius - 2, 33.5),
                    value[0].GetNetCode(),
                    layertableRev.get("B.Cu"),
                )
                v2 = addVia(t4.GetEnd(), value[0].GetNetCode())
                ringPos = v2.GetPosition()
            addTrackWithIntersection(ringPos, conPadPos, value[0].GetNetCode())
        elif num == 4:
            radius = math.sqrt(
                (
                    math.pow(value[0].GetPosition()[0], 2)
                    + math.pow(value[0].GetPosition()[1], 2)
                )
            ) / math.pow(10, 6)
            addTrackRing(radius, value[0].GetNetCode(), layertableRev.get("F.Cu"))
            for i in range(2):
                v1 = addVia(
                    getRingIntersectionByPosition(radius, [24.5, 35.5][i]),
                    value[0].GetNetCode(),
                )
                t1 = addTrack(
                    v1.GetPosition(),
                    getRingIntersectionByPosition(radius - 6, [24.5, 35.5][i]),
                    value[0].GetNetCode(),
                    layertableRev.get("B.Cu"),
                )
                v2 = addVia(t1.GetEnd(), value[0].GetNetCode())
                t2 = addTrackWithIntersection(
                    v2.GetPosition(),
                    value[[13, 12][i]].GetPosition(),
                    value[0].GetNetCode(),
                )
            # addTrack(getRingIntersectionByPosition(radius, 29.5), pcbnew.wxPoint(0,0), value[0].GetNetCode(), layertableRev.get("F.Cu"))
        elif num in [50, 51, 60, 61]:  # TODO: Sort Values?
            addTrack(
                value[2].GetPosition(),
                value[1].GetPosition(),
                value[0].GetNetCode(),
                layertableRev.get("F.Cu"),
            )
            v = addVia(
                pcbnew.wxPoint(
                    value[2].GetPosition()[0], value[2].GetPosition()[1] - 3000000
                ),
                value[0].GetNetCode(),
            )
            addTrack(
                v.GetEnd(),
                value[0].GetPosition(),
                value[0].GetNetCode(),
                layertableRev.get("B.Cu"),
            )
        elif num in [11, 21]:
            t1 = addTrack(
                value[0].GetPosition(),
                pcbnew.wxPoint(value[1].GetPosition()[0], value[0].GetPosition()[1]),
                value[0].GetNetCode(),
                layertableRev.get("F.Cu"),
            )
            v1 = addVia(t1.GetEnd(), value[0].GetNetCode())
            t1 = addTrack(
                v1.GetPosition(),
                value[1].GetPosition(),
                value[0].GetNetCode(),
                layertableRev.get("B.Cu"),
            )

import re
import collections


def regex_split_annotation(str_):
    a, i = re.match(r"([/A-Za-z]*)(\d*)", str_).groups()
    return a, int(i)


def main():

    # modules = {mod.GetReference(): mod for mod in sorted(pcb.GetModules())}
    # nets = collections.defaultdict(list)
    # for mod in modules.values():
    #     for pad in mod.Pads():
    #         nets[pad.GetShortNetname()].append(pad)
    #
    # modules_seconds = {k: modules[k] for k in ["D"+str(i) for i in range(1, 61)]}
    # modules_hours = {k: modules[k] for k in ["D"+str(i) for i in range(61, 72 + 1)]}
    #
    # setPositionSecondRing(modules_seconds, Radius)
    # setPositionHourRing(modules_hours, Radius * 1.1)
    # setPositionDigits(getDigitModules(modules), 3, 9.8, 10)
    # setSeparationModules(getSeparationModules(modules), 10)
    # setConnectorModules(getConnectorModules(modules), 10)
    # setDimension(100)
    # setDigitsConections(modules)
    # setCathodeTraks(getCathodeNets(Nets), Radius)
    # setAnodeTracks(getAnodeNets(Nets))

    return 0

if __name__ == "__main__":

    # note assumes dict are ordered, which they are in python3.9

    # find layer names
    for i in range(51):
        print(i)
        layertable[i] = pcb.GetLayerName(i)
        layertableRev[pcb.GetLayerName(i)] = i
        # print("{} {}".format(i, pcb.GetLayerName(i)))
    # Delete Old Tracks
    print(f"deleting {len(list(pcb.GetTracks()))} tracks")
    for t in pcb.GetTracks():
        pcb.Delete(t)
    print(f"deleting {len(list(pcb.GetDrawings()))} drawings")
    for d in pcb.GetDrawings():
        pcb.Remove(d)

    # get and sort modules
    modules = {mod.GetReference(): mod for mod in sorted(pcb.GetModules())}
    modules_seconds = {k: modules[k] for k in ["D" + str(i) for i in range(1, 60 + 1)]}
    modules_hours = {k: modules[k] for k in
                     ["D" + str(i) for i in range(61, 72 + 1)]}
    modules_digit = {k: modules[k] for k in ["U" + str(i) for i in range(1, 4 + 1)]}
    modules_seperation = {k: modules[k] for k in ["D" + str(i) for i in [73, 74]]}
    modules_connector = {k: modules[k] for k in ["J" + str(i) for i in [1, 2]]}

    # get and sort nets
    nets = collections.defaultdict(list)
    for mod in modules.values():
        for pad in mod.Pads():
            nets[pad.GetShortNetname()].append(pad)
    nets_kathode = {k: v for k, v in nets.items() if k.startswith("k")}
    nets_anode = {k: v for k, v in nets.items() if k.startswith("a")}

    setPositionSecondRing(modules_seconds, Radius)
    setPositionHourRing(modules_hours, Radius * 1.1)
    setPositionDigits(modules_digit, 3, 9.8, 10)
    setSeparationModules(modules_seperation, 10)
    setConnectorModules(modules_connector, 10)
    setDimension(100)
    setDigitsConections(modules_digit, modules_seperation)
    setCathodeTraks(nets_kathode, Radius)
    setAnodeTracks(nets_anode)

    pcb.Save('autogen.kicad_pcb')
