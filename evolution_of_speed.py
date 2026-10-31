"""
THE EVOLUTION OF SPEED  -  a fully procedural Blender (bpy) animation
FutureTech.ai  |  RenderJuice Blender Animation & Programmatic Rendering Contest

Every model, material, light, camera move, wheel rotation, particle streak and
HUD readout in this film is generated and animated by this single script.
No external 3D assets, textures or HDRIs are used.

Usage:  python3 evolution_of_speed.py --frames 1 396 --res 1920 1080 --samples 12 --out frames
"""
import bpy, bmesh, math, random, sys, os, argparse, time
from math import pi, sin, cos, tau, sqrt, exp
from mathutils import Vector, Matrix, Quaternion

# --------------------------------------------------------------------------
# global timeline
# --------------------------------------------------------------------------
FPS = 24
N_FRAMES = 396
SEGS = [  # name, first frame, last frame, HUD label
    ("rickshaw", 1, 72, "RICKSHAW"),
    ("bus", 73, 144, "BUS"),
    ("train", 145, 216, "TRAIN"),
    ("jet", 217, 288, "JET"),
    ("light", 289, 340, "THE SPEED OF LIGHT"),
]
END_START = 341                     # title card frames 341..360
CUTS = [73, 145, 217, 289, 341]     # whiteout transitions happen on these frames

# treadmill speed (m/s) at start / end of each segment  (what the scenery does)
V_RANGE = [(3.2, 7.5), (20, 36), (52, 80), (130, 240), (420, 5200)]
# speed shown in the HUD (km/h) at start / end of each segment
KMH_RANGE = [(6, 17), (38, 96), (118, 184), (640, 1240)]
C_KMH = 1_079_252_849               # speed of light, km/h

def seg_index(f):
    for i, (_, a, b, _) in enumerate(SEGS):
        if a <= f <= b:
            return i
    return len(SEGS) - 1 if f >= END_START else 0

def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)

def lerp(a, b, t):
    return a + (b - a) * t

def treadmill_speed(f):
    if f >= END_START:
        return 4 + (5200 - 4) * exp(-(f - END_START) / 1.3)
    i = seg_index(f)
    _, a, b, _ = SEGS[i]
    p = (f - a) / max(1, (b - a))
    v0, v1 = V_RANGE[i]
    if i == 4:
        return lerp(v0, v1, p ** 2.6)
    return lerp(v0, v1, smooth(p) * 0.85 + p * 0.15)

DIST = [0.0] * (N_FRAMES + 2)
for _f in range(1, N_FRAMES + 1):
    DIST[_f] = DIST[_f - 1] + treadmill_speed(_f) / FPS

def hud_kmh(f):
    if f >= END_START:
        return C_KMH
    i = seg_index(f)
    _, a, b, _ = SEGS[i]
    p = (f - a) / max(1, (b - a))
    if i < 4:
        k0, k1 = KMH_RANGE[i]
        return lerp(k0, k1, smooth(p))
    return exp(lerp(math.log(2500), math.log(C_KMH), smooth(p) ** 1.4))

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def C(h):
    h = h.lstrip("#")
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b))

def MAT(name, col, rough=0.55, metal=0.0, emit=None, estr=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    if isinstance(col, str):
        col = C(col)
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit is not None:
        if isinstance(emit, str):
            emit = C(emit)
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = estr
    return m

def EMIT(name, col, strength):
    if isinstance(col, str):
        col = C(col)
    return MAT(name, (0, 0, 0), 1.0, 0.0, col, strength)

# ---- bmesh primitives -----------------------------------------------------
def bm_box(sx, sy, sz, off=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx + off[0], v.co.y * sy + off[1], v.co.z * sz + off[2]))
    return bm

def bm_cyl(r, d, seg=20, axis="Z", r2=None, smooth_=False, off=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                          radius1=r, radius2=(r if r2 is None else r2), depth=d)
    _orient(bm, axis)
    if off != (0, 0, 0):
        bmesh.ops.translate(bm, vec=Vector(off), verts=bm.verts)
    for f in bm.faces:
        f.smooth = smooth_
    return bm

def bm_sphere(r, seg=16, ring=10, scale=(1, 1, 1), off=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=r)
    for v in bm.verts:
        v.co = Vector((v.co.x * scale[0] + off[0], v.co.y * scale[1] + off[1], v.co.z * scale[2] + off[2]))
    for f in bm.faces:
        f.smooth = True
    return bm

def _orient(bm, axis):
    if axis == "Y":
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(pi / 2, 3, "X"), verts=bm.verts)
    elif axis == "X":
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(pi / 2, 3, "Y"), verts=bm.verts)

def bm_torus(R, r, seg=36, rseg=8, axis="Y"):
    bm = bmesh.new()
    rows = []
    for i in range(seg):
        a = tau * i / seg
        row = []
        for j in range(rseg):
            b = tau * j / rseg
            row.append(bm.verts.new(((R + r * cos(b)) * cos(a), (R + r * cos(b)) * sin(a), r * sin(b))))
        rows.append(row)
    for i in range(seg):
        for j in range(rseg):
            f = bm.faces.new((rows[i][j], rows[(i + 1) % seg][j], rows[(i + 1) % seg][(j + 1) % rseg], rows[i][(j + 1) % rseg]))
            f.smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    _orient(bm, axis)
    return bm

def bm_poly(pts, depth, plane="XZ"):
    """extrude a 2D outline. plane XZ -> thickness along Y; XY -> thickness along Z"""
    bm = bmesh.new()
    def P(a, b, t):
        return (a, t, b) if plane == "XZ" else (a, b, t)
    lo = [bm.verts.new(P(a, b, -depth / 2)) for a, b in pts]
    hi = [bm.verts.new(P(a, b, depth / 2)) for a, b in pts]
    bm.faces.new(lo)
    bm.faces.new(list(reversed(hi)))
    n = len(pts)
    for i in range(n):
        bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm

def bm_merge(dst, src, M=None, mat_index=0):
    if M is not None:
        bmesh.ops.transform(src, matrix=M, verts=src.verts)
    for f in src.faces:
        f.material_index = mat_index
    me = bpy.data.meshes.new("tmp")
    src.to_mesh(me)
    src.free()
    dst.from_mesh(me)
    bpy.data.meshes.remove(me)

def to_mesh(name, bm, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    return me

scene = bpy.context.scene
ROOT_COLL = scene.collection

def new_coll(name):
    c = bpy.data.collections.new(name)
    ROOT_COLL.children.link(c)
    return c

def obj(name, data, coll, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), parent=None):
    ob = bpy.data.objects.new(name, data)
    coll.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = rot
    ob.scale = scale
    if parent is not None:
        ob.parent = parent
    return ob

def empty(name, coll, loc=(0, 0, 0), parent=None):
    return obj(name, None, coll, loc=loc, parent=parent)

def part(name, bm, mat, coll, parent=None, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    mats = mat if isinstance(mat, (list, tuple)) else [mat]
    return obj(name, to_mesh(name, bm, mats), coll, loc, rot, scale, parent)

def place_bone(ob, a, b):
    a = Vector(a); b = Vector(b)
    d = b - a
    ob.location = (a + b) / 2
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = d.to_track_quat("Z", "Y")
    ob.scale = (1, 1, max(d.length, 1e-4))

def ik2(a, c, l1, l2, pole):
    a = Vector(a); c = Vector(c)
    d = c - a
    dist = min(d.length, l1 + l2 - 1e-3)
    dn = d.normalized()
    x = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist)
    h = sqrt(max(l1 * l1 - x * x, 0))
    pv = Vector(pole)
    pv = (pv - dn * pv.dot(dn)).normalized()
    return a + dn * x + pv * h

def bone(name, r, mat, coll, parent, seg=10):
    return part(name, bm_cyl(r, 1.0, seg, smooth_=True), mat, coll, parent)

# ---- scrolling scenery -------------------------------------------------------
class Scroll:
    """object whose x position is wrapped around so the world streams past forever"""
    def __init__(self, ob, x0, span, center=0.0, smear=0.0, cap=40.0, base_sx=1.0):
        self.ob, self.x0, self.span, self.center = ob, x0, span, center
        self.smear, self.cap, self.base_sx = smear, cap, base_sx

    def update(self, D, v):
        x = ((self.x0 - D - self.center + self.span / 2) % self.span) - self.span / 2 + self.center
        self.ob.location.x = x
        if self.smear:
            self.ob.scale.x = self.base_sx * min(1 + v * self.smear, self.cap)

def add_speed_lines(coll, scrolls, n, ys, zs, strength, color="#ffffff", base=(2, 5), smear=0.25, cap=50, name="sl"):
    m = EMIT(name + "_m", color, strength)
    me = to_mesh(name + "_me", bm_box(1.0, 0.012, 0.012), [m])
    span = span_for(abs(ys[0]) + 4)
    for i in range(n):
        sx = RNG.uniform(*base)
        ob = obj("%s%d" % (name, i), me, coll, (0, RNG.uniform(*ys), RNG.uniform(*zs)), (0, 0, 0), (sx, 1, 1))
        scrolls.append(Scroll(ob, RNG.uniform(0, span), span, 0.0, smear, cap, sx))

def span_for(dist, cam_off=12.0):
    return 2 * (0.9 * abs(dist) + cam_off) * 1.2

