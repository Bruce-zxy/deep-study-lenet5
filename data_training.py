#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import random
import time
import numpy as np
import pandas as pd
import h5py
# import matplotlib.pyplot as plt
from math import cos, sin, atan2, sqrt, pi, radians, degrees, ceil, floor
import tensorflow as tf

file_time = time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))
# 数据集路径
data_path = './h5/'
train_file_path = data_path + 'normaliaztion_train_data.h5'
test_file_path = data_path + 'normaliaztion_test_data.h5'
log_path = './log/'
log_file_path = log_path + file_time + '.h5'
log_text_path = log_path + file_time + '.txt'
modal_file_path = 'mymodal'
# modal_path = './modal/'
# modal_file_path = modal_path + 'mymodal'

# 将所有的点集网格尺寸设置为32*32
w = 32
h = 32
c = 1

#将所有样本训练train_num次，每次训练中以batch_size个为一组训练完所有样本。
train_num = 1500
batch_size = 55
regulary = 0.00375
learning_rate = 0.00125
beta1 = 0.8
beta2 = 0.9
max_test_acc = float("-inf")
min_test_loss = float("inf")

train_acc_array = np.empty([0], dtype=np.float32)
train_loss_array = np.empty([0], dtype=np.float32)
test_acc_array = np.empty([0], dtype=np.float32)
test_loss_array = np.empty([0], dtype=np.float32)
test_avg_acc = 0

#搭建CNN 此函数可以理解为形参，用于定义过程，在执行的时候再赋具体的值,形参名X，y_
x = tf.placeholder(tf.float32, [None, w, h, c], name='x')
y_ = tf.placeholder(tf.int32, [None], name='y_')

# 随机打乱点集数据
def exchange_data_index(sum_data, label_data):
    cursor_index = 0
    max_range = len(sum_data)
    while cursor_index < max_range:
        random_index = random.randint(0, max_range-1)
        temp_sum_data = sum_data[0]
        temp_label_data = label_data[0]

        sum_data = np.delete(sum_data, 0, axis=0)
        label_data = np.delete(label_data, 0, axis=0)
        sum_data = np.insert(sum_data, random_index, temp_sum_data, axis=0)
        label_data = np.insert(label_data, random_index,
                               temp_label_data, axis=0)

        cursor_index += 1
    return sum_data, label_data

#每次获取batch_size个样本进行训练或测试
def get_batch(data, label, batch_size):
    for start_index in range(0, len(data)-batch_size+1, batch_size):
        slice_index = slice(start_index, start_index+batch_size)
        yield data[slice_index], label[slice_index]


