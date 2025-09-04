import bpy
import bmesh
from bpy.types import Operator, Menu, Panel

copied_uv_data = {}

def get_uv_backup(mesh):
    uv_data_backup = {}
    num_loop_vectors = len(mesh.loops) * 2
    for layer in mesh.uv_layers:
        if hasattr(layer.data, 'foreach_get') and len(layer.data) == len(mesh.loops):
            uv_coords = [0.0] * num_loop_vectors
            layer.data.foreach_get('uv', uv_coords)
            uv_data_backup[layer.name] = uv_coords
        else:
            uv_data_backup[layer.name] = [0.0] * num_loop_vectors
    return uv_data_backup

def rebuild_uv_maps_via_attributes(mesh, new_name_order, uv_data_backup, new_active_index):
    original_active_render_name = next((layer.name for layer in mesh.uv_layers if layer.active_render), None)
    while mesh.uv_layers:
        mesh.uv_layers.remove(mesh.uv_layers[0])
    for name in new_name_order:
        new_uv_attr = mesh.attributes.new(name=name, type='FLOAT2', domain='CORNER')
        if name in uv_data_backup and uv_data_backup[name]:
            new_uv_attr.data.foreach_set('vector', uv_data_backup[name])
    if original_active_render_name in new_name_order and original_active_render_name in mesh.uv_layers:
        mesh.uv_layers[original_active_render_name].active_render = True
    if 0 <= new_active_index < len(mesh.uv_layers):
        mesh.uv_layers.active_index = new_active_index

class UV_OT_map_list_operator(Operator):
    bl_options = {'REGISTER', 'UNDO'}
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        raise NotImplementedError()
    def execute(self, context):
        mesh = context.object.data
        active_index = mesh.uv_layers.active_index
        uv_data_backup = get_uv_backup(mesh)
        name_order = [layer.name for layer in mesh.uv_layers]
        new_name_order, new_uv_data_backup, new_active_index = self.get_new_state(context, name_order, uv_data_backup, active_index)
        rebuild_uv_maps_via_attributes(mesh, new_name_order, new_uv_data_backup, new_active_index)
        return {'FINISHED'}

class UV_OT_add_map(UV_OT_map_list_operator):
    bl_idname = "uv.add_map"
    bl_label = "Add UV Map"
    bl_description = "Add a new, blank UV map. Bypasses the 8-map limit. (Available in Object Mode only)"
    @classmethod
    def poll(cls, context): return context.object and context.object.mode == 'OBJECT'
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        new_name = "UVMap"
        counter = 1
        while new_name in uv_data_backup:
            new_name = f"UVMap.{counter:03d}"
            counter += 1
        name_order.append(new_name)
        uv_data_backup[new_name] = [0.0] * (len(context.object.data.loops) * 2)
        return name_order, uv_data_backup, len(name_order) - 1

class UV_OT_remove_map(UV_OT_map_list_operator):
    bl_idname = "uv.remove_map"
    bl_label = "Remove UV Map"
    bl_description = "Remove the selected UV map. (Available in Object Mode only)"
    @classmethod
    def poll(cls, context): return context.object and context.object.data.uv_layers.active is not None and context.object.mode == 'OBJECT'
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        del uv_data_backup[name_order.pop(active_index)]
        new_active_index = min(active_index, len(name_order) - 1)
        return name_order, uv_data_backup, new_active_index

class UV_OT_duplicate_selected(UV_OT_map_list_operator):
    bl_idname = "uv.duplicate_selected"
    bl_label = "Duplicate Selected UV Map"
    bl_description = "Duplicates the selected UV map. (Available in Object Mode only)"
    @classmethod
    def poll(cls, context): return context.object and context.object.data.uv_layers.active is not None and context.object.mode == 'OBJECT'
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        original_name = name_order[active_index]
        new_name = original_name
        counter = 1
        while new_name in uv_data_backup:
            new_name = f"{original_name}.{counter:03d}"
            counter += 1
        target_index = active_index + 1
        name_order.insert(target_index, new_name)
        uv_data_backup[new_name] = uv_data_backup[original_name][:]
        self.report({'INFO'}, f"Duplicated '{original_name}' to '{new_name}'")
        return name_order, uv_data_backup, target_index