# ---- wheels -------------------------------------------------------------------
def make_wheel(name, R, width, coll, parent, loc, tire, rim, spokes=0, bolts=0, tube=None):
    hub = empty(name, coll, loc, parent)
    tube = tube or R * 0.28
    part(name + "_tire", bm_torus(R - tube, tube, 28, 8, "Y"), tire, coll, hub, scale=(1, width / (2 * tube), 1))
    if spokes:
        for i in range(spokes):
            a = pi * i / spokes
            part(name + "_spoke%d" % i, bm_box(0.012, 0.012, 2 * (R - tube)), rim, coll, hub, rot=(0, a, 0))
        part(name + "_rim", bm_torus(R - tube * 1.6, 0.012, 28, 5, "Y"), rim, coll, hub)
        part(name + "_hub", bm_cyl(0.035, 0.07, 10, "Y"), rim, coll, hub)
    else:
        part(name + "_disc", bm_cyl(R - tube * 0.9, width * 0.7, 24, "Y"), rim, coll, hub)
        for i in range(bolts):
            a = tau * i / bolts
            part(name + "_bolt%d" % i, bm_cyl(R * 0.07, width * 0.9, 8, "Y", off=(0, 0, 0)), tire, coll, hub,
                 loc=(R * 0.36 * cos(a), 0, R * 0.36 * sin(a)))
    return hub

# --------------------------------------------------------------------------
# scene build
# --------------------------------------------------------------------------
def setup_render(res, samples, out):
    s = scene
    s.render.engine = "BLENDER_EEVEE"
    s.render.resolution_x, s.render.resolution_y = res
    s.render.resolution_percentage = 100
    s.render.fps = FPS
    s.eevee.taa_render_samples = samples
    s.eevee.use_shadows = True
    s.eevee.use_raytracing = False
    s.eevee.use_fast_gi = False
    try:
        s.eevee.shadow_ray_count = 1
        s.eevee.shadow_step_count = 6
    except Exception:
        pass
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGB"
    s.render.image_settings.color_depth = "8"
    s.render.film_transparent = False
    for vt in ("AgX", "Filmic", "Standard"):
        try:
            s.view_settings.view_transform = vt
            break
        except Exception:
            continue
    try:
        s.view_settings.look = "AgX - Punchy"
    except Exception:
        pass
    s.view_settings.exposure = 0.0

def setup_world():
    w = bpy.data.worlds.new("sky")
    w.use_nodes = True
    scene.world = w
    nt = w.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -1
    mr.inputs["From Max"].default_value = 1
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return ramp, bg

def set_ramp(ramp, stops):
    cr = ramp.color_ramp
    while len(cr.elements) > 1:
        cr.elements.remove(cr.elements[-1])
    for i, (pos, col) in enumerate(stops):
        e = cr.elements[0] if i == 0 else cr.elements.new(pos)
        e.position = pos
        e.color = (*C(col), 1)
    cr.interpolation = "EASE"

# ---- environment helpers --------------------------------------------------------
RNG = random.Random(7)

def add_scroll_layer(coll, scrolls, meshes, count_span, dist, y, z=0.0, jitter_y=0.0, scale_rng=(1, 1),
                     center=0.0, smear=0.0, cap=40.0, spacing=None, mats=None, rot_z=0.0, name="lay", z_jit=0.0):
    span = span_for(dist) if count_span is None else count_span
    spacing = spacing or 8.0
    n = max(2, int(span / spacing))
    for i in range(n):
        me = RNG.choice(meshes)
        sc = RNG.uniform(*scale_rng)
        ob = obj("%s_%d" % (name, i), me, coll, (0, y + RNG.uniform(-jitter_y, jitter_y), z + RNG.uniform(-z_jit, z_jit)),
                 (0, 0, rot_z), (sc, sc, sc))
        x0 = (i + RNG.uniform(-0.3, 0.3)) * span / n
        scrolls.append(Scroll(ob, x0, span, center, smear, cap, sc))
    return span

