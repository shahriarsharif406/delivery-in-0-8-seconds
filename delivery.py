"""DELIVERY IN 0.8 SECONDS - procedural Blender film (15 s). python3 -I delivery.py --frames a b ..."""
import importlib.util, sys, math, random, os, time, argparse
import bpy, bmesh
from mathutils import Vector, Matrix, Quaternion, Euler
from math import sin, cos, pi, sqrt, atan2, asin

spec = importlib.util.spec_from_file_location("eos", "/home/claude/speed/evolution_of_speed.py")
eos = importlib.util.module_from_spec(spec)
sys.modules["eos"] = eos
spec.loader.exec_module(eos)
MAT, EMIT, C = eos.MAT, eos.EMIT, eos.C
smooth, lerp = eos.smooth, eos.lerp

FPS = 24
N_FRAMES = 360
S1A, S2A, S3A, S4A, S5A = 1, 41, 216, 263, 327
CUTS = [41, 86, 131, 176]
RNG = random.Random(21)
L, W = 64.0, 16.0                  # city grid pitch / street width
HX, HY = 330.0, 192.0              # house centre (door faces -x at x = HX-7)
DOORX = HX - 7.0
WX = 3000.0                        # warehouse centre

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

# ------------------------------------------------------------------ flight path (straight streets + filleted corners)
CORNERS = [(-192, -236, 17), (-192, -192, 17), (-192, -64, 12), (-64, -64, 10), (-64, 64, 14), (64, 64, 9),
           (64, 192, 15), (192, 192, 11), (256, 192, 9), (HX - 30, HY, 3.0)]
RAD = 10.0

def build_path():
    pts = []     # (x, y, z)
    marks = []
    P = [Vector((c[0], c[1], 0)) for c in CORNERS]
    zs = [c[2] for c in CORNERS]
    pts.append((P[0], zs[0]))
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        d1 = (b - a).normalized(); d2 = (c - b).normalized()
        cr = d1.cross(d2).z
        if abs(cr) < 1e-6:
            pts.append((b, zs[i])); continue
        pin = b - d1 * RAD; pout = b + d2 * RAD
        side = 1.0 if cr > 0 else -1.0
        n = Vector((-d1.y, d1.x, 0)) * side
        O = pin + n * RAD
        a0 = atan2(pin.y - O.y, pin.x - O.x); a1 = atan2(pout.y - O.y, pout.x - O.x)
        da = a1 - a0
        while da > pi: da -= 2 * pi
        while da < -pi: da += 2 * pi
        for k in range(0, 13):
            t = k / 12.0
            ang = a0 + da * t
            pts.append((Vector((O.x + RAD * cos(ang), O.y + RAD * sin(ang), 0)), zs[i]))
    pts.append((P[-1], zs[-1]))
    # dense polyline with z interpolated by corner order
    poly = []
    for i in range(len(pts) - 1):
        a, za = pts[i]; b, zb = pts[i + 1]
        seg = max(1, int((b - a).length / 2.0))
        for k in range(seg):
            t = k / seg
            poly.append(Vector((lerp(a.x, b.x, t), lerp(a.y, b.y, t), lerp(za, zb, smooth(t)))))
    poly.append(Vector((pts[-1][0].x, pts[-1][0].y, pts[-1][1])))
    cum = [0.0]
    for i in range(1, len(poly)):
        cum.append(cum[-1] + (poly[i] - poly[i - 1]).length)
    return poly, cum

POLY, CUM = build_path()
LTOT = CUM[-1]

def path_at(s):
    s = clamp(s, 0.0, LTOT - 1e-3)
    lo, hi = 0, len(CUM) - 1
    while hi - lo > 1:
        m = (lo + hi) // 2
        if CUM[m] <= s: lo = m
        else: hi = m
    t = (s - CUM[lo]) / max(CUM[hi] - CUM[lo], 1e-6)
    p = POLY[lo].lerp(POLY[hi], t)
    # tangent from a slightly wider window for smoothness
    a = POLY[max(0, lo - 2)]; b = POLY[min(len(POLY) - 1, hi + 2)]
    tg = (b - a).normalized()
    return p, tg

def s_of(f):
    u = clamp((f - S2A) / float(S3A - S2A - 1))
    return LTOT * (0.985 * u + 0.015 * u * u)