class UV_OT_reorder_map_up(UV_OT_map_list_operator):
    bl_idname = "uv.reorder_map_up"
    bl_label = "Move UV Map Up"
    bl_description = "Move the selected UV map up in the list. (Available in Object Mode only)"
    @classmethod
    def poll(cls, context): uv_layers = context.object.data.uv_layers; return context.object.mode == 'OBJECT' and len(uv_layers) > 1 and uv_layers.active_index > 0
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        target_index = active_index - 1
        name_order.insert(target_index, name_order.pop(active_index))
        return name_order, uv_data_backup, target_index

class UV_OT_reorder_map_down(UV_OT_map_list_operator):
    bl_idname = "uv.reorder_map_down"
    bl_label = "Move UV Map Down"
    bl_description = "Move the selected UV map down in the list. (Available in Object Mode only)"
    @classmethod
    def poll(cls, context): uv_layers = context.object.data.uv_layers; return context.object.mode == 'OBJECT' and len(uv_layers) > 1 and uv_layers.active_index < len(uv_layers) - 1
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        target_index = active_index + 1
        name_order.insert(target_index, name_order.pop(active_index))
        return name_order, uv_data_backup, target_index

class UV_OT_move_to_top(UV_OT_map_list_operator):
    bl_idname = "uv.move_to_top"
    bl_label = "Move to Top"
    bl_description = "Move the selected UV map to the top of the list. (Available in Object Mode only)"
    @classmethod
    def poll(cls, context): uv_layers = context.object.data.uv_layers; return context.object.mode == 'OBJECT' and len(uv_layers) > 1 and uv_layers.active_index > 0
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        name_order.insert(0, name_order.pop(active_index))
        return name_order, uv_data_backup, 0

class UV_OT_move_to_bottom(UV_OT_map_list_operator):
    bl_idname = "uv.move_to_bottom"
    bl_label = "Move to Bottom"
    bl_description = "Move the selected UV map to the bottom of the list. (Available in Object Mode only)"
    @classmethod
    def poll(cls, context): uv_layers = context.object.data.uv_layers; return context.object.mode == 'OBJECT' and len(uv_layers) > 1 and uv_layers.active_index < len(uv_layers) - 1
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        name_order.append(name_order.pop(active_index))
        return name_order, uv_data_backup, len(name_order) - 1

class UV_OT_sort_by_name(UV_OT_map_list_operator):
    bl_idname = "uv.sort_by_name"
    bl_label = "Sort Maps by Name"
    bl_description = "Sort all maps alphabetically. (Available in Object Mode only)"
    @classmethod
    def poll(cls, context): return context.object.mode == 'OBJECT' and len(context.object.data.uv_layers) > 1
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        active_name = name_order[active_index]
        new_name_order = sorted(name_order, key=str.lower)
        new_active_index = new_name_order.index(active_name)
        return new_name_order, uv_data_backup, new_active_index

class UV_OT_reverse_order(UV_OT_map_list_operator):
    bl_idname = "uv.reverse_order"
    bl_label = "Reverse Map Order"
    bl_description = "Reverse the order of all maps. (Available in Object Mode only)"
    @classmethod
    def poll(cls, context): return context.object.mode == 'OBJECT' and len(context.object.data.uv_layers) > 1
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        active_name = name_order[active_index]
        new_name_order = list(reversed(name_order))
        new_active_index = new_name_order.index(active_name)
        return new_name_order, uv_data_backup, new_active_index

class UV_OT_delete_all(UV_OT_map_list_operator):
    bl_idname = "uv.delete_all"
    bl_label = "Delete All UV Maps"
    bl_description = "Deletes all UV maps from the object. (Available in Object Mode only)"
    @classmethod
    def poll(cls, context): return context.object.mode == 'OBJECT' and len(context.object.data.uv_layers) > 0
    def get_new_state(self, context, name_order, uv_data_backup, active_index):
        return [], {}, 0

class UV_OT_copy_selected_uvs(Operator):
    bl_idname = "uv.copy_selected_uvs"
    bl_label = "Copy UVs"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'MESH' and obj.data.uv_layers.active is not None and obj.mode == 'EDIT'
    def execute(self, context):
        global copied_uv_data
        copied_uv_data.clear()
        bm = bmesh.from_edit_mesh(context.object.data)
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            self.report({'WARNING'}, "No active UV map in Edit Mode")
            return {'CANCELLED'}
        for face in bm.faces:
            if face.select:
                for loop in face.loops:
                    if loop[uv_layer].select:
                        copied_uv_data[loop.index] = loop[uv_layer].uv.copy()
        self.report({'INFO'}, f"Copied {len(copied_uv_data)} UV vertices")
        return {'FINISHED'}