# --------------------------------------------------------------------------
# Segment 1: RICKSHAW  (village, golden dawn)
# --------------------------------------------------------------------------
def build_rickshaw():
    coll = new_coll("S1_rickshaw")
    scrolls = []
    # materials
    m_red = MAT("rk_red", "#d8262e", 0.45)
    m_yel = MAT("rk_yel", "#ffc21a", 0.5)
    m_blue = MAT("rk_blue", "#1c6fd1", 0.5)
    m_green = MAT("rk_green", "#17a35b", 0.5)
    m_pink = MAT("rk_pink", "#ff4f9a", 0.5)
    m_steel = MAT("rk_steel", "#2a2d33", 0.35, 0.8)
    m_chrome = MAT("rk_chrome", "#cfd3d8", 0.25, 0.9)
    m_tire = MAT("rk_tire", "#14110f", 0.8)
    m_skin = MAT("rk_skin", "#8a5a3a", 0.6)
    m_shirt = MAT("rk_shirt", "#f4ede0", 0.7)
    m_lungi = MAT("rk_lungi", "#2f7bd0", 0.7)
    m_hair = MAT("rk_hair", "#0e0b0a", 0.8)
    m_scarf = MAT("rk_scarf", "#e8332f", 0.7)
    m_lamp = EMIT("rk_lamp", "#ffe2a0", 6.0)

    root = empty("rickshaw_root", coll)
    R = 0.34
    hubs = []
    hubs.append(make_wheel("rk_wf", R, 0.05, coll, root, (1.15, 0, R), m_tire, m_chrome, spokes=14))
    hubs.append(make_wheel("rk_wr1", R, 0.05, coll, root, (-0.45, 0.62, R), m_tire, m_chrome, spokes=14))
    hubs.append(make_wheel("rk_wr2", R, 0.05, coll, root, (-0.45, -0.62, R), m_tire, m_chrome, spokes=14))
    # frame tubes
    tubes = [((1.15, 0, R), (1.0, 0, 0.96)), ((1.0, 0, 0.96), (0.3, 0, 0.93)), ((1.0, 0, 0.96), (0.64, 0, 0.42)),
             ((0.3, 0, 0.93), (0.3, 0, 0.55)), ((0.3, 0, 0.55), (0.64, 0, 0.42)), ((0.3, 0, 0.55), (-0.45, 0, R)),
             ((0.64, 0, 0.42), (-0.45, 0, R)), ((1.0, 0, 0.98), (1.0, 0.27, 0.98)), ((1.0, 0, 0.98), (1.0, -0.27, 0.98)),
             ((-0.45, 0.62, R), (-0.45, -0.62, R))]
    for i, (a, b) in enumerate(tubes):
        t = bone("rk_tube%d" % i, 0.016, m_steel, coll, root)
        place_bone(t, a, b)
    # chassis + seat + hood
    part("rk_floor", bm_box(1.0, 1.15, 0.06), m_blue, coll, root, loc=(-0.38, 0, 0.5))
    part("rk_seat", bm_box(0.72, 0.95, 0.15), m_pink, coll, root, loc=(-0.44, 0, 0.64))
    part("rk_back", bm_box(0.12, 0.95, 0.58), m_pink, coll, root, loc=(-0.84, 0, 0.98), rot=(0, 0.12, 0))
    # hood = half barrel with axis along X
    hb = bm_cyl(0.52, 0.95, 24, "X", smooth_=True)
    bmesh.ops.bisect_plane(hb, geom=hb.verts[:] + hb.edges[:] + hb.faces[:], plane_co=(0, 0, 0), plane_no=(0, 0, 1), clear_inner=True)
    for f in hb.faces:
        f.smooth = True
    hood = part("rk_hood", hb, m_red, coll, root, loc=(-0.36, 0, 1.0))
    for i, (xx, mm) in enumerate([(-0.80, m_yel), (-0.36, m_yel), (0.08, m_yel)]):
        tb = bm_torus(0.52, 0.018, 24, 5, "X")
        bmesh.ops.bisect_plane(tb, geom=tb.verts[:] + tb.edges[:] + tb.faces[:], plane_co=(0, 0, 0), plane_no=(0, 0, 1), clear_inner=True)
        part("rk_rib%d" % i, tb, mm, coll, root, loc=(xx, 0, 1.0))
    for i, c in enumerate([m_green, m_yel, m_blue, m_pink, m_green, m_yel]):
        part("rk_art%d" % i, bm_box(0.03, 0.14, 0.2), c, coll, root, loc=(-0.93, -0.38 + i * 0.152, 0.86))
    part("rk_backpanel", bm_box(0.04, 1.02, 0.48), m_red, coll, root, loc=(-0.91, 0, 0.9))
    for i, c in enumerate([m_yel, m_green, m_blue, m_pink, m_yel, m_green, m_blue, m_pink]):
        part("rk_tas%d" % i, bm_sphere(0.032, 8, 6), c, coll, root, loc=(0.12, -0.5 + i * 0.143, 1.04 + 0.1 * (0.5 - abs(i - 3.5) / 3.5) * 0.0))
    part("rk_lamp", bm_sphere(0.06, 10, 8), m_lamp, coll, root, loc=(1.05, 0, 1.08))
    # saddle
    part("rk_saddle", bm_box(0.28, 0.14, 0.05), m_steel, coll, root, loc=(0.28, 0, 0.96))
    # crank, pedals
    crank = empty("rk_crank", coll, (0.64, 0, 0.42), root)
    ped = []
    for k, sgn in enumerate((1, -1)):
        pe = part("rk_pedal%d" % k, bm_box(0.11, 0.07, 0.025), m_steel, coll, root)
        ped.append(pe)
    part("rk_chainring", bm_cyl(0.09, 0.012, 16, "Y"), m_chrome, coll, crank)
    # rider
    hip = Vector((0.27, 0, 1.0))
    sh = Vector((0.45, 0, 1.52))
    torso = bone("rk_torso", 0.14, m_shirt, coll, root, 14); place_bone(torso, hip, sh)
    part("rk_head", bm_sphere(0.115, 14, 10), m_skin, coll, root, loc=(0.52, 0, 1.76))
    part("rk_hair", bm_sphere(0.12, 12, 8, (1, 1, 0.7), (-0.015, 0, 0.04)), m_hair, coll, root, loc=(0.52, 0, 1.79))
    part("rk_scarf", bm_torus(0.095, 0.03, 14, 6, "Z"), m_scarf, coll, root, loc=(0.5, 0, 1.6))
    part("rk_lungi", bm_box(0.34, 0.34, 0.2), m_lungi, coll, root, loc=(0.27, 0, 1.0))
    limbs = {}
    for nm in ("thighR", "shinR", "thighL", "shinL"):
        limbs[nm] = bone("rk_" + nm, 0.055 if "thigh" in nm else 0.042, m_lungi if "thigh" in nm else m_skin, coll, root)
    for nm in ("uarmR", "farmR", "uarmL", "farmL"):
        limbs[nm] = bone("rk_" + nm, 0.04, m_shirt if "uarm" in nm else m_skin, coll, root)
    # ----- environment
    env = {}
    ground = part("s1_ground", bm_box(900, 400, 1.0), MAT("s1_grass", "#7fb83f", 0.9), coll, None, loc=(0, 150, -0.5))
    road = part("s1_road", bm_box(900, 4.2, 0.06), MAT("s1_road", "#b98a5b", 0.95), coll, None, loc=(0, 0, 0.0))
    # trees
    m_trunk = MAT("s1_trunk", "#8c5b34", 0.9)
    m_leaf1 = MAT("s1_leaf1", "#2f8f3a", 0.7)
    m_leaf2 = MAT("s1_leaf2", "#52b04a", 0.7)
    palms = []
    for k in range(5):
        bm = bmesh.new()
        h = RNG.uniform(5.5, 8.0)
        tilt = RNG.uniform(-0.12, 0.12)
        t = bm_cyl(0.2, h, 8, r2=0.1, off=(0, 0, h / 2))
        bm_merge(bm, t, Matrix.Rotation(tilt, 4, "Y"), 0)
        for j in range(9):
            lf = bm_box(2.4, 0.28, 0.04, off=(1.2, 0, 0))
            M = Matrix.Translation((h * math.sin(tilt) * 0.0 + math.sin(tilt) * h * 0.5, 0, h)) @ Matrix.Rotation(tau * j / 9, 4, "Z") @ Matrix.Rotation(0.5, 4, "Y")
            bm_merge(bm, lf, M, 1)
        palms.append(to_mesh("palm%d" % k, bm, [m_trunk, m_leaf1 if k % 2 else m_leaf2]))
    bushes = []
    for k in range(4):
        bm = bmesh.new()
        for j in range(4):
            sp = bm_sphere(RNG.uniform(0.6, 1.1), 10, 7, (1, 1, 0.8), (RNG.uniform(-0.8, 0.8), RNG.uniform(-0.3, 0.3), 0.6))
            bm_merge(bm, sp, None, 0)
        bushes.append(to_mesh("bush%d" % k, bm, [m_leaf1 if k % 2 else m_leaf2]))
    huts = []
    m_wall = MAT("s1_wall", "#d8b98a", 0.9)
    m_roof = MAT("s1_roof", "#7d8a8f", 0.5, 0.5)
    m_roof2 = MAT("s1_roof2", "#b5502d", 0.6)
    for k in range(3):
        bm = bmesh.new()
        w, d, h = RNG.uniform(5, 7), RNG.uniform(4, 5), RNG.uniform(2.6, 3.2)
        bm_merge(bm, bm_box(w, d, h, (0, 0, h / 2)), None, 0)
        roof = bm_poly([(-w / 2 - 0.5, 0), (w / 2 + 0.5, 0), (w / 2 + 0.5, 0.0), (0, 1.8)], d + 1.0, "XZ")
        bm_merge(bm, roof, Matrix.Translation((0, 0, h)), 1)
        huts.append(to_mesh("hut%d" % k, bm, [m_wall, m_roof if k % 2 else m_roof2]))
    posts = []
    m_wood = MAT("s1_wood", "#6e4a2a", 0.9)
    bm = bmesh.new(); bm_merge(bm, bm_box(0.09, 0.09, 0.9, (0, 0, 0.45)), None, 0)
    posts.append(to_mesh("post", bm, [m_wood]))
    reeds = []
    m_reed = MAT("s1_reed", "#8fcf5a", 0.8)
    bm = bmesh.new()
    for j in range(7):
        bm_merge(bm, bm_cyl(0.025, 1.0, 5, r2=0.002, off=(0, 0, 0.5)),
                 Matrix.Translation((RNG.uniform(-0.3, 0.3), RNG.uniform(-0.3, 0.3), 0)) @ Matrix.Rotation(RNG.uniform(-0.35, 0.35), 4, "X") @ Matrix.Rotation(RNG.uniform(-0.35, 0.35), 4, "Y"), 0)
    reeds.append(to_mesh("reed", bm, [m_reed]))
    ridge_mat = MAT("s1_ridge", "#4e9a35", 0.95)
    ridge = to_mesh("ridge", bm_box(0.6, 70, 0.04), [ridge_mat])
    pebble = to_mesh("pebble", bm_box(0.35, 0.22, 0.05), [MAT("s1_peb", "#8b6240", 0.95)])
    sunm = EMIT("s1_sun", "#fff0c0", 14.0)
    sun = part("s1_sun", bm_cyl(14, 0.5, 48, "Y"), sunm, coll, None, loc=(75, 190, 30))
    hills = []
    for k in range(3):
        bm = bm_poly([(-60, 0), (60, 0), (20, 14 + 5 * k), (-20, 11 + 6 * k)], 6, "XZ")
        hills.append(to_mesh("hill%d" % k, bm, [MAT("s1_hill%d" % k, ["#7aa05a", "#6e9a58", "#8bb069"][k], 0.95)]))
    add_scroll_layer(coll, scrolls, hills, None, 190, 190, z=0.0, spacing=120, name="hill")
    add_scroll_layer(coll, scrolls, huts, None, 36, 36, spacing=34, name="hut", jitter_y=4)
    add_scroll_layer(coll, scrolls, palms, None, 16, 16, spacing=9.5, name="palm", jitter_y=4, scale_rng=(0.9, 1.25))
    add_scroll_layer(coll, scrolls, palms, None, 60, 70, spacing=12, name="palmfar", jitter_y=20, scale_rng=(1.1, 1.6))
    add_scroll_layer(coll, scrolls, bushes, None, 8, 6.5, z=0.0, spacing=6.5, name="bush", jitter_y=1.2)
    add_scroll_layer(coll, scrolls, posts, None, 3.0, -3.3, spacing=13.0, name="post", smear=0.03, cap=6)
    add_scroll_layer(coll, scrolls, reeds, None, 3.5, -3.6, spacing=3.6, name="reed", jitter_y=0.5, scale_rng=(0.45, 0.9), smear=0.04, cap=8)
    add_scroll_layer(coll, scrolls, [ridge], None, 12, 25, z=0.02, spacing=7, name="ridge")
    add_scroll_layer(coll, scrolls, [pebble], None, 4, 0.0, z=0.03, spacing=1.6, name="peb", jitter_y=1.6, smear=0.06, cap=14)
    state = dict(root=root, hubs=hubs, ped=ped, limbs=limbs, crank=crank, R=R, sun=sun)

    def update(f, D, v, p):
        ang = D / R
        for h in hubs:
            h.rotation_euler.y = ang
        th = ang * 0.78
        root.location.z = 0.006 * sin(f * 1.7) * (0.5 + p)
        root.rotation_euler.y = 0.006 * sin(f * 0.9)
        root.rotation_euler.x = 0.012 * sin(th * 2)
        c = Vector((0.64, 0, 0.42))
        pole = (1, 0, 0)
        for k, (sgn, ysd) in enumerate(((1, 0.12), (-1, -0.12))):
            a = th + (0 if k == 0 else pi)
            pedal = c + Vector((0.17 * cos(a), ysd, 0.17 * sin(a)))
            ped[k].location = pedal
            hipv = Vector((0.27, ysd * 0.8, 1.0))
            knee = ik2(hipv, pedal + Vector((0, 0, 0.04)), 0.48, 0.48, pole)
            place_bone(limbs["thigh" + "RL"[k]], hipv, knee)
            place_bone(limbs["shin" + "RL"[k]], knee, pedal + Vector((0, 0, 0.04)))
            shv = Vector((0.45, ysd * 1.5, 1.5))
            hand = Vector((1.0, 0.27 * (1 if k == 0 else -1), 0.98))
            elb = ik2(shv, hand, 0.34, 0.36, (0, 0.3 * (1 if k == 0 else -1), -1))
            place_bone(limbs["uarm" + "RL"[k]], shv, elb)
            place_bone(limbs["farm" + "RL"[k]], elb, hand)
        for s in scrolls:
            s.update(D, v)
    return dict(coll=coll, update=update, scrolls=scrolls)

