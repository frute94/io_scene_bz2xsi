bl_info = {
	"name": "BZ2 XSI format",
	"author": "FruteSoftware@gmail.com",
	"version": (1, 0, 4),
	"blender": (2, 93, 0),
	"location": "File > Import-Export",
	"description": "Battlezone II XSI Importer/Exporter",
	"category": "Import-Export"
}

import bpy

from bpy.props import (
	StringProperty,
	BoolProperty,
	FloatProperty,
	EnumProperty
)

from bpy_extras.io_utils import (
	ImportHelper,
	ExportHelper,
	orientation_helper,
	axis_conversion
)

if "bpy" in locals():
	import importlib
	if "bz2xsi" in locals(): importlib.reload(bz2xsi)
	if "xsi_blender_importer" in locals(): importlib.reload(xsi_blender_importer)
	if "xsi_blender_exporter" in locals(): importlib.reload(xsi_blender_exporter)

class ImportXSI(bpy.types.Operator, ImportHelper):
	"""Import BZ2 XSI file"""
	bl_idname = "import_scene.io_scene_bz2xsi"
	bl_label = "Import XSI"
	bl_options = {"UNDO", "PRESET"}
	
	directory: StringProperty(subtype="DIR_PATH")
	filename_ext = ".xsi"
	filter_glob: StringProperty(default="*.xsi", options={"HIDDEN"})
	texture_image_ext_default = ".png .bmp .jpg .jpeg .gif .tga" # ".tif .tiff .jp2 .jc2 .sgi .rgb .bw .cin .dpx .exr .hdr",
	
	emulate_flags: BoolProperty(
		name="Emulate Flags",
		description="Emulate __2, __h, __c, __e XSI frame flags",
		default=True
	)
	
	import_animations: BoolProperty(
		name="Animations",
		description="Import animations",
		default=True
	)
	
	import_envelopes: BoolProperty(
		name="Bone Envelopes",
		description="Import bone envelopes",
		default=True
	)
	
	import_lights: BoolProperty(
		name="Lights",
		description="Import softimage scene lights",
		default=False
	)
	
	import_cameras: BoolProperty(
		name="Cameras",
		description="Import softimage scene cameras",
		default=False
	)
	
	import_mesh: BoolProperty(
		name="Mesh",
		description="Import mesh",
		default=True
	)
	
	import_mesh_normals: BoolProperty(
		name="Normals",
		description="Import mesh normals",
		default=True
	)

	import_mesh_materials: BoolProperty(
		name="Materials",
		description="Import mesh face materials",
		default=True
	)

	import_mesh_uvmap: BoolProperty(
		name="UV Maps",
		description="Import mesh UV texture coordinates",
		default=True
	)

	import_mesh_vertcolor: BoolProperty(
		name="Vertex Colors",
		description="Import mesh vertex colors",
		default=True
	)
	
	find_textures: BoolProperty(
		name="Recursive Image Search",
		description="Search subdirectories for any associated images (Slow for big directories)",
		default=False
	)
	
	find_textures_ext: StringProperty(
		name="Formats",
		description="Additional file extensions to check for (May be very slow when combined with Recursive Image Search)",
		default=texture_image_ext_default
	)

	add_material_overrides: BoolProperty(
		name="Material Custom Properties",
		description="Adds material values to custom properties, which are used as overrides in the XSI exporter",
		default=True
	)
	
	place_at_cursor: BoolProperty(
		name="Place at Cursor",
		description="Imported objects are placed at cursor if enabled, otherwise at world center",
		default=False
	)
	
	rotate_for_yz: BoolProperty(
		name="Rotate Root Frames",
		description="Rotate root frames so they match blender's world orientation",
		default=True
	)
	
	# https://developer.blender.org/T45473 - This may be the cause of quaternion interpolation not matching BZ2's?
	quat_anims_to_euler: BoolProperty(
		name="Quaternions to Euler",
		description="For cyclic animations to work (e.g. spinning nav beacon) quaternions would need to be exported to euler.",
		default=False
	)
	
	remove_negative_rotations: BoolProperty(
		name="Remove Negative Rotations",
		description="Converts negative animation rotation values to positive (e.g. -90 becomes 270)",
		default=False
	)

	def draw(self, context):
		layout = self.layout
		
		object_layout = layout.box()
		object_layout.prop(self, "emulate_flags")
		object_layout.prop(self, "import_lights", icon="LIGHT_DATA")
		object_layout.prop(self, "import_cameras", icon="CAMERA_DATA")
		object_layout.prop(self, "import_mesh", icon="MESH_DATA")
		
		mesh_layout = layout.box()
		sub = mesh_layout.column()
		sub.prop(self, "import_mesh_normals", icon="NORMALS_VERTEX")
		sub.enabled = self.import_mesh
		
		sub = mesh_layout.column()
		sub.prop(self, "import_mesh_materials", icon="MATERIAL_DATA")
		sub.enabled = self.import_mesh
		
		sub = mesh_layout.column()
		sub.prop(self, "import_mesh_uvmap", icon="GROUP_UVS")
		sub.enabled = self.import_mesh
		
		sub = mesh_layout.column()
		sub.prop(self, "import_mesh_vertcolor", icon="GROUP_VCOL")
		sub.enabled = self.import_mesh
		
		sub = mesh_layout.column()
		sub.prop(self, "import_animations", icon="ANIM_DATA")
		sub.enabled = True
		
		sub = mesh_layout.column()
		sub.prop(self, "import_envelopes", icon="GROUP_VERTEX")
		sub.enabled = self.import_mesh # Cannot have envelopes without any vertices to reference
		
		if self.import_envelopes and self.import_animations:
			mesh_layout.label(text="Bone animations are fucked.", icon="ERROR")
		
		texture_layout = layout.box()
		sub = texture_layout.column()
		sub.prop(self, "find_textures", icon="TEXTURE_DATA")
		sub.enabled = self.import_mesh_materials and self.import_mesh
		sub = texture_layout.column()
		sub.prop(self, "find_textures_ext")
		sub.enabled = self.import_mesh_materials and self.import_mesh
		layout.separator()
		
		anim_layout = layout.box()
		sub = anim_layout.column()
		sub.prop(self, "quat_anims_to_euler")
		sub.enabled = self.import_animations
		sub = anim_layout.column()
		sub.prop(self, "remove_negative_rotations")
		sub.enabled = self.import_animations
		layout.separator()
		
		sub = layout.column()
		sub.prop(self, "add_material_overrides", icon="MATERIAL_DATA")
		sub.enabled = self.import_mesh_materials and self.import_mesh
		layout.prop(self, "place_at_cursor", icon="PIVOT_CURSOR")
		layout.prop(self, "rotate_for_yz", icon="ORIENTATION_GLOBAL")
		# layout.separator()
	
	def execute(self, context):
		from . import xsi_blender_importer
		keywords = self.as_keywords(ignore=("filter_glob", "directory", "ui_tab"))
		return xsi_blender_importer.load(self, context, **keywords)

