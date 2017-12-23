# -*- coding: UTF-8 -*-

'''
Created on Jun 27, 2013

@author: tanel
'''
import unittest
from gi.repository import GLib, Gst
import _thread
import logging
from kaldigstserver.decoder.Nn2DecoderPipeline import Nn2DecoderPipeline
import time

class DecoderPipeline2Tests(unittest.TestCase):

    def __init__(self,  *args, **kwargs):
        super(DecoderPipeline2Tests, self).__init__(*args, **kwargs)
        logging.basicConfig(level=logging.INFO)

    def setUp(cls):
            decoder_conf = {"model" : "test/models/estonian/nnet2_online_ivector/final.mdl",
                            "word-syms" : "test/models/estonian/nnet2_online_ivector/words.txt",
                            "fst" : "test/models/estonian/nnet2_online_ivector/HCLG.fst",
                            "mfcc-config" : "test/models/estonian/nnet2_online_ivector/conf/mfcc.conf",
                            "ivector-extraction-config": "test/models/estonian/nnet2_online_ivector/conf/ivector_extractor.conf",
                            "max-active": 7000,
                            "beam": 11.0,
                            "lattice-beam": 6.0,
                            "do-endpointing" : True,
                            "endpoint-silence-phones":"1:2:3:4:5:6:7:8:9:10"}
            cls.decoder_pipeline = Nn2DecoderPipeline({"decoder" : decoder_conf})
            cls.final_hyps = []
            cls.words = []
            cls.finished = False

            cls.decoder_pipeline.set_result_handler(cls.result_getter)
            cls.decoder_pipeline.set_eos_handler(cls.set_finished, cls.finished)

            loop = GLib.MainLoop()
            _thread.start_new_thread(loop.run, ())

    def result_getter(cls, hyp, final):
        if final:
            cls.final_hyps.append(hyp)
        else:
            cls.words.append(hyp)

    def set_finished(cls, finished):
        cls.finished = True

    def send_data(self, data_iterator):
        for block in data_iterator:
            time.sleep(0.25)
            self.decoder_pipeline.process_data(block)

    def testCancelAfterEOS(self):
        self.decoder_pipeline.init_request("testCancelAfterEOS", "audio/x-raw, layout=(string)interleaved, rate=(int)16000, format=(string)S16LE, channels=(int)1")
        f = open("test/data/1234-5678.raw", "rb")
        self.send_data(iter(lambda: f.read(8000), ""))

        self.decoder_pipeline.end_request()
        self.decoder_pipeline.cancel()
        while not self.finished:
            time.sleep(1)

        self.maxDiff = None

        flat_words = u' '.join(self.words)
        logging.info(flat_words)

        # self.words is sequential partial transcription. Without inferring some kind of structure, it's best to just check whether this word has been transcribed
        # Unless there could be a lattice view for this
        for word in ["üks", "kaks", "kolm", "neli", 
                     "viis", "kuus", "seitse", "kaheksa"]:
            self.assertTrue(word.decode('utf-8') in flat_words)


    def test12345678(self):
        self.decoder_pipeline.init_request("test12345678", "audio/x-raw, layout=(string)interleaved, rate=(int)16000, format=(string)S16LE, channels=(int)1")
        adaptation_state = open("test/data/adaptation_state.txt").read()
        self.decoder_pipeline.set_adaptation_state(adaptation_state)
        f = open("test/data/1234-5678.raw", "rb")
        self.send_data(iter(lambda: f.read(8000), ""))

        self.decoder_pipeline.end_request()


        while not self.finished:
            time.sleep(1)
        self.assertEqual([u"üks kaks kolm neli",
                          u"viis kuus seitse kaheksa"],
                         self.final_hyps)

    def test8k(self):
        self.decoder_pipeline.init_request("test8k", "audio/x-raw, layout=(string)interleaved, rate=(int)8000, format=(string)S16LE, channels=(int)1")
        f = open("test/data/1234-5678.8k.raw", "rb")
        self.send_data(iter(lambda: f.read(4000), ""))

        self.decoder_pipeline.end_request()


        while not self.finished:
            time.sleep(1)
        self.assertEqual([u"üks kaks kolm neli",
                          u"viis kuus seitse kaheksa"],
                         self.final_hyps)

    def testDisconnect(self):
        self.decoder_pipeline.init_request("testDisconnect", "audio/x-raw, layout=(string)interleaved, rate=(int)8000, format=(string)S16LE, channels=(int)1")

        self.decoder_pipeline.end_request()


        while not self.finished:
            time.sleep(1)
        self.assertEqual([], self.final_hyps)


    def testWav(self):
        self.decoder_pipeline.init_request("testWav", "")
        f = open("test/data/test_with_silence.wav", "rb")
        self.send_data(iter(lambda: f.read(48000*2*2/4), ""))

        self.decoder_pipeline.end_request()

        while not self.finished:
            time.sleep(1)
        self.assertEqual([u"see on esimene lause pärast mida tuleb vaikus",
                          u"nüüd tuleb teine lause"],
                         self.final_hyps)


def main():
    unittest.main()

if __name__ == '__main__':
    main()