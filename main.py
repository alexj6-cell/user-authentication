import sys
import subprocess
import os
import requests  # Ensure requests is imported
import re  # Added for regex operations if needed

from PyQt6.QtCore import (
    Qt, QSettings, QTimer, QRect, pyqtSignal, QRegularExpression
)
from PyQt6.QtGui import (
    QIcon, QAction, QPixmap, QRegularExpressionValidator
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDialog,
    QSystemTrayIcon, QMenu, QLineEdit, QPushButton, QLabel,
    QVBoxLayout, QWidget, QMessageBox
)

########################################################################
# resource_path function for PyInstaller
########################################################################
def resource_path(relative_path):
    """Return the absolute path to the resource, works for dev and for Briefcase."""
    try:
        # Briefcase uses 'Resources' directory inside the app bundle
        base_path = sys._MEIPASS
    except AttributeError:
        # Not bundled, use current directory
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

##################################################
# User Validation via API
##################################################
def user_exists_in_db(user_id: str) -> tuple:
    """
    Checks if a user exists by sending a GET request to the validation API.
    
    Args:
        user_id (str): The username to validate.
    
    Returns:
        tuple: (bool, str) where bool indicates existence and str is fullname or error message.
    """
    base_url = "https://app.softage.net/TestingSrot/api-user-validity/"
    params = {"username": user_id}
    
    try:
        response = requests.get(base_url, params=params, timeout=5)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)

        data = response.json()
        
        # Debug: Print the response data
        print(f"Response from server: {data}")

        # Check if the response indicates success
        if data.get("status") == "success":
            fullname = data.get("fullname", "N/A")
            return True, fullname
        else:
            return False, data.get("message", "Unknown error occurred.")

    except requests.exceptions.HTTPError as http_err:
        # Handle specific HTTP errors
        if http_err.response.status_code == 404:
            return False, "User not found."
        elif http_err.response.status_code in [401, 403]:
            return False, "Unauthorized access."
        else:
            return False, "An error occurred while verifying the user."
    except requests.exceptions.RequestException:
        # Handle other exceptions like network issues
        return False, "Unable to connect to the server. Please try again later."

##################################################
# Task Assignment Validation via API
##################################################

