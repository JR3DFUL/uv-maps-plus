import bpy
import bmesh
from bpy.types import Operator, Menu, Panel, UIList
from bpy.app.handlers import depsgraph_update_post

copied_uv_data = {}
_sync_state = {}

def get_meshes(ctx):
    return [o for o in ctx.selected_objects if o.type == 'MESH']

def get_uv_backup(mesh):
    backup, n = {}, len(mesh.loops) * 2
    for layer in mesh.uv_layers:
        c = [0.0] * n
        if hasattr(layer.data, 'foreach_get') and len(layer.data) == len(mesh.loops):
            layer.data.foreach_get('uv', c)
        backup[layer.name] = c
    return backup

def rebuild_uvs(mesh, names, backup, idx):
    render = next((l.name for l in mesh.uv_layers if l.active_render), None)
    while mesh.uv_layers:
        mesh.uv_layers.remove(mesh.uv_layers[0])
    for name in names:
        attr = mesh.attributes.new(name=name, type='FLOAT2', domain='CORNER')
        if name in backup and backup[name]:
            attr.data.foreach_set('vector', backup[name])
    if render in names and render in mesh.uv_layers:
        mesh.uv_layers[render].active_render = True
    if names and 0 <= idx < len(mesh.uv_layers):
        mesh.uv_layers.active_index = idx
    mesh.update()
    for area in bpy.context.screen.areas:
        area.tag_redraw()

def is_uv_selected(loop, uv_layer):
    return loop.uv_select_vert if hasattr(loop, 'uv_select_vert') else loop[uv_layer].select

def available_name(objects, base="UVMap"):
    used = {l.name for o in objects for l in o.data.uv_layers}
    if base not in used: return base
    i = 1
    while f"{base}.{i:03d}" in used: i += 1
    return f"{base}.{i:03d}"

def ensure_uv(mesh, name):
    if name not in [l.name for l in mesh.uv_layers]:
        b = get_uv_backup(mesh)
        n = [l.name for l in mesh.uv_layers] + [name]
        b[name] = [0.0] * (len(mesh.loops) * 2)
        rebuild_uvs(mesh, n, b, mesh.uv_layers.active_index if mesh.uv_layers else 0)

# === TRANSFER ===

def transfer_uv(src, tgt, name):
    if len(src.loops) != len(tgt.loops): return False
    s, t = src.uv_layers.get(name), tgt.uv_layers.get(name)
    if not s or not t: return False
    c = [0.0] * (len(src.loops) * 2)
    s.data.foreach_get('uv', c)
    t.data.foreach_set('uv', c)
    return True

# === SYNC HANDLER ===

def sync_handler(scene, depsgraph):
    ctx = bpy.context
    if not ctx.object or ctx.object.type != 'MESH' or ctx.object.mode != 'OBJECT': return
    objs = get_meshes(ctx)
    if len(objs) <= 1: return
    
    obj, mesh = ctx.object, ctx.object.data
    if not mesh.uv_layers: return
    
    oid = id(obj)
    cur = {
        'active': mesh.uv_layers.active.name if mesh.uv_layers.active else None,
        'render': next((l.name for l in mesh.uv_layers if l.active_render), None),
        'names': [l.name for l in mesh.uv_layers]
    }
    
    if oid in _sync_state:
        last = _sync_state[oid]
        for o in objs:
            if o == obj: continue
            m = o.data
            # Sync active
            if cur['active'] and cur['active'] != last.get('active') and cur['active'] in [l.name for l in m.uv_layers]:
                m.uv_layers.active = m.uv_layers[cur['active']]
            # Sync render
            if cur['render'] and cur['render'] != last.get('render') and cur['render'] in [l.name for l in m.uv_layers]:
                m.uv_layers[cur['render']].active_render = True
            # Sync renames
            ln = last.get('names', [])
            if len(ln) == len(cur['names']):
                for old, new in zip(ln, cur['names']):
                    if old != new and old in [l.name for l in m.uv_layers] and new not in [l.name for l in m.uv_layers]:
                        m.uv_layers[old].name = new
    
    _sync_state[oid] = cur

# === BASE OPERATOR ===

class UV_OT_base(Operator):
    bl_options = {'REGISTER', 'UNDO'}
    def get_state(self, ctx, names, backup, idx): raise NotImplementedError()
    def execute(self, ctx):
        mesh = ctx.object.data
        names, backup, idx = [l.name for l in mesh.uv_layers], get_uv_backup(mesh), mesh.uv_layers.active_index
        new_names, new_backup, new_idx = self.get_state(ctx, names, backup, idx)
        rebuild_uvs(mesh, new_names, new_backup, new_idx)
        return {'FINISHED'}

