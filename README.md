# 🗺️ Offline Pathfinding Application

A powerful PyQt6-based pathfinding application with interactive map visualization, multiple routing algorithms, and real-time traffic simulation. Perfect for urban planning, delivery route optimization, and transportation analysis.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.0+-green.svg)
![NetworkX](https://img.shields.io/badge/NetworkX-2.8+-orange.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## ✨ Features

### 🎯 Core Pathfinding
- **A* Algorithm**: Efficient shortest path finding with Euclidean distance heuristic
- **Multi-Stop Routing**: Support for unlimited waypoints in a single route
- **TSP Optimization**: Traveling Salesman Problem solver to optimize waypoint order
  - Brute force for ≤7 waypoints (guaranteed optimal solution)
  - Nearest neighbor heuristic for >7 waypoints (fast approximation)
- **Smart Edge Detection**: Click anywhere on roads, not just at intersections
- **Virtual Nodes**: Place waypoints at any position along edges

### 🖱️ Interactive Map Interface
- **Visual Node Selection**: Click directly on the map to select start/end points
- **Edge Snapping**: Automatically snaps selections to nearest nodes or edges (25px threshold)
- **Virtual Nodes**: Creates temporary nodes on edges for precise waypoint placement
- **Zoom & Pan**: Smooth map navigation with mouse wheel zoom (1.15x factor)
- **Path Visualization**: Clear magenta path with 4px width
- **Real-time Updates**: Path recalculates automatically when effects change

### 🚦 Dynamic Effects & Obstacles

#### 1. Traffic Jams 🚗
- Draw traffic zones by clicking and dragging on the map
- Three intensity levels:
  - **Light**: +50 weight penalty
  - **Moderate**: +100 weight penalty
  - **Heavy**: +200 weight penalty
- Affects all edges within 20px of the drawn line
- Visual: Red solid line (2px width)

#### 2. Road Blocks 🚧
- Draw blocked road segments
- Sets affected edges to infinite weight (impassable)
- Affects edges within 20px threshold
- Visual: Black solid line (3px width)
- Forces complete route recalculation

#### 3. Traffic Lights 🚦
- Place functional traffic lights with countdown timers
- Configurable durations:
  - **Red**: 1-300 seconds (default: 30s)
  - **Yellow**: 1-60 seconds (default: 5s)
  - **Green**: 1-300 seconds (default: 25s)
- **Dynamic Weight Calculation**:
  - Red: 3.33 penalty units/second remaining
  - Yellow: 10.0 penalty units/second remaining
  - Green: 0.04 penalty units/second remaining
- Real-time state changes with countdown display
- Visual: Icon (32x32px) with orange effect line

### 📍 Waypoint Management
- Add unlimited waypoints via map clicks
- Visual numbered markers (orange circles with white text)
- Reorder waypoints with ↑ Up / ↓ Down buttons
- Remove individual waypoints or clear all
- Automatic path recalculation on changes
- Preserved through optimization cycles

### 🔍 Search & Location
- Searchable dropdown for start/end points
- Support for:
  - **Nodes**: Graph intersection points
  - **Special Places**: Named locations (from database)
- Case-insensitive auto-complete
- Switch between search and map selection modes

### ⌨️ Keyboard Shortcuts
- **Escape**: Cancel current drawing action
- **Shift + Click**: Remove effect at cursor position

## 🚀 Getting Started

### Prerequisites

```bash
Python 3.8 or higher
PyQt6 >= 6.0.0
NetworkX >= 2.8.0
SQLite3 (included with Python)
```

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/toantd181/Path-Finding---Project-1---HUST
cd pathfinding-app
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Prepare your data**
   - Place your map image in `app/assets/map.png`
   - Create graph database at `app/data/graph.db` (see schema below)
   - Add traffic light icon: `app/assets/icons/traffic-light.png` (32x32px)
   - Add traffic jam icon: `app/assets/icons/traffic-jam.png`
   - Add block icon: `app/assets/icons/block.png`

4. **Run the application**
```bash
python -m app.main
```

## 📁 Project Structure

```
pathfinding/
├── app/
│   ├── __init__.py
│   ├── main.py                      # Application entry point
│   ├── main_window.py               # Main window logic (1000+ lines)
│   ├── map_viewer.py                # Interactive map widget
│   ├── sidebar.py                   # Control panel UI
│   ├── pathfinding.py               # A* algorithm & graph management
│   ├── custom_widgets.py            # Custom buttons (FindPathButton)
│   │
│   ├── assets/
│   │   ├── map.png                 # Background map image
│   │   └── icons/
│   │       ├── traffic-jam.png     # Traffic tool icon
│   │       ├── block.png           # Block tool icon
│   │       └── traffic-light.png   # Traffic light icon (32x32)
│   │
│   ├── data/
│   │   └── graph.db                # SQLite graph database
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── traffic.py              # Traffic jam tool logic
│   │   ├── block.py                # Block way tool logic
│   │   ├── traffic_light_tool.py   # Traffic light state machine
│   │   ├── rain.py                 # Rain tool (future feature)
│   │   └── car_mode_tool.py        # Car mode (future feature)
│   │
│   └── styles/
│       └── button_style.qss        # Qt stylesheets
│
├── requirements.txt
├── README.md
├── .gitignore
└── LICENSE
```

## 💾 Database Schema

### Required Tables

#### Nodes Table
Stores graph vertices with pixel coordinates.

```sql
CREATE TABLE nodes (
    name TEXT PRIMARY KEY,      -- Unique node identifier (e.g., "N123abc")
    x REAL NOT NULL,           -- X coordinate in pixels
    y REAL NOT NULL            -- Y coordinate in pixels
);
```

**Example Data:**
```sql
INSERT INTO nodes VALUES ('N354057', 485.2, 320.5);
INSERT INTO nodes VALUES ('Nb15b5c', 520.8, 340.2);
```

#### Edges Table
Stores graph edges (directed) with weights.

```sql
CREATE TABLE edges (
    node_from TEXT NOT NULL,   -- Source node ID
    node_to TEXT NOT NULL,     -- Destination node ID
    weight REAL NOT NULL,      -- Edge cost (distance/time)
    FOREIGN KEY (node_from) REFERENCES nodes(name),
    FOREIGN KEY (node_to) REFERENCES nodes(name)
);
```

**Example Data:**
```sql
INSERT INTO edges VALUES ('N354057', 'Nb15b5c', 1.5);
INSERT INTO edges VALUES ('Nb15b5c', 'N354057', 1.5);  -- Bidirectional
```

#### Special Places Table (Optional)
Named locations for search functionality.

```sql
CREATE TABLE special_places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    custom_name TEXT NOT NULL,  -- Display name (e.g., "Hanoi University")
    x REAL NOT NULL,           -- X coordinate in pixels
    y REAL NOT NULL            -- Y coordinate in pixels
);
```

**Example Data:**
```sql
INSERT INTO special_places (custom_name, x, y) 
VALUES ('Thu Le Park', 400.0, 300.0);
```

### Creating the Database

```python
import sqlite3

conn = sqlite3.connect('app/data/graph.db')
cursor = conn.cursor()

# Create tables
cursor.executescript('''
    CREATE TABLE nodes (
        name TEXT PRIMARY KEY,
        x REAL NOT NULL,
        y REAL NOT NULL
    );
    
    CREATE TABLE edges (
        node_from TEXT NOT NULL,
        node_to TEXT NOT NULL,
        weight REAL NOT NULL,
        FOREIGN KEY (node_from) REFERENCES nodes(name),
        FOREIGN KEY (node_to) REFERENCES nodes(name)
    );
    
    CREATE TABLE special_places (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        custom_name TEXT NOT NULL,
        x REAL NOT NULL,
        y REAL NOT NULL
    );
''')

conn.commit()
conn.close()
```

## 🎮 Usage Guide

### Basic Pathfinding

1. **Set Start Point** (3 methods)
   - Click "Set Start" button → Click on map
   - Use search dropdown → Select location
   - Click "Use Map" button (if previously set)

2. **Set End Point** (3 methods)
   - Click "Set End" button → Click on map
   - Use search dropdown → Select location
   - Click "Use Map" button (if previously set)

3. **Find Path**
   - Automatic calculation when both points are set
   - Or click "Find Path" button
   - View calculated route in magenta

### Multi-Stop Routing

#### Adding Waypoints
1. Click "+ Add Stop" button (turns orange when active)
2. Click on map to place waypoints
3. Waypoints are visited in order added
4. Each waypoint shows a numbered marker (1, 2, 3...)

#### Optimizing Route (TSP)
1. Add 2+ waypoints
2. Check "🔄 Optimize Route Order (TSP)"
3. Application finds optimal waypoint order
4. Waypoint list updates to show new order
5. Uncheck to restore manual order

**Algorithm Details:**
- ≤7 waypoints: Brute force (tries all permutations)
- >7 waypoints: Nearest neighbor heuristic
- Preserves start and end positions
- Calculates A* path costs for optimization

#### Managing Waypoints
- **Reorder**: Select waypoint → Use ↑/↓ buttons
- **Remove**: Select waypoint → Click "− Remove"
- **Clear All**: Click "Clear All" button
- Virtual nodes cleaned up automatically

### Adding Effects

#### Traffic Jam
1. Click "Draw Traffic Zone" button
2. Select intensity from dropdown:
   - Light (+50)
   - Moderate (+100)
   - Heavy (+200)
3. Click and drag on map to draw affected area
4. Release mouse to apply effect

#### Road Block
1. Click "Draw Block" button
2. Click and drag to draw blocked segment
3. Release to apply blockage
4. Path automatically avoids blocked areas

#### Traffic Light
1. Click "Place Traffic Light" button
2. Click to place icon
3. Drag to define effect area (orange line)
4. Release to place
5. Configure durations before placing:
   - Red: 1-300 seconds
   - Yellow: 1-60 seconds
   - Green: 1-300 seconds

**Traffic Light Behavior:**
- Cycles: Red → Green → Yellow → Red
- Countdown timer shows remaining seconds
- Text color matches current state
- Weight penalty decreases as time passes

### Removing Effects

- **Single Effect**: Hold Shift + Click on effect
- **By Type**:
  - "Clear All Traffic" button
  - "Clear All Blocks" button
  - "Clear All Lights" button
- **All Effects**: "🗑️ Clear ALL Effects" button (purple)

## ⚙️ Configuration & Tuning

### Effect Detection
```python
# In main_window.py
self._effect_application_threshold = 20  # pixels
```
Edges within this distance are affected by drawn effects.

### Traffic Light Penalty Calculation
```python
# In traffic_light_tool.py
penalty_rate = {
    "RED": 3.33,    # penalty units per second
    "YELLOW": 10.0,
    "GREEN": 0.04
}
modified_penalty = penalty_rate * remaining_time_seconds
```

### Virtual Node Snapping
```python
# In main_window.py
NODE_SNAP_THRESHOLD = 15  # pixels (15^2 = 225)
EDGE_SNAP_THRESHOLD = 25  # pixels
EDGE_RATIO_MIN = 0.05     # Don't snap near endpoints
EDGE_RATIO_MAX = 0.95
```

### Zoom Settings
```python
# In map_viewer.py
zoom_in_factor = 1.15
zoom_out_factor = 1 / 1.15
```

## 🏗️ Architecture

### Virtual Node System
When you click on an edge (not near a node):
1. Finds nearest edge within 25px
2. Calculates projection point on edge
3. Creates virtual node: `VIRTUAL_{u}_{v}_{ratio:.3f}`
4. Splits edge proportionally:
   - `u → virtual`: `original_weight * ratio`
   - `virtual → v`: `original_weight * (1-ratio)`
5. Adds bidirectional edges to graph
6. Cleans up when waypoint removed (preserves start/end virtuals)

### Path Recalculation Flow
```
User Action → Effect Applied → Reset Graph Weights → 
Apply All Effects → Recalculate Path → Update Display
```

### TSP Algorithm
```python
# Pseudocode
if waypoints <= 7:
    # Brute force
    for each permutation:
        calculate total A* cost
        keep best
else:
    # Nearest neighbor
    current = start
    while unvisited waypoints:
        next = nearest unvisited
        move to next
```

## 🐛 Troubleshooting

### "Node not found in graph"
**Cause**: Virtual node removed prematurely or database mismatch

**Solution**:
- Clear all waypoints and restart
- Check database integrity
- Ensure virtual nodes excluded when clearing waypoints

### "No path found"
**Causes**:
- Start/end in different graph components
- All paths blocked by effects
- Invalid node coordinates

**Solutions**:
- Verify graph connectivity in database
- Remove blocking effects
- Check start/end node validity

### Traffic light not updating
**Cause**: Missing icon file or timer not starting

**Solution**:
```bash
# Verify icon exists
ls app/assets/icons/traffic-light.png

# Check console for errors
# Look for: "Warning: Could not load traffic light icon"
```

### Path ignores traffic effects
**Cause**: Effects not recalculated or threshold too small

**Solution**:
```python
# Increase detection threshold
self._effect_application_threshold = 30  # from 20
```

### Virtual nodes persisting
**Cause**: Start/end points are virtual but not excluded

**Solution**: Use "Clear All Waypoints" - automatically preserves start/end virtual nodes

### Memory leaks with traffic lights
**Cause**: Timers not stopped

**Solution**: Application automatically stops timers on close. Check console for:
```
Closing application, stopping timers...
```

## 📊 Performance

### Pathfinding Speed
- **Simple A***: <10ms for 1000 nodes
- **3 waypoints**: <50ms
- **7 waypoints (TSP brute force)**: <500ms
- **15 waypoints (TSP heuristic)**: <200ms

### Memory Usage
- Base: ~50MB
- Per 1000 nodes: +5MB
- Per traffic light: +0.5MB (timers)
- Per virtual node: +1KB

### Optimization Tips
1. Keep waypoints ≤7 for optimal TSP
2. Limit virtual nodes by clicking near existing nodes
3. Clear effects when not needed
4. Use reasonable effect detection thresholds

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

- [ ] Add more traffic light states (arrow lights)
- [ ] Implement rain weather effects
- [ ] Add car mode for single-edge blocking
- [ ] Export routes to GPX/KML
- [ ] Historical traffic data visualization
- [ ] Multi-vehicle routing
- [ ] Time-dependent routing
- [ ] Route profiles (fastest, shortest, scenic)

**Contribution Steps:**
1. Fork the project
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **NetworkX**: Graph algorithms library
- **PyQt6**: Modern GUI framework
- **A* Algorithm**: Hart, Nilsson, and Raphael (1968)
- **OpenStreetMap**: For map inspiration
- Community contributors

## 📧 Contact

Toàn TD
Email: toan.tranduc1801@gmail.com

Project Link: [https://github.com/toantd181/Path-Finding---Project-1---HUST](https://github.com/toantd181/Path-Finding---Project-1---HUST)

## 📚 Additional Resources

- [NetworkX Documentation](https://networkx.org/documentation/stable/)
- [PyQt6 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [A* Pathfinding Tutorial](https://www.redblobgames.com/pathfinding/a-star/introduction.html)
- [TSP Algorithms](https://en.wikipedia.org/wiki/Travelling_salesman_problem)

---

**Built with ❤️ for urban planning and transportation optimization**

**Note**: This application is designed for offline use and does not require an internet connection once set up. All pathfinding computations are performed locally using the provided graph database.