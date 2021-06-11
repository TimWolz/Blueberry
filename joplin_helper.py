import requests
import subprocess
import sqlite3
import config as cfg


class JoplinHelper:
    """
    Class to communicate via the joplin api to store and extract notes.
    """

    proc = subprocess.Popen(["joplin", "server", "status"], stderr=subprocess.STDOUT, stdout=subprocess.PIPE,)
    out = proc.stdout.read()
    if 'not' in (str(out).split()):  # Server is not yet running
        proc = subprocess.Popen(["joplin", "server", "start"], stderr=subprocess.STDOUT, stdout=subprocess.PIPE,)
    token = cfg.joplin['token']
    url = cfg.joplin['url']
    params = {'fields':'id, title, body, is_todo', 'token': token}
    
    @classmethod
    def get_token(cls, path=None):
        """
        extracts the token from the joplin database, necessary for every api call
        path: path to joplin database if not installed in default folder
        :return: token (str)
        """
        if path is None:
            path = r'/home/pi/.config/joplin/database.sqlite'
        conn = sqlite3.connect(path)
        c = conn.cursor()
        t = ('api.token',)
        c.execute('select * from settings where key=?', t)
        return c.fetchone()[1]
    
    @classmethod
    def get_notes(cls, search_word):
        """
        gets the notes via the Joplin api, search word is looked for in tags, tods and content
        :param search_word: word to search your notes for (str)
        :return: dictionary containing the notes with items tag, todo, content
        """
        notes_all = {'tag': [], 'todo': [], 'content': []}
        try:
            notes_tag = requests.get(cls.url+'search?query=tag:{}'.format(search_word), cls.params).json()
            notes = requests.get(cls.url+'search?query={}'.format(search_word), cls.params).json()
            print(notes)
        except requests.exceptions.ConnectionError:
            print('Connection Error')
            return notes_all
        notes_all['tag'] += notes_tag['items']
        if 'items' in notes.keys():
            for note in notes['items']:
                if bool(note['is_todo']):
                    notes_all['todo'].append(note)
                else:
                    notes_all['content'].append(note)
        return notes_all

    @classmethod
    def write_note(cls, note, title, notebook, is_todo=False):
        """
        writes notes into specified notebook via joplin api
        :param note: body of the note (str)
        :param title: title of the note (str)
        :param notebook: notebook to store the note in (str)
        :param is_todo: whether or not the note is a todo (bool)
        :return:
        """
        results = requests.get(cls.url+'search?query={}&type=folder'.format(notebook), {'token': cls.token}).json()
        notebook_id = results['items'][0]['id']
        result = requests.post(cls.url+'notes?token='+cls.token,
                               json={"title": title, "body": note, "parent_id": notebook_id, 'is_todo':is_todo})
