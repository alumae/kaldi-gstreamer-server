#! /bin/bash

BASE_URL=http://kaldi-asr.org/models/11/
MODEL=0011_multi_cn_chain_sp_online_v2.tar.gz

modeldir=`dirname $0`/chinese

mkdir -p $modeldir

cd $modeldir

wget -N $BASE_URL/$MODEL || exit 1
tar -zxvf $MODEL
rm $MODEL

sed -i 's/=.*\/conf/=test\/models\/chinese\/multi_cn_chain_sp_online\/conf/g' multi_cn_chain_sp_online/conf/online.conf
sed -i 's/=.*\/conf/=test\/models\/chinese\/multi_cn_chain_sp_online\/conf/g' multi_cn_chain_sp_online/conf/ivector_extractor.conf

cd -
