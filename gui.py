from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from assistant import Assistant
import hue_helper
from cal_helper import CalHelper
from joplin_helper import JoplinHelper
import pandas as pd
import config as cfg
import time
import datetime as dt


class Window(QMainWindow):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.tabs = Tabs(self)
        self.setCentralWidget(self.tabs)
        self.setWindowTitle(self.tr("Blueberry"))
        self.assistant_thread = Assistant()
        self.assistant_thread.output[str].connect(self.tabs.tab_home.label_words.setText)
        self.assistant_thread.start_activity_signal[bool].connect(self.tabs.tab_time.timer_start)
        self.assistant_thread.stop_activity_signal[bool].connect(self.tabs.tab_time.timer_stop)
        self.assistant_thread.activity_signal[str].connect(self.tabs.tab_time.select_activity)
        self.assistant_thread.current_tab_signal[int].connect(self.tabs.tabs.setCurrentIndex)
        self.assistant_thread.air_signal[str].connect(self.tabs.tab_home.label_air.setText)
        self.showMaximized()
        self.assistant_thread.start()


class Tabs(QWidget):

    def __init__(self, parent):
        super(QWidget, self).__init__(parent)
        self.setStyleSheet('font-size: 13pt; font-family: Sanserif;')
        self.layout = QVBoxLayout(self)

        # Initialize tab screen
        self.tabs = QTabWidget()
        self.tab_home = TabHome()
        self.tab_light = TabLights()
        self.tab_notes = TabNotes()
        self.tab_time = TabTime()
        self.tab_time_stats = TabTimeStats()

        # Add tabs
        self.tabs.addTab(self.tab_home, "Home")
        self.tabs.addTab(self.tab_light, "Lights")
        self.tabs.addTab(self.tab_notes, "Notes")
        self.tabs.addTab(self.tab_time, "Time Tracking")
        self.tabs.addTab(self.tab_time_stats, "Time Stats")
        self.tabs.currentChanged.connect(self.update_tab_content)

        # Add tabs to widget
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)
        
        # shared information
        self.tab_time.activity_signal[str].connect(self.tab_notes.update_notes_list)

    @pyqtSlot()
    def update_tab_content(self):
        if self.tabs.currentIndex() == 1:  # Lights
            self.tab_light.update_content()
        if self.tabs.currentIndex() == 3:  # Timetracking
            self.tab_time._update_widgets()


class TabHome(QWidget):
    """
    Tab displays the speech to text transcriptions
    """
    def __init__(self, parent=None):
        super(QWidget, self).__init__(parent)
        self.label_words = QLabel()
        self.label_words.setAlignment(Qt.AlignCenter)
        self.label_words.setFont(QFont('SansSerif', 20))
        layout = QGridLayout()
        layout.addWidget(self.label_words, 1, 0)
        self.label_air = QLabel()
        self.label_air.setText('Temp: \nHumidity: \nPressure:')
        self.label_air.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        self.label_air.setFont(QFont('SansSerif', 14))
        layout.addWidget(self.label_air, 2,0)
        self.setLayout(layout)


