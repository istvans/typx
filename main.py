# -*- coding: utf-8 -*-
from enum import Enum
from multiprocessing import Process, Pipe
import os
import sys

from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QVBoxLayout
from PySide2.QtCore import QFile, QTimer, Qt, QObject

################################### COMMS ######################################

class Message(object):

    def __repr__(self):
        """Return a unique & human readable string representation"""
        return "%s(%r)" % (self.__class__, self.__dict__)


class Exit(Message):
    pass


class Main(Message):
    pass


class Input(Message):
    pass


class Start(Message):

    def __init__(self, user_name):
        self.user_name = user_name

#################################### GUI #######################################

class OkDialog(QDialog):
    def __init__(self, title, message, parent=None):
        super(OkDialog, self).__init__(parent)
        self.setWindowTitle(title)
        self.message = QLabel(message)
        self.button_box = QDialogButtonBox(self)
        self.button_box.setOrientation(Qt.Orientation.Horizontal)
        self.button_box.setStandardButtons(QDialogButtonBox.Ok)
        self.button_box.accepted.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self.message)
        layout.addWidget(self.button_box)

        self.setLayout(layout)


class Gui(QObject):
    def __init__(self, pipe_gui_end, parent=None):
        super(Gui, self).__init__(parent)
        self._pipe_gui_end = pipe_gui_end

        self._window = None

        self._start_gui_loop()

        self._load_main()
        self._show()

    def exit_handler(self):
        self._pipe_gui_end.send(Exit())

    def _start_gui_loop(self, interval_msec=100):
        timer = QTimer(self)
        timer.timeout.connect(self._execute_a_backend_command)
        timer.start()

    def _execute_a_backend_command(self):
        commands_queued = self._pipe_gui_end.poll()
        if commands_queued:
            command = self._pipe_gui_end.recv()
            print("Back-end command arrived: '{}'".format(command))
            if isinstance(command, Main):
                self._load_main()
                self._show()
            elif isinstance(command, Input):
                self._load_input()
                self._show()
            else:
                raise ValueError("Unexpected back-end command: '{}'".format(command))

    def _show(self):
        """Show the `_windows`"""
        if self._window is None:
            raise ValueError("_window cannot be None!")
        self._window.show()

    def _replace_ui(self, ui_path):
        """Load a ui file to replace the window's active UI"""
        ui_file = QFile(ui_path)
        ui_file.open(QFile.ReadOnly)
        loader = QUiLoader()
        self._window = loader.load(ui_file, None)
        ui_file.close()

    def _load_main(self):
        main_ui_path = os.path.join("ui", "main.ui")
        self._replace_ui(main_ui_path)
        self._window.startButton.clicked.connect(self._start)

    def _load_input(self):
        input_ui_path = os.path.join("ui", "input.ui")
        self._replace_ui(input_ui_path)
        self._window.reviewButton.clicked.connect(self._done)

    def _show_dialog(self, title, message):
        self.dialog = OkDialog(title, message)
        self.dialog.exec()

    def _start(self):
        user_name = self._window.nameInput.text()
        if len(user_name) == 0:
            self._show_dialog("Figyelem", "Kérlek adj meg egy nevet!")
        else:
            self._pipe_gui_end.send(Start(user_name))

    def _done(self):
        self._pipe_gui_end.send(Main())

################################ BACKEND #######################################

class Backend(object):
    def __init__(self, pipe_backend_end):
        self._pipe_backend_end= pipe_backend_end
        self._process = Process(target=self._run)

        self.user_name = None

    def _run(self):
        while True:
            commands_queued = self._pipe_backend_end.poll()
            if commands_queued:
                command = self._pipe_backend_end.recv()
                print("GUI command arrived: '{}'".format(command))
                if isinstance(command, Start):
                    self.user_name = command.user_name
                    self._pipe_backend_end.send(Input())
                elif isinstance(command, Main):
                    self._pipe_backend_end.send(Main())
                elif isinstance(command, Exit):
                    print("Backend finishing...")
                    break
                else:
                    raise ValueError("Unexpected GUI command: '{}'".format(command))

    def __enter__(self):
        self._process.start()

    def __exit__(self, type, value, traceback):
        self._process.join()

################################# MAIN #########################################

class App(object):
    def __init__(self):
        """Initialise and start the GUI thread"""

        app = QApplication(sys.argv)

        pipe_gui_end, pipe_backend_end = Pipe()

        gui = Gui(pipe_gui_end)
        app.aboutToQuit.connect(gui.exit_handler)

        with Backend(pipe_backend_end):
            app.exec_()  # start the event loop


if __name__ == '__main__':
    App()
