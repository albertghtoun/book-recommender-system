#!/bin/bash
sudo yum install git
sudo pip install -r requirements.txt
./download_dataset.sh
#hdfs dfs -put datasets/ hdfs://ip-172-31-13-184.us-west-1.compute.internal:8020/user/hadoop/
hdfs dfs -put datasets/ hdfs://`hostname`:8020/user/hadoop/
