"""
.blend to TMD export.
Only objects in "Collection" collection are exported, they're automatically joined and triangulated.
Only flat shaded meshes are supported:
    Use Color Attribute -> Face Corner (NOT Vertex color).
Run via CLI:
    /usr/bin/blender <BLEND_FILE> \
            --quiet --python-exit-code 1 \
            --background --python tmd_export.py \
            -- <OUTPUT_FILE_PATH>
            
Original credit for .blend to .tmd exporter to eliasdaler (https://gist.github.com/eliasdaler/36e379a097a65c4239b042b6f43463b0)
"""

import bmesh
import bpy
import math
import struct
import sys

from operator import attrgetter

from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty
from bpy.types import Operator

bl_info = {
    "name": ".blend to .tmd export",
    "description": "A plugin for exporting meshes to .tmd",
    "author": "Elias Daler",
    "version": (0, 1),
    "blender": (4, 1, 0),
    "category": "Import-Export",
}


def triangulate_mesh(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()


def float_to_fixed_4_12(f):
    #frac, integer = math.modf(f)
    #scaled_frac = int(frac * 4096)
    #fixed_point_value = (int(integer) << 12) | scaled_frac
    #return fixed_point_value
    return max(-32768, min(32767, int(round(f * 4096.0))))

# Rounds normal to 0.01 precision to find similar normals
def to_psx_normal(normal):
    precision = 0.01
    # Blender -> PSX coordinate conversion
    # X' = +X
    # Y' = -Z
    # Z' = +Y
    # You can change the normals to change the lighting direction
    return (
        round(+normal.x / precision) * precision,
        round(-normal.z / precision) * precision,
        round(+normal.y / precision) * precision,
    )

def get_face_uvs(mesh, poly, uv_layer, op):
    if not uv_layer:
        raise ValueError(f"Mesh {mesh.name} needs an active UV map")
    tex_w = op.tex_width
    tex_h = op.tex_height
    uvs = []

    for loop_index in poly.loop_indices:
        uv = uv_layer.data[loop_index].uv

        u = int(round(uv.x * (tex_w - 1))) & 0xFF
        v = int(round((1.0 - uv.y) * (tex_h - 1))) & 0xFF

        uvs.append((u, v))

    return uvs

def get_face_color(mesh, poly, vertex_colors, vertex_colors_domain):
    # Fallback white
    face_color = [255, 255, 255]

    if vertex_colors is None:
        return face_color

    for loop_index in poly.loop_indices:
        vi = mesh.loops[loop_index].vertex_index

        if vertex_colors_domain == "POINT":
            color = vertex_colors[vi].color_srgb
        else:
            color = vertex_colors[loop_index].color_srgb

        face_color = [
            max(0, min(255, int(round(color[0] * 255.0)))),
            max(0, min(255, int(round(color[1] * 255.0)))),
            max(0, min(255, int(round(color[2] * 255.0)))),
        ]

    return face_color

def face_uses_texture(mesh, poly, op):
    if not op or op.color_mode != 'TEXTURE':
        return False

    if poly.material_index >= len(mesh.materials):
        return False

    material = mesh.materials[poly.material_index]

    if not material or not material.use_nodes:
        return False

    for node in material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image is not None:
            return True

    return False

def make_tsb(tpage, abr=0, tp=0):
    return tpage | (abr << 5) | (tp << 7)

def make_cba(clut_x, clut_y):
    return (clut_y << 6) | (clut_x >> 4)

def write_tmd_header(f, mesh, normals):
    f.write(struct.pack('I', 0x41))  # id
    f.write(struct.pack('I', 0x0))   # flags
    f.write(struct.pack('I', 1))     # num objects

    object_start = f.tell()

    vert_top_addr_pos = f.tell()
    f.write(struct.pack('I', 0))

    f.write(struct.pack('I', len(mesh.vertices)))

    normal_top_addr_pos = f.tell()
    f.write(struct.pack('I', 0))

    f.write(struct.pack('I', len(normals)))

    primitive_top_addr_pos = f.tell()
    f.write(struct.pack('I', 0))

    f.write(struct.pack('I', len(mesh.polygons)))

    f.write(struct.pack('I', 0))

    #primitive_top_addr = f.tell() - object_start
    #f.seek(primitive_top_addr_pos)
    #f.write(struct.pack('I', primitive_top_addr))
    #f.seek(object_start + 24)

    return {
        "object_start": object_start,
        "vert_top_addr_pos": vert_top_addr_pos,
        "normal_top_addr_pos": normal_top_addr_pos,
        "primitive_top_addr_pos": primitive_top_addr_pos,
    }

def prepare_mesh_data(mesh, op):
    normals = []
    normal_map = {}

    for poly in mesh.polygons:
        psx_normal = to_psx_normal(poly.normal)

        if psx_normal not in normal_map:
            normal_map[psx_normal] = len(normals)
            normals.append(list(psx_normal))

    vertex_colors = None
    vertex_colors_domain = None

    if mesh.color_attributes:
        vertex_colors = mesh.color_attributes[0].data
        vertex_colors_domain = mesh.color_attributes[0].domain

    uv_layer = mesh.uv_layers.active

    return {
        "normals": normals,
        "normal_map": normal_map,
        "vertex_colors": vertex_colors,
        "vertex_colors_domain": vertex_colors_domain,
        "uv_layer": uv_layer,
    }
    
def write_normals(f, normals, header):
    normals_pos = f.tell()
    normal_top_addr = normals_pos - header["object_start"]
    f.seek(header["normal_top_addr_pos"])
    f.write(struct.pack('I', normal_top_addr))
    f.seek(normals_pos)

    for normal in normals:
        f.write(struct.pack('h', float_to_fixed_4_12(normal[0])))
        f.write(struct.pack('h', float_to_fixed_4_12(normal[1])))
        f.write(struct.pack('h', float_to_fixed_4_12(normal[2])))
        f.write(struct.pack('H', 0))  # pad

def write_vertices(f, mesh, header):
    vertices_pos = f.tell()
    vert_top_addr = vertices_pos - header["object_start"]
    f.seek(header["vert_top_addr_pos"])
    f.write(struct.pack('I', vert_top_addr))
    f.seek(vertices_pos)

    for vertex in mesh.vertices:
        # Blender -> PSX coordinate conversion
        # X' = X
        # Y' = -Z
        # Z' = Y
        f.write(struct.pack('h', float_to_fixed_4_12(+vertex.co.x)))
        f.write(struct.pack('h', float_to_fixed_4_12(-vertex.co.z)))
        f.write(struct.pack('h', float_to_fixed_4_12(+vertex.co.y)))
        f.write(struct.pack('H', 0))  # pad

def write_colored_triangle(f, verts, normal_index, face_color, unlit_bit):
    mode = 0x21 if unlit_bit else 0x20

    f.write(struct.pack('BBBB', 4, 3, unlit_bit, mode))
    f.write(struct.pack('BBBB', face_color[2], face_color[1], face_color[0], mode))
    f.write(struct.pack('HHHH', normal_index, verts[2], verts[1], verts[0]))

def write_textured_triangle(f, verts, uvs, normal_index, op, unlit_bit):
    tsb = make_tsb(op.tpage, abr=0, tp=int(op.tp))
    cba = make_cba(op.clut_x, op.clut_y)

    mode = 0x25 if unlit_bit else 0x24

    f.write(struct.pack('BBBB',7, 5, unlit_bit, mode))

    # UVs correspond to vertices 2, 1, 0
    f.write(struct.pack('BBH', *uvs[2], cba))
    f.write(struct.pack('BBH', *uvs[1], tsb))
    f.write(struct.pack('BBH', *uvs[0], 0))

    f.write(struct.pack('HHHH', normal_index, verts[2], verts[1], verts[0]))

def write_primitives(f, mesh, data, op, header):
    unlit_bit = 1 if op and op.unlit else 0

    primitive_pos = f.tell()
    primitive_top_addr = primitive_pos - header["object_start"]
    f.seek(header["primitive_top_addr_pos"])
    f.write(struct.pack('I', primitive_top_addr))
    f.seek(primitive_pos)

    for poly in mesh.polygons:
        verts = [mesh.loops[li].vertex_index for li in poly.loop_indices]

        psx_normal = to_psx_normal(poly.normal)
        normal_index = data["normal_map"][psx_normal]

        if face_uses_texture(mesh, poly, op):
        #if op and op.color_mode == 'TEXTURE':
            uvs = get_face_uvs( mesh, poly, data["uv_layer"],op)

            write_textured_triangle(f, verts, uvs, normal_index, op, unlit_bit)
            
        else:
            face_color = get_face_color(mesh, poly, data["vertex_colors"], data["vertex_colors_domain"])

            write_colored_triangle(f, verts, normal_index, face_color, unlit_bit)

def write_tmd_from_mesh(mesh, path, op=None):
    triangulate_mesh(mesh)
    data = prepare_mesh_data(mesh, op)

    with open(path, 'wb') as f:
        header = write_tmd_header(f, mesh, data['normals'])
        write_primitives(f, mesh, data, op, header)
        write_vertices(f, mesh, header)
        write_normals(f, data["normals"], header)
        
    print("object_start:", header["object_start"])
    print("primitive_top_addr_pos:", header["primitive_top_addr_pos"])
    print("vertex_top_addr_pos:", header["vert_top_addr_pos"])
    print("normal_top_addr_pos:", header["normal_top_addr_pos"])

def apply_modifiers(obj):
    ctx = bpy.context.copy()
    ctx['object'] = obj
    for _, m in enumerate(obj.modifiers):
        try:
            ctx['modifier'] = m
            with bpy.context.temp_override(**ctx):
                bpy.ops.object.modifier_apply(modifier=m.name)
        except RuntimeError:
            print(f"Error applying {m.name} to {obj.name}, removing it instead.")
            obj.modifiers.remove(m)

    for m in obj.modifiers:
        obj.modifiers.remove(m)

def collect_objects(collection_objects):
    obj_set = set(o for o in collection_objects if o.type == 'MESH')
    obj_list = list(obj_set)
    obj_list.sort(key=attrgetter("name"))
    return obj_list

def collect_meshes(scene):
    # find objects with meshes
    mesh_objects = []
    for obj in scene.objects:
        if obj.type == 'MESH':
            mesh_objects.append(obj)
            apply_modifiers(obj)
            if obj.parent: # possibly armature?
                # apply all transforms
                with bpy.context.temp_override(
                    active_object=obj.parent,
                    selected_editable_objects=[obj.parent]
                ):
                    bpy.ops.object.transform_apply(
                        location=True,
                        rotation=True,
                        scale=True)

        # apply all transforms
        with bpy.context.temp_override(
            active_object=obj,
            selected_editable_objects=[obj]
        ):
            bpy.ops.object.transform_apply(
                location=True,
                rotation=True,
                scale=True)

    meshes_set = set(o.data for o in mesh_objects)

    mesh_list = list(meshes_set)
    mesh_list.sort(key=attrgetter("name"))

    return mesh_list


def write_tmd(context, filepath, op=None):
    bpy.ops.object.mode_set(mode='OBJECT')

    scene = context.scene
    meshes = collect_meshes(scene)
    if len(meshes) != 1:
        default_collection = bpy.data.collections.get("Collection")
        obj_list = collect_objects(default_collection.all_objects)
        for obj in obj_list:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = obj_list[0]
        bpy.ops.object.join()
        meshes = collect_meshes(scene)

    write_tmd_from_mesh(meshes[0], filepath, op)


class ExportTMD(Operator, ExportHelper):
    """Save a PSX TMD file"""
    bl_idname = "psx_tmd.save"
    bl_label = "Export PSX TMD file"

    filename_ext = ".tmd"

    filter_glob: StringProperty(
        default="*.tmd",
        options={'HIDDEN'},
        maxlen=255,
    )

    color_mode: EnumProperty(
        name="Color Mode",
        description="How to color the polygons",
        items=[
            ('VERTEX_COLOR', "Face Corner Colors", "Use Color Attribute (flat shaded)"),
            ('TEXTURE', "Texture UVs", "Use active UV map (textured)"),
        ],
        default='VERTEX_COLOR',
    )

    unlit: BoolProperty(
        name="Unlit",
        description="Disable light-source calculation (easier to see while testing)",
        default=False,
    )

    # Texture options (only used when color_mode == 'TEXTURE')
    tpage: IntProperty(name="Texture Page", default=10, min=0, max=31)
    tp: EnumProperty(
        name="Texture BPP",
        items=[
            ('0', "4-bit", ""),
            ('1', "8-bit", ""),
            ('2', "15-bit", ""),
        ],
        default='2',
    )
    clut_x: IntProperty(name="CLUT X", default=0, min=0, max=960)
    clut_y: IntProperty(name="CLUT Y", default=480, min=0, max=511)

    # For non-256 textures (e.g. your 32×32)
    tex_width: IntProperty(name="Texture Width", default=32, min=1, max=256)
    tex_height: IntProperty(name="Texture Height", default=32, min=1, max=256)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "color_mode")
        layout.prop(self, "unlit")

        if self.color_mode == 'TEXTURE':
            box = layout.box()
            box.label(text="Texture Settings")
            box.prop(self, "tpage")
            box.prop(self, "tp")
            box.prop(self, "clut_x")
            box.prop(self, "clut_y")
            box.prop(self, "tex_width")
            box.prop(self, "tex_height")

    def execute(self, context):
        write_tmd(context, self.filepath, self)
        return {'FINISHED'}


def menu_func_export(self, context):
    self.layout.operator(ExportTMD.bl_idname, text="TMD file")


classes = {
    ExportTMD
}


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    try:
        for cls in classes:
            bpy.utils.unregister_class(cls)
    except RuntimeError:
        pass


if __name__ == "__main__":
    if "--" in sys.argv:
        # create a dummy options object
        class Dummy:
            color_mode = 'VERTEX_COLOR'
            tpage = 0
            tp = '2'
            clut_x = 0
            clut_y = 480
            tex_width = 32
            tex_height = 32
            unlit = False
        write_tmd(bpy.context, "tmd_export.tmd", Dummy())
        sys.exit(0)

    register()