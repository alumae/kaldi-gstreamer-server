import json
import logging

import tornado.websocket


class WorkerSocketHandler(tornado.websocket.WebSocketHandler):
    def __init__(self, application, request, **kwargs):
        tornado.websocket.WebSocketHandler.__init__(self, application,
                                                    request, **kwargs)
        self.client_socket = None

    # needed for Tornado 4.0
    def check_origin(self, origin):
        return True

    def open(self):
        self.client_socket = None
        self.application.available_workers.add(self)
        logging.info("New worker available " + self.__str__())
        self.application.send_status_update()

    def on_close(self):
        logging.info("Worker " + self.__str__() + " leaving")
        self.application.available_workers.discard(self)
        if self.client_socket:
            self.client_socket.close()
        self.application.send_status_update()

    def on_message(self, message):
        assert self.client_socket is not None
        event = json.loads(message)
        self.client_socket.send_event(event)

    def set_client_socket(self, client_socket):
        self.client_socket = client_socket
