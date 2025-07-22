from threading import Lock
class UserDataManger:
    def __init__(self):
        self._user_data = {}
        self._set_lock = Lock()
        self._get_lock = Lock()

    def set_user_data(self, session_id, data):
        with self._set_lock:
            self._user_data[session_id] = data

    def get_user_data(self, session_id):
        with self._get_lock:
            return self._user_data.get(session_id)