# --------------------------------------------------------------------------
# Segment 2: BUS (highway, dusk)
# --------------------------------------------------------------------------
def build_bus():
    coll = new_coll("S2_bus")
    scrolls = []
    m_body = MAT("bus_body", "#ff4f30", 0.35, 0.05)
    m_cream = MAT("bus_cream", "#f4ecd8", 0.4)
    m_glass = MAT("bus_glass", "#0b1118", 0.1, 0.0, C("#ffb55a"), 0.9)
    m_dark = MAT("bus_dark", "#1b1d22", 0.6)
    m_tire = MAT("bus_tire", "#0f0f10", 0.85)
    m_rim = MAT("bus_rim", "#b9bec6", 0.3, 0.9)
    m_head = EMIT("bus_head", "#fff3c8", 18.0)
    m_tail = EMIT("bus_tail", "#ff2a1a", 8.0)
    m_amber = EMIT("bus_amber", "#ffae1a", 6.0)
    root = empty("bus_root", coll)
    L, W = 9.2, 2.5
    part("bus_lower", bm_box(L, W, 1.15), m_body, coll, root, loc=(0, 0, 0.55 + 0.6))
    part("bus_upper", bm_box(L - 0.1, W - 0.06, 1.25), m_cream, coll, root, loc=(0, 0, 1.2 + 1.2 + 0.1))
    part("bus_roof", bm_box(L - 0.4, W - 0.3, 0.12), m_cream, coll, root, loc=(0, 0, 3.0))
    part("bus_stripe", bm_box(L + 0.02, W + 0.02, 0.18), m_cream, coll, root, loc=(0, 0, 1.0))
    # window band both sides + pillars
    for sy in (-1, 1):
        part("bus_glass%d" % sy, bm_box(L - 0.9, 0.04, 0.95), m_glass, coll, root, loc=(-0.2, sy * (W / 2 - 0.02), 2.3))
        for i in range(9):
            part("bus_pil%d_%d" % (sy, i), bm_box(0.09, 0.06, 1.0), m_cream, coll, root, loc=(-4.2 + i * 0.95 + 0.0, sy * (W / 2 - 0.0), 2.3))
    part("bus_wind", bm_box(0.05, W - 0.35, 1.1), m_glass, coll, root, loc=(L / 2 - 0.02, 0, 2.15))
    part("bus_dest", bm_box(0.06, 1.3, 0.22), m_amber, coll, root, loc=(L / 2 - 0.0, 0, 2.95))
    part("bus_bumper", bm_box(0.25, W + 0.1, 0.3), m_dark, coll, root, loc=(L / 2 + 0.1, 0, 0.55))
    part("bus_bumperR", bm_box(0.25, W + 0.1, 0.3), m_dark, coll, root, loc=(-L / 2 - 0.1, 0, 0.55))
    for sy in (-1, 1):
        part("bus_hl%d" % sy, bm_box(0.12, 0.42, 0.26), m_head, coll, root, loc=(L / 2 + 0.03, sy * 0.88, 0.95))
        part("bus_tl%d" % sy, bm_box(0.1, 0.34, 0.5), m_tail, coll, root, loc=(-L / 2 - 0.02, sy * 0.95, 1.3))
        part("bus_mir%d" % sy, bm_box(0.08, 0.1, 0.45), m_dark, coll, root, loc=(L / 2 - 0.35, sy * (W / 2 + 0.28), 2.2))
    part("bus_rack", bm_box(5.0, 1.8, 0.25), m_dark, coll, root, loc=(-0.6, 0, 3.2))
    part("bus_ac", bm_box(2.2, 1.4, 0.35), m_rim, coll, root, loc=(2.2, 0, 3.25))
    hubs = []
    for nm, x, sy in (("f", 3.1, -1), ("f", 3.1, 1), ("r", -2.8, -1), ("r", -2.8, 1), ("r2", -3.5, -1), ("r2", -3.5, 1)):
        hubs.append(make_wheel("bus_w%s%d" % (nm, sy), 0.52, 0.34, coll, root, (x, sy * (W / 2 - 0.05), 0.52), m_tire, m_rim, bolts=6, tube=0.16))
    for sy in (-1, 1):
        part("bus_arch%d" % sy, bm_box(1.5, 0.04, 0.2), m_dark, coll, root, loc=(3.1, sy * (W / 2), 1.07))
    # environment
    part("s2_ground", bm_box(900, 400, 1.0), MAT("s2_ground", "#1b1d29", 0.95), coll, None, loc=(0, 150, -0.5))
    part("s2_road", bm_box(900, 11.0, 0.05), MAT("s2_road", "#2b2e3b", 0.7), coll, None, loc=(0, 0.0, 0.0))
    part("s2_curb", bm_box(900, 0.3, 0.14), MAT("s2_curb", "#8f93a3", 0.6), coll, None, loc=(0, -5.7, 0.07))
    part("s2_curbF", bm_box(900, 0.3, 0.14), MAT("s2_curbF", "#8f93a3", 0.6), coll, None, loc=(0, 5.7, 0.07))
    dash = to_mesh("dash", bm_box(3.0, 0.16, 0.02), [EMIT("s2_dash", "#f2f4ff", 2.0)])
    dashy = to_mesh("dashy", bm_box(2.0, 0.14, 0.02), [EMIT("s2_dashy", "#ffc94a", 2.0)])
    add_scroll_layer(coll, scrolls, [dash], None, 9.0, -3.0, z=0.04, spacing=9, name="dash", smear=0.12, cap=26)
    add_scroll_layer(coll, scrolls, [dash], None, 9.0, 3.0, z=0.04, spacing=9, name="dash2", smear=0.12, cap=26)
    add_scroll_layer(coll, scrolls, [dashy], None, 9.0, 0.0, z=0.04, spacing=14, name="dashy", smear=0.12, cap=26)
    # street lamps (foreground)
    m_pole = MAT("s2_pole", "#272a33", 0.5, 0.6)
    m_lamp = EMIT("s2_lamp", "#ffd48a", 22.0)
    bm = bmesh.new()
    bm_merge(bm, bm_cyl(0.09, 8.5, 8, r2=0.06, off=(0, 0, 4.25)), None, 0)
    bm_merge(bm, bm_box(2.2, 0.1, 0.1, (1.0, 0, 8.4)), None, 0)
    bm_merge(bm, bm_box(0.7, 0.3, 0.12, (2.0, 0, 8.3)), None, 1)
    lamp = to_mesh("streetlamp", bm, [m_pole, m_lamp])
    add_scroll_layer(coll, scrolls, [lamp], None, 5.5, -6.6, spacing=22, name="lamp", smear=0.012, cap=7)
    # buildings with lit windows
    bmats = [MAT("s2_b%d" % i, c, 0.6) for i, c in enumerate(["#161a33", "#1d1f3d", "#241b3a", "#12182b"])]
    wmats = [EMIT("s2_w%d" % i, c, 4.5) for i, c in enumerate(["#ffd27a", "#ffe9b5", "#8fd8ff", "#ff9bd1"])]
    def building(seed, w, h, d=9.0):
        r = random.Random(seed)
        bm = bmesh.new()
        bm_merge(bm, bm_box(w, d, h, (0, 0, h / 2)), None, 0)
        cols, rows = int(w / 1.7), int(h / 2.6)
        for cx in range(cols):
            for rz in range(rows):
                if r.random() < 0.38:
                    ww = bm_box(0.95, 0.06, 1.2, (-w / 2 + 0.9 + cx * 1.7, -d / 2 - 0.02, 1.8 + rz * 2.6))
                    bm_merge(bm, ww, None, 1 + r.randrange(len(wmats)))
        return to_mesh("bld%d" % seed, bm, [bmats[seed % 4]] + wmats)
    blds = [building(i, RNG.choice([9, 11, 14, 18]), RNG.choice([18, 26, 34, 48])) for i in range(9)]
    low = [building(30 + i, RNG.choice([8, 10, 12]), RNG.choice([6, 9, 12])) for i in range(5)]
    add_scroll_layer(coll, scrolls, low, None, 18, 15, spacing=15, name="low", jitter_y=2)
    add_scroll_layer(coll, scrolls, blds, None, 70, 70, spacing=24, name="sky", jitter_y=18)
    add_scroll_layer(coll, scrolls, blds, None, 150, 170, spacing=34, name="far", jitter_y=20, scale_rng=(1.0, 1.4))
    # neon signs
    sign_cols = ["#ff2e93", "#27e0ff", "#ffcf3a", "#7cff6b"]
    signs = [to_mesh("sign%d" % i, bm_box(0.25, 3.0, 1.0), [EMIT("s2_sign%d" % i, c, 9.0)]) for i, c in enumerate(sign_cols)]
    add_scroll_layer(coll, scrolls, signs, None, 12, 9.0, z=5.5, spacing=31, name="sign", jitter_y=2.0, z_jit=3, smear=0.01, cap=6)
    add_speed_lines(coll, scrolls, 22, (-6.2, -3.6), (0.3, 4.4), 0.9, "#ffd6ea", name="s2sl")
    # distant moon
    part("s2_moon", bm_cyl(9, 0.5, 48, "Y"), EMIT("s2_moon", "#ffe4f0", 6.0), coll, None, loc=(-90, 260, 62))

    def update(f, D, v, p):
        for h in hubs:
            h.rotation_euler.y = D / 0.52
        root.location.z = 0.012 * sin(f * 2.3) * (0.4 + p)
        root.rotation_euler.y = 0.004 * sin(f * 0.7) + (-0.0007 * v * 0.02)
        root.rotation_euler.x = 0.006 * sin(f * 1.3)
        for s in scrolls:
            s.update(D, v)
    return dict(coll=coll, update=update, scrolls=scrolls)

