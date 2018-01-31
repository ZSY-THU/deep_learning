# @author Tasuku Miura
# @brief PyTorch implementation of PilotNet (Assumes CUDA enabled)

import os
import pickle

from skimage import io, transform
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable

from torch.utils.data import Dataset, DataLoader, ConcatDataset
from torchvision import transforms, utils

# used for logging to TensorBoard
from tensorboard_logger import configure, log_value

from data_loader import *
from pilot_net import *

import math



def train_one_epoch(epoch, model, loss_fn, optimizer, train_loader):
    model.train()
    print("Epoch {} starting.".format(epoch))
    epoch_loss = 0
    for batch in train_loader:
        data, target = batch['image'].cuda(), batch['steer'].cuda()
        data = Variable(data).type(torch.cuda.FloatTensor)
        target = Variable(target).type(torch.cuda.FloatTensor)

        predict = model(data)
        loss = loss_fn(predict, target)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        epoch_loss += loss.data[0]

    epoch_loss /= len(train_loader.dataset)
    print("Epoch {:.4f}: Train set: Average loss: {:.6f}\t".format(epoch, epoch_loss))
    log_value('train_loss', epoch_loss, epoch)


def validate(epoch, model, loss_fn, optimizer, valid_loader):
    model.eval()
    valid_loss = 0
    for batch in valid_loader:
        data, target = batch['image'].cuda(), batch['steer'].cuda()
        data = Variable(data, volatile=True).type(torch.cuda.FloatTensor)
        target = Variable(target).type(torch.cuda.FloatTensor)
        predict = model(data)
        valid_loss += loss_fn(predict, target).data[0]  # sum up batch loss

    valid_loss /= len(valid_loader.dataset)
    print('Valid set: Average loss: {:.6f}\n'.format(valid_loss))
    log_value('valid_loss', valid_loss, epoch)
    return valid_loss


def test(model, loss_fn, optimizer, test_loader):
    model.eval()
    images = []
    targets = []
    predicts = []
    test_loss = 0
    for batch in test_loader:
        data, target = batch['image'].cuda(), batch['steer'].cuda()
        data = Variable(data, volatile=True).type(torch.cuda.FloatTensor)
        target = Variable(target).type(torch.cuda.FloatTensor)
        output = model(data)
        test_loss += loss_fn(output, target).data[0]  # sum up batch loss

        # Store image path as raw image too large.
        images.append(batch['image_path'])
        targets.append(target.data.cpu().numpy())
        predicts.append(output.data.cpu().numpy())

    test_loss /= len(test_loader.dataset)
    print('Test set: Average loss: {:.4f}\n'.format(test_loss))

    data_dict = {
        "image": np.array(images),
        "steer_target": np.array(targets).astype('float'),
        "steer_pred": np.array(predicts).astype('float')
    }

    with open("pyt_predictions_test.pickle", 'wb') as f:
        pickle.dump(data_dict, f)
        print("Predictions pickled...")


def save_checkpoint(state, is_best, file_name='/output/checkpoint.pth.tar'):
    """Save checkpoint if a new best is achieved"""
    if is_best:
        print ("=> Saving a new best")
        torch.save(state, file_name)  # save checkpoint
    else:
        print ("=> Validation Accuracy did not improve")

def create_dir(dir_name):
    if not os.path.isdir(dir_name):
        os.makedirs(dir_name)

def imagenet_transforms():
    channel_stats = dict(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225])
    train_transforms = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.4, hue=0.1),
        transforms.ToTensor(),
        transforms.Normalize(**channel_stats)
    ])

    eval_transforms = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(**channel_stats)
    ])

    return {
        'train_transforms': train_transforms,
        'eval_transforms': eval_transforms,
    } 

def pilotnet_transforms():
    train_transforms = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((66, 200)),
        transforms.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.4, hue=0.1),
        transforms.ToTensor()
    ])

    eval_transforms = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((66, 200)),
        transforms.ToTensor()
    ])
    return {
        'train_transforms': train_transforms,
        'eval_transforms': eval_transforms,
    } 


def main():
    bags = ['bag1', 'bag2']#, 'bag4', 'bag5', 'bag6']
    root_dir = r'/home/ubuntu/ws/deep_learning/projects/self_driving_car/1-pilot_net/data'
    ckpt_path = os.path.join(root_dir, 'output')#checkpoint.pth.tar')
    log_path = os.path.join(root_dir, 'log')
    
    create_dir(ckpt_path)
    create_dir(log_path)

    # Configure tensorboard log dir
    configure(os.path.join(root_dir, 'log'))

    train_csv_file = r'train_interpolated.csv'
    valid_csv_file = r'valid_interpolated.csv'


    transforms = imagenet_transforms()
    train_transforms = transforms['train_transforms']
    pre_process = transforms['eval_transforms']

    train_data_aug = DriveDataset(train_csv_file, root_dir, bags, train_transforms)
    train_data_orig = DriveDataset(train_csv_file, root_dir, bags, pre_process)
    train_data = ConcatDataset([train_data_orig, train_data_aug])

    print("Train data size: {}".format(len(train_data)))
    train_loader = DataLoader(train_data, batch_size=64, shuffle=True, num_workers=4)

    valid_data = DriveDataset(valid_csv_file, root_dir, bags, pre_process)
    print("Valid data size: {}".format(len(valid_data)))
    valid_loader = DataLoader(valid_data, batch_size=1, shuffle=False, num_workers=1)
    print("Data loaded...")

    model = PilotNetAlexNetTransfer().cuda()

    resume = False  # set to false for now.
    if resume:
        state_dict = torch.load(ckpt_path)
        model.load_state_dict(state_dict)

    optimizer = torch.optim.Adam(model.parameters())
    loss_fn = nn.MSELoss()
    print("Model setup...")

    for epoch in range(15):
        train_one_epoch(epoch, model, loss_fn, optimizer, train_loader)
        ave_valid_loss = validate(epoch, model, loss_fn, optimizer, valid_loader)

        is_best = True  # Save checkpoint every epoch for now.

        save_checkpoint({
            'epoch': epoch,
            'state_dict': model.state_dict(),
            'optimizer': optimizer.state_dict()
        }, is_best, os.path.join(ckpt_path, 'checkpoint.pth.tar'))

    test(model, loss_fn, optimizer, valid_loader)

if __name__ == "__main__":
    main()