import abc

class DecoderPipeline(abc.ABC):

    @abc.abstractmethod
    def __init__(self, conf={}):
        pass

    @abc.abstractmethod
    def create_pipeline(self, conf):
        pass

    @abc.abstractmethod
    def _connect_decoder(self, element, pad):
        pass

    @abc.abstractmethod
    def _on_error(self, bus, msg):
        pass

    @abc.abstractmethod
    def _on_eos(self, bus, msg):
        pass

    @abc.abstractmethod
    def finish_request(self):
        pass

    @abc.abstractmethod
    def init_request(self, id, caps_str):
        pass

    @abc.abstractmethod
    def process_data(self, data):
        pass

    @abc.abstractmethod
    def end_request(self):
        pass

    @abc.abstractmethod
    def set_eos_handler(self, handler, user_data=None):
        pass

    @abc.abstractmethod
    def set_error_handler(self, handler):
        pass

    @abc.abstractmethod
    def cancel(self):
        pass