# === OPERATORS ===

class UV_OT_add(UV_OT_base):
    bl_idname = "uv.add_map"
    bl_label = "Add UV Map"
    bl_description = "Add a new UV map to all selected objects. Bypasses 8-map limit"
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'OBJECT'
    def get_state(self, ctx, names, backup, idx):
        objs = get_meshes(ctx) or [ctx.object]
        name = available_name(objs)
        for o in objs:
            if o != ctx.object:
                ensure_uv(o.data, name)
        names.append(name)
        backup[name] = [0.0] * (len(ctx.object.data.loops) * 2)
        return names, backup, len(names) - 1

class UV_OT_remove(UV_OT_base):
    bl_idname = "uv.remove_map"
    bl_label = "Remove UV Map"
    bl_description = "Remove the active UV map from all selected objects (if available)"
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.data.uv_layers.active and ctx.object.mode == 'OBJECT'
    def get_state(self, ctx, names, backup, idx):
        name = names[idx]
        for o in get_meshes(ctx):
            if o != ctx.object and name in [l.name for l in o.data.uv_layers]:
                b = get_uv_backup(o.data)
                n = [l.name for l in o.data.uv_layers]
                i = n.index(name)
                del b[name]; n.remove(name)
                rebuild_uvs(o.data, n, b, min(i, len(n)-1) if n else -1)
        del backup[name]; names.remove(name)
        return names, backup, min(idx, len(names)-1) if names else -1
    def invoke(self, ctx, event):
        name = ctx.object.data.uv_layers.active.name
        if len([o for o in get_meshes(ctx) if name in [l.name for l in o.data.uv_layers]]) > 1:
            return ctx.window_manager.invoke_confirm(self, event)
        return self.execute(ctx)

class UV_OT_duplicate(UV_OT_base):
    bl_idname = "uv.duplicate_map"
    bl_label = "Duplicate UV Map"
    bl_description = "Duplicate the active UV map on all selected objects (if available)"
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.data.uv_layers.active and ctx.object.mode == 'OBJECT'
    def get_state(self, ctx, names, backup, idx):
        orig = names[idx]
        objs = [o for o in get_meshes(ctx) or [ctx.object] if orig in [l.name for l in o.data.uv_layers]]
        new = available_name(objs, orig)
        for o in objs:
            if o != ctx.object:
                b = get_uv_backup(o.data)
                n = [l.name for l in o.data.uv_layers]
                i = n.index(orig)
                n.insert(i+1, new)
                b[new] = b[orig][:]
                rebuild_uvs(o.data, n, b, o.data.uv_layers.active_index)
        names.insert(idx+1, new)
        backup[new] = backup[orig][:]
        return names, backup, idx+1

class UV_OT_move(Operator):
    bl_idname = "uv.move_map"
    bl_label = "Move UV Map"
    bl_description = "Move the active UV map up or down in all selected objects (if available)"
    bl_options = {'REGISTER', 'UNDO'}
    direction: bpy.props.EnumProperty(items=[('UP','Up',''),('DOWN','Down',''),('TOP','Top',''),('BOTTOM','Bottom','')])
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'OBJECT' and len(ctx.object.data.uv_layers) > 1
    def execute(self, ctx):
        name = ctx.object.data.uv_layers.active.name
        for o in get_meshes(ctx) or [ctx.object]:
            m = o.data
            n = [l.name for l in m.uv_layers]
            if name not in n: continue
            i = n.index(name)
            if self.direction == 'UP' and i > 0: t = i-1
            elif self.direction == 'DOWN' and i < len(n)-1: t = i+1
            elif self.direction == 'TOP' and i > 0: t = 0
            elif self.direction == 'BOTTOM' and i < len(n)-1: t = len(n)-1
            else: continue
            n.insert(t, n.pop(i))
            rebuild_uvs(m, n, get_uv_backup(m), t if o == ctx.object else m.uv_layers.active_index)
        return {'FINISHED'}