def inference(input_tensor, train, regularizer):

    #第一层：卷积层，过滤器的尺寸为5×5，深度为6,不使用全0补充，步长为1。
    #尺寸变化：32×32×1->28×28×6
    '''参数的初始化：tf.truncated_normal_initializer()或者简写为tf.TruncatedNormal()、tf.RandomNormal() 去掉_initializer,大写首字母即可
    生成截断正态分布的随机数，这个初始化方法好像在tf中用得比较多mean=0.0, stddev=1.0 正态分布
    http://www.mamicode.com/info-detail-1835147.html'''
    with tf.variable_scope('layer1-conv1'):
        conv1_weights = tf.get_variable(
            'weight', [5, 5, c, 6], initializer=tf.truncated_normal_initializer(stddev=0.1))
        conv1_biases = tf.get_variable(
            'bias', [6], initializer=tf.constant_initializer(0.0))
        conv1 = tf.nn.conv2d(input_tensor, conv1_weights, strides=[
            1, 1, 1, 1], padding='VALID')
        relu1 = tf.nn.relu(tf.nn.bias_add(conv1, conv1_biases))

    #第二层：池化层，过滤器的尺寸为2×2，使用全0补充，步长为2。
    #尺寸变化：28×28×6->14×14×6
    with tf.name_scope('layer2-pool1'):
        pool1 = tf.nn.max_pool(relu1, ksize=[1, 2, 2, 1], strides=[
            1, 2, 2, 1], padding='SAME')

    #第三层：卷积层，过滤器的尺寸为5×5，深度为16,不使用全0补充，步长为1。
    #尺寸变化：14×14×6->10×10×16
    with tf.variable_scope('layer3-conv2'):
        conv2_weights = tf.get_variable(
            'weight', [5, 5, 6, 16], initializer=tf.truncated_normal_initializer(stddev=0.1))
        conv2_biases = tf.get_variable(
            'bias', [16], initializer=tf.constant_initializer(0.0))
        conv2 = tf.nn.conv2d(pool1, conv2_weights, strides=[
            1, 1, 1, 1], padding='VALID')
        relu2 = tf.nn.relu(tf.nn.bias_add(conv2, conv2_biases))

    #第四层：池化层，过滤器的尺寸为2×2，使用全0补充，步长为2。
    #尺寸变化：10×10×6->5×5×16
    with tf.variable_scope('layer4-pool2'):
        pool2 = tf.nn.max_pool(relu2, ksize=[1, 2, 2, 1], strides=[
            1, 2, 2, 1], padding='SAME')

    #将第四层池化层的输出转化为第五层全连接层的输入格式。第四层的输出为5×5×16的矩阵，然而第五层全连接层需要的输入格式
    #为向量，所以我们需要把代表每张图片的尺寸为5×5×16的矩阵拉直成一个长度为5×5×16的向量。
    #举例说，每次训练64张图片，那么第四层池化层的输出的size为(64,5,5,16),拉直为向量，nodes=5×5×16=400,尺寸size变为(64,400)
    pool_shape = pool2.get_shape().as_list()
    nodes = pool_shape[1]*pool_shape[2]*pool_shape[3]
    reshaped = tf.reshape(pool2, [-1, nodes])

    #第五层：全连接层，nodes=5×5×16=400，400->120的全连接
    #尺寸变化：比如一组训练样本为64，那么尺寸变化为64×400->64×120
    #训练时，引入dropout，dropout在训练时会随机将部分节点的输出改为0，dropout可以避免过拟合问题。
    #这和模型越简单越不容易过拟合思想一致，和正则化限制权重的大小，使得模型不能任意拟合训练数据中的随机噪声，以此达到避免过拟合思想一致。
    #本文最后训练时没有采用dropout，dropout项传入参数设置成了False，因为训练和测试写在了一起没有分离，不过大家可以尝试。
    '''tf.matmul()这个函数是专门矩阵或者tensor乘法，而不是矩阵元素对应元素相乘
    tf.multiply（）两个矩阵中对应元素各自相乘
    tf.nn.dropout(x, keep_prob):TensorFlow里面为了防止或减轻过拟合而使用的函数，它一般用在全连接层，
    x：指输入;keep_prob: 设置神经元被选中的概率,使输入tensor中某些元素变为0，其它没变0的元素变为原来的1/keep_prob大小,可以想象下，比如某些元素弃用
    在初始化时keep_prob是一个占位符,keep_prob = tf.placeholder(tf.float32).
    tensorflow在run时设置keep_prob具体的值，例如keep_prob: 0.5,train的时候才是dropout起作用的时候
    keep_prob: A scalar Tensor with the same type as x. The probability that each element is kept.'''
    with tf.variable_scope('layer5-fc1'):
        fc1_weights = tf.get_variable(
            'weight', [nodes, 120], initializer=tf.truncated_normal_initializer(stddev=0.1))
        if regularizer != None:
            tf.add_to_collection('losses', regularizer(fc1_weights))
        fc1_biases = tf.get_variable(
            'bias', [120], initializer=tf.constant_initializer(0.1))
        fc1 = tf.nn.relu(tf.matmul(reshaped, fc1_weights) + fc1_biases)
        if train:
            fc1 = tf.nn.dropout(fc1, 0.5)

    #第六层：全连接层，120->84的全连接
    #尺寸变化：比如一组训练样本为64，那么尺寸变化为64×120->64×84
    '''tf.add_to_collection：把变量放入一个集合，把很多变量变成一个列表
    tf.get_collection：从一个结合中取出全部变量，是一个列表
    tf.add_n：把一个列表的东西都依次加起来'''
    with tf.variable_scope('layer6-fc2'):
        fc2_weights = tf.get_variable(
            'weight', [120, 84], initializer=tf.truncated_normal_initializer(stddev=0.1))
        if regularizer != None:
            tf.add_to_collection('losses', regularizer(fc2_weights))
        fc2_biases = tf.get_variable(
            'bias', [84], initializer=tf.truncated_normal_initializer(stddev=0.1))
        fc2 = tf.nn.relu(tf.matmul(fc1, fc2_weights) + fc2_biases)
        if train:
            fc2 = tf.nn.dropout(fc2, 0.5)

    #第七层：全连接层（近似表示），84->10的全连接
    #尺寸变化：比如一组训练样本为64，那么尺寸变化为64×84->64×10。最后，64×10的矩阵经过softmax之后就得出了64张图片分类于每种数字的概率，
    #即得到最后的分类结果。
    with tf.variable_scope('layer7-fc3'):
        fc3_weights = tf.get_variable(
            'weight', [84, 10], initializer=tf.truncated_normal_initializer(stddev=0.1))
        if regularizer != None:
            tf.add_to_collection('losses', regularizer(fc3_weights))
        fc3_biases = tf.get_variable(
            'bias', [10], initializer=tf.truncated_normal_initializer(stddev=0.1))
        logit = tf.matmul(fc2, fc3_weights) + fc3_biases
    return logit