class TabTime(QWidget):
    """
    Tab to track your time. Your scheduled data is displayed and can be shifted and you can start and
    stop the tracking and choose if it should be transferred to your tracking calendar, when stop is pushed
    by the checkbox below.
    """
    activities = cfg.assistant["activities"]
    activity_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super(QWidget, self).__init__(parent)

        self.minutes = 0
        self.hours = 0
        self.start_time = None
        self.stop_time = None
        self.current_activity = None

        self.timer_min = QTimer(self)
        self.timer_min.timeout.connect(self.on_min_timeout)

        self.layout = QGridLayout()

        self.up_next_groupBox = QGroupBox("Up next")
        self.past_groupBox = QGroupBox("Past")
        self.past_layout = QGridLayout()
        self.up_next_layout = QGridLayout()
        self.up_next_button_group = QButtonGroup()
        
        self.df_today_events = CalHelper.get_data_today()
        self.df_today_widgets = self.df_today_events.copy(deep = True)
        self.df_today_widgets = self.df_today_widgets.assign(past='', done=False, upn_bu='', upn_time_labels='',
                                                             upn_shift='', upn_discard='', past_labels='',
                                                             past_time_labels='',  past_done_labels='',
                                                             past_done_bu='', past_back_bu='')
        self._create_calendar_widgets()
        self._sort_widgets()
        self.up_next_groupBox.setLayout(self.up_next_layout)
        self.layout.addWidget(self.up_next_groupBox, 0, 0, 1, 3)
        self.past_groupBox.setLayout(self.past_layout)
        self.layout.addWidget(self.past_groupBox,1,0,1,3)

        self.activity_groupBox = QGroupBox("Activity")
        self.activity_groupBox.setFont(QFont("Sanserif", 13))
        activity_layout = QGridLayout()
        self.activity_r_buttons = []
        self.activity_button_group = QButtonGroup()
        for i, act in enumerate(self.activities):
            self.activity_r_buttons.append(QRadioButton(act))
            self.activity_r_buttons[i].setFont(QFont("Sanserif", 13))
            activity_layout.addWidget(self.activity_r_buttons[i], int(i/3), i % 3)
            self.activity_r_buttons[i].toggled.connect(self.onRadioBtn)
            self.activity_button_group.addButton(self.activity_r_buttons[i])
        self.activity_groupBox.setLayout(activity_layout)
        self.layout.addWidget(self.activity_groupBox, 2, 0, 2, 3)

        self.time_label = QLabel(self.tr("00:00"))
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setFont(QFont('SansSerif', 48))
        self.layout.addWidget(self.time_label, 0, 3, 2, 2)

        self.start_stop_box = QGroupBox("Start/Stop")
        start_stop_layout = QGridLayout()
        self.start_button = QPushButton("start")
        self.start_button.setFont(QFont("Sanserif", 13))
        self.start_button.clicked.connect(self.timer_start)
        self.stop_button = QPushButton("stop")
        self.stop_button.setFont(QFont("Sanserif", 13))
        self.stop_button.clicked.connect(self.timer_stop)
        start_stop_layout.addWidget(self.start_button, 1, 1)
        start_stop_layout.addWidget(self.stop_button, 1, 2)
        self.calendar_check_box = QCheckBox("into calendar")
        self.calendar_check_box.setChecked(True)
        start_stop_layout.addWidget(self.calendar_check_box, 2, 1)
        self.start_stop_box.setLayout(start_stop_layout)
        self.layout.addWidget(self.start_stop_box, 2, 3, 2, 2)
        self.setLayout(self.layout)

    def _create_calendar_widgets(self):
        """creates all the widgets and stores it in a pandas dataframe)"""
        for index, row in self.df_today_events.iterrows():
            self.df_today_widgets.at[index, 'past'] = row['end'] < dt.datetime.now().astimezone(tz=None)
            self.df_today_widgets.at[index, 'upn_bu'] = QRadioButton(row['summary'])
            self.up_next_button_group.addButton(self.df_today_widgets.at[index, 'upn_bu'])
            #print(self.df_today_widgets['upn_bu'])
            self.df_today_widgets.at[index, 'upn_bu'].toggled.connect(self.onRadioBtn)
            self.df_today_widgets.at[index, 'upn_time_labels'] = QLabel(self.tr('{:02}:{:02} - {:02}:{:02}'.format(
                row['start'].hour, row['start'].minute, row['end'].hour, row['end'].minute)))
            self.df_today_widgets.at[index, 'upn_shift'] = QPushButton('Shift')
            self.df_today_widgets.at[index, 'upn_shift'].clicked.connect(self.shift)
            self.df_today_widgets.at[index, 'upn_discard'] = QPushButton('Discard')
            self.df_today_widgets.at[index, 'upn_discard'].clicked.connect(self.discard)
            self.df_today_widgets.at[index, 'past_labels'] = QLabel(self.tr('{}'.format(row['summary'])))
            self.df_today_widgets.at[index, 'past_time_labels'] = QLabel(self.tr(
                '{:02}:{:02} - {:02}:{:02}'.format(row['start'].hour, row['start'].minute,
                                                   row['end'].hour, row['end'].minute)))
            self.df_today_widgets.at[index, 'past_time_labels'].setAlignment(Qt.AlignLeft)
            self.df_today_widgets.at[index, 'past_done_labels'] = QLabel(self.tr('Well Done!'))
            self.df_today_widgets.at[index, 'past_done_labels'].setVisible(False)
            self.df_today_widgets.at[index, 'past_done_bu'] = QPushButton('Done')
            self.df_today_widgets.at[index, 'past_done_bu'].clicked.connect(self.done)
            self.df_today_widgets.at[index, 'past_back_bu'] = QPushButton('Back in')
            self.df_today_widgets.at[index, 'past_back_bu'].clicked.connect(self.back_in)

    @pyqtSlot()
    def _sort_widgets(self):
        """
        sorts the widgets into the layouts depending on up next or already done
        """
        pasts = self.df_today_widgets.past.sum() + self.df_today_widgets.done.sum()
        up_nexts_all = len(self.df_today_widgets) - pasts
        up_nexts = 0
        for index, row in self.df_today_widgets.iterrows():
            if row['past'] or row['done']:
                for i, widget in enumerate(['past_labels', 'past_time_labels', 'past_back_bu']):
                    self.past_layout.addWidget(row[widget], pasts, i)
                self.past_layout.addWidget(row['past_done_labels'], pasts, 3)
                self.past_layout.addWidget(row['past_done_bu'], pasts, 3)
                row['past_done_labels'].setVisible(row['done'])
                row['past_done_bu'].setVisible(not row['done'])
                pasts -= 1
            else:
                for i, widget in enumerate(['upn_bu', 'upn_time_labels', 'upn_shift', 'upn_discard']):
                    self.up_next_layout.addWidget(row[widget], up_nexts, i)
                up_nexts += 1

    @pyqtSlot()
    def _update_widgets(self, force=False):
        """
        updates the widgets, i.e, moves them between layouts if the stop time has been passed or force = True
        :param force: forces a resort (bool)
        :return:
        """
        new_pasts = pd.DataFrame([i < dt.datetime.now().astimezone(tz=None) for i in self.df_today_widgets['end']])
        #print(new_pasts)
        if (not self.df_today_widgets['past'].equals(new_pasts)) or force:
            self.df_today_widgets['past'] = new_pasts
            for i in reversed(range(self.past_layout.count())):
                #self.past_layout.removeWidget(self.past_layout.itemAt(i).widget())
                self.past_layout.itemAt(i).widget().setParent(None)
            for i in reversed(range(self.up_next_layout.count())):
                #self.up_next_layout.removWidget(self.up_next_layout.itemAt(i).widget())
                self.up_next_layout.itemAt(i).widget().setParent(None)
            self._sort_widgets()

    @pyqtSlot()
    def onRadioBtn(self):
        """
        Sets the current activity to what was chosen by a cklick on the radio button
        :return:
        """
        act_rad_button = self.sender()
        if act_rad_button.isChecked():
            self.current_activity = act_rad_button.text()
            #print(self.current_activity)
            if act_rad_button in self.df_today_widgets['upn_bu']:
                self.activity_button_group.setExclusive(False)
                for act_butt in self.activity_r_buttons:
                    act_butt.setChecked(False)
                self.activity_button_group.setExclusive(True)
            elif act_rad_button in self.activity_r_buttons:
                self.up_next_button_group.setExclusive(False)
                for act_butt in self.df_today_widgets['upn_bu']:
                    act_butt.setChecked(False)
                self.up_next_button_group.setExclusive(True)
        self.activity_signal.emit(self.current_activity)

    @pyqtSlot(str)
    def select_activity(self, activity):
        """
        sets current activity if recognized by deepspeech
        :param activity: string of the activity (to be spoken)
        :return:
        """
        for a_but in self.activity_r_buttons:
            if activity == a_but.text():
                a_but.setChecked(True)
                self.current_activity = activity
            elif activity == 'start':
                index = self.df_today_widgets.index[
                    (self.df_today_widgets['past'] == False) & (self.df_today_widgets['done'] == False)][0]
                self.df_today_widgets.at[index, 'upn_bu'].setChecked(True)
                self.current_activity = self.df_today_widgets.at[index, 'upn_bu'].text()
                
    @pyqtSlot()
    def discard(self, from_calendar=None):
        """
        discards the planned activity from the time-tracking and in future maybe from calendar
        """
        index = self.df_today_widgets.index[self.df_today_widgets['upn_discard'] == self.sender()][0]
        for widget in ['upn_bu', 'upn_time_labels','upn_shift', 'upn_discard']:
            self.df_today_widgets.at[index, widget].deleteLater()
        self.df_today_widgets.drop(index=index, inplace=True)
        self.df_today_widgets.reset_index(drop=True, inplace=True)
        
    @pyqtSlot()
    def shift(self, minutes=30, index=None):
        """
        shifts the chosen activity and all following by a specific duration
        """
        if index is None:
            index = self.df_today_widgets.index[self.df_today_widgets['upn_shift'] == self.sender()][0]
        self.df_today_widgets.at[index, 'start'] += dt.timedelta(minutes=minutes)
        self.df_today_widgets.at[index, 'end'] += dt.timedelta(minutes=minutes)
        self.df_today_widgets.at[index, 'upn_time_labels'].setText('{:02}:{:02} - {:02}:{:02}'.format(
            self.df_today_widgets.at[index, 'start'].hour, self.df_today_widgets.at[index, 'start'].minute,
            self.df_today_widgets.at[index, 'end'].hour, self.df_today_widgets.at[index, 'end'].minute))
        for i, row in self.df_today_widgets[index:-1].iterrows():
            dist = 1
            for j, row2 in self.df_today_widgets[i:-2].iterrows():
                if row2['past'] is True:
                    dist += 1
            if self.df_today_widgets.at[i, 'end'] > self.df_today_widgets.at[i+dist, 'start'] and (row['past'] is False):
                diff = self.df_today_widgets.at[i, 'end'] - self.df_today_widgets.at[i+dist, 'start']
                self.df_today_widgets.at[i+dist, 'start'] = self.df_today_widgets.at[i, 'end']
                # shift in calendar
                self.df_today_widgets.at[i+dist, 'end'] += diff
                # shift in calendar
                self.df_today_widgets.at[i+dist, 'upn_time_labels'].setText('{:02}:{:02} - {:02}:{:02}'.format(
                        self.df_today_widgets.at[i+dist, 'start'].hour, self.df_today_widgets.at[i+dist, 'start'].minute,
                        self.df_today_widgets.at[i+dist, 'end'].hour, self.df_today_widgets.at[i+dist, 'end'].minute))
        self.df_today_widgets.sort_values('start', inplace=True)
        self.df_today_widgets.reset_index(drop=True, inplace=True)
        
    
    @pyqtSlot()
    def done(self):
        """writes event as is into the tracking calendar"""
        index = self.df_today_widgets.index[self.df_today_widgets['past_done_bu'] == self.sender()][0]
        self.df_today_widgets.at[index, 'done'] = True
        self.df_today_widgets.at[index, 'past_done_labels'].setVisible(True)
        self.df_today_widgets.at[index, 'past_done_bu'].setVisible(False)
        CalHelper.write_vevent_into_calendar(self.df_today_widgets.at[index, 'vevent'])
        
    @pyqtSlot()
    def back_in(self):
        """brings the activity to the up next tasks at time right now"""
        index = self.df_today_widgets.index[self.df_today_widgets['past_back_bu'] == self.sender()][0]
        if self.df_today_widgets.at[index, 'done'] is True:
            print('Dude already done!')
        else:
            time_delta = dt.datetime.now().astimezone(None)-self.df_today_widgets.at[index, 'start']
            self.df_today_widgets.at[index, 'past'] = False
            self.shift(minutes=int(time_delta.seconds/60), index=index)
            self._update_widgets(force=True)       
    
    @pyqtSlot()
    def timer_start(self):
        """
        starts the timer for the time tracking
        :return:
        """
        self.start_time = time.time()
        self.minutes = 0
        self.hours = 0
        self.timer_min.start(1000*60)
        self.time_label.setText('{:02}:{:02}'.format(self.hours, self.minutes))
        for i, bu in enumerate(self.df_today_widgets['upn_bu']):
            if bu.isChecked():
                CalHelper.delete_job(self.df_today_widgets.at[i, 'summary'])
                break

    @pyqtSlot()
    def timer_stop(self):
        """
        stops the timer for the time tracking and stores the tracked activity into the tracking calendar
        if checkbox is checked
        :return:
        """
        self.stop_time = time.time()
        self.timer_min.stop()
        update_gui = False
        if self.minutes == 0 and self.hours == 0:
            pass
            #return
        if self.calendar_check_box.isChecked() and self.start_time:
            CalHelper.write_into_calendar(self.start_time, self.stop_time, self.current_activity)
        for i, bu in enumerate(self.df_today_widgets['upn_bu']):
            if bu.isChecked():
                dt_start = dt.datetime.fromtimestamp(int(self.start_time)).astimezone(tz=None)
                dt_stop = dt.datetime.fromtimestamp(int(self.stop_time)).astimezone(tz=None)
                self.df_today_widgets.at[i, 'done'] = True
                self.df_today_widgets.at[i, 'start'] = dt_start
                self.df_today_widgets.at[i, 'end'] = dt_stop
                self.df_today_widgets.at[i, 'past_time_labels'].setText('{:02}:{:02} - {:02}:{:02}'.format(dt_start.hour, dt_start.minute,
                                                   dt_stop.hour, dt_stop.minute))
                self.up_next_button_group.setExclusive(False)
                bu.setChecked(False)
                self.up_next_button_group.setExclusive(True)
                update_gui = True
                CalHelper.delete_job(self.df_today_widgets.at[i, 'summary'])
                break
        self.start_time = None
        self.current_activity = None
        self.activity_button_group.setExclusive(False)
        self.up_next_button_group.setExclusive(False)
        for act_butt in (self.activity_r_buttons + self.df_today_widgets['upn_bu'].tolist()):
            act_butt.setChecked(False)
        self.activity_button_group.setExclusive(True)
        self.up_next_button_group.setExclusive(True)
        self.time_label.setText('{:02}:{:02}'.format(self.hours, self.minutes))
        if update_gui:
            self._update_widgets(force = True)

    def on_min_timeout(self):
        self.minutes += 1
        if self.minutes == 60:
            self.minutes = 0
            self.hours += 1
        self.time_label.setText('{:02}:{:02}'.format(self.hours, self.minutes))


