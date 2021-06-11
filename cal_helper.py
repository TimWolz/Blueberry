import caldav
import time
from datetime import datetime
import numpy as np
import pandas as pd
import config as cfg
import glob, os
import schedule
import threading


class CalHelper:
    """
    Class to communicate with a caldav calendar and analyze the data, i.e, compare scheduled dates with tracked
    activities
    """
    url = cfg.calendar["url"]
    username = cfg.calendar["username"]
    password = cfg.calendar["password"]
    client = caldav.DAVClient(url=url, username=username, password=password, ssl_verify_cert=False)
    principal = client.principal()
    try:
        calendar_scheduled = principal.calendars()[cfg.calendar["index_scheduled"]]
        calendar_tracking = principal.calendars()[cfg.calendar["index_tracking"]]
    except IndexError:
        print('Cannot find calendar with specified index')
    df_today = pd.DataFrame(columns=('summary', 'start', 'end', 'vevent'))
    scheduler_tasks = {}

    def __init__(self):
        self.scheduler_started = False

    @classmethod
    def get_calendars(cls):
        """returns the available calendars"""
        return cls.principal.calendars()

    @classmethod
    def write_into_calendar(cls, start_time, stop_time, activity, calendar="tracking"):
        """
        writes an event based on time and activity into the calendar
        :param start_time: ToDo what format
        :param stop_time:
        :param activity:
        :param calendar:
        :return:
        """
        str_start_time = time.strftime("%Y%m%dT%H%M", time.localtime(start_time))
        str_stop_time = time.strftime("%Y%m%dT%H%M", time.localtime(stop_time))
        if calendar == "tracking":
            calen = cls.calendar_tracking
        elif calendar == 'scheduled':
            calen = cls.calendar_scheduled
        else:
            return False
        my_event = calen.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:{}00
DTEND:{}00
SUMMARY:{}
END:VEVENT
END:VCALENDAR
""".format(str_start_time, str_stop_time, activity))

    @classmethod
    def write_vevent_into_calendar(cls, vevent, calendar='tracking'):
        """
        having already a vevent object, we can use this function. Useful to copy events from one
        calendar into another
        :param vevent: vevent object, as extracted via the caldav library
        :param calendar: calendar to store the vevent in
        :return:
        """
        if calendar == "tracking":
            calen = cls.calendar_tracking
        elif calendar == 'scheduled':
            calen = cls.calendar_scheduled
        else:
            return False
        my_event = calen.save_event(vevent)

    @classmethod
    def write_tasks_into_calendar(cls, activity, due_date, calendar="scheduled"):
        """
        Instead of an event this function writes a task/todo in the calendar.
        :param activity:
        :param due_date: ToDO check format
        :param calendar:
        :return:
        """
        if due_date == 0:
            if calendar == "scheduled":
                my_event = cls.calendar_scheduled.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VTODO
SUMMARY:{}
END:VTODO
END:VCALENDAR
""".format(activity))
        else:
            str_due_time = time.strftime("%Y%m%dT%H%M", time.localtime(due_date))
            if calendar == "scheduled":
                my_event = cls.calendar_scheduled.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VTODO