def start_training(train_data, train_label, test_data, test_label):

    #打乱训练数据及测试数据  np.arange()返回一个有终点和起点的固定步长的排列,
    train_image_num = len(train_data)
    # 起始点0，结束点train_image_num，步长1，返回类型array，一维
    train_image_index = np.arange(train_image_num)
    np.random.shuffle(train_image_index)
    train_data = train_data[train_image_index]
    train_label = train_label[train_image_index]

    test_image_num = len(test_data)
    test_image_index = np.arange(test_image_num)
    np.random.shuffle(test_image_index)
    test_data = test_data[test_image_index]
    test_label = test_label[test_image_index]

    #正则化，交叉熵，平均交叉熵，损失函数，最小化损失函数，预测和实际equal比较，tf.equal函数会得到True或False，
    #accuracy首先将tf.equal比较得到的布尔值转为float型，即True转为1.，False转为0，最后求平均值，即一组样本的正确率。
    #比如：一组5个样本，tf.equal比较为[True False True False False],转化为float型为[1. 0 1. 0 0],准确率为2./5=40%。
    '''规则化可以帮助防止过度配合，提高模型的适用性。（让模型无法完美匹配所有的训练项。）（使用规则来使用尽量少的变量去拟合数据）
        规则化就是说给需要训练的目标函数加上一些规则（限制），让他们不要自我膨胀。
        TensorFlow会将L2的正则化损失值除以2使得求导得到的结果更加简洁 
        如tf.contrib.layers.apply_regularization/l1_regularizer/l2_regularizer/sum_regularizer
        https://blog.csdn.net/liushui94/article/details/73481112
        sparse_softmax_cross_entropy_with_logits()是将softmax和cross_entropy放在一起计算
        https://blog.csdn.net/ZJRN1027/article/details/80199248'''

    global regulary, learning_rate, beta1, beta2
    regularizer = tf.contrib.layers.l2_regularizer(regulary)
    y = inference(x, False, regularizer)
    # y = inference(x, True, regularizer)
    cross_entropy = tf.nn.sparse_softmax_cross_entropy_with_logits(
        logits=y, labels=y_)
    cross_entropy_mean = tf.reduce_mean(cross_entropy)
    loss = cross_entropy_mean + tf.add_n(tf.get_collection('losses'))
    train_op = tf.train.AdamOptimizer(
        learning_rate=learning_rate, beta1=beta1, beta2=beta2).minimize(loss)
    correct_prediction = tf.equal(tf.cast(tf.argmax(y, 1), tf.int32), y_)
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))
    saver = tf.train.Saver()

    #创建Session会话
    with tf.Session() as sess:

        if os.access(modal_file_path + '.meta', os.F_OK) == True:
            saver = tf.train.import_meta_graph(modal_file_path + '.meta')
            saver.restore(sess, tf.train.latest_checkpoint('./'))
        else:
            #初始化所有变量(权值，偏置等)
            sess.run(tf.global_variables_initializer())

        # sess.run(tf.global_variables_initializer())
        for i in range(train_num):

            train_loss, train_acc, batch_num = 0, 0, 0
            for train_data_batch, train_label_batch in get_batch(train_data, train_label, batch_size):
                _, err, acc = sess.run([train_op, loss, accuracy], feed_dict={
                    x: train_data_batch, y_: train_label_batch})
                train_loss += err
                train_acc += acc
                batch_num += 1
            global train_acc_array, train_loss_array
            train_acc_array = np.append(train_acc_array, np.asarray(
                [train_loss/(batch_num)]), axis=0)
            train_loss_array = np.append(train_loss_array, np.asarray(
                [train_acc/(batch_num)]), axis=0)
            # print('【训练#第%d轮共%d批，每批%d个元数据】' % (i+1, batch_num, batch_size))
            # print("train loss:", train_loss/batch_num)
            # print("train acc:", train_acc/batch_num)

            test_loss, test_acc, batch_num = 0, 0, 0
            for test_data_batch, test_label_batch in get_batch(test_data, test_label, batch_size):
                err, acc = sess.run([loss, accuracy], feed_dict={
                                    x: test_data_batch, y_: test_label_batch})
                test_loss += err
                test_acc += acc
                batch_num += 1
            avg_acc = test_acc/(batch_num)
            avg_loss = test_loss/(batch_num)
            global test_acc_array, test_loss_array, max_test_acc, min_test_loss, test_avg_acc
            test_acc_array = np.append(test_acc_array, np.asarray(
                [avg_acc]), axis=0)
            test_loss_array = np.append(test_loss_array, np.asarray(
                [avg_loss]), axis=0)
            test_avg_acc = i/(i+1)*test_avg_acc + 1/(i+1)*avg_acc
            if max_test_acc < avg_acc:
                max_test_acc = avg_acc
            if min_test_loss > avg_loss:
                min_test_loss = avg_loss
            print('【测试-第%d轮共%d批，每批%d个元数据】' % (i+1, batch_num, batch_size))
            print("test loss:", avg_loss)
            print("test acc:", avg_acc)

        saver.save(sess, modal_file_path)


