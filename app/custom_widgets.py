import os
from PyQt6.QtWidgets import QPushButton

# Function to load stylesheet (can be kept here or in a utility module)
def load_stylesheet(file_path):
    try:
        with open(file_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Warning: Stylesheet file not found at {file_path}")
        return ""

class FindPathButton(QPushButton):
    def __init__(self, text="Find Path", parent=None):
        super().__init__(text, parent)
        self._apply_style()

    def _apply_style(self):
        # Load style from the .qss file
        # Adjust the path relative to this new file's location
        style_path = os.path.join(os.path.dirname(__file__), '..', 'styles', 'button_style.qss')
        button_style = load_stylesheet(style_path)
        if button_style:
            self.setStyleSheet(button_style)
        else:
            # Optional: Apply a default fallback style if the file is missing
            self.setStyleSheet("""
                QPushButton {
                    background-color: #CCCCCC;
                    padding: 8px 15px;
                    border-radius: 4px;
                }
            """)

# You can add other custom widgets here later