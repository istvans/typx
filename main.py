# -*- coding: utf-8 -*-
from enum import Enum
from multiprocessing import Process, Pipe
import os
from random import randint
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


class Start(Message):

    def __init__(self, user_name):
        self.user_name = user_name


class Pattern(Message):

    def __init__(self, current_round, num_rounds, value):
        self.current_round = current_round
        self.num_rounds = num_rounds
        self.value = value


class MarkedValue(object):

    def __init__(self, value, correct):
        self.value = value
        self.correct = correct


class Trial(Message):

    def __init__(self, user_input):
        self.user_input = user_input
        self.marked_user_input = []
        self.pattern = None
        self.correct = False

    def evaluate(self):
        if self.pattern is None:
            raise RuntimeError("Cannot evaluate this trial without a valid pattern")

        self.correct = self.pattern == self.user_input
        if not self.correct:
            assert len(self.pattern) == len(self.user_input)
            for (p, i) in zip(self.pattern, self.user_input):
                self.marked_user_input.append(MarkedValue(i, p == i))


class Result(Message):

    def __init__(self):
        self.user_name = None
        self.trials = []
        self.num_correct = 0
        self.num_trials = 0
        self.percent_correct = 0

    def add(self, trial):
        if trial.correct:
            self.num_correct += 1
        self.trials.append(trial)

    def prepare_to_send(self):
        self.num_trials = len(self.trials)
        self.percent_correct = (self.num_correct / self.num_trials) * 100


class Save(Message):
    pass


class BackToMain(Message):
    pass

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

        self.pattern_length = 0

        self._start_gui_loop()

        # TODO load user from db, if saved is checked

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
            if isinstance(command, Pattern):
                self._load_input()
                pattern = command
                self._update_input(pattern)
                self._show()
            elif isinstance(command, Result):
                self._load_result(command)
                self._show()
            elif isinstance(command, BackToMain):
                self._load_main()
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
        self._window.nameInput.textEdited.connect(self._enable_or_disable_main_buttons)
        self._window.nameInput.returnPressed.connect(self._start)
        self._enable_or_disable_main_buttons(self._window.nameInput.text())

    def _enable_or_disable_main_buttons(self, text):
        self._window.startButton.setEnabled(len(text) != 0)

    def _load_input(self):
        input_ui_path = os.path.join("ui", "input.ui")
        self._replace_ui(input_ui_path)
        self._window.input.textEdited.connect(self._enable_or_disable_next_button)
        self._window.input.returnPressed.connect(self._send_solution)
        self._window.nextButton.clicked.connect(self._send_solution)

    def _send_solution(self):
        if self._window.nextButton.isEnabled():
            solution = self._window.input.text()
            self._pipe_gui_end.send(Trial(user_input=solution))

    def _enable_or_disable_next_button(self, text):
        self._window.nextButton.setEnabled(len(text) == self.pattern_length)

    def _update_input(self, pattern):
        self.pattern_length = len(pattern.value)
        self._window.inputCounter.setText("{}/{}".format(pattern.current_round, pattern.num_rounds))
        self._window.patternLabel.setText(pattern.value)
        self._window.input.setFocus()

    def _load_result(self, result):
        ui_path = os.path.join("ui", "single_result.ui")
        self._replace_ui(ui_path)

        # load stuff
        for trial in result.trials:
            self._window.patternBox.addWidget(QLabel(trial.pattern))
            if trial.correct:
                user_input = "<font color=\"green\">{}</font>".format(trial.user_input)
            else:
                marked_user_input = []
                for m in trial.marked_user_input:
                    wrapper = "{}" if m.correct else "<font color=\"red\">{}</font>"
                    marked_user_input.append(wrapper.format(m.value))
                user_input = "".join(marked_user_input)
            self._window.inputBox.addWidget(QLabel(user_input))

        self._window.numberOfPatterns.setText("{}".format(result.num_trials))
        self._window.correctInputCount.setText("{}".format(result.num_correct))
        self._window.correctPercent.setText("{:.2f}%".format(result.percent_correct))

        # setup control
        self._window.saveButton.clicked.connect(self._save)

    def _save(self):
        self._pipe_gui_end.send(Save())

    def _show_dialog(self, title, message):
        self.dialog = OkDialog(title, message)
        self.dialog.exec()

    def _start(self):
        if self._window.startButton.isEnabled():
            user_name = self._window.nameInput.text()
            self._pipe_gui_end.send(Start(user_name))

################################ BACKEND #######################################

class Backend(object):
    def __init__(self, pipe_backend_end):
        self._pipe_backend_end= pipe_backend_end
        self._process = Process(target=self._run)

        self.user_name = None
        self.num_rounds = 2
        self.pattern_pool = "0123456789"
        self.pattern_length = 4

        self.current_round = 0
        self.result = Result()

    def _gen_new_pattern(self):
        pattern = []
        for _ in range(self.pattern_length):
            random_index = randint(0, len(self.pattern_pool) - 1)
            pattern.append(self.pattern_pool[random_index])
        return "".join(pattern)

    def _send_pattern_to_user(self, value):
        self._pipe_backend_end.send(Pattern(self.current_round, self.num_rounds, value))

    def _run(self):
        while True:
            commands_queued = self._pipe_backend_end.poll()
            if commands_queued:
                command = self._pipe_backend_end.recv()
                print("GUI command arrived: '{}'".format(command))
                if isinstance(command, Start):
                    # reset the state
                    self.result = Result()
                    self.current_round = 1

                    self.user_name = command.user_name
                    pattern = self._gen_new_pattern()
                    self._send_pattern_to_user(pattern)
                elif isinstance(command, Trial):
                    trial = command
                    trial.pattern = pattern

                    trial.evaluate()

                    self.result.add(trial)

                    if self.current_round < self.num_rounds:
                        self.current_round += 1
                        pattern = self._gen_new_pattern()
                        self._send_pattern_to_user(pattern)
                    else:
                        self.result.prepare_to_send()
                        self._pipe_backend_end.send(self.result)
                elif isinstance(command, Save):
                    # TODO write to db
                    self._pipe_backend_end.send(BackToMain())
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