class UV_OT_sort(UV_OT_base):
    bl_idname = "uv.sort_maps"
    bl_label = "Sort UV Maps by Name"
    bl_description = "Sort all UV maps alphabetically on all selected objects"
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'OBJECT' and len(ctx.object.data.uv_layers) > 1
    def get_state(self, ctx, names, backup, idx):
        active = names[idx]
        for o in get_meshes(ctx):
            if o != ctx.object and len(o.data.uv_layers) > 1:
                n = sorted([l.name for l in o.data.uv_layers], key=str.lower)
                a = o.data.uv_layers.active.name
                rebuild_uvs(o.data, n, get_uv_backup(o.data), n.index(a) if a in n else 0)
        names = sorted(names, key=str.lower)
        return names, backup, names.index(active)

class UV_OT_reverse(UV_OT_base):
    bl_idname = "uv.reverse_maps"
    bl_label = "Reverse UV Map Order"
    bl_description = "Reverse the order of all UV maps on all selected objects"
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'OBJECT' and len(ctx.object.data.uv_layers) > 1
    def get_state(self, ctx, names, backup, idx):
        active = names[idx]
        for o in get_meshes(ctx):
            if o != ctx.object and len(o.data.uv_layers) > 1:
                n = [l.name for l in o.data.uv_layers][::-1]
                a = o.data.uv_layers.active.name
                rebuild_uvs(o.data, n, get_uv_backup(o.data), n.index(a) if a in n else 0)
        names = names[::-1]
        return names, backup, names.index(active)

class UV_OT_delete_empty(Operator):
    bl_idname = "uv.delete_empty"
    bl_label = "Delete Empty UV Maps"
    bl_description = "Delete UV maps with all coordinates at (0,0) from all selected objects"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'OBJECT' and ctx.object.data.uv_layers
    def execute(self, ctx):
        total_deleted = 0
        for obj in get_meshes(ctx):
            m = obj.data
            to_delete = []
            for layer in m.uv_layers:
                # Check if all UVs are at origin (0,0)
                coords = [0.0] * (len(m.loops) * 2)
                if hasattr(layer.data, 'foreach_get'):
                    layer.data.foreach_get('uv', coords)
                    if all(c == 0.0 for c in coords):
                        to_delete.append(layer.name)
            # Delete empty maps
            if to_delete:
                backup = get_uv_backup(m)
                names = [l.name for l in m.uv_layers]
                for name in to_delete:
                    if name in backup:
                        del backup[name]
                    if name in names:
                        names.remove(name)
                    total_deleted += 1
                active_idx = m.uv_layers.active_index
                rebuild_uvs(m, names, backup, min(active_idx, len(names)-1) if names else -1)
        self.report({'INFO'}, f"Deleted {total_deleted} empty UV map(s)")
        return {'FINISHED'}

class UV_OT_delete_all(UV_OT_base):
    bl_idname = "uv.delete_all"
    bl_label = "Delete All UV Maps?"
    bl_description = "Delete all UV maps from all selected objects"
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'OBJECT' and ctx.object.data.uv_layers
    def get_state(self, ctx, names, backup, idx):
        for o in get_meshes(ctx):
            if o != ctx.object and o.data.uv_layers:
                rebuild_uvs(o.data, [], {}, -1)
        return [], {}, -1
    def invoke(self, ctx, event): return ctx.window_manager.invoke_confirm(self, event)

class UV_OT_sync_order(Operator):
    bl_idname = "uv.sync_order"
    bl_label = "Sync UV Map Order"
    bl_description = "Match UV map order on all selected objects to the active object"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'OBJECT' and len(get_meshes(ctx)) > 1
    def execute(self, ctx):
        order = [l.name for l in ctx.object.data.uv_layers]
        for o in get_meshes(ctx):
            if o == ctx.object: continue
            m = o.data
            cur = [l.name for l in m.uv_layers]
            new = [n for n in order if n in cur] + [n for n in cur if n not in order]
            a = m.uv_layers.active.name if m.uv_layers.active else None
            rebuild_uvs(m, new, get_uv_backup(m), new.index(a) if a in new else 0)
        return {'FINISHED'}

class UV_OT_copy_unique(Operator):
    bl_idname = "uv.sync_names"
    bl_label = "Sync UV Map Names"
    bl_description = "Create missing UV maps on all objects so all have the same map names"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'OBJECT' and len(get_meshes(ctx)) > 1
    def execute(self, ctx):
        all_names = []
        for o in get_meshes(ctx):
            for l in o.data.uv_layers:
                if l.name not in all_names: all_names.append(l.name)
        added = 0
        for o in get_meshes(ctx):
            for name in all_names:
                if name not in [l.name for l in o.data.uv_layers]:
                    ensure_uv(o.data, name)
                    added += 1
        self.report({'INFO'}, f"Added {added} UV map(s)")
        return {'FINISHED'}

