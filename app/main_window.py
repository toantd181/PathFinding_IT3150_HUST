import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QHBoxLayout, QWidget,
                             QMessageBox, QGraphicsView)
from PyQt6.QtCore import Qt, QPointF, QLineF
from PyQt6.QtGui import QKeyEvent
from .map_viewer import MapViewer, EFFECT_DATA_KEY
from .pathfinding import Pathfinding
from .sidebar import Sidebar
from .tools.traffic_light_tool import TrafficLightInstance, TrafficLightState

from itertools import permutations  


def point_segment_distance(p: QPointF, a: QPointF, b: QPointF) -> float:
    """Calculates the shortest distance from point p to line segment ab."""
    ab_x = b.x() - a.x()
    ab_y = b.y() - a.y()
    ap_x = p.x() - a.x()
    ap_y = p.y() - a.y()

    len_sq_ab = ab_x * ab_x + ab_y * ab_y
    if abs(len_sq_ab) < 1e-9:
        return QLineF(p, a).length()

    t = (ap_x * ab_x + ap_y * ab_y) / len_sq_ab
    t = max(0.0, min(1.0, t))
    
    closest_point_on_line = QPointF(a.x() + t * ab_x, a.y() + t * ab_y)
    return QLineF(p, closest_point_on_line).length()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Offline Pathfinding App")
        self.setGeometry(100, 100, 1200, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.find_path_button.clicked.connect(self._trigger_pathfinding)

        # Map Viewer
        map_file = os.path.join(os.path.dirname(__file__), "assets", "map.png")
        self.map_viewer = MapViewer(map_file, self._handle_point_selected)

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.map_viewer, 1)

        # Pathfinding Initialization
        db_file = os.path.join(os.path.dirname(__file__), "data", "graph.db")
        self.pathfinder = None
        try:
            self.pathfinder = Pathfinding(db_file)
            print("Pathfinding engine initialized.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to initialize pathfinding: {e}")
            print(f"Error initializing Pathfinding: {e}")

        self.start_node = None
        self.end_node = None
        self.node_positions = {}
        self._effect_application_threshold = 20  # Increased for better click detection
        
        if self.pathfinder:
            for node_id, data in self.pathfinder.graph.nodes(data=True):
                if 'pos' in data:
                    self.node_positions[node_id] = data['pos']
            print(f"Loaded {len(self.node_positions)} node positions.")
            
            self._original_weights = {}
            if self.pathfinder.graph.number_of_edges() > 0:
                try:
                    self._original_weights = {(u, v): data['weight'] for u, v, data in self.pathfinder.graph.edges(data=True) if 'weight' in data}
                    print(f"Stored original weights for {len(self._original_weights)} edges.")
                except KeyError as e:
                    print(f"Warning: Missing 'weight' attribute for an edge: {e}.")
            
            self._initialize_search_tool()

        # Traffic Light Management
        self._active_traffic_lights = {}

        # Connect Signals - Selection Mode
        self.sidebar.set_start_mode_button.toggled.connect(self._on_start_mode_toggled)
        self.sidebar.set_end_mode_button.toggled.connect(self._on_end_mode_toggled)
        self.sidebar.add_waypoint_button.toggled.connect(self._on_waypoint_mode_toggled)
        self.sidebar.clear_start_button.clicked.connect(self._clear_start_point)
        self.sidebar.clear_end_button.clicked.connect(self._clear_end_point)
        
        # Connect Signals - Tools
        self.sidebar.traffic_tool_activated.connect(self.map_viewer.set_traffic_drawing_mode)
        self.sidebar.block_way_tool_activated.connect(self.map_viewer.set_block_way_drawing_mode)
        self.sidebar.traffic_light_tool_activated.connect(self.map_viewer.set_traffic_light_placement_mode)

        # Connect Signals - Drawing Results
        self.map_viewer.traffic_line_drawn.connect(self.handle_traffic_line)
        self.map_viewer.block_way_drawn.connect(self.handle_block_way)
        self.map_viewer.traffic_light_visuals_created.connect(self.handle_traffic_light_finalized)
        self.map_viewer.effects_changed.connect(self._handle_effects_changed)

        # Connect Signals - Location Search
        self.sidebar.location_selected_for_start.connect(self._handle_location_selected_for_start)
        self.sidebar.location_selected_for_end.connect(self._handle_location_selected_for_end)
        self.sidebar.use_map_start_clicked.connect(self._handle_use_map_start_clicked)
        self.sidebar.use_map_end_clicked.connect(self._handle_use_map_end_clicked)

        # Connect Signals - Clear Effect Buttons
        self.sidebar.clear_traffic_jams_button.clicked.connect(self._clear_traffic_jams)
        self.sidebar.clear_block_ways_button.clicked.connect(self._clear_block_ways)
        self.sidebar.clear_traffic_lights_button.clicked.connect(self._clear_traffic_lights)
        self.sidebar.clear_all_effects_button.clicked.connect(self._clear_all_effects)
        self.sidebar.clear_waypoints_button.clicked.connect(self._clear_all_waypoints)
        self.sidebar.remove_waypoint_button.clicked.connect(self._remove_selected_waypoint)

        self._suppress_path_errors = False

    def _on_start_mode_toggled(self, checked):
        """Handle start selection mode toggle"""
        self.map_viewer.set_start_selection_mode(checked)
        if checked:
            self.sidebar._uncheck_other_tools(self.sidebar.set_start_mode_button)
            print("Start selection mode activated - Click on map to set start point")

    def _on_end_mode_toggled(self, checked):
        """Handle end selection mode toggle"""
        self.map_viewer.set_end_selection_mode(checked)
        if checked:
            self.sidebar._uncheck_other_tools(self.sidebar.set_end_mode_button)
            print("End selection mode activated - Click on map to set end point")

    def _on_waypoint_mode_toggled(self, checked):
        """Handle waypoint selection mode toggle"""
        self.map_viewer.set_waypoint_selection_mode(checked)
        if checked:
            self.sidebar._uncheck_other_tools(self.sidebar.add_waypoint_button)
            print("Waypoint mode activated - Click on map to add stops")

    def _clear_start_point(self):
        """Clear the start point"""
        self.start_node = None
        self.sidebar.start_label.setText("Start: Not Selected")
        self.sidebar.clear_start_button.setEnabled(False)
        self.map_viewer.clear_permanent_point("start")
        self.sidebar.from_location_combo.setCurrentIndex(-1)
        self.sidebar.from_location_combo.lineEdit().setText("")
        self.map_viewer.clear_path()
        print("Start point cleared")

    def _clear_end_point(self):
        """Clear the end point"""
        self.end_node = None
        self.sidebar.end_label.setText("End: Not Selected")
        self.sidebar.clear_end_button.setEnabled(False)
        self.map_viewer.clear_permanent_point("end")
        self.sidebar.to_location_combo.setCurrentIndex(-1)
        self.sidebar.to_location_combo.lineEdit().setText("")
        self.map_viewer.clear_path()
        print("End point cleared")

    def _clear_traffic_jams(self):
        """Clear all traffic jam effects"""
        self.map_viewer.clear_traffic_jams()
        self._recalculate_effects_and_path()
        print("All traffic jams cleared")

    def _clear_block_ways(self):
        """Clear all block way effects"""
        self.map_viewer.clear_block_ways()
        self._recalculate_effects_and_path()
        print("All block ways cleared")

    def _clear_traffic_lights(self):
        """Clear all traffic light effects"""
        # Stop all timers first
        for icon_id, (instance, text_item, icon_item, line_item) in list(self._active_traffic_lights.items()):
            if instance:
                instance.stop()
        self._active_traffic_lights.clear()
        
        # Clear visuals
        self.map_viewer.clear_traffic_lights()
        self._recalculate_effects_and_path()
        print("All traffic lights cleared")

    def _clear_all_waypoints(self):
        """Clear all waypoints and their visual markers"""
        print("DEBUG: _clear_all_waypoints called")
    
        # Get the virtual node IDs for start and end points (to preserve them)
        preserve_nodes = set()
        if self.start_node and self.start_node.startswith('VIRTUAL_'):
            preserve_nodes.add(self.start_node)
            print(f"Preserving start virtual node: {self.start_node}")
        if self.end_node and self.end_node.startswith('VIRTUAL_'):
            preserve_nodes.add(self.end_node)
            print(f"Preserving end virtual node: {self.end_node}")
    
        # Clear from sidebar
        cleared = self.sidebar._clear_all_waypoints()
        print(f"DEBUG: Cleared {len(cleared)} waypoints from sidebar")
    
        # Clear visual markers from map
        print(f"DEBUG: Waypoint markers before clear: {len(self.map_viewer.waypoint_markers)}")
        self.map_viewer.clear_waypoint_markers()
        print(f"DEBUG: Waypoint markers after clear: {len(self.map_viewer.waypoint_markers)}")
    
        # Remove virtual nodes from graph (but preserve start/end)
        self._remove_virtual_nodes(exclude_nodes=preserve_nodes)
    
        # Recalculate path without waypoints
        if self.start_node and self.end_node:
            self._trigger_pathfinding()
    
        print(f"Cleared {len(cleared)} waypoints and their markers")

    def _remove_selected_waypoint(self):
        """Remove selected waypoint"""
        current_row = self.sidebar.waypoints_list.currentRow()
        if current_row < 0:
            print("No waypoint selected")
            return
        
        # Get the waypoint data before removing
        if current_row >= len(self.sidebar.waypoints):
            print(f"Error: Invalid row {current_row}, only {len(self.sidebar.waypoints)} waypoints")
            return
        
        removed_waypoint = self.sidebar.waypoints[current_row]
        
        # Remove from sidebar (this updates both list widget and data)
        self.sidebar.waypoints_list.takeItem(current_row)
        self.sidebar.waypoints.pop(current_row)
        
        print(f"Removed waypoint at position {current_row}: {removed_waypoint['node_id']}")
        
        # Clear all waypoint markers and redraw remaining ones
        self.map_viewer.clear_waypoint_markers()
        
        # Redraw remaining waypoints with updated numbers
        for i, wp in enumerate(self.sidebar.waypoints):
            pos = QPointF(wp['pos'][0], wp['pos'][1])
            self.map_viewer.add_waypoint_marker(pos, i + 1)
        
        # Update the list widget text to reflect new numbering
        for i in range(self.sidebar.waypoints_list.count()):
            wp = self.sidebar.waypoints[i]
            item_text = f"{i + 1}. {wp['name']}"
            self.sidebar.waypoints_list.item(i).setText(item_text)
        
        # Remove virtual node from graph if it was virtual (but check it's not start/end)
        if removed_waypoint['node_id'].startswith('VIRTUAL_'):
            # Only remove if it's not the start or end node
            if removed_waypoint['node_id'] != self.start_node and removed_waypoint['node_id'] != self.end_node:
                self._remove_virtual_node(removed_waypoint['node_id'])
            else:
                print(f"Skipping removal of {removed_waypoint['node_id']} - it's a start/end point")
        
        # ⭐ SUPPRESS ERRORS DURING PATH RECALCULATION ⭐
        self._suppress_path_errors = True
        
        # Recalculate path
        try:
            if self.start_node and self.end_node:
                if self.sidebar.waypoints:
                    self._trigger_pathfinding_with_waypoints()
                else:
                    self._trigger_pathfinding()
        finally:
            # Always re-enable errors after recalculation
            self._suppress_path_errors = False
        
        print(f"Removed waypoint: {removed_waypoint['node_id']}")

    def _remove_virtual_nodes(self, exclude_nodes=None):
        """Remove all virtual nodes from the graph, optionally excluding specific ones"""
        if exclude_nodes is None:
            exclude_nodes = set()
    
        virtual_nodes = [
            node for node in self.pathfinder.graph.nodes() 
            if node.startswith('VIRTUAL_') and node not in exclude_nodes
        ]
    
        for node in virtual_nodes:
            self.pathfinder.graph.remove_node(node)
            if node in self.node_positions:
                del self.node_positions[node]
    
        if virtual_nodes:
            print(f"Removed {len(virtual_nodes)} virtual nodes from graph (preserved {len(exclude_nodes)})")

    def _remove_virtual_node(self, node_id):
        """Remove a specific virtual node from the graph"""
        if node_id in self.pathfinder.graph:
            self.pathfinder.graph.remove_node(node_id)
        if node_id in self.node_positions:
            del self.node_positions[node_id]
        print(f"Removed virtual node: {node_id}")

    def _clear_all_effects(self):
        """Clear all effects (traffic, blocks, lights, waypoints)"""
        # Stop all traffic light timers
        self.stop_all_traffic_light_timers()
        
        # Clear all visuals
        self.map_viewer.clear_all_effects()
        
        # Clear waypoints
        self._clear_all_waypoints()
        
        # Recalculate path
        self._recalculate_effects_and_path()
        print("All effects cleared")

    def _initialize_search_tool(self):
        if not self.pathfinder:
            print("Search tool not initialized: Pathfinding engine not available.")
            return
        
        locations_data = self.pathfinder.get_all_searchable_locations()
        if locations_data:
            self.sidebar.populate_location_search(locations_data)
            print(f"Search tool populated with {len(locations_data)} locations.")
        else:
            print("Search tool: No locations found to populate.")

    def _set_start_node_from_data(self, location_data):
        """Helper to set start node from location data."""
        node_id_to_set = None
        position_to_set = None
        display_name_for_label = location_data['display_name'].split(' (')[0]

        if location_data['type'] == 'node':
            node_id_to_set = location_data['id']
            if node_id_to_set in self.node_positions:
                position_to_set = self.node_positions[node_id_to_set]
            else:
                QMessageBox.warning(self, "Error", f"Node '{node_id_to_set}' not found in map data.")
                return False
        elif location_data['type'] == 'special_place':
            sp_x, sp_y = location_data['pos']
            node_id_to_set = self._find_nearest_node(sp_x, sp_y)
            if node_id_to_set and node_id_to_set in self.node_positions:
                position_to_set = self.node_positions[node_id_to_set]
                display_name_for_label = f"{location_data['name']} (near {node_id_to_set})"
            else:
                QMessageBox.warning(self, "Error", f"Could not find nearby node for '{location_data['name']}'.")
                return False

        if node_id_to_set and position_to_set:
            if node_id_to_set == self.end_node:
                QMessageBox.warning(self, "Selection Error", "Start cannot be the same as end location.")
                self.sidebar.from_location_combo.setCurrentIndex(-1)
                self.sidebar.from_location_combo.lineEdit().setText("")
                return False

            self.start_node = node_id_to_set
            snapped_pos = QPointF(position_to_set[0], position_to_set[1])
            self.sidebar.start_label.setText(f"Start: {display_name_for_label}")
            self.sidebar.clear_start_button.setEnabled(True)
            self.map_viewer.set_permanent_point("start", snapped_pos)
            print(f"Start node set to {self.start_node}")
            return True
        return False

    def _set_end_node_from_data(self, location_data):
        """Helper to set end node from location data."""
        node_id_to_set = None
        position_to_set = None
        display_name_for_label = location_data['display_name'].split(' (')[0]

        if location_data['type'] == 'node':
            node_id_to_set = location_data['id']
            if node_id_to_set in self.node_positions:
                position_to_set = self.node_positions[node_id_to_set]
            else:
                QMessageBox.warning(self, "Error", f"Node '{node_id_to_set}' not found in map data.")
                return False
        elif location_data['type'] == 'special_place':
            sp_x, sp_y = location_data['pos']
            node_id_to_set = self._find_nearest_node(sp_x, sp_y)
            if node_id_to_set and node_id_to_set in self.node_positions:
                position_to_set = self.node_positions[node_id_to_set]
                display_name_for_label = f"{location_data['name']} (near {node_id_to_set})"
            else:
                QMessageBox.warning(self, "Error", f"Could not find nearby node for '{location_data['name']}'.")
                return False

        if node_id_to_set and position_to_set:
            if node_id_to_set == self.start_node:
                QMessageBox.warning(self, "Selection Error", "End cannot be the same as start location.")
                self.sidebar.to_location_combo.setCurrentIndex(-1)
                self.sidebar.to_location_combo.lineEdit().setText("")
                return False

            self.end_node = node_id_to_set
            snapped_pos = QPointF(position_to_set[0], position_to_set[1])
            self.sidebar.end_label.setText(f"End: {display_name_for_label}")
            self.sidebar.clear_end_button.setEnabled(True)
            self.map_viewer.set_permanent_point("end", snapped_pos)
            print(f"End node set to {self.end_node}")
            return True
        return False

    def _handle_location_selected_for_start(self, location_data):
        if self._set_start_node_from_data(location_data):
            # Auto-deactivate start selection mode after selecting from search
            if self.sidebar.set_start_mode_button.isChecked():
                self.sidebar.set_start_mode_button.setChecked(False)
            
            if self.start_node and self.end_node:
                self._trigger_pathfinding()
            else:
                self.map_viewer.clear_path()

    def _handle_location_selected_for_end(self, location_data):
        if self._set_end_node_from_data(location_data):
            # Auto-deactivate end selection mode after selecting from search
            if self.sidebar.set_end_mode_button.isChecked():
                self.sidebar.set_end_mode_button.setChecked(False)
            
            if self.start_node and self.end_node:
                self._trigger_pathfinding()
            else:
                self.map_viewer.clear_path()

    def _handle_use_map_start_clicked(self):
        if self.start_node and self.start_node in self.node_positions:
            self.sidebar.start_label.setText(f"Start: {self.start_node} (Map)")
            self.sidebar.from_location_combo.lineEdit().setText(f"{self.start_node} (Map)")
            self.sidebar.from_location_combo.setCurrentIndex(-1)
            # Auto-deactivate mode
            if self.sidebar.set_start_mode_button.isChecked():
                self.sidebar.set_start_mode_button.setChecked(False)
        else:
            # No start point yet, activate selection mode
            self.sidebar.set_start_mode_button.setChecked(True)
            QMessageBox.information(self, "Info", "Click on the map to set start point.")

    def _handle_use_map_end_clicked(self):
        if self.end_node and self.end_node in self.node_positions:
            self.sidebar.end_label.setText(f"End: {self.end_node} (Map)")
            self.sidebar.to_location_combo.lineEdit().setText(f"{self.end_node} (Map)")
            self.sidebar.to_location_combo.setCurrentIndex(-1)
            # Auto-deactivate mode
            if self.sidebar.set_end_mode_button.isChecked():
                self.sidebar.set_end_mode_button.setChecked(False)
        else:
            # No end point yet, activate selection mode
            self.sidebar.set_end_mode_button.setChecked(True)
            QMessageBox.information(self, "Info", "Click on the map to set end point.")

    def _handle_effects_changed(self):
        """Handle signal when an effect is removed."""
        print("Effect removed, recalculating...")

        active_icon_ids = {id(visual[0]) for visual in self.map_viewer.traffic_light_visuals}
        lights_to_remove = []

        for icon_id in list(self._active_traffic_lights.keys()):
            if icon_id not in active_icon_ids:
                instance, text_item, _, _ = self._active_traffic_lights[icon_id]
                print(f"Stopping timer for removed traffic light")
                instance.stop()
                lights_to_remove.append(icon_id)

        for icon_id in lights_to_remove:
            if icon_id in self._active_traffic_lights:
                del self._active_traffic_lights[icon_id]

        self._recalculate_effects_and_path()

    def handle_traffic_line(self, start_point, end_point):
        """Handle traffic line drawn."""
        if not self.pathfinder:
            return

        traffic_weight_increase = self.sidebar.traffic_tool.get_weight()
        print(f"Traffic line drawn. Applying weight +{traffic_weight_increase}")

        if self.map_viewer.traffic_jam_lines:
            last_line_item = self.map_viewer.traffic_jam_lines[-1]
            traffic_data = {
                "type": "traffic",
                "weight": traffic_weight_increase,
                "start": start_point,
                "end": end_point
            }
            last_line_item.setData(EFFECT_DATA_KEY, traffic_data)

        self._recalculate_effects_and_path()

    def handle_block_way(self, start_point, end_point):
        """Handle block way line drawn."""
        if not self.pathfinder:
            return

        print(f"Block way line drawn from {start_point} to {end_point}")

        if self.map_viewer.block_way_visuals:
            last_block_item = self.map_viewer.block_way_visuals[-1]
            block_data = {
                "type": "block_way",
                "start": start_point,
                "end": end_point
            }
            last_block_item.setData(EFFECT_DATA_KEY, block_data)

        self._recalculate_effects_and_path()

    def handle_traffic_light_finalized(self, icon_pos, line_start, line_end, icon_item, line_item, text_item):
        """Handle finalized traffic light placement."""
        if not self.pathfinder:
            return

        durations = self.sidebar.get_current_traffic_light_durations()
        print(f"Traffic light finalized at {icon_pos} with durations: {durations}")

        traffic_light_instance = TrafficLightInstance(durations)
        traffic_light_instance.state_changed.connect(self._traffic_light_state_updated)
        traffic_light_instance.remaining_time_updated.connect(self._update_traffic_light_countdown_display)

        existing_data = icon_item.data(EFFECT_DATA_KEY) or {}
        traffic_light_data = {
            **existing_data,
            "durations": durations,
            "instance": traffic_light_instance,
            "text_item": text_item
        }
        
        icon_item.setData(EFFECT_DATA_KEY, traffic_light_data)
        line_item.setData(EFFECT_DATA_KEY, traffic_light_data)
        text_item.setData(EFFECT_DATA_KEY, traffic_light_data)

        for i, (ic, ln, tx, data) in enumerate(self.map_viewer.traffic_light_visuals):
            if ic == icon_item:
                self.map_viewer.traffic_light_visuals[i] = (ic, ln, tx, traffic_light_data)
                break

        icon_id = id(icon_item)
        self._active_traffic_lights[icon_id] = (traffic_light_instance, text_item, icon_item, line_item)

        self.map_viewer.update_traffic_light_visual_state(icon_item, text_item, traffic_light_instance.current_state)
        self.map_viewer.update_traffic_light_countdown(text_item, traffic_light_instance.get_remaining_time())

        self._recalculate_effects_and_path()

    def _traffic_light_state_updated(self):
        traffic_light_instance = self.sender()
        if traffic_light_instance and isinstance(traffic_light_instance, TrafficLightInstance):
            found_icon_item = None
            found_text_item = None
            
            for _icon_id, (instance_from_dict, text_item_from_dict, icon_item_from_dict, _line_item_from_dict) in self._active_traffic_lights.items():
                if instance_from_dict == traffic_light_instance:
                    found_icon_item = icon_item_from_dict
                    found_text_item = text_item_from_dict
                    break

            if found_icon_item and found_text_item:
                self.map_viewer.update_traffic_light_visual_state(found_icon_item, found_text_item, traffic_light_instance.current_state)
                self.map_viewer.update_traffic_light_countdown(found_text_item, traffic_light_instance.get_remaining_time())

        self._recalculate_effects_and_path()

    def _update_traffic_light_countdown_display(self, remaining_seconds: int):
        """Update countdown display."""
        sender_instance = self.sender()
        if not isinstance(sender_instance, TrafficLightInstance):
            return

        found_text_item = None
        for instance, text_item, _, _ in self._active_traffic_lights.values():
            if instance == sender_instance:
                found_text_item = text_item
                break

        if found_text_item:
            self.map_viewer.update_traffic_light_countdown(found_text_item, remaining_seconds)

    def _recalculate_effects_and_path(self):
        if not self.pathfinder or not self.pathfinder.graph:
            return

        print("Recalculating effects and path...")
        self.reset_graph_weights()

        # Apply Traffic Jam Effects
        for line_item in self.map_viewer.traffic_jam_lines:
            data = line_item.data(EFFECT_DATA_KEY)
            if data and data.get("type") == "traffic":
                p1 = data["start"]
                p2 = data["end"]
                weight_increase = data["weight"]
                affected_edges = self.pathfinder.find_edges_near_line(p1, p2, self._effect_application_threshold)
                print(f"Traffic jam affecting {len(affected_edges)} edges with +{weight_increase}")
                for u, v in affected_edges:
                    self.pathfinder.modify_edge_weight(u, v, add_weight=weight_increase)

        # Apply Block Way Effects
        for line_item in self.map_viewer.block_way_visuals:
            data = line_item.data(EFFECT_DATA_KEY)
            if data and data.get("type") == "block_way":
                p1 = data["start"]
                p2 = data["end"]
                affected_edges = self.pathfinder.find_edges_near_line(p1, p2, self._effect_application_threshold)
                print(f"Block way affecting {len(affected_edges)} edges (setting to infinity)")
                for u, v in affected_edges:
                    print(f"  Blocking edge: {u} -> {v}")
                    self.pathfinder.modify_edge_weight(u, v, set_weight=float('inf'))

        # Apply Traffic Light Effects
        for icon_id, (traffic_light_instance, text_item, icon_item, line_item) in self._active_traffic_lights.items():
            if not traffic_light_instance:
                continue

            weight_modifier = traffic_light_instance.get_current_weight_modifier()
            effect_qlinef = line_item.line()
            p1 = effect_qlinef.p1()
            p2 = effect_qlinef.p2()
            
            affected_edges_for_tl = self.pathfinder.find_edges_near_line(p1, p2, threshold=self._effect_application_threshold)

            for u_edge, v_edge in affected_edges_for_tl:
                if self.pathfinder.graph.has_edge(u_edge, v_edge):
                    self.pathfinder.modify_edge_weight(u_edge, v_edge, add_weight=weight_modifier)

        # Recalculate path if both points are set
        if self.start_node and self.end_node:
            self._trigger_pathfinding()
        else:
            self.map_viewer.clear_path()

    def reset_graph_weights(self):
        """Reset graph edge weights to original values."""
        if not self.pathfinder or not self._original_weights:
            return

        for (u, v), original_weight in self._original_weights.items():
            if self.pathfinder.graph.has_edge(u, v):
                self.pathfinder.graph[u][v]['weight'] = original_weight

    def stop_all_traffic_light_timers(self):
        """Stop all active traffic light timers."""
        for data_tuple in list(self._active_traffic_lights.values()):
            tl_instance = data_tuple[0]
            if tl_instance: 
                tl_instance.stop()
        self._active_traffic_lights.clear()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle key presses."""
        if event.key() == Qt.Key.Key_Escape:
            print("Escape pressed - Cancelling current action.")
            
            if self.sidebar._traffic_tool_active:
                self.sidebar.traffic_jam_button.setChecked(False)
            elif self.sidebar._block_way_tool_active:
                self.sidebar.block_way_button.setChecked(False)
            elif self.sidebar._traffic_light_tool_active or self.map_viewer._is_drawing_traffic_light_line:
                self.sidebar.traffic_light_button.setChecked(False)
                self.map_viewer.set_traffic_light_placement_mode(False)

            self.map_viewer._cleanup_temp_drawing()
            self.map_viewer.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.map_viewer.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().keyPressEvent(event)

    def _set_start_node_from_data(self, location_data):
        """Helper to set start node from location data (node or special place)."""
        node_id_to_set = None
        position_to_set = None
        display_name_for_label = location_data['display_name'].split(' (')[0]

        if location_data['type'] == 'node':
            node_id_to_set = location_data['id']
            if node_id_to_set in self.node_positions:
                position_to_set = self.node_positions[node_id_to_set]
            else:
                QMessageBox.warning(self, "Error", f"Node '{node_id_to_set}' not found in map data.")
                return False
        elif location_data['type'] == 'special_place':
            sp_x, sp_y = location_data['pos']
            # Use simple nearest node for search results
            node_id_to_set = self._find_simple_nearest_node(sp_x, sp_y)
            if node_id_to_set and node_id_to_set in self.node_positions:
                position_to_set = self.node_positions[node_id_to_set]
                display_name_for_label = f"{location_data['name']} (near {node_id_to_set})"
            else:
                QMessageBox.warning(self, "Error", f"Could not find nearby node for special place '{location_data['name']}'.")
                return False
        else:
            print(f"Unknown location type: {location_data['type']}")
            return False

        if node_id_to_set and position_to_set:
            if node_id_to_set == self.end_node:
                QMessageBox.warning(self, "Selection Error", "Start cannot be the same as the end location.")
                self.sidebar.from_location_combo.setCurrentIndex(-1)
                self.sidebar.from_location_combo.lineEdit().setText("")
                return False

            self.start_node = node_id_to_set
            snapped_pos = QPointF(position_to_set[0], position_to_set[1])
            self.sidebar.start_label.setText(f"Start: {display_name_for_label}")
            self.sidebar.clear_start_button.setEnabled(True)
            self.map_viewer.set_permanent_point("start", snapped_pos)
            print(f"Start node set to {self.start_node}")
            return True
        return False

    def _set_end_node_from_data(self, location_data):
        """Helper to set end node from location data."""
        node_id_to_set = None
        position_to_set = None
        display_name_for_label = location_data['display_name'].split(' (')[0]

        if location_data['type'] == 'node':
            node_id_to_set = location_data['id']
            if node_id_to_set in self.node_positions:
                position_to_set = self.node_positions[node_id_to_set]
            else:
                QMessageBox.warning(self, "Error", f"Node '{node_id_to_set}' not found in map data.")
                return False
        elif location_data['type'] == 'special_place':
            sp_x, sp_y = location_data['pos']
            node_id_to_set = self._find_simple_nearest_node(sp_x, sp_y)
            if node_id_to_set and node_id_to_set in self.node_positions:
                position_to_set = self.node_positions[node_id_to_set]
                display_name_for_label = f"{location_data['name']} (near {node_id_to_set})"
            else:
                QMessageBox.warning(self, "Error", f"Could not find nearby node for special place '{location_data['name']}'.")
                return False
        else:
            print(f"Unknown location type: {location_data['type']}")
            return False

        if node_id_to_set and position_to_set:
            if node_id_to_set == self.start_node:
                QMessageBox.warning(self, "Selection Error", "End cannot be the same as start location.")
                self.sidebar.to_location_combo.setCurrentIndex(-1)
                self.sidebar.to_location_combo.lineEdit().setText("")
                return False

            self.end_node = node_id_to_set
            snapped_pos = QPointF(position_to_set[0], position_to_set[1])
            self.sidebar.end_label.setText(f"End: {display_name_for_label}")
            self.sidebar.clear_end_button.setEnabled(True)
            self.map_viewer.set_permanent_point("end", snapped_pos)
            print(f"End node set to {self.end_node}")
            return True
        return False

    def _find_simple_nearest_node(self, x, y):
        """Simple nearest node finder for search results (no virtual nodes)"""
        if not self.node_positions:
            return None
        
        min_dist_sq = float('inf')
        nearest_node = None
        
        for node_id, pos in self.node_positions.items():
            # Skip virtual nodes
            if node_id.startswith('VIRTUAL_'):
                continue
            dist_sq = (pos[0] - x)**2 + (pos[1] - y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                nearest_node = node_id
        
        return nearest_node

    def _find_nearest_node_or_edge(self, x, y):
        """
        Find nearest node OR position on edge.
        Returns: (node_id, pos, is_virtual, edge_info)
        - If close to existing node: (node_id, pos, False, None)
        - If on edge: (virtual_id, pos, True, (u, v, ratio))
        """
        if not self.node_positions:
            return None, None, False, None
        
        click_point = QPointF(x, y)
        min_node_dist_sq = float('inf')
        nearest_node = None
        nearest_node_pos = None
        
        # First, find nearest node by direct distance
        for node_id, pos in self.node_positions.items():
            dist_sq = (pos[0] - x)**2 + (pos[1] - y)**2
            if dist_sq < min_node_dist_sq:
                min_node_dist_sq = dist_sq
                nearest_node = node_id
                nearest_node_pos = pos
        
        # If we're very close to a node (within 15 pixels), return it directly
        if min_node_dist_sq < 225:  # 15^2
            return nearest_node, nearest_node_pos, False, None
        
        # Check if we're close to any edge
        if self.pathfinder:
            best_edge_dist = float('inf')
            best_edge = None
            best_point_on_edge = None
            best_ratio = 0.0
            
            for u, v in self.pathfinder.graph.edges():
                try:
                    pos_u = self.node_positions[u]
                    pos_v = self.node_positions[v]
                    point_u = QPointF(pos_u[0], pos_u[1])
                    point_v = QPointF(pos_v[0], pos_v[1])
                    
                    # Calculate closest point on edge and distance
                    edge_vec_x = point_v.x() - point_u.x()
                    edge_vec_y = point_v.y() - point_u.y()
                    click_vec_x = click_point.x() - point_u.x()
                    click_vec_y = click_point.y() - point_u.y()
                    
                    edge_len_sq = edge_vec_x * edge_vec_x + edge_vec_y * edge_vec_y
                    
                    if edge_len_sq < 1e-9:
                        continue
                    
                    # Project click onto edge
                    t = (click_vec_x * edge_vec_x + click_vec_y * edge_vec_y) / edge_len_sq
                    t = max(0.0, min(1.0, t))  # Clamp to edge
                    
                    # Point on edge
                    point_on_edge = QPointF(
                        point_u.x() + t * edge_vec_x,
                        point_u.y() + t * edge_vec_y
                    )
                    
                    # Distance from click to edge
                    dist = QLineF(click_point, point_on_edge).length()
                    
                    if dist < best_edge_dist and dist < 25:  # Within 25 pixels
                        best_edge_dist = dist
                        best_edge = (u, v)
                        best_point_on_edge = (point_on_edge.x(), point_on_edge.y())
                        best_ratio = t
                        
                except KeyError:
                    continue
            
            # If we found a close edge, return virtual node info
            if best_edge and best_ratio > 0.05 and best_ratio < 0.95:
                # Not too close to endpoints (at least 5% along the edge)
                u, v = best_edge
                virtual_id = f"VIRTUAL_{u}_{v}_{best_ratio:.3f}"
                print(f"Virtual node on edge {u}-{v} at ratio {best_ratio:.2f}")
                return virtual_id, best_point_on_edge, True, (u, v, best_ratio)
        
        # Fallback to nearest node
        return nearest_node, nearest_node_pos, False, None

    def _handle_point_selected(self, point_type, x, y):
        """Handle clicks on map for selecting start/end/waypoint points."""
        if x == -1 and y == -1:
            return

        node_id, pos, is_virtual, edge_info = self._find_nearest_node_or_edge(x, y)
        
        if node_id is None:
            print("No nearby node or edge found.")
            self.map_viewer.clear_temporary_point()
            return

        snapped_pos = QPointF(pos[0], pos[1])
        
        # Store virtual node info if needed
        if is_virtual:
            u, v, ratio = edge_info
            # Store virtual node position
            self.node_positions[node_id] = pos
            # Add temporary edges to graph for pathfinding
            self._add_virtual_node_to_graph(node_id, u, v, ratio)
            print(f"Created virtual node {node_id} on edge {u}-{v}")

        # Handle based on explicit mode
        if point_type == "start":
            if node_id == self.end_node:
                QMessageBox.warning(self, "Selection Error", "Start cannot be the same as end point.")
                self.map_viewer.clear_temporary_point()
                return
            
            self.start_node = node_id
            display_name = f"{node_id[:20]}..." if is_virtual else node_id
            self.sidebar.start_label.setText(f"Start: {display_name}")
            self.sidebar.clear_start_button.setEnabled(True)
            self.map_viewer.set_permanent_point("start", snapped_pos)
            self.sidebar.from_location_combo.lineEdit().setText(f"{display_name} (Map)")
            self.sidebar.from_location_combo.setCurrentIndex(-1)
            print(f"Start node set to {node_id}")
            
            # Auto-switch to end mode
            self.sidebar.set_start_mode_button.setChecked(False)
            if not self.end_node:
                self.sidebar.set_end_mode_button.setChecked(True)
        
        elif point_type == "end":
            if node_id == self.start_node:
                QMessageBox.warning(self, "Selection Error", "End cannot be the same as start point.")
                self.map_viewer.clear_temporary_point()
                return
            
            self.end_node = node_id
            display_name = f"{node_id[:20]}..." if is_virtual else node_id
            self.sidebar.end_label.setText(f"End: {display_name}")
            self.sidebar.clear_end_button.setEnabled(True)
            self.map_viewer.set_permanent_point("end", snapped_pos)
            self.sidebar.to_location_combo.lineEdit().setText(f"{display_name} (Map)")
            self.sidebar.to_location_combo.setCurrentIndex(-1)
            print(f"End node set to {node_id}")
            
            # Deactivate selection mode
            self.sidebar.set_end_mode_button.setChecked(False)
        
        elif point_type == "waypoint":
            # Add waypoint
            waypoint_number = len(self.sidebar.waypoints) + 1
            display_name = f"Stop {waypoint_number}: {node_id[:15] if is_virtual else node_id}"
            
            print(f"DEBUG: Adding waypoint - node_id={node_id}, is_virtual={is_virtual}")
            
            # Add to sidebar list
            self.sidebar.add_waypoint_to_list(node_id, display_name, pos)
            
            # Add visual marker
            marker = self.map_viewer.add_waypoint_marker(snapped_pos, waypoint_number)
            print(f"DEBUG: Added waypoint marker, total markers: {len(self.map_viewer.waypoint_markers)}")
            
            print(f"Added waypoint {waypoint_number}: {node_id}")

        self.map_viewer.clear_temporary_point()

        # Trigger pathfinding if start and end are set
        if self.start_node and self.end_node:
            self._trigger_pathfinding_with_waypoints()
        else:
            self.map_viewer.clear_path()

    def _add_virtual_node_to_graph(self, virtual_id, u, v, ratio):
        """Add a virtual node to the graph at position ratio along edge u-v"""
        if virtual_id in self.pathfinder.graph:
            return  # Already added
        
        # Get original edge weight
        if not self.pathfinder.graph.has_edge(u, v):
            print(f"Warning: Edge {u}-{v} doesn't exist for virtual node")
            return
        
        original_weight = self.pathfinder.graph[u][v].get('weight', 1.0)
        
        # Add virtual node
        pos = self.node_positions[virtual_id]
        self.pathfinder.graph.add_node(virtual_id, pos=pos)
        
        # Split the edge: u -> virtual -> v
        weight_u_to_virtual = original_weight * ratio
        weight_virtual_to_v = original_weight * (1 - ratio)
        
        # Add edges (bidirectional)
        self.pathfinder.graph.add_edge(u, virtual_id, weight=weight_u_to_virtual)
        self.pathfinder.graph.add_edge(virtual_id, u, weight=weight_u_to_virtual)
        self.pathfinder.graph.add_edge(virtual_id, v, weight=weight_virtual_to_v)
        self.pathfinder.graph.add_edge(v, virtual_id, weight=weight_virtual_to_v)
        
        print(f"Added virtual edges: {u}->{virtual_id}({weight_u_to_virtual:.2f}), {virtual_id}->{v}({weight_virtual_to_v:.2f})")

    def _trigger_pathfinding_with_waypoints(self):
        """Calculate path including waypoints with optional TSP optimization"""
        if not self.start_node or not self.end_node:
            return
        
        if not self.pathfinder:
            QMessageBox.critical(self, "Error", "Pathfinding engine not available.")
            return
        
        # Check if route optimization is enabled
        if self.sidebar.optimize_route_checkbox.isChecked() and len(self.sidebar.waypoints) > 1:
            print("🔄 TSP Route Optimization ENABLED")
            
            # Solve TSP to get optimal waypoint order
            optimal_order = self._solve_tsp_route(
                self.start_node, 
                self.end_node, 
                self.sidebar.waypoints
            )
            
            # Reorder waypoints based on TSP solution
            optimized_waypoints = [self.sidebar.waypoints[i] for i in optimal_order]
            
            print(f"Original order: {[wp['node_id'][:15] + '...' if len(wp['node_id']) > 15 else wp['node_id'] for wp in self.sidebar.waypoints]}")
            print(f"Optimized order: {[wp['node_id'][:15] + '...' if len(wp['node_id']) > 15 else wp['node_id'] for wp in optimized_waypoints]}")
            
            # Update sidebar to show optimized order
            self.sidebar.waypoints = optimized_waypoints
            self.sidebar.waypoints_list.clear()
            for i, wp in enumerate(optimized_waypoints):
                item_text = f"{i + 1}. {wp['name']}"
                self.sidebar.waypoints_list.addItem(item_text)
            
            # Redraw markers with new order
            self.map_viewer.clear_waypoint_markers()
            for i, wp in enumerate(optimized_waypoints):
                pos = QPointF(wp['pos'][0], wp['pos'][1])
                self.map_viewer.add_waypoint_marker(pos, i + 1)
            
            waypoints = optimized_waypoints
        else:
            # Restore original order if optimization was previously enabled
            if len(self.sidebar.waypoints) > 0 and len(self.sidebar.original_waypoint_order) > 0:
                # Check if current order differs from original (means it was optimized)
                current_ids = [wp['node_id'] for wp in self.sidebar.waypoints]
                original_ids = [wp['node_id'] for wp in self.sidebar.original_waypoint_order]
                
                if current_ids != original_ids:
                    print("↩️  Restoring original waypoint order")
                    
                    # Restore original order
                    self.sidebar.waypoints = [wp.copy() for wp in self.sidebar.original_waypoint_order]
                    
                    # Update UI
                    self.sidebar.waypoints_list.clear()
                    for i, wp in enumerate(self.sidebar.waypoints):
                        item_text = f"{i + 1}. {wp['name']}"
                        self.sidebar.waypoints_list.addItem(item_text)
                    
                    # Redraw markers with original order
                    self.map_viewer.clear_waypoint_markers()
                    for i, wp in enumerate(self.sidebar.waypoints):
                        pos = QPointF(wp['pos'][0], wp['pos'][1])
                        self.map_viewer.add_waypoint_marker(pos, i + 1)
            
            print("Following user-defined waypoint order")
            waypoints = self.sidebar.waypoints
        
        # Build route: start → waypoint1 → waypoint2 → ... → end
        route_points = [self.start_node]
        route_points.extend([wp['node_id'] for wp in waypoints])
        route_points.append(self.end_node)
        
        print(f"Finding multi-stop route: {' → '.join([p[:15] + '...' if len(p) > 15 else p for p in route_points])}")
        
        try:
            full_path = []
            total_cost = 0.0
            
            # Calculate path for each segment
            for i in range(len(route_points) - 1):
                segment_start = route_points[i]
                segment_end = route_points[i + 1]
                
                # Check if both nodes are directly connected (on same edge)
                if self.pathfinder.graph.has_edge(segment_start, segment_end):
                    # Direct connection exists
                    segment_path = [segment_start, segment_end]
                    segment_cost = self.pathfinder.graph[segment_start][segment_end].get('weight', 0)
                    print(f"Direct edge: {segment_start[:15]}... → {segment_end[:15]}...")
                else:
                    # Need to find path
                    segment_path = self.pathfinder.find_path(segment_start, segment_end)
                    
                    if not segment_path:
                        if not self._suppress_path_errors:
                            QMessageBox.warning(self, "No Path", 
                                f"No path found between stop {i} and stop {i+1}")
                        self.map_viewer.clear_path()
                        return
                    
                    # Calculate segment cost
                    segment_cost = 0.0
                    has_infinite = False
                    for j in range(len(segment_path) - 1):
                        u, v = segment_path[j], segment_path[j+1]
                        if self.pathfinder.graph.has_edge(u, v):
                            weight = self.pathfinder.graph[u][v].get('weight', 0)
                            if weight == float('inf'):
                                has_infinite = True
                                break
                            segment_cost += weight
                    
                    if has_infinite:
                        QMessageBox.warning(self, "Blocked Path",
                            f"Path blocked between stop {i} and stop {i+1}")
                        self.map_viewer.clear_path()
                        return
                
                total_cost += segment_cost
                
                # Add to full path (avoid duplicates at connection points)
                if i == 0:
                    full_path.extend(segment_path)
                else:
                    full_path.extend(segment_path[1:])  # Skip first node (duplicate)
            
            print(f"✓ Multi-stop path found: {len(full_path)} nodes, total cost: {total_cost:.2f}")
            self.map_viewer.draw_path(full_path, self.node_positions)
            
        except Exception as e:
            print(f"Error during multi-stop pathfinding: {e}")
            if not self._suppress_path_errors:
                QMessageBox.critical(self, "Pathfinding Error", f"An error occurred: {e}")
            self.map_viewer.clear_path()

    def _optimize_route_order(self, route_points):
        """
        Optimize route by checking if waypoints are already on the direct path.
        If waypoint W is on the path from A to B, and we're going A→W→B,
        check if W is actually between A and B or if we need to backtrack.
        """
        if len(route_points) <= 2:
            return route_points
        
        optimized = [route_points[0]]
        
        for i in range(1, len(route_points) - 1):
            prev = route_points[i - 1]
            curr = route_points[i]
            next_point = route_points[i + 1]
            
            # Check if curr is on the direct path from prev to next
            try:
                direct_path = self.pathfinder.find_path(prev, next_point)
                if direct_path and curr in direct_path:
                    # curr is already on the path from prev to next
                    # Check if adding it explicitly causes backtracking
                    path_with_waypoint_1 = self.pathfinder.find_path(prev, curr)
                    path_with_waypoint_2 = self.pathfinder.find_path(curr, next_point)
                    
                    if path_with_waypoint_1 and path_with_waypoint_2:
                        total_nodes_with = len(path_with_waypoint_1) + len(path_with_waypoint_2) - 1
                        total_nodes_direct = len(direct_path)
                        
                        # If going through waypoint doesn't add many extra nodes, keep it
                        if total_nodes_with <= total_nodes_direct * 1.2:  # Allow 20% overhead
                            optimized.append(curr)
                            continue
                    
                    # Otherwise skip this waypoint as it causes backtracking
                    print(f"Skipping waypoint {curr} - would cause backtracking")
                    continue
            except:
                pass
            
            # Keep this waypoint
            optimized.append(curr)
        
        optimized.append(route_points[-1])
        
        if len(optimized) < len(route_points):
            print(f"Route optimized: {len(route_points)} → {len(optimized)} stops")
        
        return optimized
    
    def _solve_tsp_route(self, start, end, waypoints):
        """
        Solve TSP to find optimal order to visit waypoints.
        Returns optimized list of waypoint indices.
        Uses nearest neighbor heuristic for reasonable performance.
        """
        if not waypoints:
            return []
        
        # Build distance matrix
        all_points = [start] + [wp['node_id'] for wp in waypoints] + [end]
        n = len(all_points)
        
        # Calculate all pairwise distances using A* path costs
        print(f"Calculating distance matrix for {n} points...")
        dist_matrix = {}
        
        for i in range(n):
            for j in range(n):
                if i == j:
                    dist_matrix[(i, j)] = 0
                    continue
                
                # Try to use cached distance or calculate
                key = (all_points[i], all_points[j])
                
                # Check direct edge first
                if self.pathfinder.graph.has_edge(all_points[i], all_points[j]):
                    dist_matrix[(i, j)] = self.pathfinder.graph[all_points[i]][all_points[j]].get('weight', float('inf'))
                else:
                    # Calculate path
                    path = self.pathfinder.find_path(all_points[i], all_points[j])
                    if path:
                        cost = 0.0
                        for k in range(len(path) - 1):
                            u, v = path[k], path[k + 1]
                            if self.pathfinder.graph.has_edge(u, v):
                                weight = self.pathfinder.graph[u][v].get('weight', 0)
                                if weight == float('inf'):
                                    cost = float('inf')
                                    break
                                cost += weight
                        dist_matrix[(i, j)] = cost
                    else:
                        dist_matrix[(i, j)] = float('inf')
        
        # Solve TSP using nearest neighbor heuristic
        # Start must be first (index 0), end must be last (index n-1)
        # We need to find optimal order for waypoints (indices 1 to n-2)
        
        waypoint_indices = list(range(1, n - 1))  # Indices of waypoints only
        
        if len(waypoint_indices) <= 1:
            return waypoint_indices  # No optimization needed
        
        # For small number of waypoints, try all permutations (brute force)
        if len(waypoint_indices) <= 7:  # 7! = 5040 permutations (manageable)
            print(f"Using brute force TSP for {len(waypoint_indices)} waypoints...")
            from itertools import permutations
            
            best_order = None
            best_cost = float('inf')
            
            for perm in permutations(waypoint_indices):
                # Calculate total cost: start -> perm[0] -> perm[1] -> ... -> perm[-1] -> end
                route = [0] + list(perm) + [n - 1]
                cost = sum(dist_matrix[(route[i], route[i + 1])] for i in range(len(route) - 1))
                
                if cost < best_cost:
                    best_cost = cost
                    best_order = list(perm)
            
            print(f"Brute force TSP found route with cost: {best_cost:.2f}")
            # Convert back to 0-indexed for waypoints array
            return [idx - 1 for idx in best_order]
        
        else:
            # For larger number, use nearest neighbor heuristic
            print(f"Using nearest neighbor heuristic for {len(waypoint_indices)} waypoints...")
            
            unvisited = set(waypoint_indices)
            current = 0  # Start from start point
            route = []
            
            while unvisited:
                # Find nearest unvisited waypoint
                nearest = min(unvisited, key=lambda x: dist_matrix[(current, x)])
                route.append(nearest)
                unvisited.remove(nearest)
                current = nearest
            
            total_cost = sum(dist_matrix[(route[i] if i > 0 else 0, route[i + 1] if i + 1 < len(route) else n - 1)] 
                            for i in range(-1, len(route)))
            print(f"Nearest neighbor TSP found route with cost: {total_cost:.2f}")
            
            # Convert back to 0-indexed for waypoints array
            return [idx - 1 for idx in route]

    def _trigger_pathfinding(self):
        """Initiate pathfinding between selected points (with or without waypoints)."""
        # If waypoints exist, use multi-stop routing
        if self.sidebar.waypoints:
            self._trigger_pathfinding_with_waypoints()
            return
        
        # Otherwise, simple start-to-end routing
        if self.start_node is None or self.end_node is None:
            self.map_viewer.clear_path()
            return

        if not self.pathfinder:
            if not self._suppress_path_errors:
                QMessageBox.critical(self, "Error", "Pathfinding engine not available.")
            return

        print(f"Finding path from {self.start_node} to {self.end_node}...")
        
        try:
            path_nodes = self.pathfinder.find_path(self.start_node, self.end_node)

            if path_nodes:
                # Calculate path cost
                cost = 0.0
                path_has_infinite_weight = False
                
                if self.pathfinder.graph and len(path_nodes) > 1:
                    for i in range(len(path_nodes) - 1):
                        u, v = path_nodes[i], path_nodes[i+1]
                        if self.pathfinder.graph.has_edge(u, v):
                            edge_weight = self.pathfinder.graph[u][v].get('weight', 0)
                            if edge_weight == float('inf'):
                                path_has_infinite_weight = True
                                break
                            cost += edge_weight
                        else:
                            cost = float('inf')
                            path_has_infinite_weight = True
                            break
                
                # Don't draw path if it contains blocked edges
                if path_has_infinite_weight or cost == float('inf'):
                    print(f"Path contains blocked edges (cost: {cost}). Not displaying.")
                    if not self._suppress_path_errors:
                        QMessageBox.warning(self, "No Valid Path", 
                            f"The path between {self.start_node} and {self.end_node} is blocked.\n\n"
                            f"All available routes contain blocked roads.")
                    self.map_viewer.clear_path()
                else:
                    print(f"Path found: {len(path_nodes)} nodes, cost: {cost:.2f}")
                    self.map_viewer.draw_path(path_nodes, self.node_positions)
            else:
                print("No path found.")
                if not self._suppress_path_errors:
                    QMessageBox.information(self, "Pathfinding", 
                        f"No path found between {self.start_node} and {self.end_node}.")
                self.map_viewer.clear_path()
        except Exception as e:
            print(f"Error during pathfinding: {e}")
            if not self._suppress_path_errors:
                QMessageBox.critical(self, "Pathfinding Error", f"An error occurred: {e}")
            self.map_viewer.clear_path()

    def closeEvent(self, event):
        """Ensure timers are stopped when window closes."""
        print("Closing application, stopping timers...")
        self.stop_all_traffic_light_timers()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())