def check_task_assignment(user_id: str, task_id: str) -> tuple:
    """
    Checks if a task is assigned to a user by sending a GET request to the check_task_assignment API.
    
    Args:
        user_id (str): The username.
        task_id (str): The task ID.
    
    Returns:
        tuple: (bool, str) where bool indicates validity and str is an error message or success message.
    """
    check_url = "https://app.softage.net/TestingSrot/check_task_assignment/"
    params = {"username": user_id, "T_ID": task_id}
    
    try:
        resp = requests.get(check_url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        # Debug: Print the response data
        print(f"Task Assignment Response: {data}")

        # Updated Validation Logic
        if data.get("status") == "success" and not data.get("error") and data.get("is_assigned") == True:
            return True, "Task assignment is valid. Proceeding with recording."
        else:
            # Construct a detailed error message based on the response
            if not data.get("is_assigned", False):
                error_message = data.get("message", "Task is not assigned to the user.")
            else:
                error_message = data.get("message", "Task assignment check failed or invalid response.")
            return False, error_message

    except requests.exceptions.HTTPError as http_err:
        # Handle specific HTTP errors
        if http_err.response.status_code == 404:
            return False, "Task not found."
        elif http_err.response.status_code in [401, 403]:
            return False, "Unauthorized access."
        else:
            return False, "An error occurred while verifying task assignment."
    except requests.exceptions.RequestException:
        # Handle other exceptions like network issues
        return False, "Unable to connect to the server. Please try again later."


##################################################
# Countdown / Timer Window
##################################################
class TimerWindow(QMainWindow):
    countdown_finished = pyqtSignal()  # emitted when countdown completes

    def __init__(self, countdown_seconds=3, message="Recording starts in"):
        super().__init__()
        self.countdown_seconds = countdown_seconds
        self.message = message
        self.initUI()

    def initUI(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Decide on window size
        window_width = 720
        window_height = 250
        self.setFixedSize(window_width, window_height)

        # Position near top-right
        screen_geo = QApplication.primaryScreen().availableGeometry()
        x = screen_geo.right() - window_width - 20
        y = screen_geo.top() + 60
        self.setGeometry(x, y, window_width, window_height)

        self.timer_label = QLabel(self)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setStyleSheet("""
            color: white;
            font-size: 48px;
            font-weight: bold;
            background-color: rgba(0, 0, 0, 150);
            padding: 20px;
            border-radius: 20px;
        """)
        self.setCentralWidget(self.timer_label)

        self.update_timer_display()
        self.start_countdown()

    def start_countdown(self):
        """Start a 1-second timer to decrement the countdown."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)

    def update_timer_display(self):
        self.timer_label.setText(f"{self.message}: {self.countdown_seconds} seconds")

    def update_timer(self):
        if self.countdown_seconds > 1:
            self.countdown_seconds -= 1
            self.update_timer_display()
        else:
            self.timer.stop()
            self.display_go_message()

    def display_go_message(self):
        self.timer_label.setText("Go!")
        self.timer_label.setStyleSheet("""
            color: #00FF00;
            font-size: 48px;
            font-weight: bold;
            background-color: rgba(0, 0, 0, 150);
            padding: 20px;
            border-radius: 20px;
        """)
        QTimer.singleShot(1000, self.finish_countdown)

    def finish_countdown(self):
        self.close()
        self.countdown_finished.emit()

##################################################
# Login Window
##################################################
class LoginWindow(QMainWindow):
    """
    Lets user enter user_id (username). If valid via API, save in QSettings and open TaskWindow.
    Otherwise, show error.
    """
    def __init__(self):
        super().__init__()
        # Remove window decorations and fix size
        self.setWindowTitle("Login - SrotApp")
        self.setFixedSize(400, 450)
        self.setStyleSheet("background-color: #f0f0f0;")  # Light gray background

        # Position near top-right
        screen_geo = QApplication.primaryScreen().availableGeometry()
        x = screen_geo.right() - 400 - 20
        y = screen_geo.top() + 60
        self.setGeometry(x, y, 400, 450)

        # Main widget + layout
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        # Slightly reduce spacing + margins
        layout.setSpacing(8)                      
        layout.setContentsMargins(30, 20, 30, 20)

        # Logo (slightly larger than before)
        self.logo_label = QLabel(self)
        pixmap = QPixmap(resource_path("srot_logo.png"))
        if pixmap.isNull():
            print("Warning: Logo file not found!")
        else:
            # Scale the logo to around 140×140
            pixmap = pixmap.scaled(
                140, 140,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.logo_label.setPixmap(pixmap)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.logo_label)

        # Label for User ID
        self.label = QLabel("Enter your User ID", self)
        self.label.setStyleSheet("color: black; font-size: 16px;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        # User ID Input
        self.user_id_input = QLineEdit(self)
        self.user_id_input.setStyleSheet(
            "background-color: white; color: black; font-size: 14px;"
            "padding: 5px; border-radius: 5px;"
        )
        layout.addWidget(self.user_id_input)

        # Login button (Saffron)
        self.login_button = QPushButton("Login", self)
        self.login_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #FF671F; color: white; font-size: 16px;"
            "  border: none; padding: 8px; border-radius: 5px;"
            "}"
            "QPushButton:hover { background-color: #E65A1A; }"
        )
        self.login_button.clicked.connect(self.on_login_clicked)
        layout.addWidget(self.login_button)

        # Quit button (Green)
        self.quit_button = QPushButton("Quit", self)
        self.quit_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #046A38; color: white; font-size: 16px;"
            "  border: none; padding: 8px; border-radius: 5px;"
            "}"
            "QPushButton:hover { background-color: #035B30; }"
        )
        self.quit_button.clicked.connect(lambda: QApplication.quit())
        layout.addWidget(self.quit_button)

        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def on_login_clicked(self):
        user_id = self.user_id_input.text().strip()
        if not user_id:
            QMessageBox.warning(self, "Error", "User ID cannot be empty.")
            return

        # Validate user via API
        exists, result = user_exists_in_db(user_id)
        
        if exists:
            fullname = result  # Assuming 'result' contains fullname
            # Save user_id and fullname in QSettings
            settings = QSettings("MyCompany", "SrotApp")
            settings.setValue("username", user_id)
            settings.setValue("fullname", fullname)

            # Show TaskWindow
            self.task_window = TaskWindow()
            self.task_window.show()
            self.hide()
        else:
            # 'result' contains the error message
            QMessageBox.warning(self, "Invalid", result)

##################################################
# Task Window
##################################################
class TaskWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Frameless, fixed size
        self.setWindowTitle("Task Management - SrotApp")

        self.setFixedSize(400, 450)
        self.setStyleSheet("background-color: #f0f0f0;")  # Light gray background

        # Position near top-right
        screen_geo = QApplication.primaryScreen().availableGeometry()
        x = screen_geo.right() - 400 - 20
        y = screen_geo.top() + 60
        self.setGeometry(x, y, 400, 450)

        # Main layout
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 20, 30, 20)

        # Logo
        self.logo_label = QLabel(self)
        pixmap = QPixmap(resource_path("srot_logo.png"))
        if pixmap.isNull():
            print("Warning: Logo file not found!")
        else:
            self.logo_label.setPixmap(
                pixmap.scaled(
                    120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.logo_label)

        # Show user ID and fullname at the top
        settings = QSettings("MyCompany", "SrotApp")
        current_user = settings.value("username", "")
        fullname = settings.value("fullname", "User")
        user_label = QLabel(f"Welcome, {fullname} ({current_user})")
        user_label.setStyleSheet("color: black; font-size: 16px;")
        user_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(user_label)

        # Label for Task ID
        self.label = QLabel("Enter Task ID (10 chars):", self)
        self.label.setStyleSheet("color: black; font-size: 16px;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        # Task ID input
        self.task_id_input = QLineEdit(self)
        self.task_id_input.setStyleSheet(
            "background-color: white; color: black; font-size: 14px;"
            "padding: 5px; border-radius: 5px;"
        )
        validator = QRegularExpressionValidator(QRegularExpression(r"^[A-Za-z0-9]{0,10}$"))
        self.task_id_input.setValidator(validator)

        # Convert to uppercase when user types
        self.task_id_input.textChanged.connect(self.convert_to_uppercase)

        layout.addWidget(self.task_id_input)

        # Start Recording button (Saffron)
        self.start_button = QPushButton("Start Recording", self)
        self.start_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #FF671F; color: white; font-size: 16px;"
            "  border: none; padding: 8px; border-radius: 5px;"
            "}"
            "QPushButton:hover { background-color: #E65A1A; }"
        )
        self.start_button.clicked.connect(self.on_start_clicked)
        layout.addWidget(self.start_button)

        # Logout button (White with Black Text)
        self.logout_button = QPushButton("Logout", self)
        self.logout_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #FFFFFF; color: black; font-size: 16px;"
            "  border: 1px solid black; padding: 8px; border-radius: 5px;"
            "}"
            "QPushButton:hover { background-color: #E0E0E0; }"
        )
        self.logout_button.clicked.connect(self.on_logout_clicked)
        layout.addWidget(self.logout_button)

        # Quit button (Green)
        self.quit_button = QPushButton("Quit", self)
        self.quit_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #046A38; color: white; font-size: 16px;"
            "  border: none; padding: 8px; border-radius: 5px;"
            "}"
            "QPushButton:hover { background-color: #035B30; }"
        )
        self.quit_button.clicked.connect(lambda: QApplication.quit())
        layout.addWidget(self.quit_button)

        self.setCentralWidget(widget)

    def convert_to_uppercase(self, text: str):
        """
        Convert user input to uppercase in the Task ID field.
        """
        self.task_id_input.blockSignals(True)  # Temporarily block signals to avoid recursion
        self.task_id_input.setText(text.upper())
        self.task_id_input.blockSignals(False)

    def on_start_clicked(self):
        task_id = self.task_id_input.text().strip()
        if len(task_id) != 10:
            QMessageBox.warning(self, "Invalid ID", "Task ID must be exactly 10 alphanumeric characters.")
            return

        # Retrieve current user_id
        settings = QSettings("MyCompany", "SrotApp")
        user_id = settings.value("username", "")
        if not user_id:
            QMessageBox.critical(self, "Error", "User ID not found. Please login again.")
            return

        # ----------------- Validate Task Assignment via API -----------------
        valid, message = check_task_assignment(user_id, task_id)
        if valid:
            # Proceed with recording
            print(message)  # For debugging purposes
            # Hide this Task window
            self.hide()

            # Show countdown window before actually starting the recording
            self.timer_window = TimerWindow(3, "Recording starts in")
            self.timer_window.countdown_finished.connect(lambda: self.start_recording_script(task_id))
            self.timer_window.show()
        else:
            # Show error message box and do not proceed with recording
            QMessageBox.critical(self, "Invalid Task Assignment", message)
            # Optionally, you can also print the error for debugging
            print(f"Task assignment invalid: {message}")

    def start_recording_script(self, task_id):
        """
        Launch the recording script (Record_Mac.py) with the given task ID.
        """
        # Example snippet inside on_start_clicked or wherever you're launching Record_Mac.py
        script_path = resource_path("Record_Mac.py")
        if not os.path.exists(script_path):
            print(f"Error: {script_path} does not exist.")
            QMessageBox.critical(self, "Error", "Recording script not found.")
            return

        # Retrieve the username from QSettings (or however you stored it)
        settings = QSettings("MyCompany", "SrotApp")
        user_id = settings.value("username", "")

        # Launch Record_Mac with 2 arguments: task_id and username
        try:
            subprocess.Popen([sys.executable, script_path, task_id, user_id])
            print(f"Recording started for Task ID: {task_id} by User ID: {user_id}")
        except Exception as e:
            print(f"Failed to start recording script: {e}")
            QMessageBox.critical(self, "Error", "Failed to start recording.")

    def on_logout_clicked(self):
        """
        Clear stored username and return to login window.
        """
        settings = QSettings("MyCompany", "SrotApp")
        settings.remove("username")
        settings.remove("fullname")

        # Show login window
        self.login_window = LoginWindow()
        self.login_window.show()

        # Close this task window
        self.close()

##################################################
# Main entry point
##################################################
def main():
    app = QApplication(sys.argv)

    # Optional system tray icon
    tray_icon = QSystemTrayIcon(QIcon(resource_path("srot_logo.png")), parent=app)
    tray_menu = QMenu()
    quit_action = QAction("Quit", tray_icon)
    quit_action.triggered.connect(app.quit)
    tray_menu.addAction(quit_action)
    tray_icon.setContextMenu(tray_menu)
    tray_icon.show()

    # Check if we already have a user in QSettings
    settings = QSettings("MyCompany", "SrotApp")
    saved_user = settings.value("username", "")
    saved_fullname = settings.value("fullname", "")

    if saved_user:
        # If we already have a user, go directly to TaskWindow
        task_window = TaskWindow()
        task_window.show()
    else:
        # Otherwise, show login
        login_window = LoginWindow()
        login_window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