def drone_state(f):
    """returns pos, forward dir, roll, speed (m/s), mode"""
    if f < S2A:
        # warehouse launch (local to WX)
        t = (f - 20) / 12.0
        pad = Vector((WX + 2.0, 0.0, 0.55))
        if f < 14:
            return pad, Vector((1, 0, 0)), 0.0, 0.0, "pad"
        if f < 20:
            return pad + Vector((0, 0, 0.03 * sin((f - 14) * 2.0))), Vector((1, 0, 0)), 0.0, 0.0, "spin"
        k = clamp(t)
        pos = pad + Vector((0.5 * k ** 3 * 14.0, 0, 1.6 * smooth(clamp(k * 1.5)) + 0.3 * k))
        return pos, Vector((1, 0, -0.1)), 0.0, 25.0 * k * k, "launch"
    if f < S3A:
        s = s_of(f)
        p, tg = path_at(s)
        p2, tg2 = path_at(s + 6.0)
        yaw1 = atan2(tg.y, tg.x); yaw2 = atan2(tg2.y, tg2.x)
        dy = yaw2 - yaw1
        while dy > pi: dy -= 2 * pi
        while dy < -pi: dy += 2 * pi
        return p, tg, clamp(dy * 1.6, -0.6, 0.6), 110.0, "fly"
    if f < S4A:
        t = f - S3A
        x = DOORX - 1.5 - 21.5 * math.exp(-t / 4.7)
        z = 1.5 + 1.5 * math.exp(-t / 4.0)
        y = HY
        fwd = Vector((1, 0, 0))
        spd = 110.0 * math.exp(-t / 4.7)
        if f >= 241:                                 # doorbell nudges
            y = HY + 1.1
            nud = 0.0
            for fb in (243, 246):
                nud += 0.55 * math.exp(-((f - fb) / 0.9) ** 2)
            x = DOORX - 1.5 + nud
            z = 1.5
        if f >= 249:
            u = (f - 249) / 12.0
            x = DOORX - 1.5 - 4.0 * u * u
            y = HY + 1.1 + 1.0 * u * u
            z = 1.5 + 70.0 * u ** 3
            spd = 120.0 * u
        return Vector((x, y, z)), fwd, 0.0, spd, "door"
    return Vector((0, 0, -100)), Vector((1, 0, 0)), 0.0, 0.0, "gone"

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", nargs="+", type=int, default=[1, N_FRAMES])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--res", nargs=2, type=int, default=[1920, 1080])
    ap.add_argument("--samples", type=int, default=12)
    ap.add_argument("--out", default="delivery_frames")
    ap.add_argument("--wip", action="store_true")
    a = ap.parse_args(sys.argv[1:])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    eos.scene = scene
    eos.ROOT_COLL = scene.collection
    root = scene.collection
    eos.setup_render(tuple(a.res), a.samples, a.out)
    scene.view_settings.look = "AgX - Punchy"
    ramp, bgn = eos.setup_world()
    eos.set_ramp(ramp, [(0.0, "#2a1a4a"), (0.46, "#ff9a5c"), (0.52, "#ff7aa0"), (0.62, "#7a4ab5"), (0.8, "#2b2f7a"), (1.0, "#0c1038")])
    bgn.inputs["Strength"].default_value = 1.0

    cd = bpy.data.cameras.new("cam"); cd.sensor_width = 36; cd.clip_start = 0.05; cd.clip_end = 4000
    cam = bpy.data.objects.new("cam", cd); root.objects.link(cam); scene.camera = cam
    sd = bpy.data.lights.new("key", "SUN"); sd.angle = 0.05; sd.color = C("#ffb27a"); sd.energy = 3.2
    sun = bpy.data.objects.new("key", sd); root.objects.link(sun)
    sun.rotation_euler = (math.radians(80), math.radians(0), math.radians(125))
    fd = bpy.data.lights.new("fill", "SUN"); fd.angle = 0.4; fd.color = C("#8a8cff"); fd.energy = 0.9
    fill = bpy.data.objects.new("fill", fd); root.objects.link(fill)
    fill.rotation_euler = (math.radians(50), 0, math.radians(-60))

    # ---------------------------------------------------------------- materials
    def node_building(name, wall, glass, lit_cols, seed):
        m = bpy.data.materials.new(name); m.use_nodes = True
        nt = m.node_tree; nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial"); bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bs.outputs["BSDF"], out.inputs["Surface"])
        tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs[0])
        geo = nt.nodes.new("ShaderNodeNewGeometry"); gsep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Normal"], gsep.inputs[0])
        def M(op, a=None, b=None, v0=None, v1=None):
            n = nt.nodes.new("ShaderNodeMath"); n.operation = op
            if a is not None: nt.links.new(a, n.inputs[0])
            elif v0 is not None: n.inputs[0].default_value = v0
            if b is not None: nt.links.new(b, n.inputs[1])
            elif v1 is not None: n.inputs[1].default_value = v1
            return n
        u = M("ADD", sep.outputs["X"], sep.outputs["Y"])
        uf = M("MULTIPLY", u.outputs[0], v1=0.5)
        zf = M("MULTIPLY", sep.outputs["Z"], v1=0.25)
        ufr = M("FRACT", uf.outputs[0]); zfr = M("FRACT", zf.outputs[0])
        wu = M("LESS_THAN", ufr.outputs[0], v1=0.5); wz = M("LESS_THAN", zfr.outputs[0], v1=0.5)
        wmask = M("MULTIPLY", wu.outputs[0], wz.outputs[0])
        ab = M("ABSOLUTE", gsep.outputs["Z"])
        side = M("LESS_THAN", ab.outputs[0], v1=0.5)
        win = M("MULTIPLY", wmask.outputs[0], side.outputs[0])
        # per-window random
        fl_u = M("FLOOR", uf.outputs[0]); fl_z = M("FLOOR", zf.outputs[0])
        comb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(fl_u.outputs[0], comb.inputs["X"]); nt.links.new(fl_z.outputs[0], comb.inputs["Y"])
        comb.inputs["Z"].default_value = seed
        wn = nt.nodes.new("ShaderNodeTexWhiteNoise"); wn.noise_dimensions = "3D"
        nt.links.new(comb.outputs[0], wn.inputs["Vector"])
        lit = M("GREATER_THAN", wn.outputs["Value"], v1=0.5)
        litw = M("MULTIPLY", win.outputs[0], lit.outputs[0])
        estr = M("MULTIPLY", litw.outputs[0], v1=2.0)
        # colour pick
        ecr = nt.nodes.new("ShaderNodeValToRGB")
        ecr.color_ramp.elements[0].color = (*C(lit_cols[0]), 1); ecr.color_ramp.elements[1].color = (*C(lit_cols[1]), 1)
        nt.links.new(wn.outputs["Value"], ecr.inputs["Fac"])
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
        nt.links.new(win.outputs[0], mix.inputs["Factor"])
        mix.inputs["A"].default_value = (*C(wall), 1); mix.inputs["B"].default_value = (*C(glass), 1)
        nt.links.new(mix.outputs["Result"], bs.inputs["Base Color"])
        rg = M("SUBTRACT", None, win.outputs[0], v0=0.7)
        rr = M("MULTIPLY", rg.outputs[0], v1=0.8)
        rr2 = M("ADD", rr.outputs[0], v1=0.1)
        nt.links.new(rr2.outputs[0], bs.inputs["Roughness"])
        nt.links.new(ecr.outputs["Color"], bs.inputs["Emission Color"])
        nt.links.new(estr.outputs[0], bs.inputs["Emission Strength"])
        bs.inputs["Metallic"].default_value = 0.2
        return m
    pal = [("#2d3250", "#10162f", ("#ffb870", "#ffe9b0")), ("#3a2f45", "#12112a", ("#ff9d6e", "#ffd9a0")),
           ("#24344a", "#0b1a33", ("#7fe6ff", "#d8f6ff")), ("#4a3d36", "#1a1426", ("#ffc07a", "#fff0c4")),
           ("#303a55", "#0e1630", ("#ff86d0", "#ffd6f2")), ("#1f2a3c", "#0a1228", ("#8affc8", "#f0fff6"))]
    bmats = [node_building("bld%d" % i, p[0], p[1], p[2], 3.7 * i) for i, p in enumerate(pal)]
    m_asph = MAT("asphalt", "#2a2c38", 0.85)
    m_walk = MAT("walk", "#2e2f3a", 0.9)
    m_dash = EMIT("dash", "#ffd98a", 0.9)
    m_ring = EMIT("ring", "#18c8ff", 2.6)
    m_neonP = EMIT("neonP", "#ff3fb4", 5.0); m_neonC = EMIT("neonC", "#35e0ff", 5.0); m_neonY = EMIT("neonY", "#ffd23b", 5.0)
    m_glass = MAT("skyglass", "#9fd6ff", 0.1, 0.4, "#6fb7ff", 0.6)
    m_grass = MAT("grass", "#4f9a3e", 0.95)
    m_conc = MAT("conc", "#c9c4bd", 0.9)
    m_house = MAT("house", "#f1e3c8", 0.85)
    m_roof = MAT("roof", "#8a3b3b", 0.8)
    m_wood = MAT("wood", "#8a5a34", 0.7)
    m_door = MAT("door", "#2f6bd6", 0.5)
    m_win = MAT("hwin", "#ffd98a", 0.4, 0, "#ffc86a", 3.0)
    m_lamp = EMIT("lamp", "#ffe2a8", 14.0)
    m_leaf = MAT("leaf", "#2f7a3a", 0.9)
    m_trunk = MAT("trunk", "#5a3d27", 0.9)
    m_card = MAT("card", "#c89458", 0.8)
    m_cardin = MAT("cardin", "#a77a45", 0.9)
    m_tape = MAT("tape", "#e9dcb8", 0.6)
    m_dwhite = MAT("dwhite", "#f4f6fa", 0.35)
    m_dorange = MAT("dorange", "#ff7a2d", 0.4)
    m_dgrey = MAT("dgrey", "#2a2d38", 0.4, 0.5)
    m_led_g = EMIT("ledg", "#46ff8a", 8.0); m_led_r = EMIT("ledr", "#ff4655", 8.0)
    m_trail = EMIT("trail", "#7ff0ff", 7.0)
    m_rotor = bpy.data.materials.new("rotor"); m_rotor.use_nodes = True
    try: m_rotor.surface_render_method = "BLENDED"
    except Exception: pass
    rb = m_rotor.node_tree.nodes["Principled BSDF"]
    rb.inputs["Base Color"].default_value = (0.85, 0.9, 1.0, 1); rb.inputs["Alpha"].default_value = 0.16
    m_blade = MAT("blade", "#15161c", 0.5)
    m_floor = MAT("wfloor", "#4a4d5a", 0.5)
    m_wall = MAT("wwall", "#d7d9e2", 0.8)
    m_shelf = MAT("shelf", "#2e5aa8", 0.6)
    m_panel = EMIT("panel", "#fff1dc", 6.0)
    m_pad = MAT("pad", "#ffb347", 0.4, 0, "#ffb347", 1.5)
    m_dough = MAT("dough", "#e8b768", 0.7)
    m_cheese = MAT("cheese", "#ffd34d", 0.45)
    m_pep = MAT("pep", "#c0392b", 0.5)
    m_steam = MAT("steam", "#ffffff", 0.9, 0, "#ffffff", 0.4)
    m_skin = MAT("skin", "#e9ad86", 0.6)
    m_pj = MAT("pj", "#7aa6ff", 0.7)
    m_pjp = MAT("pjp", "#4a63c9", 0.7)
    m_hair = MAT("hair", "#2a1c14", 0.8)
    m_eye = MAT("eye", "#ffffff", 0.2); m_pup = MAT("pup", "#111118", 0.2)
    m_black = MAT("black", "#16161c", 0.6)
    m_slip = MAT("slip", "#ff9f43", 0.7)
    m_txt = EMIT("txt", "#ffffff", 7.0); m_txtY = EMIT("txtY", "#ffd23b", 8.0); m_txtG = EMIT("txtG", "#5dff9a", 7.0)
    m_txtD = EMIT("txtD", "#8d93a8", 3.0)
    m_hudw = EMIT("hudw", "#ffffff", 4.0); m_huda = EMIT("huda", "#ffb347", 5.0); m_hudc = EMIT("hudc", "#7ff0ff", 5.0)
    m_btn = EMIT("btn", "#ff5a5a", 1.0)

    # ---------------------------------------------------------------- the city
    cs = eos.new_coll("CITY")
    eos.part("asph", eos.bm_box(1400, 1400, 0.4), m_asph, cs, loc=(0, 0, -0.22))
    # lane dashes
    bmd = bmesh.new()
    for k in range(-4, 5):
        c = k * L
        for t in range(-260, 261, 8):
            eos.bm_merge(bmd, eos.bm_box(3.5, 0.25, 0.03), Matrix.Translation((t, c, 0.02)))
            eos.bm_merge(bmd, eos.bm_box(0.25, 3.5, 0.03), Matrix.Translation((c, t, 0.02)))
    eos.part("dashes", bmd, m_dash, cs)
    # buildings
    bcount = 0
    for i in range(-4, 4):
        for j in range(-4, 4):
            cx = (i + 0.5) * L; cy = (j + 0.5) * L
            dist = math.hypot(cx, cy) / (4.5 * L)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    w = RNG.uniform(14, 21); d = RNG.uniform(14, 21)
                    h = RNG.uniform(14, 34) + (1 - dist) * RNG.uniform(10, 60)
                    if RNG.random() < 0.12: h *= 0.45
                    lx = cx + sx * 12.0; ly = cy + sy * 12.0
                    mt = bmats[RNG.randrange(len(bmats))]
                    eos.part("bld", eos.bm_box(w, d, h), mt, cs, loc=(lx, ly, h / 2))
                    bcount += 1
                    if RNG.random() < 0.25:
                        eos.part("ant", eos.bm_cyl(0.15, 8, 6), m_dgrey, cs, loc=(lx, ly, h + 4))
                        eos.part("antl", eos.bm_sphere(0.3, 8, 6), m_led_r, cs, loc=(lx, ly, h + 8))
                    if RNG.random() < 0.3:     # neon strip on a facade
                        col = RNG.choice((m_neonP, m_neonC, m_neonY))
                        zz = RNG.uniform(6, max(8, h - 3))
                        if RNG.random() < 0.5:
                            eos.part("neon", eos.bm_box(0.25, RNG.uniform(5, 9), 0.5), col, cs,
                                     loc=(lx + (-1 if sx > 0 else 1) * (w / 2 + 0.15) * (-1) * (-1), ly, zz))
                        else:
                            eos.part("neon", eos.bm_box(RNG.uniform(5, 9), 0.25, 0.5), col, cs,
                                     loc=(lx, ly + (-1 if sy > 0 else 1) * (d / 2 + 0.15) * (-1) * (-1), zz))
    # skybridges over streets
    for (bx, by, along) in ((-192, -150, "x"), (-64, 0, "x"), (64, 120, "x"), (-128, -64, "y"), (0, 64, "y"), (128, 192, "y")):
        if along == "x":
            eos.part("bridge", eos.bm_box(W + 3, 4.0, 3.2), m_glass, cs, loc=(bx, by, 26))
        else:
            eos.part("bridge", eos.bm_box(4.0, W + 3, 3.2), m_glass, cs, loc=(bx, by, 26))
    # billboards
    for (bx, by, rot, msg, mt) in ((-100, -150, 0, "ZIPPY", m_neonC), (30, -20, 0, "0.8 s", m_neonY), (100, 100, 0, "NO TRAFFIC", m_neonP),
                                   (-140, 10, 0, "FAST", m_neonC), (150, 150, 0, "ZIPPY", m_neonY)):
        pass
    # rings along the path
    ring_objs = []
    for sr in range(120, int(LTOT) - 80, 95):
        p, tg = path_at(sr)
        r = eos.part("ring", eos.bm_torus(4.6, 0.28, 40, 8, axis="Z"), m_ring, cs, loc=p)
        r.rotation_mode = "QUATERNION"; r.rotation_quaternion = tg.to_track_quat("Z", "Y")
        r.visible_shadow = False
        ring_objs.append(r)
    # traffic
    cars = []
    for k in range(70):
        horiz = RNG.random() < 0.5
        lane = RNG.randrange(-4, 5) * L + (3.0 if RNG.random() < 0.5 else -3.0)
        dirn = 1 if lane % L > 0 else -1
        bmc = bmesh.new()
        eos.bm_merge(bmc, eos.bm_box(4.2, 1.8, 1.2), Matrix.Translation((0, 0, 0.8)), 0)
        eos.bm_merge(bmc, eos.bm_box(0.12, 1.5, 0.35), Matrix.Translation((-2.1, 0, 0.9)), 1)
        eos.bm_merge(bmc, eos.bm_box(0.12, 1.5, 0.3), Matrix.Translation((2.1, 0, 0.9)), 2)
        mc = MAT("car%d" % k, RNG.choice(("#3d4a6b", "#7a2f3d", "#d9d9e3", "#2a2a33", "#e6a82b")), 0.4, 0.4)
        o = eos.part("car", bmc, [mc, EMIT("tl%d" % k, "#ff2a3a", 6.0), EMIT("hl%d" % k, "#fff1c9", 8.0)], cs)
        cars.append((o, horiz, lane, dirn, RNG.uniform(0, 520), RNG.uniform(8, 20)))
    # suburb
    sb = eos.new_coll("SUBURB")
    eos.part("lawn", eos.bm_box(260, 190, 0.3), m_grass, sb, loc=(HX + 20, HY, -0.15))
    eos.part("road", eos.bm_box(80, 9, 0.2), m_asph, sb, loc=(HX - 52, HY, 0.0))
    eos.part("pave", eos.bm_box(80, 2.4, 0.21), m_walk, sb, loc=(HX - 52, HY - 5.8, 0.0))
    eos.part("drive", eos.bm_box(8, 4.0, 0.12), m_conc, sb, loc=(HX - 11.5, HY - 3, 0.05))
    # porch + house
    eos.part("porch", eos.bm_box(3.4, 6.0, 0.36), m_conc, sb, loc=(DOORX - 1.7, HY, 0.18))
    eos.part("step1", eos.bm_box(0.9, 3.2, 0.2), m_conc, sb, loc=(DOORX - 3.85, HY, 0.1))
    eos.part("hbody", eos.bm_box(14, 13, 6.2), m_house, sb, loc=(HX, HY, 3.1))
    pts = [(-7.4, 0), (7.4, 0), (0, 3.4)]
    roof = eos.bm_poly([(-7.8, 0), (7.8, 0), (0, 3.6)], 13.8, "XZ")
    eos.part("hroof", roof, m_roof, sb, loc=(HX, HY, 6.2), rot=(0, 0, pi / 2))
    # door frame + door (hinged)
    eos.part("hdframe", eos.bm_box(0.3, 1.5, 2.5), m_wood, sb, loc=(DOORX - 0.05, HY, 1.45 + 0.18))
    eos.part("hint", eos.bm_box(6, 5, 3.2), MAT("hint", "#f6d9a0", 0.8, 0, "#ffcf8a", 0.35), sb, loc=(DOORX + 3.2, HY, 1.8))
    eos.part("hwinL", eos.bm_box(0.12, 2.0, 1.5), m_win, sb, loc=(DOORX - 0.01, HY - 3.6, 2.6))
    eos.part("hwinR", eos.bm_box(0.12, 2.0, 1.5), m_win, sb, loc=(DOORX - 0.01, HY + 3.6, 2.6))
    door_piv = eos.empty("doorpiv", sb, loc=(DOORX - 0.1, HY + 0.55, 0.18))
    eos.part("door", eos.bm_box(0.08, 1.1, 2.2), m_door, sb, door_piv, loc=(0, -0.55, 1.1))
    eos.part("knob", eos.bm_sphere(0.05, 8, 6), m_dorange, sb, door_piv, loc=(-0.07, -1.0, 1.0))
    mat_ = eos.part("mat", eos.bm_box(0.9, 1.4, 0.03), MAT("matc", "#7a3b2a", 0.95), sb, loc=(DOORX - 1.4, HY, 0.37))
    btn = eos.part("btn", eos.bm_cyl(0.06, 0.04, 12, axis="X"), m_btn, sb, loc=(DOORX - 0.05, HY + 1.25, 1.45 + 0.18))
    # porch light
    eos.part("plamp", eos.bm_sphere(0.14, 10, 8), m_lamp, sb, loc=(DOORX - 0.25, HY - 0.95, 2.75))
    pl = bpy.data.lights.new("porch", "POINT"); pl.color = C("#ffcf8a"); pl.energy = 900; pl.shadow_soft_size = 0.3
    plo = bpy.data.objects.new("porch", pl); root.objects.link(plo); plo.location = (DOORX - 0.8, HY - 0.95, 2.5)
    il = bpy.data.lights.new("inside", "POINT"); il.color = C("#ffd9a0"); il.energy = 1600; il.shadow_soft_size = 0.8
    ilo = bpy.data.objects.new("inside", il); root.objects.link(ilo); ilo.location = (DOORX + 2.5, HY, 2.6)
    # mailbox, hedge, trees, neighbours
    eos.part("mbpost", eos.bm_cyl(0.06, 1.1, 8), m_wood, sb, loc=(HX - 24, HY - 6.8, 0.55))
    eos.part("mbox", eos.bm_box(0.5, 0.3, 0.3), m_door, sb, loc=(HX - 24, HY - 6.8, 1.2))
    for k in range(-5, 6):
        if abs(k) > 1:
            eos.part("hedge", eos.bm_sphere(0.55, 10, 8, scale=(1, 1.1, 0.9)), m_leaf, sb, loc=(DOORX - 0.8, HY + k * 1.1, 0.5))
    for (tx_, ty_, th) in ((HX - 20, HY + 10, 7), (HX - 18, HY - 11, 6), (HX - 34, HY + 9, 8), (HX + 25, HY, 9), (HX - 40, HY - 12, 7)):
        eos.part("trunk", eos.bm_cyl(0.35, th, 8), m_trunk, sb, loc=(tx_, ty_, th / 2))
        eos.part("crown", eos.bm_sphere(th * 0.45, 12, 8), m_leaf, sb, loc=(tx_, ty_, th + 1.0))
    for (nx, ny) in ((HX - 8, HY + 26), (HX - 8, HY - 26), (HX - 8, HY + 48), (HX + 8, HY + 38)):
        eos.part("nbody", eos.bm_box(11, 10, 5.5), m_house, sb, loc=(nx, ny, 2.75))
        eos.part("nroof", eos.bm_poly([(-6, 0), (6, 0), (0, 3)], 10.8, "XZ"), m_roof, sb, loc=(nx, ny, 5.5), rot=(0, 0, pi / 2))
        eos.part("nwin", eos.bm_box(0.12, 2.0, 1.3), m_win, sb, loc=(nx - 5.55, ny + 2.2, 2.4))
    for lx in range(int(HX - 100), int(HX - 20), 18):
        eos.part("lpole", eos.bm_cyl(0.1, 5.5, 8), m_dgrey, sb, loc=(lx, HY - 6.2, 2.75))
        eos.part("lhead", eos.bm_sphere(0.28, 8, 6), m_lamp, sb, loc=(lx, HY - 5.9, 5.6))

    # ---------------------------------------------------------------- warehouse
    wh = eos.new_coll("WAREHOUSE")
    eos.part("wfloor", eos.bm_box(16, 14, 0.2), m_floor, wh, loc=(WX, 0, -0.1))
    eos.part("wback", eos.bm_box(0.3, 14, 6), m_wall, wh, loc=(WX - 8, 0, 3))
    eos.part("wleft", eos.bm_box(16, 0.3, 6), m_wall, wh, loc=(WX, -7, 3))
    eos.part("wright", eos.bm_box(16, 0.3, 6), m_wall, wh, loc=(WX, 7, 3))
    eos.part("wceil", eos.bm_box(16, 14, 0.3), m_wall, wh, loc=(WX, 0, 6.1))
    eos.part("wfrontL", eos.bm_box(0.3, 3.5, 6), m_wall, wh, loc=(WX + 8, -5.25, 3))
    eos.part("wfrontR", eos.bm_box(0.3, 3.5, 6), m_wall, wh, loc=(WX + 8, 5.25, 3))
    eos.part("wlintel", eos.bm_box(0.3, 7, 1.5), m_wall, wh, loc=(WX + 8, 0, 5.25))
    eos.part("wout", eos.bm_box(60, 60, 0.2), m_asph, wh, loc=(WX + 38, 0, -0.1))
    for k, yy in enumerate((-4, 0, 4)):
        eos.part("wpanel", eos.bm_box(3.0, 1.0, 0.1), m_panel, wh, loc=(WX - 2 + k * 0.0, yy, 5.9))
    for k, xx in enumerate((-4, 3)):
        eos.part("wpanel2", eos.bm_box(1.0, 3.0, 0.1), m_panel, wh, loc=(WX + xx, 0, 5.9))
    wl = bpy.data.lights.new("wl", "POINT"); wl.energy = 2600; wl.color = C("#fff0d8"); wl.shadow_soft_size = 1.5
    wlo = bpy.data.objects.new("wl", wl); root.objects.link(wlo); wlo.location = (WX - 1, 0, 5.2)
    # shelves
    for k in range(5):
        for lvl in range(3):
            eos.part("shelf", eos.bm_box(2.4, 0.7, 0.08), m_shelf, wh, loc=(WX - 6 + k * 2.8, 6.4, 0.6 + lvl * 1.4))
            for q in range(2):
                eos.part("sbox", eos.bm_box(0.7, 0.5, 0.55), m_card, wh, loc=(WX - 6.6 + k * 2.8 + q * 1.1, 6.4, 0.95 + lvl * 1.4))
    # launch pad
    eos.part("pad", eos.bm_cyl(1.1, 0.14, 32, smooth_=True), m_pad, wh, loc=(WX + 2.0, 0, 0.07))
    # table + pizza
    eos.part("tabtop", eos.bm_box(1.8, 1.1, 0.08), m_conc, wh, loc=(WX - 0.4, -2.7, 0.85))
    for tx_, ty_ in ((-1.2, -3.1), (0.4, -3.1), (-1.2, -2.3), (0.4, -2.3)):
        eos.part("tableg", eos.bm_cyl(0.05, 0.85, 8), m_dgrey, wh, loc=(WX + tx_, ty_, 0.42))
    pz = eos.empty("pizza", wh, loc=(WX - 0.4, -2.7, 0.93))
    eos.part("pbox", eos.bm_box(0.62, 0.62, 0.05), m_card, wh, pz, loc=(0, 0, 0.0))
    eos.part("pdough", eos.bm_cyl(0.27, 0.05, 28, smooth_=True), m_dough, wh, pz, loc=(0, 0, 0.05))
    eos.part("pchz", eos.bm_cyl(0.24, 0.03, 28, smooth_=True), m_cheese, wh, pz, loc=(0, 0, 0.075))
    for k in range(9):
        ang = RNG.uniform(0, 2 * pi); rr = RNG.uniform(0.02, 0.19)
        eos.part("pep", eos.bm_cyl(0.035, 0.02, 12), m_pep, wh, pz, loc=(rr * cos(ang), rr * sin(ang), 0.1))
    steam = []
    for k in range(10):
        o = eos.part("steam", eos.bm_sphere(0.018, 8, 6), m_steam, wh, pz); o.visible_shadow = False
        steam.append((o, RNG.uniform(0, 1), RNG.uniform(-0.12, 0.12), RNG.uniform(-0.12, 0.12)))
    # wall screen
    scr = eos.part("screen", eos.bm_box(0.08, 3.4, 1.6), MAT("scr", "#0d1b2a", 0.3, 0, "#16324d", 1.2), wh, loc=(WX - 7.8, -1.5, 3.0))
    t_scr1 = eos.make_text("scr1", "ORDER #0001", 0.45, wh, None, (WX - 7.7, -1.5, 3.4), EMIT("scrt1", "#7ff0ff", 5.0), eos.FONT_B, "CENTER")
    t_scr1.rotation_euler = (pi / 2, 0, pi / 2)
    t_scr2 = eos.make_text("scr2", "ETA 0.8 s", 0.55, wh, None, (WX - 7.7, -1.5, 2.55), EMIT("scrt2", "#ffb347", 6.0), eos.FONT_B, "CENTER")
    t_scr2.rotation_euler = (pi / 2, 0, pi / 2)

    # ---------------------------------------------------------------- the drone
    dc = eos.new_coll("DRONE")
    droot = eos.empty("drone", dc)
    SCL = 1.5
    eos.part("dbody", eos.bm_sphere(0.34 * SCL, 20, 12, scale=(1.2, 0.9, 0.55)), m_dwhite, dc, droot)
    eos.part("dstripe", eos.bm_sphere(0.345 * SCL, 20, 12, scale=(0.5, 0.92, 0.2)), m_dorange, dc, droot, loc=(0, 0, 0.02))
    eos.part("deye", eos.bm_sphere(0.1 * SCL, 12, 8), m_dgrey, dc, droot, loc=(0.38 * SCL, 0, -0.03))
    eos.part("deyeg", eos.bm_sphere(0.04 * SCL, 8, 6), m_led_g, dc, droot, loc=(0.46 * SCL, 0, -0.02))
    rotors = []
    for (ax, ay) in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        arm = eos.part("darm", eos.bm_box(0.5 * SCL, 0.06 * SCL, 0.05 * SCL), m_dgrey, dc, droot)
        eos.place_bone(arm, (0, 0, 0), (0, 0, 0))
        arm.location = (ax * 0.28 * SCL, ay * 0.28 * SCL, 0.04 * SCL); arm.rotation_euler = (0, 0, atan2(ay, ax))
        arm.scale = (1, 1, 1)
        eos.part("dmotor", eos.bm_cyl(0.07 * SCL, 0.1 * SCL, 12), m_dgrey, dc, droot, loc=(ax * 0.5 * SCL, ay * 0.5 * SCL, 0.08 * SCL))
        rt = eos.empty("rotor", dc, loc=(ax * 0.5 * SCL, ay * 0.5 * SCL, 0.15 * SCL), parent=droot)
        eos.part("rdisc", eos.bm_cyl(0.3 * SCL, 0.004, 24), m_rotor, dc, rt).visible_shadow = False
        eos.part("rbl1", eos.bm_box(0.6 * SCL, 0.04 * SCL, 0.01), m_blade, dc, rt)
        eos.part("rbl2", eos.bm_box(0.04 * SCL, 0.6 * SCL, 0.01), m_blade, dc, rt)
        rotors.append(rt)
    for ys in (-0.12, 0.12):
        eos.part("rope", eos.bm_cyl(0.008, 0.6, 6), m_dgrey, dc, droot, loc=(0.1, ys, -0.5))
    parcel = eos.empty("parcel", dc, loc=(0, 0, -0.62), parent=droot)       # re-parented in set_frame for the drop
    pbm = bmesh.new()
    eos.bm_merge(pbm, eos.bm_box(0.6, 0.46, 0.4), None, 0)
    eos.part("pcard", pbm, m_card, dc, parcel)
    eos.part("ptape", eos.bm_box(0.08, 0.47, 0.41), m_tape, dc, parcel)
    ptxt = eos.make_text("ptxt", "ZIPPY", 0.14, dc, parcel, (-0.301, 0.0, -0.02), EMIT("ptxtm", "#15161c", 0.0), eos.FONT_B, "CENTER")
    ptxt.rotation_euler = (pi / 2, 0, -pi / 2)
    pfam = set()
    def _walk(o):
        for c in o.children:
            pfam.add(c); _walk(c)
    trail = eos.part("dtrail", eos.bm_box(1, 0.03, 0.03), m_trail, dc)
    trail.visible_shadow = False
    # flaps (open box on the doorstep)
    flaps = []
    for sgn in (-1, 1):
        fp = eos.empty("flap", dc, loc=(0, sgn * 0.23, 0.2), parent=parcel)
        eos.part("flapb", eos.bm_box(0.6, 0.23, 0.015), m_card, dc, fp, loc=(0, sgn * 0.115, 0.0))
        flaps.append((fp, sgn))
    inner = eos.part("pinner", eos.bm_box(0.56, 0.42, 0.01), m_cardin, dc, parcel, loc=(0, 0, 0.19))

    _walk(parcel)
    # ---------------------------------------------------------------- receiver
    kc = eos.new_coll("PERSON")
    pr = {}
    pr["torso"] = eos.part("torso", eos.bm_box(0.26, 0.44, 0.62), m_pj, kc)
    pr["pelvis"] = eos.part("pelvis", eos.bm_box(0.25, 0.4, 0.28), m_pjp, kc)
    pr["head"] = eos.part("head", eos.bm_sphere(0.135, 18, 12), m_skin, kc)
    pr["hair"] = eos.part("hair", eos.bm_sphere(0.14, 14, 10, scale=(1, 1, 0.7)), m_hair, kc)
    pr["eyes"] = []
    for sgn in (-1, 1):
        pr["eyes"].append((eos.part("eye", eos.bm_sphere(0.032, 10, 8), m_eye, kc), eos.part("pup", eos.bm_sphere(0.017, 8, 6), m_pup, kc),
                           eos.part("brow", eos.bm_box(0.012, 0.07, 0.014), m_hair, kc)))
    pr["mouth"] = [eos.part("mouth", eos.bm_box(0.01, 0.05, 0.012), m_black, kc) for _ in range(3)]
    pr["nose"] = eos.part("nose", eos.bm_sphere(0.02, 8, 6), m_skin, kc)
    pr["leg"] = [(eos.bone("thigh", 0.085, m_pjp, kc, None), eos.bone("shin", 0.075, m_pjp, kc, None), eos.part("slip", eos.bm_box(0.3, 0.12, 0.08, off=(-0.06, 0, 0)), m_slip, kc)) for _ in (0, 1)]
    pr["arm"] = [(eos.bone("uarm", 0.055, m_pj, kc, None), eos.bone("farm", 0.048, m_skin, kc, None), eos.part("hand", eos.bm_sphere(0.052, 8, 6), m_skin, kc)) for _ in (0, 1)]
    pr["neck"] = eos.part("neck", eos.bm_cyl(0.05, 0.1, 8), m_skin, kc)
    person_parts = [pr["torso"], pr["pelvis"], pr["head"], pr["hair"], pr["nose"], pr["neck"]] + pr["mouth"]
    for e in pr["eyes"]: person_parts += list(e)
    for l in pr["leg"]: person_parts += list(l)
    for a_ in pr["arm"]: person_parts += list(a_)

    # ---------------------------------------------------------------- fx: stars, texts
    tx = eos.new_coll("TXT")
    k_ = 0.5 / 3.0
    hudroot = eos.empty("hudroot", tx, loc=(0, 0, 0), parent=cam)
    def ctext(name, body, size, mat, x=0.0, y=0.0, font=eos.FONT_B, align="CENTER"):
        return eos.make_text(name, body, size * k_, tx, hudroot, (x * k_, y * k_, -0.5), mat, font, align)
    hud_a = ctext("hud_a", "DELIVERY TIME", 0.07, m_hudw, 0, 1.02, eos.FONT_M)
    hud_n = ctext("hud_n", "0.00 s", 0.2, m_huda, 0, 0.82, eos.FONT_B)
    hud_s = ctext("hud_s", "ZIPPY-1   400 km/h", 0.075, m_hudc, 0, -1.02, eos.FONT_M)
    s1a = ctext("s1a", "ORDER #0001  -  ESTIMATED DELIVERY: 0.8 s", 0.1, m_hudw, 0, 1.0, eos.FONT_B)
    s5a = ctext("s5a", "DELIVERED IN 0.8 s", 0.2, m_txtG, 0, 0.55, eos.FONT_B)
    s5b = ctext("s5b", "*contents not included.", 0.1, m_txtD, 0, 0.2, eos.FONT_M)
    s5c = ctext("s5c", "FutureTech.ai", 0.15, m_txtY, 0, -0.55, eos.FONT_S)
    s5d = ctext("s5d", "a 100% procedural Blender Python film", 0.07, m_txt, 0, -0.85, eos.FONT_M)
    rv1 = ctext("rv1", "\"Box was empty.\"", 0.1, m_txt, 0, 0.5, eos.FONT_B)
    rv2 = ctext("rv2", "Customer review - 0.8 seconds ago", 0.06, m_txtD, 0, 0.36, eos.FONT_M)
    stars = []
    star_pts = []
    for q in range(10):
        ang = pi / 2 + q * pi / 5
        rr = 1.0 if q % 2 == 0 else 0.42
        star_pts.append((rr * cos(ang), rr * sin(ang)))
    for q in range(5):
        so = eos.part("star", eos.bm_poly(star_pts, 0.01, "XY"), m_txtY if q == 0 else m_txtD, tx, hudroot,
                      loc=((q - 2) * 0.1 * k_ * 4.2, 0.72 * k_, -0.5), scale=(0.04 * k_ * 4.2, 0.04 * k_ * 4.2, 1))
        stars.append(so)

    # ---------------------------------------------------------------- helpers per frame
    def doorbell_light(f):
        on = any(abs(f - fb) < 2 for fb in (243, 246))
        btn.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 14.0 if on else 1.0

    def person_pose(f):
        """returns True if person visible; updates all parts"""
        if f < 270:
            return False
        feet_x = DOORX - 0.9          # standing on the porch just outside the door
        # phases
        walk_t = clamp((f - 270) / 13.0)
        px = lerp(DOORX + 2.6, DOORX - 1.0, smooth(walk_t))
        lean = 0.0; hipz = 0.95; head_pitch = 0.0; head_yaw = 0.0; smile = 1.0; brow = 0.0
        hold = 0.0; tilt = 0.0; flap = 0.0; sag = 0.0
        if f >= 284:
            a_ = smooth(clamp((f - 284) / 7.0)); lean = lerp(0.0, 1.2, a_); hipz = lerp(0.95, 0.5, a_); px = DOORX - 1.0 - 0.25 * a_
        if f >= 291:
            b_ = smooth(clamp((f - 291) / 9.0)); lean = lerp(1.2, 0.18, b_); hipz = lerp(0.5, 0.95, b_); px = lerp(DOORX - 1.25, DOORX - 1.0, b_); hold = b_
        if f >= 300:
            flap = smooth(clamp((f - 300) / 6.0)); head_pitch = 0.45 * smooth(clamp((f - 300) / 6.0))
            tilt = smooth(clamp((f - 304) / 5.0))
            smile = 1.0 - 2.0 * smooth(clamp((f - 306) / 6.0))
            brow = 0.8 * smooth(clamp((f - 303) / 3.0)) - 1.8 * smooth(clamp((f - 308) / 5.0))
        if f >= 309:
            sag = smooth(clamp((f - 309) / 7.0))
            head_yaw = 0.25 * sin((f - 312) * 0.9) * clamp((f - 312) / 3.0) * (1 - smooth(clamp((f - 322) / 4.0)))
        floor_z = 0.36
        hip = Vector((px, HY, floor_z + hipz - 0.1 * sag))
        R = Euler((0, -lean, 0), "XYZ").to_matrix()
        # torso & pelvis
        pr["pelvis"].location = hip + Vector((0, 0, 0.0)); pr["pelvis"].rotation_euler = (0, -lean * 0.4, 0)
        tor_c = hip + R @ Vector((0, 0, 0.43))
        pr["torso"].location = tor_c; pr["torso"].rotation_euler = (0, -lean, 0)
        neck_p = hip + R @ Vector((0, 0, 0.78))
        pr["neck"].location = neck_p; pr["neck"].rotation_euler = (0, -lean, 0)
        head_c = hip + R @ Vector((0, 0, 0.97))
        hq = Euler((0, -lean * 0.5 + head_pitch * 0.0, head_yaw), "XYZ")
        hp_ = Euler((0, head_pitch, 0), "XYZ")
        Hm = Euler((0, -lean, 0), "XYZ").to_matrix() @ Euler((0, head_pitch, head_yaw), "XYZ").to_matrix()
        pr["head"].location = head_c; pr["head"].rotation_euler = Hm.to_euler()
        pr["hair"].location = head_c + Hm @ Vector((0.012, 0, 0.045)); pr["hair"].rotation_euler = Hm.to_euler()
        pr["nose"].location = head_c + Hm @ Vector((-0.135, 0, -0.005))
        for k, sgn in enumerate((-1, 1)):
            eye, pup, br = pr["eyes"][k]
            ec = head_c + Hm @ Vector((-0.112, sgn * 0.05, 0.03))
            eye.location = ec; pup.location = head_c + Hm @ Vector((-0.138, sgn * 0.05, 0.028))
            br.location = head_c + Hm @ Vector((-0.12, sgn * 0.05, 0.085 + 0.02 * max(0, brow)))
            br.rotation_euler = (Hm.to_euler()[0] + sgn * (-0.4 * brow) * 0.0, Hm.to_euler()[1], Hm.to_euler()[2] + sgn * (-0.55 * brow) * -1.0)
        for k in range(3):
            m = pr["mouth"][k]
            base = head_c + Hm @ Vector((-0.12, (k - 1) * 0.034, -0.062 + (0.012 * smile if k != 1 else 0.0) * (-1 if k != 1 else 1) * 0 ))
            yoff = 0.0
            if k == 1:
                m.location = head_c + Hm @ Vector((-0.125, 0, -0.065))
                m.rotation_euler = Hm.to_euler()
            else:
                sg = -1 if k == 0 else 1
                m.location = head_c + Hm @ Vector((-0.12, sg * 0.04, -0.065 + 0.013 * smile))
                e0 = Hm.to_euler()
                m.rotation_euler = (e0[0] + sg * 0.55 * smile * -1, e0[1], e0[2])
                m.scale = (1, 0.7, 1)
        # legs
        stride = (f - 270) * 0.95
        for k, sgn in enumerate((-1, 1)):
            hipP = hip + Vector((0, sgn * 0.1, 0.0))
            if f < 284:
                ph = stride + (pi if sgn > 0 else 0)
                fx_ = hipP.x + (-0.12 * sin(ph)) * (1 - walk_t * 0.0)
                lift = 0.1 * max(0.0, cos(ph)) * (1 if walk_t < 1 else 0)
                if walk_t >= 1: fx_ = hipP.x - 0.05
                foot = Vector((fx_, hipP.y, floor_z + 0.045 + lift))
            else:
                foot = Vector((DOORX - 1.0 - 0.05, HY + sgn * 0.12, floor_z + 0.045))
            knee = eos.ik2(hipP, foot, 0.46, 0.46, (-1, 0, 0))
            th, sh_, sl = pr["leg"][k]
            eos.place_bone(th, hipP, knee); eos.place_bone(sh_, knee, foot)
            sl.location = foot + Vector((0, 0, -0.02))
        # arms
        for k, sgn in enumerate((-1, 1)):
            shoulder = hip + R @ Vector((0, sgn * 0.25, 0.66))
            if f < 284:
                ph = stride + (0 if sgn > 0 else pi)
                hand = shoulder + Vector((-0.12 * sin(ph), sgn * 0.04, -0.52))
                pole = Vector((0.3, sgn * 0.5, -0.2))
            else:
                # box reference
                box_rest = Vector((DOORX - 1.4, HY, floor_z + 0.2))
                box_hold = Vector((px - 0.38, HY, floor_z + hipz + 0.52 - 0.06 * sag))
                bp = box_rest.lerp(box_hold, hold)
                hand = bp + Vector((0, sgn * 0.3, 0.0))
                pole = Vector((0.2, sgn * 1.0, -0.6))
            elbow = eos.ik2(shoulder, hand, 0.29, 0.27, pole)
            ua, fa, hd = pr["arm"][k]
            eos.place_bone(ua, shoulder, elbow); eos.place_bone(fa, elbow, hand); hd.location = hand
        # box + flaps
        if f >= 284:
            box_rest = Vector((DOORX - 1.4, HY, floor_z + 0.2))
            box_hold = Vector((px - 0.38, HY, floor_z + hipz + 0.52 - 0.06 * sag))
            parcel.parent = None
            parcel.location = box_rest.lerp(box_hold, hold)
            parcel.rotation_mode = "XYZ"
            parcel.rotation_euler = (0, -0.85 * tilt, 0)
            for (fp, sgn) in flaps:
                fp.rotation_euler = (sgn * -1.9 * flap, 0, 0) if sgn > 0 else (sgn * -1.9 * flap, 0, 0)
        return True

    # ---------------------------------------------------------------- camera design
    def cam_for(f):
        shk = 0.0; roll = 0.0
        if f < S2A:                                  # warehouse
            p = clamp((f - 1) / 13.0)
            pos = Vector((WX - 4.6, -4.0, 1.55)).lerp(Vector((WX - 1.6, -2.3, 1.35)), smooth(p))
            dpos = drone_state(f)[0]
            tg0 = Vector((WX + 1.2, -0.9, 0.85))
            if f < 22:
                tgt = tg0.lerp(Vector((WX + 2.0, 0, 1.0)), smooth(p)); lens = lerp(26, 34, p)
            else:
                k = clamp((f - 22) / 6.0)
                tgt = Vector((WX + 2.0, 0, 1.0)).lerp(dpos + Vector((2.0, 0, 0)), smooth(k)); lens = lerp(34, 28, k)
                pos = pos + Vector((0.6 * k, 0.4 * k, 0))
            shk = 0.01 + (0.04 if f > 20 else 0)
            return pos, tgt, lens, shk, roll
        if f < S3A:
            s = s_of(f)
            p, tg = path_at(s)
            if f < 86:                               # A: chase
                q = (f - S2A) / 44.0
                pb, tb = path_at(s - 8.5)
                pos = pb + Vector((0, 0, 3.0 + 0.6 * sin(f * 0.25))) + Vector((-tb.y, tb.x, 0)) * (1.2 * sin(f * 0.11))
                tgt = p + tg * 7.0
                lens = lerp(26, 22, q); shk = 0.05; roll = 0.05 * sin(f * 0.2)
            elif f < 131:                            # B: street-level looking up as it flies overhead
                sB = s_of(108)
                pB, tB = path_at(sB)
                side = Vector((-tB.y, tB.x, 0))
                pos = Vector((pB.x, pB.y, 1.8)) + side * 3.5
                tgt = p
                dist = (p - pos).length
                lens = lerp(34, 18, clamp((dist - 10) / 8.0)) if (p - pos).dot(tB) < 0 else 14
                shk = 0.02; roll = 0.0
            elif f < 176:                            # C: front camera, drone approaching
                pf, tf = path_at(s + 11.0)
                pos = pf + Vector((0, 0, 0.5)) + Vector((-tf.y, tf.x, 0)) * 1.0
                tgt = p + Vector((0, 0, 0.1))
                lens = lerp(20, 24, (f - 131) / 45.0); shk = 0.06; roll = 0.08 * sin(f * 0.17)
            else:                                    # D: high chase
                pb, tb = path_at(s - 17.0)
                pos = pb + Vector((0, 0, 8.5)) + Vector((-tb.y, tb.x, 0)) * 5.0
                tgt = p
                lens = lerp(28, 22, (f - 176) / 40.0); shk = 0.05; roll = -0.06
            return pos, tgt, lens, shk, roll
        if f < S4A:                                  # door arrival
            p = clamp((f - S3A) / 46.0)
            pos = Vector((DOORX - 14.0 + 1.0 * p, HY - 5.5 + 0.8 * p, 1.35))
            dpos = drone_state(f)[0]
            tgt = Vector((DOORX - 2.0, HY + 0.3, 1.6)).lerp(dpos, 0.0)
            if f < 226: tgt = Vector((DOORX - 2.0, HY + 0.2, 1.55)).lerp(dpos, 0.55)
            if f >= 249: tgt = Vector((DOORX - 2.0, HY + 0.5, 2.2 + 1.5 * (f - 249) / 13.0))
            lens = 28 - 3 * p; shk = 0.012; roll = 0.0
            return pos, tgt, lens, shk, roll
        if f < S5A:                                  # reveal
            p = clamp((f - S4A) / 63.0)
            pos = Vector((DOORX - 8.2 + 0.8 * smooth(p), HY - 1.3, 1.5))
            tgt = Vector((DOORX - 1.0, HY, 1.2 + 0.15 * smooth(clamp((f - 298) / 14.0))))
            lens = 32 + 10 * smooth(clamp((f - 298) / 14.0)); shk = 0.0; roll = 0.0
            return pos, tgt, lens, shk, roll
        p = clamp((f - S5A) / 33.0)                  # warehouse end card
        pos = Vector((WX - 3.6, -3.7, 1.45)).lerp(Vector((WX - 3.1, -3.4, 1.4)), p)
        tgt = Vector((WX - 0.4, -2.7, 0.98)); lens = 34 + 4 * p
        return pos, tgt, lens, 0.0, 0.0

    def set_frame(f):
        # which zone is visible
        zone = 0 if f < S2A else (1 if f < S3A else (2 if f < S5A else 3))
        # drone
        dpos, fwd, roll, spd, mode = drone_state(f)
        droot.location = dpos
        yaw = atan2(fwd.y, fwd.x); pitch = (0.22 if mode in ("fly",) else (0.0 if mode in ("pad", "spin") else 0.1)) - asin(clamp(fwd.z, -1, 1))
        droot.rotation_euler = (roll, pitch, yaw)
        drone_vis = f < S3A + 48
        for o in dc.objects:
            o.hide_render = not (drone_vis or o in pfam)
        dropped = S3A + 17 <= f < S4A
        released = f >= S3A + 17 or f >= S4A
        # parcel: hangs on drone until released at f=233 then falls onto the mat; person takes over at 284
        if f < S3A + 17 or (f < 249 and False):
            parcel.parent = droot; parcel.location = (0, 0, -0.62); parcel.rotation_euler = (0, 0, 0)
        elif f < 284:
            parcel.parent = None
            t = (f - (S3A + 17)) / 24.0
            fall = clamp(t * 24 / 7.0)
            z0 = 0.75; zf = 0.36 + 0.2
            parcel.location = (DOORX - 1.4 + 0.0, HY, lerp(z0, zf, fall ** 2) + 0.06 * math.exp(-max(0, (f - 240)) / 2.0) * abs(sin((f - 240) * 1.2)) * (1 if f > 240 else 0))
            parcel.rotation_euler = (0, 0, 0)
            for (fp, sgn) in flaps: fp.rotation_euler = (0, 0, 0)
        for k, rt in enumerate(rotors):
            rt.rotation_euler = (0, 0, f * (1.7 + 0.4 * k) * (1.0 if mode in ("spin", "launch", "fly", "door") else 0.2))
        # trail
        showtrail = mode in ("fly", "launch") or (mode == "door" and f >= 249)
        trail.hide_render = not (showtrail and drone_vis)
        if showtrail:
            ln = clamp(spd / 110.0) * 16.0 if mode == "fly" else clamp(spd / 25.0) * 2.5
            if mode == "door": ln = clamp(spd / 120.0) * 30.0
            back = -fwd.normalized() if mode != "door" else Vector((0, 0, -1))
            trail.location = dpos + back * (ln / 2 + 0.3); trail.scale = (ln, 1, 1)
            trail.rotation_mode = "QUATERNION"; trail.rotation_quaternion = (back).to_track_quat("X", "Z")
        # visibility by zone
        # (everything is in one world; zones are separated by distance)
        # person
        pvis = person_pose(f) if f >= 263 else False
        for o in person_parts: o.hide_render = not pvis
        door_ang = 0.0
        if f >= 263: door_ang = 1.85 * smooth(clamp((f - 264) / 8.0))
        door_piv.rotation_euler = (0, 0, door_ang)
        doorbell_light(f)
        # cars
        for (o, horiz, lane, dirn, x0, v) in cars:
            pos1 = ((x0 + dirn * v * f / FPS * 3.0 + 260) % 520) - 260
            if horiz:
                o.location = (pos1, lane, 0.1); o.rotation_euler = (0, 0, 0 if dirn > 0 else pi)
            else:
                o.location = (lane, pos1, 0.1); o.rotation_euler = (0, 0, pi / 2 if dirn > 0 else -pi / 2)
            o.hide_render = zone != 1
        # steam on pizza
        for (o, ph, dx, dy) in steam:
            tt = ((f * 0.02 + ph) % 1.0)
            o.location = (dx * (1 + tt) * 0.8, dy * (1 + tt) * 0.8, 0.15 + 0.4 * tt)
            o.scale = (1 - tt * 0.6,) * 3
            o.hide_render = False
        # camera
        pos, tgt, lens, shk, roll = cam_for(f)
        cd.lens = lens
        cam.location = pos + eos.shake(f, shk, 2.3)
        eos.look_at(cam, tgt + eos.shake(f, shk * 0.7, 4.1), roll)
        # exposure flashes on cuts
        ex = 0.0
        for cf in CUTS:
            ex = max(ex, 2.6 * smooth(1 - abs(f - (cf - 0.5)) / 2.6))
        if f <= 3: ex = -2.0 * (1 - (f - 1) / 3.0)
        if S3A <= f <= S3A + 1: ex = 1.5
        if f >= 250 and f < 262: ex = max(ex, 1.8 * smooth(clamp((f - 253) / 5.0)) * (1 - smooth(clamp((f - 258) / 4.0))))
        scene.view_settings.exposure = ex
        # sunlight only for outdoors; warehouse is lit by lamps; hide big lights per zone
        wl.energy = 2600 if (zone == 0 or zone == 3) else 0
        pl.energy = 900 if zone == 2 else 0
        il.energy = 1600 if zone == 2 else 0
        # text
        def vis(ob, on): ob.hide_render = not on
        # HUD scale compensation
        for ob in (hud_a, hud_n, hud_s, s1a, s5a, s5b, s5c, s5d, rv1, rv2):
            pass
        vis(s1a, 4 <= f < 40)
        fl = zone == 1
        vis(hud_a, fl); vis(hud_n, fl); vis(hud_s, fl)
        if fl:
            tsec = 0.8 * clamp((f - S2A) / float(S3A - S2A - 1))
            hud_n.data.body = "%.2f s" % tsec
            hud_s.data.body = "ZIPPY-1     %d km/h" % (396 + 7 * sin(f * 0.4))
        vis(s5a, f >= S5A + 3); vis(s5b, f >= S5A + 11); vis(s5c, f >= S5A + 19); vis(s5d, f >= S5A + 23)
        vis(rv1, 314 <= f < S5A); vis(rv2, 316 <= f < S5A)
        for q, so in enumerate(stars):
            so.hide_render = not (314 + q <= f < S5A)
        # compensate camera-parented text for lens change (reference lens 26)
        hudroot.scale = (26.0 / lens,) * 3
        return zone

    if a.wip:
        set_frame(150)
        clay = MAT("clayw", "#33476b", 0.5, 0.1); wire = EMIT("wirew", "#3fd9ff", 3.2)
        # show only the drone + parcel
        for o in bpy.data.objects:
            if o.type == "MESH":
                inside = (o.users_collection[0].name in ("DRONE",))
                if not inside:
                    o.hide_render = True; continue
                o.hide_render = False
                me = o.data
                if len(me.materials) >= 1 and o.name.startswith(("dbody", "dstripe", "darm", "dmotor", "deye", "pcard", "ptape", "rope")):
                    me.materials[0] = clay; me.materials.append(wire)
                    md = o.modifiers.new("wf", "WIREFRAME"); md.thickness = 0.006; md.use_replace = False; md.material_offset = len(me.materials) - 1
        for o in tx.objects: o.hide_render = True
        droot.location = Vector((0, 0, 0)); droot.rotation_euler = (0.1, 0.35, 0.0)
        parcel.parent = droot; parcel.location = (0, 0, -0.62)
        trail.hide_render = True
        eos.set_ramp(ramp, [(0.0, "#050b18"), (0.5, "#0c1d3a"), (1.0, "#050b18")])
        scene.view_settings.exposure = 0.0
        sd.energy = 3.0
        gp = eos.part("gridfloor", eos.bm_box(20, 8, 0.02), MAT("gf", "#0a1426", 0.8), root, loc=(0, 0, -1.3))
        cam.location = (-2.6, -4.4, 0.6); cd.lens = 40
        eos.look_at(cam, Vector((0, 0, -0.15)))
        scene.render.filepath = "/home/claude/speed/delivery_wip_wireframe.png"
        bpy.ops.render.render(write_still=True)
        return

    frames = a.frames if a.list else list(range(a.frames[0], a.frames[1] + 1))
    os.makedirs(a.out, exist_ok=True)
    for f in frames:
        t0 = time.time()
        set_frame(f)
        scene.frame_set(f)
        scene.render.filepath = os.path.join(a.out, "f_%04d.png" % f)
        bpy.ops.render.render(write_still=True)
        print("DONE frame %d in %.1fs" % (f, time.time() - t0), flush=True)

if __name__ == "__main__":
    main()