class UV_OT_transfer(Operator):
    bl_idname = "uv.transfer"
    bl_label = "Replace All UV Maps?"
    bl_description = "Transfer UV coordinate data from active object to others (requires matching topology)"
    bl_options = {'REGISTER', 'UNDO'}
    mode: bpy.props.EnumProperty(items=[('SEL','Selected',''),('ALL','All',''),('REP','Replace','')])
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'OBJECT' and ctx.object.data.uv_layers and len(get_meshes(ctx)) > 1
    def execute(self, ctx):
        src = ctx.object.data
        uv_names = [src.uv_layers.active.name] if self.mode == 'SEL' else [l.name for l in src.uv_layers]
        ok = skip = 0
        for o in get_meshes(ctx):
            if o == ctx.object: continue
            t = o.data
            if len(src.loops) != len(t.loops): skip += 1; continue
            if self.mode == 'REP': rebuild_uvs(t, [], {}, -1)
            for n in uv_names:
                ensure_uv(t, n)
                transfer_uv(src, t, n)
            ok += 1
        self.report({'INFO'} if ok else {'WARNING'}, f"Transferred to {ok}" + (f", skipped {skip}" if skip else ""))
        return {'FINISHED'}
    def invoke(self, ctx, event):
        return ctx.window_manager.invoke_confirm(self, event) if self.mode == 'REP' else self.execute(ctx)

class UV_OT_copy_uvs(Operator):
    bl_idname = "uv.copy_uvs"
    bl_label = "Copy UVs"
    bl_description = "Copy selected UV coordinates in Edit Mode"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'EDIT' and ctx.object.data.uv_layers.active
    def execute(self, ctx):
        global copied_uv_data
        copied_uv_data.clear()
        bm = bmesh.from_edit_mesh(ctx.object.data)
        uv = bm.loops.layers.uv.active
        if not uv: return {'CANCELLED'}
        for f in bm.faces:
            for l in f.loops:
                if is_uv_selected(l, uv): copied_uv_data[l.index] = l[uv].uv.copy()
        self.report({'INFO'}, f"Copied {len(copied_uv_data)} UVs")
        return {'FINISHED'}

class UV_OT_paste_uvs(Operator):
    bl_idname = "uv.paste_uvs"
    bl_label = "Paste UVs"
    bl_description = "Paste copied UV coordinates in Edit Mode"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.mode == 'EDIT' and ctx.object.data.uv_layers.active and copied_uv_data
    def execute(self, ctx):
        bm = bmesh.from_edit_mesh(ctx.object.data)
        uv = bm.loops.layers.uv.active
        if not uv: return {'CANCELLED'}
        n = sum(1 for f in bm.faces for l in f.loops if l.index in copied_uv_data and not (l[uv].uv.__setitem__(slice(None), copied_uv_data[l.index]) or True) or l.index in copied_uv_data)
        for f in bm.faces:
            for l in f.loops:
                if l.index in copied_uv_data: l[uv].uv = copied_uv_data[l.index]
        bmesh.update_edit_mesh(ctx.object.data)
        self.report({'INFO'}, f"Pasted {len([1 for f in bm.faces for l in f.loops if l.index in copied_uv_data])} UVs")
        return {'FINISHED'}

# === MENUS ===