# --------------------------------------------------------------------------
# Segment 3: TRAIN (railway across paddy fields, sunset)
# --------------------------------------------------------------------------
def build_train():
    coll = new_coll("S3_train")
    scrolls = []
    m_green = MAT("tr_green", "#0f7a4a", 0.3, 0.2)
    m_cream = MAT("tr_cream", "#f2e6c4", 0.4)
    m_yellow = MAT("tr_yellow", "#ffc61a", 0.4)
    m_red = MAT("tr_red", "#c9262a", 0.4)
    m_glass = MAT("tr_glass", "#0a0f14", 0.1, 0.0, C("#ffc36a"), 1.2)
    m_dark = MAT("tr_dark", "#1a1c20", 0.6)
    m_metal = MAT("tr_metal", "#50555f", 0.4, 0.8)
    m_tire = MAT("tr_wheel", "#1d1e22", 0.5, 0.7)
    m_head = EMIT("tr_head", "#fff6d8", 40.0)
    root = empty("train_root", coll)
    # loco side profile (XZ) extruded across Y
    Lw = 2.9
    prof = [(-7, 0.95), (6.8, 0.95), (7.2, 1.5), (7.2, 3.1), (6.0, 3.85), (-7, 3.85)]
    part("loco_body", bm_poly(prof, Lw, "XZ"), m_green, coll, root)
    part("loco_stripe", bm_poly([(-7, 1.7), (7.2, 1.7), (7.2, 2.05), (-7, 2.05)], Lw + 0.04, "XZ"), m_yellow, coll, root)
    part("loco_roof", bm_box(11.0, Lw - 0.6, 0.18), m_cream, coll, root, loc=(-0.5, 0, 3.95))
    part("loco_vent", bm_box(1.2, 1.2, 0.35), m_dark, coll, root, loc=(-3.0, 0, 4.1))
    part("loco_vent2", bm_box(1.2, 1.2, 0.35), m_dark, coll, root, loc=(0.2, 0, 4.1))
    part("loco_cabwin", bm_box(0.06, 2.1, 0.8), m_glass, coll, root, loc=(6.35, 0, 3.2), rot=(0, 0.58, 0))
    for sy in (-1, 1):
        part("loco_win%d" % sy, bm_box(1.4, 0.05, 0.75), m_glass, coll, root, loc=(5.3, sy * (Lw / 2 + 0.0), 3.0))
        for i in range(6):
            part("loco_louv%d_%d" % (sy, i), bm_box(0.12, 0.05, 1.6), m_dark, coll, root, loc=(-5.5 + i * 1.7, sy * (Lw / 2), 2.4))
    part("loco_headlight", bm_sphere(0.22, 12, 8), m_head, coll, root, loc=(7.22, 0, 2.5))
    for sy in (-1, 1):
        part("loco_hl%d" % sy, bm_sphere(0.1, 8, 6), m_head, coll, root, loc=(7.22, sy * 0.9, 1.5))
    part("loco_plow", bm_poly([(6.9, 0.95), (7.7, 0.95), (7.2, 1.6)], 2.2, "XZ"), m_red, coll, root)
    hubs = []
    def bogie(xc, parent_name, sx=1.0):
        for ax in (-1.1, 0.0, 1.1):
            for sy in (-1, 1):
                hubs.append(make_wheel("%s_w%.1f_%d" % (parent_name, ax, sy), 0.52, 0.18, coll, root, (xc + ax, sy * 0.72, 0.52), m_tire, m_metal, bolts=0, tube=0.08))
        part(parent_name + "_frame", bm_box(3.6, 1.7, 0.22), m_dark, coll, root, loc=(xc, 0, 0.78))
    bogie(3.7, "lb1"); bogie(-3.9, "lb2")
    # carriages
    n_car = 2
    car_x = []
    x = -7.0 - 0.7
    for c in range(n_car):
        cl = 18.0
        cx = x - cl / 2
        car_x.append(cx)
        part("car%d_body" % c, bm_box(cl, Lw, 2.9), m_cream, coll, root, loc=(cx, 0, 2.35))
        part("car%d_stripe" % c, bm_box(cl + 0.02, Lw + 0.03, 0.34), m_green, coll, root, loc=(cx, 0, 1.75))
        part("car%d_roof" % c, bm_box(cl - 0.3, Lw - 0.5, 0.18), m_green, coll, root, loc=(cx, 0, 3.9))
        for sy in (-1, 1):
            for i in range(10):
                part("car%d_win%d_%d" % (c, sy, i), bm_box(1.2, 0.05, 0.85), m_glass, coll, root, loc=(cx - 7.8 + i * 1.7, sy * (Lw / 2 + 0.0), 2.85))
        bogie(cx + 6.2, "c%db1" % c); bogie(cx - 6.2, "c%db2" % c)
        part("car%d_gap" % c, bm_box(0.7, 2.0, 2.4), m_dark, coll, root, loc=(cx + cl / 2 + 0.35, 0, 2.2))
        x = cx - cl / 2 - 0.7
    # environment
    part("s3_field", bm_box(900, 500, 1.0), MAT("s3_field", "#8cc04a", 0.95), coll, None, loc=(0, 220, -0.5))
    part("s3_bed", bm_box(900, 7.0, 0.5), MAT("s3_bed", "#8d8478", 1.0), coll, None, loc=(0, 0, 0.05), scale=(1, 1, 1))
    for sy in (-0.75, 0.75):
        part("s3_rail%+.2f" % sy, bm_box(900, 0.1, 0.16), MAT("s3_rail", "#aab0b8", 0.3, 0.9), coll, None, loc=(0, sy, 0.38))
    sleeper = to_mesh("sleeper", bm_box(0.3, 2.9, 0.16), [MAT("s3_sleeper", "#3a2a22", 0.9)])
    add_scroll_layer(coll, scrolls, [sleeper], None, 5.0, 0.0, z=0.3, spacing=1.0, name="slp", smear=0.05, cap=18)
    # catenary masts at the near side
    m_mast = MAT("s3_mast", "#3a3f48", 0.5, 0.7)
    bm = bmesh.new()
    bm_merge(bm, bm_box(0.22, 0.22, 7.2, (0, 0, 3.6)), None, 0)
    bm_merge(bm, bm_box(0.18, 3.6, 0.14, (0, 1.8, 6.9)), None, 0)
    bm_merge(bm, bm_box(0.18, 3.6, 0.14, (0, 1.8, 5.6)), None, 0)
    mast = to_mesh("mast", bm, [m_mast])
    add_scroll_layer(coll, scrolls, [mast], None, 7.5, -4.4, spacing=30, name="mast", smear=0.01, cap=6)
    part("s3_wire1", bm_box(900, 0.04, 0.04), m_mast, coll, None, loc=(0, 0, 6.9))
    part("s3_wire2", bm_box(900, 0.04, 0.04), m_mast, coll, None, loc=(0, 0.0, 5.6))
    # paddy strips, trees, villages, hills
    strip = to_mesh("strip", bm_box(5.0, 90, 0.05), [MAT("s3_strip", "#6aa23a", 0.95)])
    add_scroll_layer(coll, scrolls, [strip], None, 20, 40, z=0.02, spacing=11, name="strip")
    m_trunk = MAT("s3_trunk", "#6b4a2d", 0.9)
    m_leafA = MAT("s3_lA", "#3d8b3a", 0.7)
    trees = []
    for k in range(4):
        bm = bmesh.new()
        h = RNG.uniform(3.0, 5.0)
        bm_merge(bm, bm_cyl(0.16, h, 7, r2=0.1, off=(0, 0, h / 2)), None, 0)
        for j in range(3):
            bm_merge(bm, bm_sphere(RNG.uniform(1.4, 2.2), 12, 8, (1, 1, 0.9), (RNG.uniform(-0.7, 0.7), RNG.uniform(-0.7, 0.7), h + j * 0.6)), None, 1)
        trees.append(to_mesh("s3tree%d" % k, bm, [m_trunk, m_leafA]))
    add_scroll_layer(coll, scrolls, trees, None, 24, 22, spacing=12, name="tree", jitter_y=5, scale_rng=(0.9, 1.4))
    add_scroll_layer(coll, scrolls, trees, None, 70, 80, spacing=14, name="treefar", jitter_y=25, scale_rng=(1.3, 2.0))
    hills = [to_mesh("s3hill%d" % k, bm_poly([(-90, 0), (90, 0), (30, 22 + 8 * k), (-35, 18 + 9 * k)], 8, "XZ"), [MAT("s3hill%d" % k, ["#6a8f4b", "#5f8444", "#7a9b57"][k], 0.95)]) for k in range(3)]
    add_scroll_layer(coll, scrolls, hills, None, 260, 260, spacing=170, name="hill")
    part("s3_sun", bm_cyl(20, 0.5, 48, "Y"), EMIT("s3_sun", "#ffe9b0", 12.0), coll, None, loc=(-80, 300, 34))
    add_speed_lines(coll, scrolls, 26, (-8.0, -4.5), (0.15, 5.2), 0.8, "#fff0c4", name="s3sl", smear=0.12, cap=40)
    # billboard-ish poles: telegraph poles far
    tp = to_mesh("tpole", bm_box(0.2, 0.2, 9.0, (0, 0, 4.5)), [m_mast])
    add_scroll_layer(coll, scrolls, [tp], None, 14, 14, spacing=28, name="tpole")

    def update(f, D, v, p):
        for h in hubs:
            h.rotation_euler.y = D / 0.52
        root.location.z = 0.008 * sin(f * 3.1) * (0.4 + p)
        root.rotation_euler.x = 0.004 * sin(f * 2.1)
        for s in scrolls:
            s.update(D, v)
    return dict(coll=coll, update=update, scrolls=scrolls)