class TabTimeStats(QWidget):
    """
    Displays the time for your activities as planned and compares it to your actual data for the last week
    """
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.table = QTableWidget(1, 3)
        headings = ['Activity', 'Actual', 'Planned']
        for i in range(3):
            self.table.setItem(0,i, QTableWidgetItem(headings[i]))
        layout = QGridLayout()
        self.update_content()
        layout.addWidget(self.table)
        self.setLayout(layout)

    @pyqtSlot()
    def update_content(self):
        self.df_time = CalHelper.get_data_stats()
        self.table.setRowCount(len(self.df_time.index)+1)
        for i in range(len(self.df_time.index)):
            self.table.setItem(i+1, 0, QTableWidgetItem(str(self.df_time.index[i])))
            for j in range(2):
                if pd.isna(self.df_time.iloc[i,j]):
                    display_string = "--"
                else:
                    display_string = "{:02}:{:02}".format(int(self.df_time.iloc[i, j]),
                                                          int((self.df_time.iloc[i, j] % 1)*60))
                self.table.setItem(i+1, j+1, QTableWidgetItem(display_string))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)


class TabLights(QWidget):
    """
    Tab to control you hue lights in (so far) one group. You can choose the scene, brightness, and temperature
    as well as turn on and off all groups.
    """
    def __init__(self, parent=None):
        super(QWidget, self).__init__(parent)
        self.hue = hue_helper.HueHelper()
        self.layout = QGridLayout()
        self.scenes_group_box = QGroupBox("Scenes")
        self.scenes_group_box.setFont(QFont("Sanserif", 13))
        scenes_layout = QGridLayout()
        self.scene_buttons = []
        for i, s in enumerate(self.hue.scenes_df['name'].tolist()):
            self.scene_buttons.append(QRadioButton(s))
            self.scene_buttons[i].setFont(QFont("Sanserif", 13))
            self.scene_buttons[i].clicked.connect(lambda: self.set_scene(scene_name=s))
            scenes_layout.addWidget(self.scene_buttons[i], i/2, i%2)
        self.scenes_group_box.setLayout(scenes_layout)
        self.layout.addWidget(self.scenes_group_box, 0, 0, 3, 3)

        self.brightness_box = QGroupBox("Brightness")
        self.brightness_box.setFont(QFont("Sanserif", 13))
        self.brightness_box_layout = QHBoxLayout()
        self.brightness_slider = QSlider(Qt.Vertical)
        self.brightness_slider.setMaximum(255)
        self.brightness_slider.valueChanged.connect(self.change_brightness)
        self.brightness_box_layout.addWidget(self.brightness_slider)
        self.brightness_box.setLayout(self.brightness_box_layout)
        self.layout.addWidget(self.brightness_box, 0, 3, 3, 1)
        
        self.groups_group_box = QGroupBox("Groups")
        self.groups_group_box.setFont(QFont("Sanserif", 13))
        groups_layout = QVBoxLayout()
        self.group_buttons = []
        for i, g in enumerate(hue_helper.HueHelper.groups_df['name'].tolist()):
            self.group_buttons.append(QCheckBox())
            self.group_buttons[i].setText(g)
            self.group_buttons[i].stateChanged.connect(lambda clicked, i=i:
                                                       self.set_on_off(groupsbutton=self.group_buttons[i]))
            groups_layout.addWidget(self.group_buttons[i])
        self.groups_group_box.setLayout(groups_layout)
        self.layout.addWidget(self.groups_group_box, 0, 4, 2,2)
        
        self.temperature_box = QGroupBox("Temperature")
        self.temperature_box.setFont(QFont("Sanserif", 13))
        self.temp_box_layout = QGridLayout()
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setMinimum(153)
        self.temp_slider.setMaximum(500)
        self.temp_slider.valueChanged.connect(self.change_temperature)
        self.temp_box_layout.addWidget(self.temp_slider, 0, 0, 1, 3)
        self.l_cold = QLabel()
        self.l_cold.setAlignment(Qt.AlignLeft)
        self.l_cold.setFont(QFont('SansSerif', 13))
        self.l_cold.setText("Cold")
        self.l_warm = QLabel()
        self.l_warm.setAlignment(Qt.AlignRight)
        self.l_warm.setFont(QFont('SansSerif', 13))
        self.l_warm.setText("Warm")
        self.temp_box_layout.addWidget(self.l_cold, 1,0,1,1)
        self.temp_box_layout.addWidget(self.l_warm, 1,2,1,1)
        self.temperature_box.setLayout(self.temp_box_layout)
        
        self.layout.addWidget(self.temperature_box, 2,4, 1,2)
        self.setLayout(self.layout)

    @pyqtSlot()
    def change_brightness(self):
        self.hue.set_brightness(self.brightness_slider.value())
        
    @pyqtSlot()
    def change_temperature(self):
        self.hue.set_temperature(self.temp_slider.value())

    @pyqtSlot()
    def set_scene(self, scene_name):
        for s in self.scene_buttons:
            if s.isChecked():
                scene_name = s.text()
        self.hue.set_scene_by_name(scene_name)
        for g in self.group_buttons:
            if self.hue.get_status(g.text()):
                g.setChecked(True)
            else:
                g.setChecked(False)
        time.sleep(0.5)
        self.update_content()
        

    @pyqtSlot()
    def set_on_off(self, groupsbutton):
        if groupsbutton.isChecked():
            self.hue.turn_on(groupsbutton.text())
        else:
            self.hue.turn_off(groupsbutton.text())
            
    @pyqtSlot()
    def update_content(self):
        brightness = self.hue.get_brightness()
        self.brightness_slider.setValue(brightness)
        temperature = self.hue.get_temperature()
        self.temp_slider.setValue(temperature)
        
        for g in self.group_buttons:
            if self.hue.get_status(g.text()):
                g.setChecked(True)
            else:
                g.setChecked(False)
                
                
