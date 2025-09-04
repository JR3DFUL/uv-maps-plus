## UV Maps+

UV Maps+ (UV Maps Plus) bypasses Blender's default 8 UV map limit, allowing you to add and organize as many UV channels as your project needs. It replaces the standard UV panel with a new one, adding buttons for reordering, duplicating, and copying data across UV Maps.

### Features

Main Panel Controls

* `+` (Add UV Map): Adds a new, blank UV map to the list, bypassing the 8-map limit.

* `-` (Remove UV Map): Deletes the currently selected UV map.

* `▼` (Specials Menu): Opens a dropdown menu with more advanced management tools (see below).

* `▲` (Move Up): Moves the selected UV map one position up in the list.

* `▼` (Move Down): Moves the selected UV map one position down in the list.

Specials Menu (Dropdown)

* Sort Maps by Name: Alphabetically sorts all UV maps in the list.

* Reverse Map Order: Reverses the current order of all UV maps.

* Move to Top: Instantly moves the selected UV map to the top of the list.

* Move to Bottom: Instantly moves the selected UV map to the bottom of the list.

* Duplicate Selected: Creates an exact copy of the selected UV map.

* Delete All UV Maps: Removes all UV maps from the object.

Edit Mode Tools

* Copy UVs: While in Edit Mode, this copies the UV coordinates of your current vertex selection on the active UV map.

* Paste UVs: Pastes the copied UV coordinates onto the corresponding vertices of the active UV map.

Warning System

When you have more than 8 UV maps, a notice will appear. While the add-on can store unlimited maps, Blender's UV Editor can only *preview** the first 8 at a time. To see a map beyond the 8th slot, simply use the reordering arrows to move it into one of the top 8 positions.