DTSTART:{}00
SUMMARY:{}
END:VTODO
END:VCALENDAR
""".format(str_due_time, activity))

    @classmethod
    def get_data_last_week(cls, calendar='tracking'):
        """
        gets all the data from last week and stores it in dictionary
        :param calendar: from which the data should be extracted
        :return: all activities with start stop and summary in a dictionary
        """
        st_time = time.localtime(time.time() - (7 * 24 * 3600))[0:3]
        if calendar == 'tracking':
            events = cls.calendar_tracking.date_search(datetime(*st_time), datetime(*time.localtime()[0:3]))
        elif calendar == 'scheduled':
            events = cls.calendar_scheduled.date_search(datetime(*st_time), datetime(*time.localtime()[0:3]))
        else:
            print('wrong input')
            return
        activities = {}
        for e in events:
            try:  # Don't know why it's needed
                start = e.vobject_instance.vevent.dtstart.value
                stop = e.vobject_instance.vevent.dtend.value
                act = e.vobject_instance.vevent.summary.value.lower()
                duration = (stop-start).total_seconds()/3600
                if duration > 0.01:
                    if act in activities.keys():
                        activities[act] += np.round(duration, 2)
                    else:
                        activities[act] = np.round(duration, 2)
            except AttributeError:
                pass
        return activities

    @classmethod
    def generate_data_today(cls):
        """
        Generates/updates a new dataframe from specified calendar and returns true
        if the class dataframe has been changed.
        I.e. a change in the calendar has occured since the last time, generate data today was executed.
        :return: True or false, depending on today's calendar events have been changed (on the server)
        """
        events = cls.calendar_scheduled.date_search(datetime(*time.localtime()[0:3], 0, 0),
                                                    datetime(*time.localtime()[0:3], 23, 59))
        df_today = pd.DataFrame(columns=('summary', 'start', 'end'))
        for e in events:
            start = e.vobject_instance.vevent.dtstart.value.astimezone(tz=None)
            end = e.vobject_instance.vevent.dtend.value.astimezone(tz=None)
            summary = e.vobject_instance.vevent.summary.value
            df_today = df_today.append({'start': start, 'end': end, 'summary': summary, 'vevent': e.vobject_instance},
                                       ignore_index=True)
        df_today = df_today.sort_values(by=['start']).reset_index(drop=True)
        if not df_today.equals(cls.df_today):
            cls.df_today = df_today
            return True
        else:
            return False

    @classmethod
    def get_data_today(cls):
        """
        Only returns the previously generated dataframe without checking the calendar again (convenience function)
        :return: dataframe of the events
        """
        if len(cls.df_today) == 0:
            cls.generate_data_today()
        return cls.df_today

    def generate_scheduler_tasks(self, func):  # schedule only as module, makes problems when run from differnt parts
        """
        Starts a scheduler to update the task dataframe and also to execute a function func at time
        of the calendar tasks
        :return: None
        """
        self.generate_data_today()
        for i, start_time in enumerate(self.df_today['start']):
            self.scheduler_tasks[self.df_today.at[i, 'summary']] = schedule.every().day.at(
                '{:02}:{:02}'.format(start_time.hour, start_time.minute)).do(func).tag('event_start')
        schedule.every(10).minutes.do(self.update_scheduler, func=func)

    def update_scheduler(self, func):
        """
        updates the scheduler if the calendar has changed
        :return: None
        """
        # ToDo: how to avoid jobs for time passed? (should not be a problem at first)
        if self.generate_data_today():
            schedule.clear('event_start')
            self.scheduler_tasks = {}
            for i, start_time in enumerate(self.df_today['start']):
                self.scheduler_tasks[self.df_today.at[i, 'summary']] = schedule.every().day.at('{:02}:{:02}'.format(
                    start_time.hour, start_time.minute)).do(func).tag('event_start')
        else:
            print('Nothing new here.')

    @classmethod  # Defined as class method to access via the gui, probably not the best way
    def delete_job(cls, summary):
        """
        deletes a job for given summary, so that lights won't blink if planned activity has already been performed
        :param summary: of the activity (str)
        :return:
        """
        # ToDo: how to deal with double jobs
        try:
            schedule.cancel_job(cls.scheduler_tasks[summary])
        except KeyError:
            print('No job to cancel')

    def _start_scheduler(self):
        """To be used without the PiServiotr, otherwise the tasks are started with schedule there"""
        self.update_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.update_thread.start()
        self.scheduler_started = True

    def _run_scheduler(self):
        while True:
            schedule.run_pending()
            time.sleep(1)

    @classmethod
    def get_data_stats(cls):
        """ Gets the data from the two calendars used and writes+returns them in a pandas dataframe"""
        scheduled_data = cls.get_data_last_week(calendar='scheduled')
        actual_data = cls.get_data_last_week(calendar='tracking')
        activites = set(list(scheduled_data.keys())+list(actual_data.keys()))
        time_df = pd.DataFrame.from_records([actual_data, scheduled_data]).transpose()
        time_df = time_df.sort_values(by=[0], axis=0, ascending=False)
        return time_df 

    # --------- work in progress -----
    @classmethod
    def get_calendar_tasks(cls, calendar='scheduled'):
        all_tasks = {}
        if calendar == 'scheduled':
            tasks_cal = cls.calendar_scheduled.date_search(datetime(*time.localtime()[0:3]), compfilter='VTODO')
        for t in tasks_cal:
            task_content = {}
            try:
                task_content['todo_due'] = t.vobject_instance.vtodo.dtstart.value
            except AttributeError:
                pass
            all_tasks[t.vobject_instance.vtodo.summary.value] = task_content
        return all_tasks

    @classmethod
    def get_joplin_tasks(cls, cache, folder="1 Next Actions"):
        all_notes = {}
        tasks = {}
        os.chdir(cache)
        for file in glob.glob("*.md"):
            with open(file) as f:
                notes = {}
                t_content, metadata = f.read().split('\nid')
                title = t_content.split('\n')[0]
                content = t_content.split('\n')[1:]
                all_notes[title] = notes
                notes['content'] = content
                notes['title'] = title
                for line in ('id' + metadata).split('\n'):
                    try:
                        key, item = line.split(': ')
                    except ValueError:
                        pass
                    notes[key] = item.strip()
        tasks_id = all_notes[folder]['id']
        for key, note in all_notes.items():
            try:
                if note['parent_id'] == tasks_id and int(note['is_todo']) == 1:
                    tasks[key] = note
            except KeyError:
                pass
        return tasks

    @classmethod
    def move_someday_to_inbox(cls):
        someday_tasks = cls.get_joplin_tasks("Someday")
        for task_title in someday_tasks:
            # Only take tasks which are within the next 7 days
            if time.time()+7*24*3600 > int(someday_tasks[task_title]['todo_due']/1000) > time.time():
                os.system('mv {} "0 inbox"'.format(someday_tasks[task_title][id]))

    @classmethod
    def synchronize_calendar_joplin(cls, cal_tasks, joplin_tasks):
        task_titles_jop = list(joplin_tasks.keys())
        for task_title in set(task_titles_jop) - set(cal_tasks):
            cls.write_tasks_into_calendar(task_title, int(joplin_tasks[task_title]['todo_due'])/1000)
