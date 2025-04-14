# -*- coding: utf-8 -*-
# Use UTF-8 encoding

import bpy
from bpy.props import StringProperty, EnumProperty, IntProperty, BoolProperty
from bpy.types import UIList, Operator, Panel # Explicit imports

bl_info = {
    "name": "Animation Manager",
    "blender": (3, 6, 0),  # Adjusted Blender version for consistency
    "category": "Animation",
    "version": (1, 1, 0),  # Incremented version for Sync feature
    "author": "Evilmushroom",
    "description": "A tool for managing animations with features like action selection (synced with Game Exporter), NLA operations, batch renaming, and more.",
    "location": "3D View > Sidebar > Animation Tab",
    "doc_url": "https://github.com/evilmushroom/blender-AnimationManager",
    "support": "COMMUNITY",
}

# --- Update Function for Syncing ---
# This function will be called when Action.select changes
def update_select_sync(self, context):
    """Updates Action.export if it exists and has a different value."""
    # Check if the 'export' property exists (i.e., Game Exporter is loaded)
    if hasattr(self, "export"):
        # Check if the value needs changing to prevent infinite loops
        if self.export != self.select:
            # print(f"SYNC: Setting 'export' from 'select' for {self.name} to {self.select}") # Optional Debug Print
            try:
                self.export = self.select # Update the 'export' property
            except Exception as e:
                # Handle potential errors if property is read-only or other issues
                print(f"ERROR in update_select_sync: Could not set 'export' for {self.name}: {e}")

# --- UI List Class ---
class ACTION_UL_list(UIList):
    # Added bl_idname for robustness
    bl_idname = "ANIM_UL_manager_action_list"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        action = item # item is the action
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            # Use 'select' property defined by this addon
            if hasattr(action, "select"):
                 row.prop(action, "select", text="")
            else:
                 row.label(text="", icon='ERROR') # Fallback if property doesn't exist
            row.prop(action, "name", text="", emboss=False, icon_value=icon)

            # Play button
            op = row.operator("anim.set_active_action", text="", icon='PLAY')
            op.action_name = action.name

            # Fake User button (Rely on Blender's default icon handling)
            row.prop(action, "use_fake_user", text="", toggle=True)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

# --- Operators ---
class ANIM_OT_set_active_action(Operator):
    bl_idname = "anim.set_active_action"
    bl_label = "Set Active Action"
    bl_description = "Set this action as the active one"

    action_name: StringProperty()

    def execute(self, context):
        obj = context.object
        if obj and obj.animation_data:
            action = bpy.data.actions.get(self.action_name)
            if action:
                try: obj.animation_data.action = action
                except Exception as e: self.report({'ERROR'}, f"Could not set action: {e}"); return {'CANCELLED'}
            else: self.report({'WARNING'}, f"Action '{self.action_name}' not found."); return {'CANCELLED'}
        elif not obj: self.report({'ERROR'}, "No active object."); return {'CANCELLED'}
        else: self.report({'WARNING'}, "Active object has no Animation Data."); return {'CANCELLED'}
        return {'FINISHED'}

class ANIM_OT_push_actions_to_nla(Operator):
    bl_idname = "anim.push_actions_to_nla"
    bl_label = "Push Selected to NLA"
    bl_description = "Push selected actions to NLA strips on the active object"

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        obj = context.object
        if not obj: self.report({'ERROR'}, "No active object selected"); return {'CANCELLED'}
        if not obj.animation_data:
            try: obj.animation_data_create()
            except Exception as e: self.report({'ERROR'}, f"Could not create Animation Data: {e}"); return {'CANCELLED'}

        pushed_count = 0
        actions_to_push = [action for action in bpy.data.actions if getattr(action, "select", False)]
        if not actions_to_push: self.report({'WARNING'}, "No actions selected in the list."); return {'CANCELLED'}

        for action in actions_to_push:
            existing_track = next((track for track in obj.animation_data.nla_tracks if track.strips and track.strips[0].action == action), None)
            if existing_track: obj.animation_data.nla_tracks.remove(existing_track)

            track = obj.animation_data.nla_tracks.new(); track.name = action.name
            start_frame = int(action.frame_range[0]) if action.frame_range else 0
            strip = track.strips.new(action.name, start_frame, action)
            strip.frame_start = start_frame
            strip.frame_end = int(action.frame_range[1]) if action.frame_range else start_frame + 1
            pushed_count += 1

        if pushed_count > 0: self.report({'INFO'}, f"Pushed {pushed_count} selected actions to NLA for '{obj.name}'")
        else: self.report({'WARNING'}, "No actions were pushed to NLA.")
        return {'FINISHED'}

