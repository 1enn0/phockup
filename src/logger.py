import pickle
import datetime

ACTIONS_STR = [
    'copy',
    'move',
    'link',
    'skip',
    'ignore',
]

class Logger ():

    ACTION_COPY = ACTIONS_STR.index('copy')
    ACTION_MOVE = ACTIONS_STR.index('move')
    ACTION_LINK = ACTIONS_STR.index('link')
    ACTION_SKIP = ACTIONS_STR.index('skip')
    ACTION_IGNORE = ACTIONS_STR.index('ignore')

    def __init__ (self):
        self.entries = {}

    def add_entry (self, hashsum, src, dst, action):
        assert action in [Logger.ACTION_COPY, Logger.ACTION_MOVE, Logger.ACTION_LINK, Logger.ACTION_SKIP, Logger.ACTION_IGNORE], "illegal action in Logger.add_entry()"
        
        entry = {
            'src': src,
            'dst': dst,
            'action': ACTIONS_STR[action],
            'timestamp': datetime.datetime.now(),
        }

        if hashsum in self.entries:
            self.entries[hashsum].append(entry)
        else:
            self.entries[hashsum] = [entry]

    def save_to_disk (self, filename):
        with open(filename, 'wb') as f:
            pickle.dump(self.entries, f)

    def read_from_disk (self, filename):
        with open(filename, 'rb') as f:
            self.entries = pickle.load (f)
