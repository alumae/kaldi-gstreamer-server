import logging
import os
import _thread

import gi
from gi.repository import GObject, Gst

from kaldigstserver.decoder.DecoderPipeline import DecoderPipeline

gi.require_version('Gst', '1.0')

GObject.threads_init()
Gst.init(None)


class KaldiDecoderPipeline(DecoderPipeline):
    def __init__(self, conf={}, logger=logging.getLogger(__name__)):
        self.logger = logger

        self.logger.info("Creating decoder using conf: %s" % conf)
        self.use_cutter = conf.get("use-vad", False)
        self.create_pipeline(conf)
        self.output_dir = conf.get("out-dir", None)
        if self.output_dir:
            if not os.path.exists(self.output_dir):
                os.mkdir(self.output_dir)
            elif not os.path.isdir(self.output_dir):
                raise Exception("Output directory %s already exists\
 as a file" % self.output_dir)

        self.word_handler = None
        self.eos_handler = None
        self.request_id = "<undefined>"

    def create_pipeline(self, conf):
        self.appsrc = Gst.ElementFactory.make("appsrc", "appsrc")

        self.decodebin = Gst.ElementFactory.make("decodebin", "decodebin")
        self.audioconvert = Gst.ElementFactory.make("audioconvert",
                                                    "audioconvert")
        self.audioresample = Gst.ElementFactory.make("audioresample",
                                                     "audioresample")
        self.tee = Gst.ElementFactory.make("tee", "tee")
        self.queue1 = Gst.ElementFactory.make("queue", "queue1")
        self.filesink = Gst.ElementFactory.make("filesink", "filesink")
        self.queue2 = Gst.ElementFactory.make("queue", "queue2")
        self.cutter = Gst.ElementFactory.make("cutter", "cutter")
        self.asr = Gst.ElementFactory.make("onlinegmmdecodefaster", "asr")
        self.fakesink = Gst.ElementFactory.make("fakesink", "fakesink")

        for (key, value) in conf.get("decoder", {}).items():
            self.logger.info("Setting decoder property: %s = %s" % (key, value))
            self.asr.set_property(key, value)

        self.appsrc.set_property("is-live", True)
        self.filesink.set_property("location", "/dev/null")
        self.cutter.set_property("leaky", False)
        self.cutter.set_property("pre-length",   1000 * 1000000)
        self.cutter.set_property("run-length",   1000 * 1000000)
        self.cutter.set_property("threshold", 0.01)
        if self.use_cutter:
            self.asr.set_property("silent", True)
        self.logger.info('Created GStreamer elements')

        self.pipeline = Gst.Pipeline()
        for element in [self.appsrc, self.decodebin, self.audioconvert,
                        self.audioresample, self.tee, self.queue1,
                        self.filesink, self.queue2, self.cutter, self.asr,
                        self.fakesink]:
            self.logger.debug("Adding %s to the pipeline" % element)
            self.pipeline.add(element)

        self.logger.info('Linking GStreamer elements')

        self.appsrc.link(self.decodebin)
        self.decodebin.connect('pad-added', self._connect_decoder)
        if self.use_cutter:
            self.cutter.link(self.audioconvert)

        self.audioconvert.link(self.audioresample)

        self.audioresample.link(self.tee)

        self.tee.link(self.queue1)
        self.queue1.link(self.filesink)

        self.tee.link(self.queue2)
        self.queue2.link(self.asr)

        self.asr.link(self.fakesink)

        #  Create bus and connect several handlers
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.enable_sync_message_emission()
        self.bus.connect('message::eos', self._on_eos)
        self.bus.connect('message::error', self._on_error)

        cutter_type = 'sync'
        if cutter_type == 'async':
            self.bus.connect('message::element', self._on_element_message)
        else:
            self.bus.connect('sync-message::element',
                             self._on_element_message)
        self.asr.connect('hyp-word', self._on_word)
        self.logger.info("Setting pipeline to READY")
        self.pipeline.set_state(Gst.State.READY)
        self.logger.info("Set pipeline to READY")

    def _connect_decoder(self, element, pad):
        self.logger.info("%s: Connecting audio decoder" % self.request_id)
        if self.use_cutter:
            pad.link(self.cutter.get_static_pad("sink"))
        else:
            pad.link(self.audioconvert.get_static_pad("sink"))

        self.logger.info("%s: Connected audio decoder" % self.request_id)

    def _on_element_message(self, bus, message):
        if message.has_name("cutter"):
            if message.get_structure().get_value('above'):
                self.logger.info("LEVEL ABOVE")
                self.asr.set_property("silent", False)
            else:
                self.logger.info("LEVEL BELOW")
                self.asr.set_property("silent", True)

    def _on_word(self, asr, word):
        self.logger.info("%s: Got word: %s"
                    % (self.request_id, word))
        if self.word_handler:
            self.word_handler(word)

    def _on_error(self, bus, msg):
        self.error = msg.parse_error()
        self.logger.error(self.error)
        self.finish_request()
        if self.error_handler:
            self.error_handler(self.error[0].message)

    def _on_eos(self, bus, msg):
        self.logger.info('%s: Pipeline received eos signal' % self.request_id)
        self.finish_request()
        if self.eos_handler:
            self.eos_handler[0](self.eos_handler[1])

    def finish_request(self):
        self.logger.info('%s: Finishing request' % self.request_id)
        if self.output_dir:
            self.filesink.set_state(Gst.State.NULL)
            self.filesink.set_property('location', "/dev/null")
            self.filesink.set_state(Gst.State.PLAYING)
        self.pipeline.set_state(Gst.State.NULL)
        self.request_id = "<undefined>"

    def init_request(self, id, caps_str):
        self.request_id = id
        if caps_str and len(caps_str) > 0:
            self.logger.info("%s: Setting caps to %s"
                        % (self.request_id, caps_str))
            caps = Gst.caps_from_string(caps_str)
            self.appsrc.set_property("caps", caps)
        else:
            self.appsrc.set_property("caps", None)
            pass

        if self.output_dir:
            self.pipeline.set_state(Gst.State.PAUSED)
            self.filesink.set_state(Gst.State.NULL)
            self.filesink.set_property('location', "%s/%s.raw"
                                       % (self.output_dir, id))
            self.filesink.set_state(Gst.State.PLAYING)

        self.pipeline.set_state(Gst.State.PLAYING)
        self.filesink.set_state(Gst.State.PLAYING)
        # push empty buffer (to avoid hang on client diconnect)
        buf = Gst.Buffer.new_allocate(None, 0, None)
        self.appsrc.emit("push-buffer", buf)
        self.logger.info('%s: Pipeline initialized' % (self.request_id))

    def process_data(self, data):
        self.logger.debug('%s: Pushing buffer of size %d to pipeline'
                     % (self.request_id, len(data)))
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        self.appsrc.emit("push-buffer", buf)

    def end_request(self):
        self.logger.info("%s: Pushing EOS to pipeline" % self.request_id)
        self.appsrc.emit("end-of-stream")

    def set_word_handler(self, handler):
        self.word_handler = handler

    def set_eos_handler(self, handler, user_data=None):
        self.eos_handler = (handler, user_data)

    def set_error_handler(self, handler):
        self.error_handler = handler

    def cancel(self):
        self.logger.info("%s: Cancelling pipeline" % self.request_id)
        self.pipeline.send_event(Gst.Event.new_eos())
        self.logger.info("%s: Cancelled pipeline" % self.request_id)