class ANIM_OT_delete_selected_actions(Operator):
    bl_idname = "anim.delete_selected_actions"
    bl_label = "Delete Selected"
    bl_description = "Delete selected actions"

    # Added invoke_confirm for safety
    def invoke(self, context, event):
       return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        actions_to_remove = [action for action in bpy.data.actions if getattr(action, "select", False)]
        removed_count = 0
        if not actions_to_remove: self.report({'WARNING'}, "No actions selected for deletion."); return {'CANCELLED'}

        for action in actions_to_remove:
            try:
                bpy.data.actions.remove(action, do_unlink=True)
                removed_count += 1
            except Exception as e:
                 print(f"Error removing action {action.name}: {e}")
                 self.report({'WARNING'}, f"Could not remove action '{action.name}'. It might be in use.")

        if removed_count > 0: self.report({'INFO'}, f"Deleted {removed_count} actions."); context.area.tag_redraw()
        else: self.report({'WARNING'}, "No actions were deleted (possibly due to errors).")
        return {'FINISHED'}

class ANIM_OT_batch_rename_actions(Operator):
    bl_idname = "anim.batch_rename_actions"
    bl_label = "Batch Rename Actions"
    bl_description = "Rename selected actions using a pattern"

    prefix: StringProperty(name="Prefix", description="Prefix for the new names")
    suffix: StringProperty(name="Suffix", description="Suffix for the new names")
    base_name: StringProperty(name="Base Name", description="Base name for the new names")
    start_number: IntProperty(name="Start Number", description="Starting number for numbered names", default=1, min=0)
    naming_method: EnumProperty(
        name="Naming Method",
        items=[ ('PREFIX_SUFFIX', "Prefix/Suffix", "Add prefix and/or suffix to existing names"),
                ('NUMBERED', "Numbered", "Replace names with Base Name + Number (e.g., Anim_001)"),
                ('REPLACE', "Find and Replace", "Replace part of the existing name"),],
        default='PREFIX_SUFFIX'
    )
    find_text: StringProperty(name="Find", description="Text to find in existing names")
    replace_text: StringProperty(name="Replace", description="Text to replace found text with")

    def execute(self, context):
        selected_actions = [action for action in bpy.data.actions if getattr(action, "select", False)]
        if not selected_actions: self.report({'WARNING'}, "No actions selected"); return {'CANCELLED'}

        renamed_count = 0
        if self.naming_method == 'PREFIX_SUFFIX':
            for action in selected_actions: action.name = f"{self.prefix}{action.name}{self.suffix}"; renamed_count += 1
        elif self.naming_method == 'NUMBERED':
            if not self.base_name: self.report({'ERROR'}, "Base Name cannot be empty for Numbered method."); return {'CANCELLED'}
            for i, action in enumerate(selected_actions, start=self.start_number): action.name = f"{self.base_name}_{i:03d}"; renamed_count += 1
        elif self.naming_method == 'REPLACE':
             if not self.find_text: self.report({'WARNING'}, "Find text is empty, no replacement performed."); return {'CANCELLED'}
             for action in selected_actions:
                new_name = action.name.replace(self.find_text, self.replace_text)
                if new_name != action.name: action.name = new_name; renamed_count += 1

        if renamed_count > 0: self.report({'INFO'}, f"Renamed {renamed_count} actions")
        else: self.report({'INFO'}, "No action names were changed.")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout; layout.prop(self, "naming_method", expand=True); layout.separator()
        if self.naming_method == 'PREFIX_SUFFIX': layout.prop(self, "prefix"); layout.prop(self, "suffix")
        elif self.naming_method == 'NUMBERED': layout.prop(self, "base_name"); layout.prop(self, "start_number")
        elif self.naming_method == 'REPLACE': layout.prop(self, "find_text"); layout.prop(self, "replace_text")

