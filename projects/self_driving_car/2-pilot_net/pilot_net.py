# @author Tasuku Miura
# @brief PyTorch implementation of PilotNet (Assumes CUDA enabled)

import torch
import torch.nn as nn
import torch.nn.functional as F


class PilotNet(nn.Module):

    """
    PilotNet per Nvidia paper.
    """

    def __init__(self):
        super(PilotNet, self).__init__()
        self.conv1 = nn.Conv2d(3, 24, kernel_size=5, stride=2, padding=0)
        self.conv2 = nn.Conv2d(24, 36, kernel_size=5, stride=2, padding=0)
        self.conv3 = nn.Conv2d(36, 48, kernel_size=5, stride=2, padding=0)
        self.conv4 = nn.Conv2d(48, 64, kernel_size=3, stride=1, padding=0)
        self.conv5 = nn.Conv2d(64, 64, kernel_size=3, stride=1, padding=0)
        self.fc1 = nn.Linear(64 * 1 * 18, 100)
        self.fc2 = nn.Linear(100, 50)
        self.fc3 = nn.Linear(50, 10)
        self.fc4 = nn.Linear(10, 1)

    def forward(self, x):
        x = (x - 0.5) * 2.0
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        x = F.relu(self.conv3(x))
        x = F.relu(self.conv4(x))
        x = F.relu(self.conv5(x))
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        x = self.fc4(x)
        return x


class PilotNetBn(nn.Module):

    """
    PilotNet with Batch Normalization.
    """

    def __init__(self):
        super(PilotNetBn, self).__init__()
        self.conv1 = nn.Conv2d(3, 24, kernel_size=5, stride=2, padding=0)
        self.bn1 = nn.BatchNorm2d(24)
        self.conv2 = nn.Conv2d(24, 36, kernel_size=5, stride=2, padding=0)
        self.bn2 = nn.BatchNorm2d(36)
        self.conv3 = nn.Conv2d(36, 48, kernel_size=5, stride=2, padding=0)
        self.bn3 = nn.BatchNorm2d(48)
        self.conv4 = nn.Conv2d(48, 64, kernel_size=3, stride=1, padding=0)
        self.bn4 = nn.BatchNorm2d(64)
        self.conv5 = nn.Conv2d(64, 64, kernel_size=3, stride=1, padding=0)
        self.bn5 = nn.BatchNorm2d(64)
        self.fc1 = nn.Linear(64 * 1 * 18, 100)
        self.fc2 = nn.Linear(100, 50)
        self.fc3 = nn.Linear(50, 10)
        self.fc4 = nn.Linear(10, 1)

    def forward(self, x):
        x = (x - 0.5) * 2.0
        x = self.bn1(F.relu(self.conv1(x)))
        x = self.bn2(F.relu(self.conv2(x)))
        x = self.bn3(F.relu(self.conv3(x)))
        x = self.bn4(F.relu(self.conv4(x)))
        x = self.bn5(F.relu(self.conv5(x)))
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        x = self.fc4(x)
        return x


from torchvision import models


class AlexNetConv4(nn.Module):

    """
    Use conv layers as feature extractor.
    """

    def __init__(self):
        super(AlexNetConv4, self).__init__()
        self.alexnet = models.alexnet(pretrained=True)

        self.features = nn.Sequential(
            # stop at conv4
            *list(self.alexnet.features.children())[:-3]
        )

    def forward(self, x):
        x = self.features(x)
        return x


class PilotNetAlexNetTransfer(nn.Module):

    """
    Fine tuning with AlexNet. Remove classification layers (basically all the fc
    layers) and retrain for regression.
    """

    def __init__(self):
        super(PilotNetAlexNetTransfer, self).__init__()
        self.features = AlexNetConv4()
        self.fc1 = nn.Linear(43264, 1024)
        self.fc2 = nn.Linear(1024, 10)
        self.fc3 = nn.Linear(10, 1)

    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x

# Fine tuning from intermediate layer:
# https://discuss.pytorch.org/t/how-to-extract-features-of-an-image-from-a-trained-model/119/3


class PilotNetCNNLSTM(nn.Module):
    # Note not an CLSTM. Using CNN to extract features and feed into LSTM.

    """
    Use CNN to extract features and pass to LSTM.
    """

    def __init__(self):
        super(PilotNetCNNLSTM, self).__init__()
        self.alexnet = models.alexnet(pretrained=True)
        self.cnn = nn.Sequential(*list(self.alexnet.children())[:-1])
        self.rnn = nn.LSTM(9216, hidden_size=512, num_layers=2, dropout=0.2, batch_first=True)
        self.fc = nn.Sequential(
            nn.Linear(512, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1)
        )

    def forward(self, x, train=True):
        sequence = []
        for feature in x:
            out = self.cnn(feature)
            out = out.view(out.size(0), -1)
            sequence.append(out)
        if train:
            sequence = torch.squeeze(torch.stack(sequence))
        else:
            # If validation or test, sample is 1, need to adjust dimensions.
            sequence = torch.stack(sequence)

        out, h = self.rnn(sequence)
        return self.fc(out[-1])


# batch_first – If True, then the input and output tensors are provided as (batch, seq, feature))
