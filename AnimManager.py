import bpy
from bpy.props import StringProperty, EnumProperty, IntProperty, BoolProperty

bl_info = {
    "name": "Animation Manager",
    "blender": (3, 6, 9),  
    "category": "Animation",
    "version": (1, 0, 0),  
    "author": "Evilmushroom",
    "description": "A tool for managing animations with features like action selection, NLA operations, batch renaming, and more.",
    "location": "3D View > Sidebar > Animation Tab",
    "doc_url": "https://github.com/evilmushroom/blender-AnimationManager",  
    "support": "COMMUNITY",  
}

class ACTION_UL_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "select", text="")
            row.prop(item, "name", text="", emboss=False, icon_value=icon)
            
            # Play button
            op = row.operator("anim.set_active_action", text="", icon='PLAY')
            op.action_name = item.name
            
            # Fake User button
            row.prop(item, "use_fake_user", text="", toggle=True)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

class ANIM_OT_set_active_action(bpy.types.Operator):
    bl_idname = "anim.set_active_action"
    bl_label = "Set Active Action"
    bl_description = "Set this action as the active one"
    
    action_name: StringProperty()

    def execute(self, context):
        obj = context.object
        if obj and obj.animation_data:
            action = bpy.data.actions.get(self.action_name)
            if action:
                obj.animation_data.action = action
        return {'FINISHED'}

class ANIM_OT_push_actions_to_nla(bpy.types.Operator):
    bl_idname = "anim.push_actions_to_nla"
    bl_label = "Push Selected to NLA"
    bl_description = "Push selected actions to NLA strips"

    def execute(self, context):
        obj = context.object
        if not obj:
            self.report({'ERROR'}, "No active object selected")
            return {'CANCELLED'}
        
        if not obj.animation_data:
            obj.animation_data_create()
        
        pushed_count = 0
        for action in bpy.data.actions:
            if action.select:
                # Check if a track for this action already exists
                existing_track = next((track for track in obj.animation_data.nla_tracks if track.strips and track.strips[0].action == action), None)
                
                if existing_track:
                    # If a track exists, remove it to avoid duplicates
                    obj.animation_data.nla_tracks.remove(existing_track)
                
                # Create a new track
                track = obj.animation_data.nla_tracks.new()
                track.name = action.name
                
                # Create a new strip in the track
                start_frame = int(action.frame_range[0])
                strip = track.strips.new(action.name, start_frame, action)
                
                # Set the strip's frame range
                strip.frame_start = start_frame
                strip.frame_end = int(action.frame_range[1])
                
                pushed_count += 1
        
        if pushed_count > 0:
            self.report({'INFO'}, f"Pushed {pushed_count} actions to NLA")
        else:
            self.report({'WARNING'}, "No actions were pushed to NLA. Make sure actions are selected.")
        
        return {'FINISHED'}

class ANIM_OT_delete_selected_actions(bpy.types.Operator):
    bl_idname = "anim.delete_selected_actions"
    bl_label = "Delete Selected"
    bl_description = "Delete selected actions"

    def execute(self, context):
        actions_to_remove = [action for action in bpy.data.actions if action.select]
        for action in actions_to_remove:
            bpy.data.actions.remove(action)
        return {'FINISHED'}

class ANIM_OT_batch_rename_actions(bpy.types.Operator):
    bl_idname = "anim.batch_rename_actions"
    bl_label = "Batch Rename Actions"
    bl_description = "Rename selected actions using a pattern"
    
    prefix: StringProperty(name="Prefix", description="Prefix for the new names")
    suffix: StringProperty(name="Suffix", description="Suffix for the new names")
    base_name: StringProperty(name="Base Name", description="Base name for the new names")
    start_number: IntProperty(name="Start Number", description="Starting number for numbered names", default=1)
    naming_method: EnumProperty(
        name="Naming Method",
        items=[
            ('PREFIX_SUFFIX', "Prefix/Suffix", "Use prefix and suffix"),
            ('NUMBERED', "Numbered", "Use base name with numbers"),
            ('REPLACE', "Find and Replace", "Replace part of the existing name"),
        ],
        default='PREFIX_SUFFIX'
    )
    find_text: StringProperty(name="Find", description="Text to find in existing names")
    replace_text: StringProperty(name="Replace", description="Text to replace found text with")

    def execute(self, context):
        selected_actions = [action for action in bpy.data.actions if action.select]
        
        if not selected_actions:
            self.report({'WARNING'}, "No actions selected")
            return {'CANCELLED'}
        
        if self.naming_method == 'PREFIX_SUFFIX':
            for action in selected_actions:
                action.name = f"{self.prefix}{action.name}{self.suffix}"
        
        elif self.naming_method == 'NUMBERED':
            for i, action in enumerate(selected_actions, start=self.start_number):
                action.name = f"{self.base_name}_{i:03d}"
        
        elif self.naming_method == 'REPLACE':
            for action in selected_actions:
                action.name = action.name.replace(self.find_text, self.replace_text)
        
        self.report({'INFO'}, f"Renamed {len(selected_actions)} actions")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "naming_method")
        
        if self.naming_method == 'PREFIX_SUFFIX':
            layout.prop(self, "prefix")
            layout.prop(self, "suffix")
        elif self.naming_method == 'NUMBERED':
            layout.prop(self, "base_name")
            layout.prop(self, "start_number")
        elif self.naming_method == 'REPLACE':
            layout.prop(self, "find_text")
            layout.prop(self, "replace_text")

