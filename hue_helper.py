import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import json
import time
import pandas as pd
import config as cfg

url = cfg.hue["user"]
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class HueHelper:
    """
    This class helps controlling Hue lights via a Hue bridge. Data is collected from the bridge and stored in
    a pandas data frame
    """
    # get groups to switch on and off
    r = requests.get(url+'/groups', verify=False)
    groups_df = pd.DataFrame.from_dict(r.json(), orient='index')
    groups_df = groups_df.loc[groups_df['type'] != 'Entertainment']

    def __init__(self, group_number=cfg.hue["standard_group"]):
        r = requests.get(url+'/scenes', verify=False)
        self.group_number = group_number
        self.scenes_df = pd.DataFrame.from_dict(r.json(), orient='index')
        self.scenes_df = self.scenes_df.loc[self.scenes_df['group'] == str(self.group_number)]
        self.scenes_df['name'] = self.scenes_df['name'].str.lower()

    def extract_scene_id_by_name(self, name):
        """
        gets the id of the chosen scene
        :param name: name of the scene you want to set
        :return:
        """
        list_index = self.scenes_df.index[self.scenes_df['name'] == name].tolist()
        if len(list_index) == 1:
            return list_index[0]
        else:
            return False

    def set_scene(self, scene_id):
        """
        sets the scene by ID
        :param scene_id: scene_id as defined by HUE
        :return:
        """
        _ = requests.put(url+'/groups/{}/action'.format(self.group_number),
                         data=json.dumps({"on": True, "scene": scene_id}), verify=False)

    def set_scene_by_name(self, name):
        """
        convenience function to set the scene by name instead of ID
        :param name: name of the scene you want to set
        :return:
        """
        id = self.extract_scene_id_by_name(name)
        if id:
            self.set_scene(id)
        
    def get_brightness(self):
        """
        asks the current brightness level (0-255) of the default groupe
        :return: int value of brightness
        """
        return int(requests.get(url+'/groups/{}'.format(self.group_number), verify=False).json()['action']['bri'])

    def reduce_brightness(self, multiplicator=0.7):
        """
        reduces the brightnes by a certain amount (mulitplicater)
        :param multiplicator: float value between 0 and 1
        :return:
        """
        brightness = self.get_brightness()
        new_brightness = brightness*multiplicator
        requests.put(url+'/groups/{}/action'.format(self.group_number),
                     data=json.dumps({"bri": int(new_brightness)}), verify=False)
        
    def increase_brightness(self, multiplicator=0.7):
        """
        increases the brightnes by a certain amount (mulitplicater)
        :param multiplicator: float value between 0 and 1
        :return:
        """
        brightness = self.get_brightness()
        new_brightness = brightness/multiplicator
        if new_brightness > 254:
            new_brightness = 254
        requests.put(url+'/groups/1/action', data=json.dumps({"bri": int(new_brightness)}), verify=False)

    def set_brightness(self, value):
        """
        sets the brightness directly
        :param value: int value between 0 and 255
        :return:
        """
        if value > 254:
            value = 254
        elif value < 0:
            value = 0
        requests.put(url + '/groups/1/action', data=json.dumps({"bri": int(value)}), verify=False)

    def get_temperature(self, group_number=None):
        """
        gets the temperature of the group
        :param group_number: number of the group to request, if not specified, default group is used
        return: temperature value
        """
        if group_number is None:
            group_number = self.group_number
        return int(requests.get(url+'/groups/{}'.format(group_number), verify=False).json()['action']['ct'])
    
    def set_temperature(self, value, group_number=None):
        """
        sets the temperature of the group
        :param group_number: number of the group to request, if not specified, default group is used
        return: temperature value
        """
        if value > 500:
            value = 500
        elif value < 153:
            value = 153
        if group_number is None:
            group_number = self.group_number
        requests.put(url+'/groups/{}/action'.format(group_number), data=json.dumps({"ct": int(value)}), verify=False)
    
    def turn_on(self, name):
        """
        allows to turn on lights of a specific group
        :param name: name of the group
        :return:
        """
        index = HueHelper.groups_df.index[HueHelper.groups_df['name'] == name].tolist()[0]
        if index:
            requests.put(url + '/groups/{}/action'.format(index), data=json.dumps({'on': True}), verify=False)

    def turn_off(self, name):
        """
        allows to turn off lights of a specific group
        :param name: name of the group
        :return:
        """
        index = HueHelper.groups_df.index[HueHelper.groups_df['name'] == name].tolist()[0]
        if index:
            requests.put(url + '/groups/{}/action'.format(index), data=json.dumps({'on': False}), verify=False)

    def get_status(self, name):
        """gets on/off status of the group"""
        index = HueHelper.groups_df.index[HueHelper.groups_df['name'] == name].tolist()[0]
        return requests.get(url + '/groups/{}'.format(index), verify=False).json()['action']['on']

    def set_alert(self, duration=5, group_number=None):
        """
        lets your light blinks
        :param duration: duration of blinking in seconds
        :param group_number: of the lights to control
        :return:
        """
        if group_number is None:
            group_number = self.group_number
        if duration > 15:  # max value
            duration = 15
        requests.put(url + '/groups/{}/action'.format(group_number), data=json.dumps({'alert': 'lselect'}),
                     verify=False)
        time.sleep(duration)
        requests.put(url + '/groups/{}/action'.format(group_number), data=json.dumps({'alert': 'none'}),
                     verify=False)
