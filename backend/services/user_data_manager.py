from threading import Lock
# services/user_data_manager.py
class UserDataManager:
    def __init__(self):
        self._user_data = {}
        self._set_lock = Lock()
        self._get_lock = Lock()

    def initialize_user_data(self, session_id):
        """确保用户数据结构存在，避免覆盖"""
        with self._set_lock:
            if session_id not in self._user_data:
                self._user_data[session_id] = {
                    "resume": "",
                    "paper_urls": []
                }

    def get_user_data(self, session_id):
        with self._get_lock:
            return self._user_data.get(session_id, {})

    def set_user_data(self, session_id, data):
        with self._set_lock:
            # 更新而非覆盖，保留已有字段
            self._user_data.setdefault(session_id, {}).update(data)