Kaldi GStreamer server
======================

This is an implementation of a real-time full-duplex speech recognition server, based on
the Kaldi toolkit and the GStreamer framework.

Communication with the server is based on websockets. Client sends speech to the server using
small chunks, while the server sends partial and full recognition hypotheses back to
the client via the same websocket, thus enabling full-duplex communication (as in Google's
voice typing in Android). Client can be implemented in Javascript, thus enabling browser-based
speech recognition.

Installation
------------

### Requirements

#### Python 2.7 with the following packages:

  * Tornado 3, see http://www.tornadoweb.org/en/stable/
  * ws4py
  * YAML
  * JSON


#### Kaldi

Download and compile Kaldi (http://kaldi.sourceforge.net). Also compile the online extensions (`make ext`)
and the Kaldi GStreamer plugin (see `README` in Kaldi's `src/gst-plugin` directory).

#### Acoustic and language models for Kaldi

You need GMM-HMM-based acoustic and n-gram language models (actually their FST cascade) for your language.

Working (but not very accurate) recognition models are available for English and Estonian in the  `test/models/` directory.
English models are based on Voxforge acoustic models and the CMU Sphinx  2013 general English trigram language model (http://cmusphinx.sourceforge.net/2013/01/a-new-english-language-model-release/).
The language models were heavily pruned so that the resulting FST cascade would be less than the
100 MB GitHub file size limit.

*Update:* the server also supports Kaldi's new "online2" online decoder that uses DNN-based acoustic models with i-vector input. See below on
how to use it. According to experiments on two Estonian online decoding setups, the DNN-based models result in about 20% (or more) relatively less
errors than GMM-based models (e.g., WER fropped from 13% to 9%).


Running the server
------------------

### Running the master server

The following starts the main server on localhost:8888

    python kaldigstserver/master_server.py --port=8888

### Running workers


The master server doesn't perform speech recognition itself, it simply delegates client recognition
requests to workers. You need one worker per recognition session. So, the number of running workers
should be at least the number of potential concurrent recognition sessions. Good thing is that
workers are fully independent and do not even have to be running on the same machine, thus
offering practically unlimited parallelness.

There are two decoders that a worker can use: based on the Kaldi `onlinegmmdecodefaster` GStreamer plugin
or based on the newer `kaldinnet2onlinedecoder` plugin. The first one supports GMM models, the latter one needs
"online2" DNN-based models with i-vector input.

To run a worker, first write a configuration file. A sample configuration that uses the English GMM-HMM
models that come with this project is available in `sample_worker.yaml`. A sample worker that uses
"online2" DNN-based models is in `sample_english_nnet2.yaml`.

#### Using the 'onlinegmmdecodefaster' based worker

Before starting a worker, make sure that the GST plugin path includes Kaldi's `src/gst-plugin` directory
(which should contain the file `libgstkaldi.so`), something like:

    export GST_PLUGIN_PATH=~/tools/kaldi-trunk/src/gst-plugin

Test if it worked:

    gst-inspect-1.0 onlinegmmdecodefaster

The latter should print out information about the Kaldi's GStreamer plugin.

Now, you can start a worker:

    python kaldigstserver/worker.py -u ws://localhost:8888/worker/ws/speech -c sample_worker.yaml

The `-u ws://localhost:8890/worker/ws/speech` argument specifies the address of the main server
that the worker should connect to. Make sure you are using the same port as in the server invocation.

You can start any number of worker processes, just use the same command to start the next workers.

It might be a good idea to use [supervisord](http://supervisord.org) to start and stop the main server and
several workers. A sample supervisord configuration file is in `etc/english-supervisord.conf`.


#### Using the 'kaldinnet2onlinedecoder' based worker

The DNN-based online decoder requires a newer GStreamer plugin that is not in the Kaldi codebase and has to be compiled
seperately. It's available at https://github.com/alumae/gst-kaldi-nnet2-online. Clone it, e.g., under `~/tools/gst-kaldi-nnet2-online`.
Follow the instuctions and compile it. This should result in a file `~/tools/gst-kaldi-nnet2-online/src/libgstkaldionline2.so`.

Also, download the DNN-based models for English, trained on the Fisher speech corpus. Run the `download-fisher-nnet2.sh` under
`test/models` to download the models from https://kaldi-asr.org:

    ./test/models/download-fisher-nnet2.sh

Before starting a worker, make sure that the GST plugin path includes the path where the `libgstkaldionline2.so` library you compiled earlier
resides, something like:

    export GST_PLUGIN_PATH=~/tools/gst-kaldi-nnet2-online/src

Test if it worked:

    gst-inspect-1.0 kaldinnet2onlinedecoder

The latter should print out information about the new Kaldi's GStreamer plugin.

Now, you can start a worker:

    python kaldigstserver/worker.py -u ws://localhost:8888/worker/ws/speech -c sample_english_nnet2.yaml


Server usage
------------

A sample implementation of the client is in `kaldigstserver/client.py`.

If you started the server/worker as described above, you should be able to test the installation by invoking:

    python kaldigstserver/client.py -r 32000 test/data/english_test.raw

Expected output:

    THE. ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT.

Expected output when using using the DNN-based online models based on Fisher:

    one two or three you fall five six seven eight. yeah.

The `-r 32000` in the last command tells the client to send audio to the server at 32000 bytes per second. The raw
sample audio file uses a sample rate of 16k with a 16-bit encoding which results in a byterate of 32000.

You can also send ogg audio:

    python kaldigstserver/client.py -r 4800 test/data/english_test.ogg

The rate in the last command is 4800. The bit rate of the ogg file is 37.5k, which results in a byte rate of 4800.


Client-server protocol
----------------------

### Opening a session

To open a session, connect to the specified server websocket address (e.g. ws://localhost:8888/client/ws/speech).
The server assumes by default that incoming audio is sent using 16 kHz, mono, 16bit little-endian format. This can be overriden
using the 'content-type' request parameter. The content type has to be specified using GStreamer 1.0 caps format,
e.g. to send 44100 Hz mono 16-bit data, use: "audio/x-raw, layout=(string)interleaved, rate=(int)44100, format=(string)S16LE, channels=(int)1".
This needs to be url-encoded of course, so the actual request is something like:

    ws://localhost:8888/client/ws/speech?content-type=audio/x-raw,+layout=(string)interleaved,+rate=(int)44100,+format=(string)S16LE,+channels=(int)1

Audio can also be encoded using any codec recognized by GStreamer (assuming the needed packages are installed on the server).
E.g., to send audio encoded using the Speex codec in an Ogg container, use the following URL to open the session (server should
automatically recognize the codec):

    ws://localhost:8888/client/ws/speech?content-type=audio/ogg

### Sending audio

Speech should be sent to the server in raw blocks of data, using the encoding specified when session was opened.
It is recommended that a new block is sent at least 4 times per second (less infrequent blocks would increase the recognition lag).
Blocks do not have to be of equal size.

After the last block of speech data, a special 3-byte ANSI-encoded string "EOS"  ("end-of-stream") needs to be sent to the server. This tells the
server that no more speech is coming and the recognition can be finalized.

After sending "EOS", client has to keep the websocket open to receive recognition results from the server. Server
closes the connection itself when all recognition results have been sent to the client.
No more audio can be sent via the same websocket after an "EOS" has been sent. In order to process a new
audio stream, a new websocket connection has to be created by the client.

### Reading results

Server sends recognition results and other information to the client using the JSON format.
The response can contain the following fields:

  * status -- response status (integer), see codes below
  * message -- (optional) status message
  * result -- (optional) recognition result, containing the following fields:
    - hypotheses - recognized words, a list with each item containing the following:
        + transcript -- recognized words
        + confidence -- (optional) confidence of the hypothesis (float, 0..1)
    - final -- true when the hypothesis is final, i.e., doesn't change any more

The following status codes are currently in use:

  * 0 -- Success. Usually used when recognition results are sent
  * 2 -- Aborted. Recognition was aborted for some reason.
  * 1 -- No speech. Sent when the incoming audio contains a large portion of silence or non-speech.
  * 9 -- Not avalailable. Used when all recognizer processes are currently in use and recognition cannot be performed.

Websocket is always closed by the server after sending a non-zero status update.

Examples of server responses:

    {"status": 9}
    {"status": 0, "result": {"hypotheses": [{"transcript": "see on"}], "final": false}}
    {"status": 0, "result": {"hypotheses": [{"transcript": "see on teine lause."}], "final": true}}

Server segments incoming audio on the fly. For each segment, many non-final hypotheses, followed by one final
hypothesis are sent. Non-final hypotheses are used to present partial recognition hypotheses
to the client. A sequence of non-final hypotheses is always followed by a final hypothesis for that segment.
After sending a final hypothesis for a segment,
server starts decoding the next segment, or closes the connection, if all audio sent by the client has been processed.

Client is reponsible for presenting the results to the user in a way
suitable for the application.

Client software
---------------

Javascript client is available here: http://kaljurand.github.io/dictate.js