# --------------------------------------------------------------------------
# Segment 4: JET (above the clouds)
# --------------------------------------------------------------------------
def build_jet():
    coll = new_coll("S4_jet")
    scrolls = []
    m_white = MAT("jt_white", "#e9edf2", 0.28, 0.15)
    m_grey = MAT("jt_grey", "#8993a1", 0.3, 0.5)
    m_dark = MAT("jt_dark", "#1b1f27", 0.4, 0.6)
    m_red = MAT("jt_red", "#d6262f", 0.35)
    m_green = MAT("jt_green", "#0c8a52", 0.35)
    m_glass = MAT("jt_glass", "#0a1a2a", 0.05, 0.0, C("#4ab2ff"), 0.5)
    m_flameC = EMIT("jt_flame", "#ffb347", 14.0)
    m_flameB = EMIT("jt_flameB", "#8fd0ff", 20.0)
    m_trail = EMIT("jt_trail", "#ffffff", 1.5)
    root = empty("jet_root", coll)
    bm = bmesh.new()
    bm_merge(bm, bm_cyl(0.92, 10.5, 24, "X", smooth_=True), None, 0)
    bm_merge(bm, bm_cyl(0.92, 3.6, 24, "X", r2=0.05, smooth_=True, off=(7.05, 0, 0)), None, 0)
    bm_merge(bm, bm_cyl(0.92, 2.2, 24, "X", r2=0.62, smooth_=True, off=(-6.35, 0, 0)), None, 0)
    fus = part("jet_fuselage", bm, m_white, coll, root)
    part("jet_nose", bm_cyl(0.14, 0.7, 12, "X", r2=0.03, smooth_=True), m_grey, coll, root, loc=(8.95, 0, 0))
    part("jet_canopy", bm_sphere(1.0, 16, 10, (1.9, 0.52, 0.5)), m_glass, coll, root, loc=(3.7, 0, 0.78))
    part("jet_stripeR", bm_cyl(0.935, 0.5, 24, "X", smooth_=True), m_red, coll, root, loc=(-1.2, 0, 0))
    part("jet_stripeG", bm_cyl(0.935, 0.5, 24, "X", smooth_=True), m_green, coll, root, loc=(-0.5, 0, 0))
    for sy in (-1, 1):
        wing = [(2.8, 0.7), (-3.2, 6.4), (-4.7, 6.4), (-4.7, 0.7)]
        pts = [(a, b * sy) for a, b in wing] if sy > 0 else [(a, b * sy) for a, b in reversed(wing)]
        part("jet_wing%d" % sy, bm_poly(pts, 0.14, "XY"), m_white, coll, root, loc=(0, 0, -0.18))
        tip = [(-3.2, 6.4), (-4.7, 6.4), (-4.7, 6.8), (-3.6, 6.8)]
        tp = [(a, b * sy) for a, b in tip] if sy > 0 else [(a, b * sy) for a, b in reversed(tip)]
        part("jet_tip%d" % sy, bm_poly(tp, 0.16, "XY"), m_red, coll, root, loc=(0, 0, -0.18))
        tail = [(-4.2, 0.7), (-6.4, 3.0), (-7.4, 3.0), (-7.2, 0.7)]
        tpp = [(a, b * sy) for a, b in tail] if sy > 0 else [(a, b * sy) for a, b in reversed(tail)]
        part("jet_tailplane%d" % sy, bm_poly(tpp, 0.1, "XY"), m_grey, coll, root, loc=(0, 0, -0.1))
        fin = [(-4.0, 0.8), (-6.6, 3.4), (-7.5, 3.4), (-7.1, 0.8)]
        part("jet_fin%d" % sy, bm_poly(fin, 0.1, "XZ"), m_white, coll, root, loc=(0, sy * 0.62, 0.0), rot=(sy * 0.32, 0, 0))
        part("jet_finstripe%d" % sy, bm_poly([(-6.5, 3.3), (-7.5, 3.3), (-7.35, 2.6), (-6.2, 2.6)], 0.12, "XZ"), m_green, coll, root, loc=(0, sy * 0.62, 0.0), rot=(sy * 0.32, 0, 0))
        part("jet_eng%d" % sy, bm_cyl(0.52, 2.8, 16, "X", r2=0.44, smooth_=True), m_grey, coll, root, loc=(-5.9, sy * 0.78, -0.12))
        part("jet_noz%d" % sy, bm_cyl(0.46, 0.8, 16, "X", r2=0.36, smooth_=True), m_dark, coll, root, loc=(-7.6, sy * 0.78, -0.12))
        part("jet_intake%d" % sy, bm_cyl(0.34, 1.9, 14, "X", r2=0.26, smooth_=True), m_grey, coll, root, loc=(1.7, sy * 1.05, -0.12))
    flames = []
    for sy in (-1, 1):
        fo = part("jet_flame%d" % sy, bm_cyl(0.34, 1.0, 12, "X", r2=0.02, smooth_=True), m_flameC, coll, root, loc=(-8.0, sy * 0.78, -0.12))
        fi = part("jet_flameI%d" % sy, bm_cyl(0.22, 1.0, 12, "X", r2=0.01, smooth_=True), m_flameB, coll, root, loc=(-8.0, sy * 0.78, -0.12))
        flames.append((fo, fi, sy))
    # contrails from wing tips
    trails = []
    for sy in (-1, 1):
        tr = part("jet_trail%d" % sy, bm_cyl(0.05, 1.0, 8, "X", r2=0.42, smooth_=True), m_trail, coll, root, loc=(-5.0, sy * 6.8, -0.18))
        trails.append((tr, sy))
    # clouds and streaks
    m_cloudA = MAT("jt_cl", "#ffffff", 0.9, 0.0, C("#ffffff"), 0.9)
    m_cloudB = MAT("jt_clB", "#ffd3c2", 0.9, 0.0, C("#ffd0b8"), 0.8)
    clouds = [to_mesh("cl%d" % k, bm_sphere(1.0, 14, 9, (1.0, 1.0, 0.35)), [m_cloudA if k % 2 else m_cloudB]) for k in range(4)]
    cl_ob = []
    for layer, (y0, y1, z0, z1, sx, n) in enumerate([(-30, -10, -10, -5, 4, 12), (6, 40, -18, -8, 6, 14), (40, 110, -34, -14, 11, 14), (-24, -12, 8, 16, 3, 5), (20, 80, 14, 34, 7, 6)]):
        span = span_for(abs(y0) + 20) * 1.2
        for i in range(n):
            me = RNG.choice(clouds)
            sc = RNG.uniform(0.7, 1.4)
            ob = obj("cl%d_%d" % (layer, i), me, coll, (0, RNG.uniform(y0, y1), RNG.uniform(z0, z1)), (0, 0, 0), (sx * sc, sx * 0.6 * sc, sx * 0.5 * sc))
            scrolls.append(Scroll(ob, (i + RNG.random() * 0.8) * span / n, span, 0.0, 0.03, 9, sx * sc))
    m_streak = EMIT("jt_streak", "#ffffff", 1.6)
    streak = to_mesh("streak", bm_box(1.0, 0.035, 0.035), [m_streak])
    for i in range(70):
        ang = RNG.uniform(0, tau)
        rr = RNG.uniform(5, 26)
        sc = RNG.uniform(5, 14)
        ob = obj("stk%d" % i, streak, coll, (0, rr * cos(ang) * 1.2, rr * sin(ang) * 0.6), (0, 0, 0), (sc, 1, 1))
        scrolls.append(Scroll(ob, RNG.uniform(0, 300), 300, 0.0, 0.5, 40, sc))
    part("jt_sea", bm_box(2000, 1200, 1.0), MAT("jt_sea", "#fff0e6", 1.0, 0.0, C("#ffe0cc"), 0.9), coll, None, loc=(0, 0, -62))

    def update(f, D, v, p):
        t = f / FPS
        root.rotation_euler.x = 0.07 * sin(t * 1.3) + 0.03 * sin(t * 3.7)
        root.rotation_euler.y = -0.05 + 0.02 * sin(t * 1.9)
        root.location.z = 0.35 * sin(t * 1.1)
        fl = 1.0 + 0.1 * sin(f * 3.1) + 0.06 * sin(f * 7.3)
        flen = lerp(2.6, 9.0, smooth(p)) * fl
        for fo, fi, sy in flames:
            fo.scale = (flen, 1, 1); fo.location.x = -8.0 - flen / 2 + 0.2
            fi.scale = (flen * 0.6, 1, 1); fi.location.x = -8.0 - flen * 0.3 + 0.2
        for tr, sy in trails:
            ln = lerp(80, 340, smooth(p))
            tr.scale = (ln, 1.0, 1.0)
            tr.location.x = -5.0 - ln / 2
        for s in scrolls:
            s.update(D, v)
    return dict(coll=coll, update=update, scrolls=scrolls)

