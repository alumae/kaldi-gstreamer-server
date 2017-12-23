FROM debian:9
LABEL Author="Paulius Sukys <paul.sukys@gmail.com>"

# TODO: for next image release, move python3.6 installation here
RUN apt update && apt install -y autoconf \
                                 automake \
                                 g++ \
                                 git \
                                 gstreamer1.0-plugins-good \
                                 gstreamer1.0-tools \
                                 gstreamer1.0-pulseaudio \
                                 gstreamer1.0-plugins-bad \
                                 gstreamer1.0-plugins-base \
                                 gstreamer1.0-plugins-ugly  \
                                 libatlas3-base \
                                 libgstreamer1.0-dev \
                                 libtool-bin \
                                 libjansson4 \
                                 libjansson-dev \
                                 make \
                                 python2.7 \
                                 python3 \
                                 python-pip \
                                 python-yaml \
                                 python-simplejson \
                                 python-gi \
                                 subversion \
                                 wget \
                                 zlib1g-dev

RUN apt clean autoclean && \
    apt autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Server dependencies, TODO: move to requirements.txt or even better pypy package
RUN pip install ws4py==0.3.2 tornado

# Set default Python
RUN update-alternatives --install /usr/bin/python python /usr/bin/python2.7 1

# Set default Shell
RUN chsh -s $(which bash)

WORKDIR /opt

# Setup Kaldi
RUN git clone https://github.com/kaldi-asr/kaldi
RUN cd /opt/kaldi/tools && make && ./install_portaudio.sh && \
    cd /opt/kaldi/src && ./configure --shared && \
    sed -i '/-g # -O0 -DKALDI_PARANOID/c\-O3 -DNDEBUG' kaldi.mk && \
    make depend && make -j 2 && \
    cd /opt/kaldi/src/online && make depend && make && \
    cd /opt/kaldi/src/gst-plugin && make depend && make
    
# Setup kaldi-gst-nnet2-online lib
RUN git clone https://github.com/alumae/gst-kaldi-nnet2-online
RUN cd /opt/gst-kaldi-nnet2-online/src && \
    sed -i '/KALDI_ROOT?=\/home\/tanel\/tools\/kaldi-trunk/c\KALDI_ROOT?=\/opt\/kaldi' Makefile && \
    make depend && make

RUN rm -rf /opt/gst-kaldi-nnet2/.git && \
    find /opt/gst-kaldi-nnet2-online/src -type f -not -name "*.so" -delete && \
    rm -rf /opt/kaldi/.git /opt/kaldi/egs /opt/kaldi/windows /opt/kaldi/misc && \
    find /opt/kaldi/src/ -type f -not -name '*.so' -delete && \
    find /opt/kaldi/tools/ -type f \( -not -name '*.so' -and -not -name '*.so*' \) -delete

RUN git clone https://github.com/shookees-TUM/kaldi-gstreamer-server.git && \
    rm -rf /opt/kaldi-gstreamer-server/.git/ && \
    rm -rf /opt/kaldi-gstreamer-server/test/    

# FIXME: python3.6 install
RUN echo 'deb http://ftp.de.debian.org/debian testing main' | tee -a /etc/apt/sources.list.d/debian-testing.list && \
    echo 'APT::Default-Release "stable";' | tee -a /etc/apt/apt.conf.d/00local && \
    apt update && \
    apt-get -t testing install -y python3.6 python3-pip

RUN pip3 install ws4py==0.3.2 tornado

ENV GST_PLUGIN_PATH=/opt/kaldi/src/gst-plugin/:/opt/gst-kaldi-nnet2-online