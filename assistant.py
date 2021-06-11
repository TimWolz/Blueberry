import time, os
import numpy as np
import scipy.signal as sg
from PyQt5.QtCore import *

import deepspeech as ds
import pvporcupine  
import struct
import pyaudio

from hue_helper import HueHelper
from led_helper import LedHelper
from cal_helper import CalHelper
from joplin_helper import JoplinHelper
from thermometer import Thermometer
import config as cfg

import threading
import schedule


class Assistant(QThread):
    """
    Main class, managing all the work, i.e., recognizing the voice commands and executing them.
    """
    output = pyqtSignal(str)
    start_activity_signal = pyqtSignal(bool)
    stop_activity_signal = pyqtSignal(bool)
    activity_signal = pyqtSignal(str)
    current_tab_signal = pyqtSignal(int)
    air_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        QThread.__init__(self, parent)
        self.exiting = False
    
    def _startup(self):
        """
        This should normally be the init but because of the gui, we have to start it manually
        """
        self.startup_string = "Hello {}, just need a second to get ready for you!".format(cfg.assistant["name"])
        self.output.emit(self.startup_string)
        self.listen_lock = threading.Lock()
        
        self.led = LedHelper()
        with self.led.led_lock:
            stop_threads = False
            t_wheel_led = threading.Thread(target=self.led.run_color_wheel, args=(lambda: stop_threads,
                                                                                  self.led.listening_led_values))
            t_wheel_led.start()
            
            try:
                self.hue = HueHelper()
                self.hue_connected = True
                self.startup_string += "\n Connected to your hue bridge"
            except OSError:
                self.startup_string += "\n Couldn't connect to your hue bridge"
                self.hue_connected = False
                
            self.output.emit(self.startup_string)
            
            if self.hue_connected:  # So that lights will blink when a new event starts
                self.cal = CalHelper()
                self.cal.generate_scheduler_tasks(self.hue.set_alert)

            self.porcupine = pvporcupine.create(keywords=['blueberry'], sensitivities=[0.8])
            time.sleep(1)
            self.pa = pyaudio.PyAudio()  # not sure if this should be here
            device_index = self._find_device_index(name=cfg.assistant['soundcard_name'])
            self.audio_stream = self.pa.open(rate=self.porcupine.sample_rate, channels=4,
                                            format=pyaudio.paInt16, input=True,
                                            frames_per_buffer=self.porcupine.frame_length,
                                            input_device_index=device_index)
            self.silence_level = self.measure_silence_level()
            
            self.startup_string += '\n now starting deepspeech'
            self.output.emit(self.startup_string)
            self.ds_model = ds.Model(cfg.assistant['deepspeech_model'])
            self.ds_model.enableExternalScorer(cfg.assistant['deepspeech_scorer']+'')
            self.startup_string += '\n finished initiating deepspeech, \n now syncing your notes'
            self.output.emit(self.startup_string)
            os.system('joplin sync')
        
            stop_threads = True
            t_wheel_led.join()
        
        self.thermo = Thermometer()
        self.update_thermo()
                    
        schedule.every(60).seconds.do(self.update_values)
        schedule.every().day.at("20:30").do(self.led.set_night_lights)  # ToDO
        self.update_thread = threading.Thread(target=self.scheduler, daemon=True)
        self.update_thread.start()
    
    def __del__(self):
        self.exiting = True
        self.wait()

    
    def run(self):
        """
        This function is the background loop, which listens and decides what to do if the right words are spoken.
        :return:
        """
        # Note: This is never called directly. It is called by Qt once the
        # thread environment has been set up.

        self._startup()
        # Main loop always running and listening for your hotwords (Blueberry)
        while True:
            self.led.set_standby_leds()
            if self.listen_for_hotword():
                word = self.listen_for_command()
                words = set(word.split())
                #checking if a command exists and executing it
                for func_name, hotwords in cfg.commands.items():
                    if any(command.issubset(words) for command in hotwords):
                        func = getattr(self, func_name, None)
                        if callable(func):
                            func()
                        else:
                            self.output.emit("I recognized your command and want to help you but your function is not in my memory. Please teach me!")
                        break
                #start an activity as specified in the config
                activity = words.intersection(set(cfg.assistant["activities"]))
                if len(activity) == 1:
                    self.start_activity(activity.pop())
                #setting hue scenes simply according to the name
                if self.hue_connected:
                    scene = words.intersection(set(self.hue.scenes_df['name']))
                    if len(scene) == 1:
                        self.hue.set_scene_by_name(scene.pop())
                        self.output.emit('I understood: ' + word + '\n\n' + 'I changed the scene of your lights for you!')
                #clearing the LEDs
                with self.led.led_lock:
                    self.led.leds.clear_strip()
                    self.thermo.show_temperature(self.led.leds)
        
    def listen_for_command(self):
        """
        wakes up blueberry, listens, displays what was understood and returns the wordstring
        """
        os.system('xset dpms force on')
        word = self.listen_and_think()
        self.current_tab_signal.emit(0)
        self.output.emit('I understood: {}'.format(word))
        time.sleep(1)
        return word
    
    def take_note(self, todo=False, rgb=(0, 192, 16)):
        """
        Speech is transcribed, stored in Joplin (the note taking app) and syncronized
        :param rgb: Colors of the LEDs
        :return:
        """
        self.output.emit('I am eager to listen for your note!')
        word = self.listen_and_think(rgb, chunk_length=5)
        self.output.emit('I understood: {} \n \n now synchronizig...'.format(word))
        with self.led.led_lock:
            print('recorded note: ' + word)
            stop_threads = False
            t_wheel_led = threading.Thread(target=self.led.run_color_wheel, args=(lambda: stop_threads, ))
            t_wheel_led.start()
            note_title = ' '.join(word.split()[:5])
            JoplinHelper.write_note(word, note_title, cfg.assistant["joplin_folder"], is_todo=todo)
            os.system('joplin sync')
            stop_threads = True
            t_wheel_led.join()
        
    def write_todo(self, rgb=(0, 192, 16)):
        """creates a task in Joplin, convenience function"""
        self.take_note(todo = True, rgb=rgb)
        
    def show_notes(self):
        """switches to the note tab to dispay the notes for your current activities"""
        self.current_tab_signal.emit(2)
    
    def shut_down(self):
        """ shuts down the rasperry pi"""
        os.system('xset dpms force off')
        self.led.set_shutdown_leds()
        self.audio_stream.close()
        time.sleep(0.2)
        self.pa.terminate()
        time.sleep(0.2)
        try:
            os.system('joplin sync')
        except:  # Todo
            pass
        finally:
            self.led.leds.clear_strip()
            self.power.off()
            os.system('sudo shutdown')
            
    def start_work_out(self):
        """Starts tracking the workout time and also sets the hue lamps to a cold white"""
        self.activity_signal.emit('sport')
        self.start_activity_signal.emit(True)
        self.current_tab_signal.emit(3)
        if self.hue_connected:
            self.hue.set_scene_by_name('energize') # Pre defined hue scene
            
    def start_activity(self, activity='start'):
        """
        starts tracking of the specified activity
        activity: (str) activity to start, if it's simply start (default) then the one up next is started)
        """
        self.activity_signal.emit(activity)
        self.start_activity_signal.emit(True)
        self.current_tab_signal.emit(3)
        
    def stop_activity(self):
        """stops the tracking of the current activity"""
        self.stop_activity_signal.emit(True)
        self.current_tab_signal.emit(3)
        
    def increase_brightness(self):
        """increases the brightness of your hue lights"""
        if self.hue_connected:
            self.hue.increase_brightness()
        else:
            self.output.emit('I am sorry, but your hue lights are not connected')
            
    def reduce_brightness(self):
        """reduces the brightness of your hue lights"""
        if self.hue_connected:
            self.hue.reduce_brightness()
        else:
            self.output.emit('I am sorry, but your hue lights are not connected')
            
    def _find_device_index(self, name=cfg.assistant['soundcard_name']):
        """
        Getting the device index from pyaudio to specify the soundcard
        :param name: Name of your soundcard
        :return:
        """
        devices = self.pa.get_device_count()
        for i in range(devices):
            dev_name = self.pa.get_device_info_by_index(i)['name']
            if name in dev_name:
                self.startup_string += '\n soundcard found with index {}'.format(i)
                self.output.emit(self.startup_string)
                return i
            
        self.startup_string = 'Dang! No soundcard here, trying to reinstall and reboot'
        self.output.emit(self.startup_string)
        if name == 'seeed-4mic-voicecard':  # change accordinly to your driver
            os.system('sudo /home/pi/seeed-voicecard/install.sh')
            os.system('sudo reboot')

    def update_thermo(self):
        """
        Changes the LEDs according to the current temperature
        :return:
        """
        with self.led.led_lock:
            self.thermo.show_temperature(self.led.leds, value=self.led.thermo_led_value)
        temp, hum, press = self.thermo.get_temperature()
        self.air_signal.emit('Temperature: {:.2f} °C\nHumidity: {:.2f} %\nPressure: {} hPa'.format(temp, hum, int(press)))
            
    def measure_silence_level(self, length=2):
        """
        Measures the background noise, which acts as the baseline for when to stop listening after speech
        has been finished
        :param length: duration for the measurement
        :return:
        """
        with self.listen_lock:
            last_second = np.frombuffer(self.audio_stream.read(self.porcupine.sample_rate*length,
                                                           exception_on_overflow=False), dtype=np.int16)
        #pcm2 = struct.unpack_from("h" * len(audio), audio)
        silence_level = np.median(np.abs(last_second))  # don't need to reshape array because of median
        if silence_level < 60:  # There seems to be some fluctuations, better be safe
            silence_level = 60
        print(silence_level)
        return silence_level
    
    def update_values(self):
        """
        Updates silence level and temperature
        :return:
        """
        self.silence_level = self.measure_silence_level()
        self.update_thermo()
            
    def scheduler(self):
        """
        Starts the scheduler for the re-occuring taks
        :return:
        """
        while True:
            schedule.run_pending()
            time.sleep(1)

    def listen_for_hotword(self):
        """
        Listens in the background for the hotword from porcupine, if it has been recognized, recording (listen for
        speech) will be started (in the run function) and analyzed with deepspeech
        :return: True, if hotword has been heard, else False
        """
        with self.listen_lock:
            pcm = self.audio_stream.read(self.porcupine.frame_length, exception_on_overflow=False)
        pcm = struct.unpack_from("h" * self.porcupine.frame_length*4, pcm)[0::4]
        result = self.porcupine.process(pcm)
        return result

    def listen_for_speech(self, chunk_length=1):
        """
        Records the spoken word as long as input volume is greater than silence levels
        :param chunk_length: minimum recording duration (one block) in sec to compare with silence level
        :return: the audio data as numpy array
        """
        audio=np.array([[],[],[],[]], dtype=np.int16) # empty array with shape (4,0)
        time.sleep(0.2)  # usual reaction time to not end listening to early
        last_seconds = np.frombuffer(self.audio_stream.read(self.porcupine.sample_rate*chunk_length,
                                                           exception_on_overflow=False),
                                     dtype=np.int16).reshape(4,-1, order='F')
        audio = np.append(audio, last_seconds, axis=1)
        #pcm2 = struct.unpack_from("h" * len(audio), audio)
        while np.median(np.abs(last_seconds))>self.silence_level+20:
            last_seconds = np.frombuffer(self.audio_stream.read(self.porcupine.sample_rate*chunk_length,
                                                               exception_on_overflow=False),
                                        dtype=np.int16).reshape(4,-1, order='F')
            audio = np.append(audio, last_seconds, axis=1)
        print('finished_listening')
        
        # simple beamforming, does not matter much due to short distance though
        for i in np.arange(1,4):
            c = sg.correlate((audio[0]-np.mean(audio[0]))/np.std(audio[0]), (audio[i,:]-np.mean(audio[i,:]))/np.std(audio[i,:]))
            lag = np.arange(-audio.shape[1]+1, audio.shape[1])[np.argmax(c)]
            if lag > 0:
                audio[i,:] = np.append([0]*lag, audio[i,:-lag])
            elif lag < 0:
                audio[i,:] = np.append(audio[i,-lag:],[0]*(-1*lag))
        audio = np.mean(audio.astype(np.float64),axis=0)
        
        return audio.astype(np.int16)
    
    def listen_and_think(self, rgb=None, chunk_length=1):
        """
        calls the listen function first and then transribes the data with mozilla deepspech engine.
        Also leds the leds blink
        :param rgb: Tuple (RGB) of the color for the LEDs to blink with
        :param chunk_length: minimum recording duration (one block) in sec to compare with silence level
        :return: the transcribed text as a string
        """
        with self.led.led_lock:
            if rgb:
                self.led.set_listening_leds(rgb)
            else:
                self.led.set_listening_leds()
            with self.listen_lock:
                audio = self.listen_for_speech(chunk_length=chunk_length)
            stop_threads = False
            t_think_led = threading.Thread(target=self.led.set_thinking_leds, args=(lambda: stop_threads, ))
            t_think_led.start()
            word = self.ds_model.stt(audio)
            stop_threads = True
            t_think_led.join()
            return word