# --------------------------------------------------------------------------
# Segment 5: LIGHT (tunnel of light) + end card background
# --------------------------------------------------------------------------
def build_light():
    coll = new_coll("S5_light")
    scrolls = []
    pal = ["#00d8ff", "#2f5bff", "#8a3dff", "#ff2fcf", "#ff9a1f", "#19ffb0"]
    mats = [EMIT("lt_ring%d" % i, c, 1.5) for i, c in enumerate(pal)]
    mat_white = EMIT("lt_white", "#ffffff", 5.0)
    ring_meshes = [to_mesh("ring%d" % i, bm_torus(5.0, 0.07, 48, 6, "X"), [mats[i % len(mats)]]) for i in range(len(pal))]
    hex_meshes = [to_mesh("hex%d" % i, bm_torus(8.0, 0.05, 6, 5, "X"), [mats[(i + 2) % len(mats)]]) for i in range(len(pal))]
    n = 60
    span = 420.0
    rings = []
    for i in range(n):
        ob = obj("ring%d" % i, ring_meshes[i % len(pal)], coll, (0, 0, 0), (0, 0, 0), (1, 1 + 0.4 * (i % 3), 1 + 0.4 * (i % 3)))
        s = Scroll(ob, i * span / n, span, 215.0, 0.006, 22, 1.0)
        scrolls.append(s); rings.append(ob)
    for i in range(n // 2):
        ob = obj("hex%d" % i, hex_meshes[i % len(pal)], coll, (0, 0, 0), (i * 0.5, 0, 0), (1, 1, 1))
        scrolls.append(Scroll(ob, i * span / (n // 2) + 3.3, span, 215.0, 0.006, 22, 1.0))
    streak_mats = [EMIT("lt_s%d" % i, c, 2.2) for i, c in enumerate(["#ffffff", "#00d8ff", "#ff2fcf", "#ffb02e"])]
    streak_mesh = [to_mesh("lstreak%d" % i, bm_box(1.0, 0.05, 0.05), [streak_mats[i]]) for i in range(4)]
    for i in range(260):
        ang = RNG.uniform(0, tau)
        rr = RNG.uniform(1.6, 8.5)
        ob = obj("ls%d" % i, RNG.choice(streak_mesh), coll, (0, rr * cos(ang), rr * sin(ang)))
        base = RNG.uniform(2, 9)
        scrolls.append(Scroll(ob, RNG.uniform(0, span), span, 215.0, 0.1, 140, base))
        ob.scale = (base, 1, 1)
    core = part("lt_core", bm_sphere(1.0, 24, 16), mat_white, coll, None, loc=(430, 0, 0))
    halo_m = EMIT("lt_halo", "#9fd9ff", 2.5)
    halo = part("lt_halo", bm_sphere(1.0, 24, 16), halo_m, coll, None, loc=(432, 0, 0))
    dimm = [(m, m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value) for m in mats + streak_mats + [mat_white, halo_m]]

    def update(f, D, v, p):
        t = f / FPS
        pull = smooth((f - 300) / 40.0)
        if f >= END_START:
            core.scale = (0.0001,) * 3; halo.scale = (0.0001,) * 3
        else:
            r = lerp(2.0, 64.0, (pull ** 2.2))
            core.scale = (r, r, r)
            halo.scale = (r * 1.6, r * 1.6, r * 1.6)
        k = 1.0 if f < END_START else lerp(1.0, 0.07, smooth((f - END_START) / 9.0))
        for m_, b_ in dimm:
            m_.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = b_ * k
        for s in scrolls:
            s.update(D, v)
    return dict(coll=coll, update=update, scrolls=scrolls)

# --------------------------------------------------------------------------
# HUD (3D text parented to camera) + camera + lights
# --------------------------------------------------------------------------
FONT_B = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
FONT_M = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
FONT_S = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"

def make_text(name, body, size, coll, parent, loc, mat, font, align="LEFT"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.extrude = 0.0
    try:
        cu.font = bpy.data.fonts.load(font)
    except Exception:
        pass
    cu.materials.append(mat)
    ob = obj(name, cu, coll, loc, parent=parent)
    return ob

def build_hud(cam):
    coll = new_coll("HUD")
    hud = empty("hud_root", coll, loc=(0, 0, -1.0), parent=cam)
    # soft dark gradient behind the readout (alpha-blended plane, no shadows)
    gm = bpy.data.materials.new("hud_shade")
    gm.use_nodes = True
    try:
        gm.surface_render_method = "BLENDED"
    except Exception:
        pass
    nt = gm.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 1.4
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 0.82
    tr = nt.nodes.new("ShaderNodeBsdfTransparent"); bk = nt.nodes.new("ShaderNodeEmission")
    bk.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0); bk.inputs["Strength"].default_value = 1.0
    mx = nt.nodes.new("ShaderNodeMixShader"); out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Y"], inv.inputs[1]); nt.links.new(inv.outputs[0], pw.inputs[0])
    nt.links.new(pw.outputs[0], mul.inputs[0]); nt.links.new(mul.outputs[0], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(bk.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    gbm = bmesh.new()
    gv = [gbm.verts.new(c) for c in ((-1.05, -0.62, 0), (1.05, -0.62, 0), (1.05, -0.06, 0), (-1.05, -0.06, 0))]
    gbm.faces.new(gv)
    shade = part("hud_shade", gbm, gm, coll, hud, loc=(0, 0, -0.012))
    shade.visible_shadow = False
    mw = EMIT("hud_white", "#ffffff", 3.2)
    md = EMIT("hud_dim", "#ffffff", 1.1)
    ma = EMIT("hud_acc", "#ffb347", 3.6)
    lab = make_text("hud_label", "RICKSHAW", 0.036, coll, hud, (-0.925, -0.285, 0), ma, FONT_S)
    num = make_text("hud_num", "6", 0.125, coll, hud, (-0.93, -0.425, 0), mw, FONT_B)
    unit = make_text("hud_unit", "km/h", 0.036, coll, hud, (-0.93, -0.475, 0), md, FONT_M)
    idx = make_text("hud_idx", "01 / 05", 0.026, coll, hud, (0.925, -0.285, 0), md, FONT_M, "RIGHT")
    brand = make_text("hud_brand", "FutureTech.ai", 0.026, coll, hud, (0.925, 0.50, 0), md, FONT_S, "RIGHT")
    track = part("hud_track", bm_box(1.85, 0.0035, 0.0005, (0.925, 0, 0)), md, coll, hud, loc=(-0.925, -0.525, 0))
    fill = part("hud_fill", bm_box(1.85, 0.0075, 0.001, (0.925, 0, 0)), mw, coll, hud, loc=(-0.925, -0.525, 0))
    ticks = []
    for i in range(1, 5):
        ticks.append(part("hud_tick%d" % i, bm_box(0.003, 0.02, 0.001), md, coll, hud, loc=(-0.925 + 1.85 * (SEGS[i][1] - 1) / 340.0, -0.525, 0)))
    # end-card title
    mt = EMIT("title_white", "#ffffff", 0.0)
    ms = EMIT("title_sub", "#bcd8ff", 0.0)
    mb = EMIT("title_brand", "#ffb347", 0.0)
    t1 = make_text("title1", "THE EVOLUTION OF SPEED", 0.115, coll, hud, (0, 0.04, 0), mt, FONT_B, "CENTER")
    t2 = make_text("title2", "from a rickshaw to the speed of light", 0.045, coll, hud, (0, -0.075, 0), ms, FONT_M, "CENTER")
    t3 = make_text("title3", "FutureTech.ai", 0.042, coll, hud, (0, -0.32, 0), mb, FONT_S, "CENTER")
    t4 = make_text("title4", "a 100% procedural Blender Python film", 0.028, coll, hud, (0, -0.375, 0), ms, FONT_M, "CENTER")
    hud_parts = [lab, num, unit, idx, brand, track, fill, shade] + ticks
    return dict(root=hud, lab=lab, num=num, unit=unit, idx=idx, fill=fill, hud_parts=hud_parts,
                titles=[(t1, mt, 6.0), (t2, ms, 3.0), (t3, mb, 4.0), (t4, ms, 2.2)], mats=[mw, md, ma], coll=coll)

def look_at(cam_ob, target, roll=0.0):
    d = Vector(target) - cam_ob.location
    q = d.to_track_quat("-Z", "Y")
    if roll:
        q = q @ Quaternion((0, 0, 1), roll)
    cam_ob.rotation_euler = q.to_euler()

def shake(f, amp, seed=0.0):
    t = f * 0.31 + seed
    return Vector((sin(t * 3.1) + 0.6 * sin(t * 7.7 + 1.0), sin(t * 2.3 + 2.0) + 0.6 * sin(t * 6.1), sin(t * 2.9 + 0.5) + 0.5 * sin(t * 8.9))) * amp

# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", nargs="+", type=int, default=[1, 396], help="a b = range, or list with --list")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--res", nargs=2, type=int, default=[1920, 1080])
    ap.add_argument("--samples", type=int, default=12)
    ap.add_argument("--out", default="frames")
    ap.add_argument("--save-blend", default="")
    a = ap.parse_args(sys.argv[1:])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    global scene, ROOT_COLL
    scene = bpy.context.scene
    ROOT_COLL = scene.collection
    setup_render(tuple(a.res), a.samples, a.out)
    ramp, bgn = setup_world()

    cam_data = bpy.data.cameras.new("cam")
    cam_data.sensor_width = 36
    cam_data.clip_start = 0.05
    cam_data.clip_end = 4000
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    sun_d = bpy.data.lights.new("key", "SUN"); sun_d.angle = 0.05
    sun = bpy.data.objects.new("key", sun_d); scene.collection.objects.link(sun)
    fill_d = bpy.data.lights.new("fill", "SUN"); fill_d.angle = 0.3
    fill = bpy.data.objects.new("fill", fill_d); scene.collection.objects.link(fill)

    segs = [build_rickshaw(), build_bus(), build_train(), build_jet(), build_light()]
    hud = build_hud(cam)

    vl = bpy.context.view_layer
    names = ["S1_rickshaw", "S2_bus", "S3_train", "S4_jet", "S5_light"]

    # per-segment look
    LOOK = [
        dict(sky=[(0.0, "#ffe6bd"), (0.48, "#ffd08a"), (0.55, "#ffb86b"), (0.75, "#79a7e0"), (1.0, "#3d6fc4")], bg=1.0,
             sun=("#ffd9a0", 4.5, (math.radians(62), 0, math.radians(-115))), fill=("#9fc3ff", 0.7, (math.radians(50), 0, math.radians(60)))),
        dict(sky=[(0.0, "#1a1c4a"), (0.48, "#ff7e5f"), (0.55, "#d9487f"), (0.75, "#4a2a78"), (1.0, "#0b0f33")], bg=1.0,
             sun=("#ffb48a", 3.6, (math.radians(66), 0, math.radians(30))), fill=("#8fb0ff", 1.4, (math.radians(55), 0, math.radians(-150)))),
        dict(sky=[(0.0, "#ffe3a8"), (0.48, "#ffc267"), (0.55, "#ffa75a"), (0.72, "#6aa0dc"), (1.0, "#2e5fb0")], bg=1.0,
             sun=("#ffc98a", 4.6, (math.radians(70), 0, math.radians(-70))), fill=("#a8c7ff", 1.2, (math.radians(50), 0, math.radians(90)))),
        dict(sky=[(0.0, "#fff0e6"), (0.45, "#ffd2b0"), (0.5, "#ff9f6b"), (0.56, "#c8689f"), (0.68, "#3556c9"), (1.0, "#06103f")], bg=1.0,
             sun=("#ffd7b0", 5.0, (math.radians(95), 0, math.radians(-115))), fill=("#8fb4ff", 1.0, (math.radians(40), 0, math.radians(60)))),
        dict(sky=[(0.0, "#05010f"), (0.5, "#080318"), (1.0, "#05010f")], bg=0.6,
             sun=("#ffffff", 0.0, (math.radians(70), 0, 0)), fill=("#ffffff", 0.0, (math.radians(50), 0, 0))),
    ]

    # camera design per segment: (start pos, end pos, target, lens start, lens end, shake)
    def camera_for(f, i, p, v):
        t = f / FPS
        if i == 0:
            pos = Vector((lerp(1.4, 0.5, smooth(p)), lerp(-6.4, -5.0, smooth(p)), lerp(0.85, 1.15, smooth(p))))
            tgt = Vector((0.35, 0, 0.95))
            lens = lerp(34, 29, smooth(p)); sh = 0.004 + 0.002 * p
            roll = 0.0
        elif i == 1:
            pos = Vector((lerp(7.2, 5.4, smooth(p)), lerp(-10.5, -8.2, smooth(p)), lerp(0.9, 1.7, smooth(p))))
            tgt = Vector((0.4, 0, 1.55))
            lens = lerp(34, 26, smooth(p)); sh = 0.010 + 0.006 * p
            roll = 0.02 * sin(t * 1.4)
        elif i == 2:
            pos = Vector((lerp(-1.0, 6.5, smooth(p)), lerp(-17.5, -13.0, smooth(p)), lerp(1.0, 1.6, smooth(p))))
            tgt = Vector((lerp(0.5, 3.5, smooth(p)), 0, 2.4))
            lens = lerp(24, 18, smooth(p)); sh = 0.014 + 0.008 * p
            roll = 0.01 * sin(t * 1.9)
        elif i == 3:
            pos = Vector((lerp(2.0, 9.5, smooth(p)), lerp(-19.5, -14.0, smooth(p)), lerp(-3.4, -1.2, smooth(p))))
            tgt = Vector((lerp(0.0, 1.5, p), 0, lerp(2.4, 1.6, p)))
            lens = lerp(30, 21, smooth(p)); sh = 0.03 + 0.03 * p
            roll = 0.05 * sin(t * 1.1) + 0.06 * p
        else:
            q = max(0.0, (f - 289) / 51.0)
            pos = Vector((0, 0, 0))
            tgt = Vector((100, 0, 0))
            lens = lerp(24, 12, smooth(min(q, 1.0)) ** 1.2) if f < END_START else 16
            sh = 0.03 + 0.12 * q ** 2 if f < END_START else 0.01
            roll = (0.25 * t + 1.1 * q * q) if f < END_START else 0.0
        return pos, tgt, lens, sh, roll

    def hud_visible(f):
        return f < END_START

    def set_frame(f):
        i = seg_index(f)
        si = min(i, 4)
        nm, a0, b0, label = SEGS[si]
        p = (f - a0) / max(1, (b0 - a0)) if f < END_START else 1.0
        for k, n in enumerate(names):
            vl.layer_collection.children[n].exclude = (k != si)
        look = LOOK[si]
        set_ramp(ramp, look["sky"])
        bgn.inputs["Strength"].default_value = look["bg"]
        sun_d.color = C(look["sun"][0]); sun_d.energy = look["sun"][1]; sun.rotation_euler = look["sun"][2]
        fill_d.color = C(look["fill"][0]); fill_d.energy = look["fill"][1]; fill.rotation_euler = look["fill"][2]
        scene.eevee.use_shadows = (si != 4)
        D = DIST[f]; v = treadmill_speed(f)
        segs[si]["update"](f, D, v, p)
        pos, tgt, lens, sh, roll = camera_for(f, si, p, v)
        # punch in on cuts
        for cf in CUTS:
            d = f - cf
            if 0 <= d < 8:
                lens *= 1.0 - 0.28 * (1 - smooth(d / 8.0))
        cam_data.lens = lens
        cam.location = pos + shake(f, sh, si * 3.7)
        look_at(cam, tgt + shake(f, sh * 0.8, si * 5.1 + 1.0), roll)
        # exposure whiteout around cuts
        ex = 0.0
        for cf in CUTS:
            d = abs(f - cf + 0.0)
            if cf == 341:
                if f <= 340:
                    d = max(0, 340 - f)
                    ex = max(ex, 14.0 * smooth(1 - d / 5.0))
                else:
                    ex = max(ex, 14.0 * smooth(1 - (f - 340) / 6.0))
            else:
                ex = max(ex, 14.0 * smooth(1 - abs(f - (cf - 0.5)) / 3.2))
        scene.view_settings.exposure = ex
        # HUD
        hud["root"].scale = (18.0 / lens,) * 3
        vis = hud_visible(f)
        for ob in hud["hud_parts"]:
            ob.hide_render = not vis
        for (to, mt, st) in hud["titles"]:
            to.hide_render = vis
        if vis:
            kmh = hud_kmh(f)
            hud["lab"].data.body = label
            hud["num"].data.body = "{:,.0f}".format(kmh)
            hud["num"].data.size = 0.125 if kmh < 1e7 else 0.1
            hud["unit"].location.x = -0.93 + (0.0)
            hud["idx"].data.body = "%02d / 05" % (si + 1)
            hud["fill"].scale.x = max(0.0005, (f - 1) / 339.0)
            hud["unit"].location.y = -0.475
            hud["lab"].data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (*C(["#ffb347", "#ff7e5f", "#ffc267", "#8fb4ff", "#9fe9ff"][si]), 1)
        else:
            u = min(1.0, (f - END_START) / 19.0)
            for (to, mt, st) in hud["titles"]:
                k = smooth((u - 0.05) / 0.55)
                mt.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = st * k
        return si

    # frame list
    if a.list:
        frames = a.frames
    else:
        frames = list(range(a.frames[0], a.frames[1] + 1))
    os.makedirs(a.out, exist_ok=True)
    if a.save_blend:
        set_frame(frames[0]); bpy.ops.wm.save_as_mainfile(filepath=a.save_blend)
    for f in frames:
        t0 = time.time()
        set_frame(f)
        scene.frame_set(f)
        scene.render.filepath = os.path.join(a.out, "f_%04d.png" % f)
        bpy.ops.render.render(write_still=True)
        print("DONE frame %d in %.1fs" % (f, time.time() - t0), flush=True)

if __name__ == "__main__":
    main()