class MESH_UL_uvmaps_plus(bpy.types.UIList):
    """Custom UV Map list with warning colors for maps past slot 8"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            if index >= 8:
                layout.alert = True
            layout.prop(item, "name", text="", emboss=False, icon_value=icon)
            icon = 'RESTRICT_RENDER_OFF' if item.active_render else 'RESTRICT_RENDER_ON'
            layout.prop(item, "active_render", text="", icon=icon, emboss=False)
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

class UV_MT_specials(Menu):
    bl_idname = "UV_MT_specials"
    bl_label = "UV Map Specials"
    def draw(self, ctx):
        l = self.layout
        l.operator(UV_OT_sort.bl_idname, icon='SORTALPHA')
        l.operator(UV_OT_reverse.bl_idname, icon='SORT_DESC')
        l.separator()
        l.operator(UV_OT_move.bl_idname, text="Move to Top", icon='TRIA_UP_BAR').direction = 'TOP'
        l.operator(UV_OT_move.bl_idname, text="Move to Bottom", icon='TRIA_DOWN_BAR').direction = 'BOTTOM'
        l.separator()
        l.operator(UV_OT_duplicate.bl_idname, icon='DUPLICATE')
        l.operator(UV_OT_delete_empty.bl_idname, icon='TRASH')
        l.operator(UV_OT_delete_all.bl_idname, text="Delete All UV Maps", icon='TRASH')
        if len(get_meshes(ctx)) > 1:
            l.separator()
            l.label(text="Batch", icon='OBJECT_DATA')
            l.operator(UV_OT_sync_order.bl_idname, icon='SORTSIZE')
            l.operator(UV_OT_copy_unique.bl_idname, icon='FONT_DATA')
            l.separator()
            l.label(text="UV Data", icon='UV')
            l.operator(UV_OT_transfer.bl_idname, text="Transfer UV Data", icon='FORWARD').mode = 'SEL'
            l.operator(UV_OT_transfer.bl_idname, text="Transfer All UV Data", icon='FORWARD').mode = 'ALL'
            l.operator(UV_OT_transfer.bl_idname, text="Replace All UV Data", icon='FILE_REFRESH').mode = 'REP'

# === PANEL ===

class UVMAPSPLUS_PT_panel(Panel):
    bl_label = "UV Maps+"
    bl_idname = "UVMAPSPLUS_PT_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    
    @classmethod
    def poll(cls, ctx): return ctx.object and ctx.object.type == 'MESH'
    
    def draw(self, ctx):
        l = self.layout
        mesh = ctx.object.data
        uvs = mesh.uv_layers
        
        row = l.row()
        col = row.column()
        col.template_list("MESH_UL_uvmaps_plus", "", mesh, "uv_layers", uvs, "active_index", rows=5 if uvs else 2)
        col = row.column(align=True)
        col.operator(UV_OT_add.bl_idname, icon='ADD', text="")
        col.operator(UV_OT_remove.bl_idname, icon='REMOVE', text="")
        col.separator()
        col.menu(UV_MT_specials.bl_idname, icon='DOWNARROW_HLT', text="")
        if uvs:
            col.separator()
            col.operator(UV_OT_move.bl_idname, text="", icon='TRIA_UP').direction = 'UP'
            col.operator(UV_OT_move.bl_idname, text="", icon='TRIA_DOWN').direction = 'DOWN'
        
        sel = get_meshes(ctx)
        show_batch = len(sel) > 1 and ctx.object.mode == 'OBJECT'
        show_slot_warning = uvs and uvs.active_index >= 8
        
        if show_batch or show_slot_warning:
            l.separator()
            box = l.box()
            if show_batch:
                box.label(text=f"Batch: {len(sel)} objects", icon='OBJECT_DATA')
            if show_slot_warning:
                box.alert = True
                box.label(text="Slot 9+ cannot be edited in UV Editor. Move to slot 1-8 to edit.", icon='ERROR')
        
        if ctx.object.mode == 'EDIT':
            l.separator()
            row = l.row(align=True)
            row.operator(UV_OT_copy_uvs.bl_idname, text="Copy UVs", icon='COPYDOWN')
            row.operator(UV_OT_paste_uvs.bl_idname, text="Paste UVs", icon='PASTEDOWN')

# === REGISTER ===

classes = (
    UV_OT_add, UV_OT_remove, UV_OT_duplicate, UV_OT_move, UV_OT_sort, UV_OT_reverse, UV_OT_delete_empty, UV_OT_delete_all,
    UV_OT_sync_order, UV_OT_copy_unique, UV_OT_transfer, UV_OT_copy_uvs, UV_OT_paste_uvs,
    MESH_UL_uvmaps_plus, UV_MT_specials, UVMAPSPLUS_PT_panel,
)

_default_panel = None

def register():
    global _default_panel
    for name in ('DATA_PT_uv_texture', 'DATA_PT_mesh_uv_maps'):
        if hasattr(bpy.types, name):
            try:
                _default_panel = getattr(bpy.types, name)
                bpy.utils.unregister_class(_default_panel)
                break
            except: pass
    for cls in classes: bpy.utils.register_class(cls)
    if sync_handler not in depsgraph_update_post: depsgraph_update_post.append(sync_handler)

def unregister():
    if sync_handler in depsgraph_update_post: depsgraph_update_post.remove(sync_handler)
    for cls in reversed(classes):
        try: bpy.utils.unregister_class(cls)
        except: pass
    if _default_panel:
        try: bpy.utils.register_class(_default_panel)
        except: pass