class ANIM_OT_create_new_action(Operator):
    bl_idname = "anim.create_new_action"
    bl_label = "Create New Action"
    bl_description = "Create a new action"

    action_type: EnumProperty(
        name="Action Type",
        items=[ ('EMPTY', "Empty Action", "Create a new empty action"),
                ('DUPLICATE', "Duplicate Active", "Duplicate the active action"),],
        default='EMPTY'
    )
    new_name: StringProperty(name="New Name", default="NewAction")

    def execute(self, context):
        obj = context.object
        if not obj: self.report({'ERROR'}, "No active object selected"); return {'CANCELLED'}
        if not obj.animation_data:
            try: obj.animation_data_create()
            except Exception as e: self.report({'ERROR'}, f"Could not create Animation Data: {e}"); return {'CANCELLED'}

        new_action = None
        if self.action_type == 'EMPTY':
            new_action = bpy.data.actions.new(name=self.new_name)
        elif self.action_type == 'DUPLICATE':
            active_action = obj.animation_data.action
            if active_action: new_action = active_action.copy(); new_action.name = self.new_name
            else: self.report({'ERROR'}, "No active action to duplicate"); return {'CANCELLED'}

        if new_action:
             obj.animation_data.action = new_action
             # Try to set select=True on the new action for immediate visibility
             if hasattr(new_action, "select"): setattr(new_action, "select", True)
             self.report({'INFO'}, f"Created new action: {new_action.name}"); return {'FINISHED'}
        else: self.report({'ERROR'}, "Failed to create action."); return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout; layout.prop(self, "action_type", expand=True); layout.prop(self, "new_name")

class ANIM_PT_animation_manager_panel(Panel):
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
        # *** Use the defined bl_idname for the list ***
        row.template_list(ACTION_UL_list.bl_idname, "", bpy.data, "actions", scene, "action_index")

        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator("anim.create_new_action", text="New", icon='ADD')
        row.operator("anim.push_actions_to_nla", text="To NLA", icon='NLA')

        row = col.row(align=True)
        row.operator("anim.batch_rename_actions", text="Rename", icon='SORTALPHA')
        row.operator("anim.delete_selected_actions", text="Delete", icon='X')


# --- Registration ---

# Update function for the 'Select All' checkbox
def update_select_all(self, context):
    """ Toggles the 'select' property on all actions """
    val = self.select_all_actions
    for action in bpy.data.actions:
        setattr(action, "select", val) # Targets 'select' property

# List of classes to register
classes = (
    ACTION_UL_list, # Must be registered before panel using it
    ANIM_OT_set_active_action,
    ANIM_OT_push_actions_to_nla,
    ANIM_OT_delete_selected_actions,
    ANIM_OT_batch_rename_actions,
    ANIM_OT_create_new_action,
    ANIM_PT_animation_manager_panel,
)

def register():
    # Register classes
    for cls in classes:
        bpy.utils.register_class(cls)

    # Scene property for the active index in the UI list
    bpy.types.Scene.action_index = IntProperty()

    # Custom property added to Action datablocks
    # Check if it already exists (e.g., from a previous registration)
    if not hasattr(bpy.types.Action, "select"):
        bpy.types.Action.select = BoolProperty(
            name="Select Action",
            description="Select action for batch operations / sync with Game Exporter", # Updated description
            default=False, # Default to False, user explicitly selects
            update=update_select_sync # *** Assign the update function ***
            )
    else:
         # If it exists, maybe try to assign update? This is risky.
         # Best practice is that only one addon "owns" defining a property on a built-in type.
         # For now, we assume if it exists, it might have the update already or is managed elsewhere.
         print("INFO: Action.select already exists. Sync might rely on other addon's update.")


    # Scene property for the 'Select All' checkbox
    # Check if it exists before defining
    if not hasattr(bpy.types.Scene, "select_all_actions"):
        bpy.types.Scene.select_all_actions = BoolProperty(
            name="Select All Actions", # More descriptive name
            description="Select or deselect all actions in the list",
            default=False, # Match default of Action.select
            update=update_select_all
        )

def unregister():
    # Delete custom properties first (use try-except for safety)
    # Only delete properties this addon DEFINES
    if hasattr(bpy.types.Action, "select"):
        # Check if the update function matches before deleting? Complex.
        # Safest is to just try removing if it exists.
        try: del bpy.types.Action.select
        except Exception as e: print(f"Could not delete Action.select: {e}")

    if hasattr(bpy.types.Scene, "action_index"):
        try: del bpy.types.Scene.action_index
        except Exception as e: print(f"Could not delete Scene.action_index: {e}")

    if hasattr(bpy.types.Scene, "select_all_actions"):
        try: del bpy.types.Scene.select_all_actions
        except Exception as e: print(f"Could not delete Scene.select_all_actions: {e}")


    # Unregister classes in reverse order
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
             print(f"Could not unregister class: {cls.__name__}")


if __name__ == "__main__":
    # Allow running the script directly in Blender Text Editor for testing
    try:
        unregister() # Unregister previous version first
    except Exception as e:
        print(f"Unregistration failed: {e}")
        pass
    register()