if __name__ == "__main__":

    with h5py.File(train_file_path, 'r') as f:
        normalized_train_data = f['data'][()]
        rand_train_typical_data = f['label'][()]

    with h5py.File(test_file_path, 'r') as f:
        normalized_test_data = f['data'][()]
        rand_test_typical_data = f['label'][()]

    print(normalized_train_data.shape)
    print(normalized_test_data.shape)

    start_time = time.time()

    start_training(normalized_train_data, rand_train_typical_data,
                   normalized_test_data, rand_test_typical_data)

    end_time = time.time()

    if os.access(log_file_path, os.F_OK) == True:
        os.remove(log_file_path)
    open(log_file_path, 'w')
    with h5py.File(log_file_path, 'r+') as f:
        f.create_dataset('train_acc', data=train_acc_array)
        f.create_dataset('train_loss', data=train_loss_array)
        f.create_dataset('test_acc', data=test_acc_array)
        f.create_dataset('test_loss', data=test_loss_array)
    with open(log_text_path, 'w') as f:
        f.write('regulary:' + str(regulary) + '\r\n')
        f.write('learning_rate:' + str(learning_rate) + '\r\n')
        f.write('beta1:' + str(beta1) + '\r\n')
        f.write('beta2:' + str(beta2) + '\r\n')
        f.write('train_num:' + str(train_num) + '\r\n')
        f.write('batch_size:' + str(batch_size) + '\r\n')
        f.write('test_avg_acc:' + str(test_avg_acc) + '\r\n')
        f.write('max_test_acc:' + str(max_test_acc) + '\r\n')
        f.write('min_test_loss:' + str(min_test_loss) + '\r\n')
        f.write('time:' + str(end_time - start_time) + 's\r\n')
        f.close()

    # acc_len = len(test_acc_array)
    # plt.plot([i for i in range(acc_len)], test_acc_array)
    # plt.show()

    # plt.plot([i for i in range(acc_len)], test_loss_array)
    # plt.show()