class UV_OT_paste_selected_uvs(Operator):
    bl_idname = "uv.paste_selected_uvs"
    bl_label = "Paste UVs"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.data.uv_layers.active is not None and obj.mode == 'EDIT' and copied_uv_data
    def execute(self, context):
        bm = bmesh.from_edit_mesh(context.object.data)
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            self.report({'WARNING'}, "No active UV map in Edit Mode")
            return {'CANCELLED'}
        pasted_count = 0
        for face in bm.faces:
            for loop in face.loops:
                if loop.index in copied_uv_data:
                    loop[uv_layer].uv = copied_uv_data[loop.index]
                    pasted_count += 1
        bmesh.update_edit_mesh(context.object.data)
        self.report({'INFO'}, f"Pasted {pasted_count} UV vertices")
        return {'FINISHED'}

class UV_MT_specials_menu(Menu):
    bl_label = "UV Map Specials"
    bl_idname = "UV_MT_specials_menu"
    def draw(self, context):
        layout = self.layout
        layout.operator(UV_OT_sort_by_name.bl_idname, icon='SORTALPHA')
        layout.operator(UV_OT_reverse_order.bl_idname, icon='SORT_DESC')
        layout.separator()
        layout.operator(UV_OT_move_to_top.bl_idname, icon='TRIA_UP_BAR')
        layout.operator(UV_OT_move_to_bottom.bl_idname, icon='TRIA_DOWN_BAR')
        layout.separator()
        layout.operator(UV_OT_duplicate_selected.bl_idname, icon='DUPLICATE')
        layout.operator(UV_OT_delete_all.bl_idname, icon='TRASH')

class UVMAPSPLUS_PT_panel(Panel):
    bl_label = "UV Maps+"
    bl_idname = "DATA_PT_uv_texture"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    @classmethod
    def poll(cls, context): return (context.object and context.object.type == 'MESH')
    def draw(self, context):
        layout = self.layout
        obj = context.object
        mesh = obj.data
        uv_layers = mesh.uv_layers
        row = layout.row()
        col = row.column()
        list_rows = 5 if len(uv_layers) > 0 else 2
        col.template_list("MESH_UL_uvmaps", "", mesh, "uv_layers", uv_layers, "active_index", rows=list_rows)
        col = row.column(align=True)
        col.operator(UV_OT_add_map.bl_idname, icon='ADD', text="")
        col.operator(UV_OT_remove_map.bl_idname, icon='REMOVE', text="")
        col.separator()
        col.menu(UV_MT_specials_menu.bl_idname, icon='DOWNARROW_HLT', text="")
        if len(uv_layers) > 0:
            col.separator()
            col.operator(UV_OT_reorder_map_up.bl_idname, text="", icon='TRIA_UP')
            col.operator(UV_OT_reorder_map_down.bl_idname, text="", icon='TRIA_DOWN')
        if obj.mode == 'EDIT':
            layout.separator()
            row = layout.row(align=True)
            row.operator(UV_OT_copy_selected_uvs.bl_idname, text="Copy UVs", icon='COPYDOWN')
            row.operator(UV_OT_paste_selected_uvs.bl_idname, text="Paste UVs", icon='PASTEDOWN')
        if len(uv_layers) > 8:
            layout.separator()
            box = layout.box()
            box.alert = True
            box.label(text="Over 8 UV Maps: UV Editor & Export may only show up to 8.", icon='INFO')

classes = (
    UV_OT_add_map,
    UV_OT_remove_map,
    UV_OT_reorder_map_up,
    UV_OT_reorder_map_down,
    UV_OT_duplicate_selected,
    UV_OT_sort_by_name,
    UV_OT_reverse_order,
    UV_OT_delete_all,
    UV_OT_copy_selected_uvs,
    UV_OT_paste_selected_uvs,
    UV_MT_specials_menu,
    UV_OT_move_to_top,
    UV_OT_move_to_bottom,
    UVMAPSPLUS_PT_panel,
)

def register():
    try: bpy.utils.unregister_class(bpy.types.DATA_PT_uv_texture)
    except RuntimeError: pass
    for cls in classes: bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        try: bpy.utils.unregister_class(cls)
        except RuntimeError: pass
    try:
        from bpy.types import DATA_PT_uv_texture
        bpy.utils.register_class(DATA_PT_uv_texture)
    except (ImportError, RuntimeError): pass

if __name__ == "__main__":
    try: unregister()
    except Exception: pass
    register()