class TabNotes(QWidget):
    """
    Tab to display notes from joplin.
    Notes are automatically searched for the "activity" key word in the time tracking tab. So that
    you always get the right notes for your what you are doing. Pro-tip employing tags in joplin with the name
    of your activity.
    """
    def __init__(self, parent=None):
        super(QWidget, self).__init__(parent)
        self.layout = QGridLayout()
        self.notes_list_tag = QListWidget()
        self.notes_list_todo = QListWidget()
        self.notes_list_content = QListWidget()
        self.notes_lists = [self.notes_list_tag, self.notes_list_todo, self.notes_list_content]
        self.notes_list_tag.itemClicked.connect(self.display_note)
        self.notes_list_todo.itemClicked.connect(self.display_note)
        self.notes_list_content.itemClicked.connect(self.display_note)
        self.notes_display = QTextEdit()
        self.group_box_tags = QGroupBox('Tag')
        self.group_box_todo = QGroupBox('ToDo')
        self.group_box_content = QGroupBox('Content')
        tag_layout = QVBoxLayout()
        todo_layout = QVBoxLayout()
        content_layout = QVBoxLayout()
        tag_layout.addWidget(self.notes_list_tag)
        todo_layout.addWidget(self.notes_list_todo)
        content_layout.addWidget(self.notes_list_content)
        self.group_box_tags.setLayout(tag_layout)
        self.group_box_todo.setLayout(todo_layout)
        self.group_box_content.setLayout(content_layout)
        self.layout.addWidget(self.group_box_tags, 0, 0, 1, 2)
        self.layout.addWidget(self.group_box_todo, 1, 0, 1, 2)
        self.layout.addWidget(self.group_box_content, 2, 0, 1, 2)
        self.layout.addWidget(self.notes_display, 0, 2, 3, 5)
        self.setLayout(self.layout)

        
    @pyqtSlot(str)
    def update_notes_list(self, activity):
        """
        updates the note list depending on the chosen activity in the time tracking tab
        :param activity: as chosen in the time tracking tab (str)
        :return:
        """
        if len(activity) >1:  # Variable comes as a string
            self.notes_display.setPlainText(' ')
            for lists in self.notes_lists:
                lists.clear()
            self.all_notes = JoplinHelper.get_notes(activity)
            print(self.all_notes)
            for typ, notes in self.all_notes.items():
                if typ == 'tag':
                    for note in notes:
                        self.notes_list_tag.addItem(note['title'])
                elif typ == 'todo':
                    for note in notes:
                        self.notes_list_todo.addItem(note['title'])
                elif typ == 'content':
                    for note in notes:
                        self.notes_list_content.addItem(note['title'])

    @pyqtSlot()
    def display_note(self):
        """
        displays the text of the respective note
        :return:
        """
        note_type = self.sender().parent().title().lower()
        print(note_type)
        box_index = {'tag': 0, 'todo': 1, 'content': 2}
        index = self.notes_lists[box_index[note_type]].currentRow()
        self.notes_display.setPlainText(self.all_notes[note_type][index]['body'])