class ANIM_OT_create_new_action(bpy.types.Operator):
    bl_idname = "anim.create_new_action"
    bl_label = "Create New Action"
    bl_description = "Create a new action"
    
    action_type: EnumProperty(
        name="Action Type",
        items=[
            ('EMPTY', "Empty Action", "Create a new empty action"),
            ('DUPLICATE', "Duplicate Active", "Duplicate the active action"),
            ('FROM_POSE', "From Current Pose", "Create a new action from the current pose"),
        ],
        default='EMPTY'
    )

    def execute(self, context):
        obj = context.object
        if not obj:
            self.report({'ERROR'}, "No active object selected")
            return {'CANCELLED'}
        
        if not obj.animation_data:
            obj.animation_data_create()
        
        if self.action_type == 'EMPTY':
            new_action = bpy.data.actions.new(name="New Action")
        elif self.action_type == 'DUPLICATE':
            if obj.animation_data.action:
                new_action = obj.animation_data.action.copy()
            else:
                self.report({'ERROR'}, "No active action to duplicate")
                return {'CANCELLED'}
        elif self.action_type == 'FROM_POSE':
            new_action = bpy.data.actions.new(name="New Action From Pose")
            obj.animation_data.action = new_action
            bpy.ops.anim.keyframe_insert_menu(type='WholeCharacter')
        
        obj.animation_data.action = new_action
        new_action.select = True
        self.report({'INFO'}, f"Created new action: {new_action.name}")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "action_type")

class ANIM_PT_animation_manager_panel(bpy.types.Panel):
    bl_label = "Animation Manager"
    bl_idname = "ANIM_PT_animation_manager_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Animation'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        row = layout.row()
        row.prop(scene, "select_all_actions", text="Select All")
        
        row = layout.row()
        row.template_list("ACTION_UL_list", "", bpy.data, "actions", scene, "action_index")
        
        row = layout.row(align=True)
        row.operator("anim.create_new_action", text="New Action", icon='ADD')
        row.operator("anim.push_actions_to_nla", text="Push to NLA", icon='NLA')
        row.operator("anim.delete_selected_actions", text="Delete Selected", icon='X')
        
        row = layout.row()
        row.operator("anim.batch_rename_actions", text="Batch Rename", icon='SORTALPHA')

def update_select_all(self, context):
    for action in bpy.data.actions:
        action.select = self.select_all_actions

def register():
    bpy.utils.register_class(ACTION_UL_list)
    bpy.utils.register_class(ANIM_OT_set_active_action)
    bpy.utils.register_class(ANIM_OT_push_actions_to_nla)
    bpy.utils.register_class(ANIM_OT_delete_selected_actions)
    bpy.utils.register_class(ANIM_OT_batch_rename_actions)
    bpy.utils.register_class(ANIM_OT_create_new_action)
    bpy.utils.register_class(ANIM_PT_animation_manager_panel)
    bpy.types.Scene.action_index = IntProperty()
    bpy.types.Action.select = BoolProperty(default=True)
    bpy.types.Scene.select_all_actions = BoolProperty(
        name="Select All",
        description="Select or deselect all actions",
        default=True,
        update=update_select_all
    )

def unregister():
    bpy.utils.unregister_class(ACTION_UL_list)
    bpy.utils.unregister_class(ANIM_OT_set_active_action)
    bpy.utils.unregister_class(ANIM_OT_push_actions_to_nla)
    bpy.utils.unregister_class(ANIM_OT_delete_selected_actions)
    bpy.utils.unregister_class(ANIM_OT_batch_rename_actions)
    bpy.utils.unregister_class(ANIM_OT_create_new_action)
    bpy.utils.unregister_class(ANIM_PT_animation_manager_panel)
    del bpy.types.Scene.action_index
    del bpy.types.Action.select
    del bpy.types.Scene.select_all_actions

if __name__ == "__main__":
    register()