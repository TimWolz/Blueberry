hue = {'user': r'https://192.168.0.1/api/XXX',  # XXX represents the token
       'standard_group': 1}

calendar = {'url': r"https://192.168.0.2/remote.php/dav",
            'username': r"XXX",
            'password': r"XXX",
            'index_scheduled': 0,
            'index_tracking': 2}  # Indexes need to be extracted via CalHelper.get_calendars()

assistant = {'soundcard_name': 'seeed-4mic-voicecard',
             'deepspeech_model': r'/home/pi/deepspeech-models/deepspeech-0.9.3-models.tflite',
             'deepspeech_scorer': r'/home/pi/deepspeech-models/deepspeech-0.9.3-models.scorer',
             'name': 'Your name',
             'night_time': "20:30",  # the leds switch to more nightly colors
             'activities': ['sport', 'reading', 'coding', 'socializing', 'walking',
                                   'writing', 'reflecting', 'relaxing'],  # so far only one word activites work
             'joplin_folder': 'Inbox'}  # your notes are stored there by default

joplin = {'url': r'http://localhost:41184/',  # this is the default where the api server is normally running
          'token': 'XXX'}  # Can be extracted via JoplinHelper.get_token()

thermometer = {'feel_well_temperature': 22}

commands = {'take_note': [{'take', 'note'}, {'write', 'note'}, {'write', 'notebook'}, {'new', 'entry'}, {'new', 'note'}],
            'write_todo': [{'new', 'task'}, {'remind', 'me'}, {'new', 'reminder'},],
            'show_notes': [{'show', 'notes'}],
            'start_work_out': [{'work', 'out'}],
            'shut_down': [{'shut', 'off'}, {'shut', 'down'}],
            'start_activity': [{'start', 'activity'}, {'start', 'task'}, {'start', 'up', 'next'}, {'start', 'event'}],
            'stop_activity': [{'finish'},{'finished'}, {'done'}, {'stop', 'activity'}, {'stop', 'it'}, {'stop', 'task'}],
            'increase_brightness': [{'increase', 'brightness'}, {'brighter'}, {'more', 'light'}, {'reduce', 'darkness'}],
            'reduce_brightness': [{'dimm', 'lights'}, {'darker'}, {'increase', 'darkness'}, 'reduce', 'brightness']}