class ExportXSI(bpy.types.Operator, ExportHelper):
	"""Export BZ2 XSI file"""
	bl_idname = "export_scene.io_scene_bz2xsi"
	bl_label = "Export XSI"
	bl_options = {"UNDO", "PRESET"}
	
	directory: StringProperty(subtype="DIR_PATH")
	filename_ext = ".xsi"
	filter_glob: StringProperty(default="*.xsi", options={'HIDDEN'})
	
	export_mode: EnumProperty(
		items=(
			("ACTIVE_COLLECTION", "Active Collection", "Export objects in active collection", "OUTLINER_COLLECTION", 1),
			("SELECTED_OBJECTS", "Only Selected Objects", "Export selected objects, including child objects", "OUTLINER", 2)
		),
		
		name="Export Mode",
		description="Which objects are to be exported",
		default="ACTIVE_COLLECTION"
	)

	export_mesh: BoolProperty(
		name="Mesh",
		description="Export mesh data",
		default=True
	)

	export_mesh_uvmap: BoolProperty(
		name="UV Map",
		description="Export mesh uv map coordinates",
		default=True
	)

	export_mesh_materials: BoolProperty(
		name="Materials",
		description="Export mesh materials",
		default=True
	)

	export_mesh_vertcolor: BoolProperty(
		name="Vertex Colors",
		description="Export mesh vertex colors",
		default=True
	)

	export_envelopes: BoolProperty(
		name="Bone Envelopes",
		description="Export envelopes for bones",
		default=True
	)

	export_animations: BoolProperty(
		name="Animations",
		description="Export rotation & translation animations",
		default=True
	)

	zero_root_transforms: BoolProperty(
		name="Reset Root Transforms",
		description="If enabled, root-level objects have default transform matrices",
		default=True
	)

	generate_empty_mesh: BoolProperty(
		name="Generate Empty Mesh",
		description="Create a pointer-like mesh for empty objects to visualize their direction (e.g. for hardpoints)",
		default=False
	)

	generate_bone_mesh: BoolProperty(
		name="Generate Bone Mesh",
		description="Create meshes for bones to visualize bones for debugging purposes",
		default=False
	)
	
	def draw(self, context):
		layout = self.layout
		
		export_layout = layout.box()
		export_layout.prop(self, "export_mode", expand=True)
		if self.export_mode == "ACTIVE_COLLECTION":
			collection = bpy.context.view_layer.active_layer_collection.collection
			export_layout.label(text="%s (%d objects)" % (collection.name, len(collection.objects)))
		layout.separator()
		
		mesh_layout = layout.box()
		mesh_layout.prop(self, "export_mesh", icon="MESH_DATA")
		
		sub = mesh_layout.column()
		sub.prop(self, "export_mesh_uvmap", icon="GROUP_UVS")
		sub.enabled = self.export_mesh
		
		sub = mesh_layout.column()
		sub.prop(self, "export_mesh_materials", icon="MATERIAL_DATA")
		sub.enabled = self.export_mesh

		sub = mesh_layout.column()
		sub.prop(self, "export_mesh_vertcolor", icon="GROUP_VCOL")
		sub.enabled = self.export_mesh
		mesh_layout.separator()
		
		mesh_layout.prop(self, "generate_empty_mesh", icon="EMPTY_DATA")
		
		anim_layout = layout.box()
		anim_layout.prop(self, "export_animations", icon="ANIM_DATA")
		sub = anim_layout.column()
		sub.prop(self, "export_envelopes", icon="GROUP_VERTEX")
		sub.enabled = self.export_mesh
		anim_layout.separator()
		
		sub = anim_layout.column()
		sub.prop(self, "generate_bone_mesh", icon="GROUP_BONE")
		
		layout.separator()
		layout.prop(self, "zero_root_transforms", icon="ORIENTATION_GLOBAL")
		layout.separator()
	
	def execute(self, context):
		from . import xsi_blender_exporter
		keywords = self.as_keywords(ignore=("filter_glob", "directory"))
		return xsi_blender_exporter.save(self, context, **keywords)

def menu_func_import(self, context):
	self.layout.operator(ImportXSI.bl_idname, text="BZ2 XSI (.xsi)")

def menu_func_export(self, context):
	self.layout.operator(ExportXSI.bl_idname, text="BZ2 XSI (.xsi)")

classes = (
	ImportXSI,
	ExportXSI
)

def register():
	for cls in classes:
		bpy.utils.register_class(cls)

	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

	for cls in classes:
		bpy.utils.unregister_class(cls)

if __name__ == "__main__":
	register()
