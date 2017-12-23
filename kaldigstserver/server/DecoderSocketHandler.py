import json
import logging

import tornado.websocket


class DecoderSocketHandler(tornado.websocket.WebSocketHandler):
    # needed for Tornado 4.0
    def check_origin(self, origin):
        return True

    def send_event(self, event):
        event["id"] = self.id
        event_str = str(event)
        if len(event_str) > 100:
            event_str = event_str[:97] + "..."
        logging.info("%s: Sending event %s to client" % (self.id, event_str))
        self.write_message(json.dumps(event))

    def open(self):
        self.id = str(uuid.uuid4())
        logging.info("%s: OPEN" % (self.id))
        logging.info("%s: Request arguments: %s"
                     % (self.id, " ".join(["%s=\"%s\""
                                          % (a, self.get_argument(a)) for a
                        in self.request.arguments])))
        self.user_id = self.get_argument("user-id", "none", True)
        self.content_id = self.get_argument("content-id", "none", True)
        self.worker = None
        try:
            self.worker = self.application.available_workers.pop()
            self.application.send_status_update()
            logging.info("%s: Using worker %s" % (self.id, self.__str__()))
            self.worker.set_client_socket(self)

            content_type = self.get_argument("content-type", None, True)
            if content_type:
                logging.info("%s: Using content type: %s"
                             % (self.id, content_type))

            self.worker.write_message(json.dumps(
                                      dict(id=self.id,
                                           content_type=content_type,
                                           user_id=self.user_id,
                                           content_id=self.content_id)))
        except KeyError:
            logging.warn("%s: No worker available for client request"
                         % self.id)
            event = dict(status=STATUS_NOT_AVAILABLE,
                         message="No decoder available, try again later")
            self.send_event(event)
            self.close()

    def on_connection_close(self):
        logging.info("%s: Handling on_connection_close()" % self.id)
        self.application.num_requests_processed += 1
        self.application.send_status_update()
        if self.worker:
            try:
                self.worker.set_client_socket(None)
                logging.info("%s: Closing worker connection" % self.id)
                self.worker.close()
            except:
                pass

    def on_message(self, message):
        assert self.worker is not None
        logging.info("%s: Forwarding client message (%s) of length %d\
 to worker" % (self.id, type(message), len(message)))
        if isinstance(message, unicode):
            self.worker.write_message(message, binary=False)
        else:
            self.worker.write_message(message, binary=True)
