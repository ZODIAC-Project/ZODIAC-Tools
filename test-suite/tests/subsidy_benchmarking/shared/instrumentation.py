import threading

class RunCounters:
    def __init__(self):
        self._lock = threading.Lock()
        self.messages_sent = 0
        self.messages_received = 0
        self.tool_calls = 0

    def record_sent(self, n=1):
        with self._lock: 
            self.messages_sent += n

    def record_received(self, n=1):
        with self._lock: 
            self.messages_received += n

    def record_tool_call(self, n=1):
        with self._lock: 
            self.tool_calls += n

    def as_dict(self):
        return {
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "tool_calls": self.tool_calls,
        }