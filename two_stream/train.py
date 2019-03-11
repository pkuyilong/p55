# /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8

import os
import torch
import numpy as np
from torch.utils.data import DataLoader
import torch.nn as nn
import torch.optim as optim
from torchvision import models
from dataset import VideoDataset

device = torch.device('cuda:2')

train_data = VideoDataset(
    root_dir='/home/datasets/mayilong/PycharmProjects/p55/data/rgb_flow_300',
    split_data='/home/datasets/mayilong/PycharmProjects/p55/data/split_data',
    split='train',
    )
val_data = VideoDataset(
    root_dir='/home/datasets/mayilong/PycharmProjects/p55/data/rgb_flow_300',
    split_data='/home/datasets/mayilong/PycharmProjects/p55/data/split_data',
    split='val',
    )

train_loader = DataLoader(train_data, batch_size=8, shuffle=True, num_workers=4)
val_loader = DataLoader(val_data, batch_size=4, shuffle=True, num_workers=4)

n_epoch = 150
lr = 0.0001
interval = 50

class Model(nn.Module):
    def __init__(self, n_class):
        super().__init__()
        self.rgb_extractor = models.vgg16(pretrained=True).features
        self.flow_extractor = models.vgg16(pretrained=True).features

        old_param = self.flow_extractor[0].weight.data
        old_param = torch.mean(old_param, dim=1, keepdim=True)
        new_param = old_param.repeat(1, 20, 1, 1)
        self.flow_extractor[0] = nn.Conv2d(20, 64, 3, 1, 1)
        self.flow_extractor[0].weight.data = new_param

        self.conv1 = nn.Conv2d(1024, 512, 3, 1)
        self.conv2 = nn.Conv2d(512, 32, 3, 1)
        self.fc = nn.Linear(32*3*3, n_class)

    def forward(self, rgb_buf, flow_buf):
        rgb_features = self.rgb_extractor(rgb_buf)
        flow_features = self.flow_extractor(flow_buf)
        features = torch.cat((rgb_features, flow_features), dim=1)
        # print('features size ', features.size())
        outputs = self.conv1(features)
        # print('output1 size', outputs.size())
        outputs = self.conv2(outputs)
        # print('output2 size', outputs.size())
        outputs = outputs.view(-1, 32*3*3)
        # print('reshape size', outputs.size())
        outputs = self.fc(outputs)
        return outputs

model = Model(7)
model = model.to(device)

criterion = nn.CrossEntropyLoss()
# optimizer = optim.SGD([{'params':rgb_model.model.classifier.parameters()}, {'params':flow_model.model.classifier.parameters()}], lr=lr, momentum=0.9, weight_decay=0.0005 )
optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=0.0005 )
scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.2, patience=5)
# scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=10, gamma=0.2, last_epoch=-1)

def train_model(model, n_epoch, optimizer, scheduler, train_loader, val_loader, model_dir):
    print('Start trianning')
    record = open('./{}.txt'.format(os.path.basename(__file__).split('.')[0]), 'w+')
    for epoch in range(n_epoch):
        model.train()
        corrects = 0
        total_loss = 0
        total = 0
        loss = 0

        for idx, (rgb_buf, flow_buf, labels) in enumerate(train_loader):
            rgb_buf = rgb_buf.to(device)
            flow_buf = flow_buf.to(device)
            labels = labels.to(device)

            outputs = model(rgb_buf, flow_buf)
            loss = criterion(outputs, labels)

            _, pred_label = torch.max(outputs, 1)

            total_loss += loss.item()
            corrects += torch.sum(pred_label == labels).item()
            total += rgb_buf.size(0)

            print('pred label', pred_label)
            print('true label', labels)

            if (idx+1) %  interval == 0:
                print('[acc-{:.4f}, loss-{:.4f} [{}/{}]'.format(corrects/total, total_loss/total, corrects, total))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        print('[train-{}/{}] [acc-{:.4f}, loss-{:.4f}] [{}/{}]\n'.format(epoch, n_epoch, corrects/total, total_loss/total, corrects, total))

        with open('./{}.txt'.format(os.path.basename(__file__).split('.')[0]),  'a+') as record:
            record.write('[train-{}/{}] [acc-{:.4f}, loss-{:.4f}] [{}/{}]\n'.
                    format(epoch, n_epoch, corrects/total, total_loss/total, corrects, total))

        model.eval()
        with torch.no_grad():
            corrects = 0
            total = 0
            total_loss = 0

            for idx, (rgb_buf, flow_buf, labels) in enumerate(val_loader):
                rgb_buf = rgb_buf.to(device)
                flow_buf = flow_buf.to(device)
                labels = labels.to(device)

                outputs = model(rgb_buf, flow_buf)

                loss = criterion(outputs, labels)
                total_loss += loss.item()
                total += rgb_buf.size(0)
                _, pred_labels = torch.max(outputs, 1)
                corrects += torch.sum(pred_labels == labels).item()

            # may modify learning rate
            scheduler.step(loss)
            print('[val-{}/{}] [acc-{:.4f}, loss-{:.4f}] [{}/{}]\n'.format(epoch, n_epoch, corrects/total, total_loss/total, corrects, total))

            with open(os.path.join(os.getcwd(), '{}.txt'.format(os.path.basename(__file__).split('.')[0])), 'a+') as record:
                record.write('[val-{}/{}] [acc-{:.4f}, loss-{:.4f}] [{}/{}]\n'.
                        format(epoch, n_epoch, corrects/total, total_loss/total, corrects, total))

            if corrects/total >= 0.70:
                try:
                    if not os.path.exists(model_dir):
                        os.makedirs(model_dir)

                    torch.save(model.state_dict(), os.path.join(model_dir,'two_stream_{:.4f}.pth'.format(corrects/total)))

                except Exception as e:
                    print(str(e))
                    with open(os.path.join(os.getcwd(), '{}.txt'.format(os.path.basename(__file__).split('.')[0])), 'a+') as record:
                        record.write('[ERROR] ' + str(e) + '\n')

if __name__ == '__main__':
    train_model(model,
                n_epoch,
                optimizer,
                scheduler,
                train_loader,
                val_loader,
                os.path.join(os.getcwd(), 'trained_model'))