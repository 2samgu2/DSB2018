import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from torchvision import models

class DilatedConvBlock(nn.Module):
    ''' no dilation applied if dilation equals to 1 '''
    def __init__(self, in_size, out_size, kernel_size=3, dropout_rate=0.1, activation=F.relu, dilation=1):
        super().__init__()
        # to keep same width output, assign padding equal to dilation
        self.conv = nn.Conv2d(in_size, out_size, kernel_size, padding=dilation, dilation=dilation)
        self.norm = nn.BatchNorm2d(out_size)
        self.activation = activation
        if dropout_rate > 0:
            self.drop = nn.Dropout2d(p=dropout_rate)
        else:
            self.drop = lambda x: x # no-op

    def forward(self, x):
        # CAB: conv -> activation -> batch normal
        x = self.norm(self.activation(self.conv(x)))
        x = self.drop(x)
        return x

class ConvBlock(nn.Module):
    def __init__(self, in_size, out_size, dropout_rate=0.2, dilation=1):
        super().__init__()
        self.block1 = DilatedConvBlock(in_size, out_size, dropout_rate=0)
        self.block2 = DilatedConvBlock(out_size, out_size, dropout_rate=dropout_rate, dilation=dilation)
        self.pool = nn.MaxPool2d(kernel_size=2)

    def forward(self, x):
        x = self.block1(x)
        x = self.block2(x)
        return self.pool(x), x

class ConvUpBlock(nn.Module):
    def __init__(self, in_size, out_size, dropout_rate=0.2, dilation=1):
        super().__init__()
        self.up = nn.ConvTranspose2d(in_size, out_size, 2, stride=2)
        self.block1 = DilatedConvBlock(in_size, out_size, dropout_rate=0)
        self.block2 = DilatedConvBlock(out_size, out_size, dropout_rate=dropout_rate, dilation=dilation)

    def forward(self, x, bridge):
        x = self.up(x)
        x = torch.cat([x, bridge], 1)
        # CAB: conv -> activation -> batch normal
        x = self.block1(x)
        x = self.block2(x)
        return x
    
class UNet(nn.Module):
    def __init__(self):
        super().__init__()
        # down conv
        self.c1 = ConvBlock(3, 16)
        self.c2 = ConvBlock(16, 32)
        self.c3 = ConvBlock(32, 64)
        self.c4 = ConvBlock(64, 128)
        # bottom conv tunnel
        self.cu = ConvBlock(128, 256)
        # up conv
        self.u5 = ConvUpBlock(256, 128)
        self.u6 = ConvUpBlock(128, 64)
        self.u7 = ConvUpBlock(64, 32)
        self.u8 = ConvUpBlock(32, 16)
        # final conv tunnel
        self.ce = nn.Conv2d(16, 1, 1)

    def forward(self, x):
        x, c1 = self.c1(x)
        x, c2 = self.c2(x)
        x, c3 = self.c3(x)
        x, c4 = self.c4(x)
        _, x = self.cu(x) # no maxpool for U bottom
        x = self.u5(x, c4)
        x = self.u6(x, c3)
        x = self.u7(x, c2)
        x = self.u8(x, c1)
        x = self.ce(x)
        x = F.sigmoid(x)
        return x

class DUNet(nn.Module):
    def __init__(self):
        super().__init__()
        # down conv
        self.c1 = ConvBlock(3, 16, dilation=2)
        self.c2 = ConvBlock(16, 32, dilation=2)
        self.c3 = ConvBlock(32, 64, dilation=2)
        self.c4 = ConvBlock(64, 128, dilation=2)
        # bottom dilated conv tunnel
        self.d1 = DilatedConvBlock(128, 256)
        self.d2 = DilatedConvBlock(256, 256, dilation=2)
        self.d3 = DilatedConvBlock(256, 256, dilation=4)
        self.d4 = DilatedConvBlock(256, 256, dilation=8)
        # up conv
        self.u5 = ConvUpBlock(256, 128)
        self.u6 = ConvUpBlock(128, 64)
        self.u7 = ConvUpBlock(64, 32)
        self.u8 = ConvUpBlock(32, 16)
        # final conv tunnel
        self.ce = nn.Conv2d(16, 1, 1)

    def forward(self, x):
        x, c1 = self.c1(x)
        x, c2 = self.c2(x)
        x, c3 = self.c3(x)
        x, c4 = self.c4(x)
        x = self.d1(x)
        x = self.d2(x)
        x = self.d3(x)
        x = self.d4(x)
        x = self.u5(x, c4)
        x = self.u6(x, c3)
        x = self.u7(x, c2)
        x = self.u8(x, c1)
        x = self.ce(x)
        x = F.sigmoid(x)
        return x

# Contour Aware UNet
class CAUNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.c1 = ConvBlock(3, 16)
        self.c2 = ConvBlock(16, 32)
        self.c3 = ConvBlock(32, 64)
        self.c4 = ConvBlock(64, 128)
        # bottom conv tunnel
        self.cu = ConvBlock(128, 256)
        # segmentation up conv branch
        self.u5s = ConvUpBlock(256, 128)
        self.u6s = ConvUpBlock(128, 64)
        self.u7s = ConvUpBlock(64, 32)
        self.u8s = ConvUpBlock(32, 16)
        self.ces = nn.Conv2d(16, 1, 1)
        # contour up conv branch
        self.u5c = ConvUpBlock(256, 128)
        self.u6c = ConvUpBlock(128, 64)
        self.u7c = ConvUpBlock(64, 32)
        self.u8c = ConvUpBlock(32, 16)
        self.cec = nn.Conv2d(16, 1, 1)

    def forward(self, x):
        x, c1 = self.c1(x)
        x, c2 = self.c2(x)
        x, c3 = self.c3(x)
        x, c4 = self.c4(x)
        _, x = self.cu(x) # no maxpool for U bottom
        xs = self.u5s(x, c4)
        xs = self.u6s(xs, c3)
        xs = self.u7s(xs, c2)
        xs = self.u8s(xs, c1)
        xs = self.ces(xs)
        xs = F.sigmoid(xs)
        xc = self.u5c(x, c4)
        xc = self.u6c(xc, c3)
        xc = self.u7c(xc, c2)
        xc = self.u8c(xc, c1)
        xc = self.cec(xc)
        xc = F.sigmoid(xc)
        return xs, xc

# Contour Aware Dilated UNet
class CADUNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.c1 = ConvBlock(3, 16, dilation=2)
        self.c2 = ConvBlock(16, 32, dilation=2)
        self.c3 = ConvBlock(32, 64, dilation=2)
        self.c4 = ConvBlock(64, 128, dilation=2)
        # bottom dilated conv tunnel
        self.d1 = DilatedConvBlock(128, 256)
        self.d2 = DilatedConvBlock(256, 256, dilation=2)
        self.d3 = DilatedConvBlock(256, 256, dilation=4)
        self.d4 = DilatedConvBlock(256, 256, dilation=8)
        # segmentation up conv branch
        self.u5s = ConvUpBlock(256, 128)
        self.u6s = ConvUpBlock(128, 64)
        self.u7s = ConvUpBlock(64, 32)
        self.u8s = ConvUpBlock(32, 16)
        self.ces = nn.Conv2d(16, 1, 1)
        # contour up conv branch
        self.u5c = ConvUpBlock(256, 128)
        self.u6c = ConvUpBlock(128, 64)
        self.u7c = ConvUpBlock(64, 32)
        self.u8c = ConvUpBlock(32, 16)
        self.cec = nn.Conv2d(16, 1, 1)

    def forward(self, x):
        x, c1 = self.c1(x)
        x, c2 = self.c2(x)
        x, c3 = self.c3(x)
        x, c4 = self.c4(x)
        x = self.d1(x)
        x = self.d2(x)
        x = self.d3(x)
        x = self.d4(x)
        xs = self.u5s(x, c4)
        xs = self.u6s(xs, c3)
        xs = self.u7s(xs, c2)
        xs = self.u8s(xs, c1)
        xs = self.ces(xs)
        xs = F.sigmoid(xs)
        xc = self.u5c(x, c4)
        xc = self.u6c(xc, c3)
        xc = self.u7c(xc, c2)
        xc = self.u8c(xc, c1)
        xc = self.cec(xc)
        xc = F.sigmoid(xc)
        return xs, xc

# Contour Aware Marker Unet
class CAMUNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.c1 = ConvBlock(3, 16)
        self.c2 = ConvBlock(16, 32)
        self.c3 = ConvBlock(32, 64)
        self.c4 = ConvBlock(64, 128)
        # bottom conv tunnel
        self.cu = ConvBlock(128, 256)
        # segmentation up conv branch
        self.u5s = ConvUpBlock(256, 128)
        self.u6s = ConvUpBlock(128, 64)
        self.u7s = ConvUpBlock(64, 32)
        self.u8s = ConvUpBlock(32, 16)
        self.ces = nn.Conv2d(16, 1, 1)
        # contour up conv branch
        self.u5c = ConvUpBlock(256, 128)
        self.u6c = ConvUpBlock(128, 64)
        self.u7c = ConvUpBlock(64, 32)
        self.u8c = ConvUpBlock(32, 16)
        self.cec = nn.Conv2d(16, 1, 1)
        # marker up conv branch
        self.u5m = ConvUpBlock(256, 128)
        self.u6m = ConvUpBlock(128, 64)
        self.u7m = ConvUpBlock(64, 32)
        self.u8m = ConvUpBlock(32, 16)
        self.cem = nn.Conv2d(16, 1, 1)

    def forward(self, x):
        x, c1 = self.c1(x)
        x, c2 = self.c2(x)
        x, c3 = self.c3(x)
        x, c4 = self.c4(x)
        _, x = self.cu(x) # no maxpool for U bottom
        xs = self.u5s(x, c4)
        xs = self.u6s(xs, c3)
        xs = self.u7s(xs, c2)
        xs = self.u8s(xs, c1)
        xs = self.ces(xs)
        xs = F.sigmoid(xs)
        xc = self.u5c(x, c4)
        xc = self.u6c(xc, c3)
        xc = self.u7c(xc, c2)
        xc = self.u8c(xc, c1)
        xc = self.cec(xc)
        xc = F.sigmoid(xc)
        xm = self.u5m(x, c4)
        xm = self.u6m(xm, c3)
        xm = self.u7m(xm, c2)
        xm = self.u8m(xm, c1)
        xm = self.cem(xm)
        xm = F.sigmoid(xm)
        return xs, xc, xm

# Contour Aware Marker Dilated Unet
class CAMDUNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.c1 = ConvBlock(3, 16, dilation=2)
        self.c2 = ConvBlock(16, 32, dilation=2)
        self.c3 = ConvBlock(32, 64, dilation=2)
        self.c4 = ConvBlock(64, 128, dilation=2)
        # bottom dilated conv tunnel
        self.d1 = DilatedConvBlock(128, 256)
        self.d2 = DilatedConvBlock(256, 256, dilation=2)
        self.d3 = DilatedConvBlock(256, 256, dilation=4)
        self.d4 = DilatedConvBlock(256, 256, dilation=8)
        # segmentation up conv branch
        self.u5s = ConvUpBlock(256, 128)
        self.u6s = ConvUpBlock(128, 64)
        self.u7s = ConvUpBlock(64, 32)
        self.u8s = ConvUpBlock(32, 16)
        self.ces = nn.Conv2d(16, 1, 1)
        # contour up conv branch
        self.u5c = ConvUpBlock(256, 128)
        self.u6c = ConvUpBlock(128, 64)
        self.u7c = ConvUpBlock(64, 32)
        self.u8c = ConvUpBlock(32, 16)
        self.cec = nn.Conv2d(16, 1, 1)
        # marker up conv branch
        self.u5m = ConvUpBlock(256, 128)
        self.u6m = ConvUpBlock(128, 64)
        self.u7m = ConvUpBlock(64, 32)
        self.u8m = ConvUpBlock(32, 16)
        self.cem = nn.Conv2d(16, 1, 1)

    def forward(self, x):
        x, c1 = self.c1(x)
        x, c2 = self.c2(x)
        x, c3 = self.c3(x)
        x, c4 = self.c4(x)
        x = self.d1(x)
        x = self.d2(x)
        x = self.d3(x)
        x = self.d4(x)
        xs = self.u5s(x, c4)
        xs = self.u6s(xs, c3)
        xs = self.u7s(xs, c2)
        xs = self.u8s(xs, c1)
        xs = self.ces(xs)
        xs = F.sigmoid(xs)
        xc = self.u5c(x, c4)
        xc = self.u6c(xc, c3)
        xc = self.u7c(xc, c2)
        xc = self.u8c(xc, c1)
        xc = self.cec(xc)
        xc = F.sigmoid(xc)
        xm = self.u5m(x, c4)
        xm = self.u6m(xm, c3)
        xm = self.u7m(xm, c2)
        xm = self.u8m(xm, c1)
        xm = self.cem(xm)
        xm = F.sigmoid(xm)
        return xs, xc, xm


# Transfer Learning VGG16_BatchNorm as Encoder part of UNet
class DeConvBlk(nn.Module):
    def __init__(self, in_ch, out_ch, dropout_ratio=0.2):
        super().__init__()
        self.upscaling = nn.ConvTranspose2d(in_ch, in_ch//2, 2, stride=2)
        self.convs = nn.Sequential(
            nn.Conv2d(in_ch//2 + out_ch, out_ch, 3, padding=1),
            nn.ReLU(inplace=True),
            nn.BatchNorm2d(out_ch),
            nn.Dropout2d(p=dropout_ratio),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.ReLU(inplace=True),
            nn.BatchNorm2d(out_ch),
            nn.Dropout2d(p=dropout_ratio)
        )

    def forward(self, x1, x2):
        x1 = self.upscaling(x1)
        diffX = x1.size()[2] - x2.size()[2]
        diffY = x1.size()[3] - x2.size()[3]
        x2 = F.pad(x2, (diffX // 2, int(diffX / 2),
                        diffY // 2, int(diffY / 2)))
        x = torch.cat([x1, x2], dim=1)
        x = self.convs(x)
        return x


class outConv(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, 1)

    def forward(self, x):
        x = self.conv(x)
        return x


class UNetVgg16(nn.Module):
    def __init__(self, n_channels, n_classes, fixed_vgg = False):
        super().__init__()
        self.maxpool = nn.MaxPool2d(2, 2)
        self.relu = nn.ReLU(inplace=True)
        self.vgg16 = models.vgg16_bn(pretrained=True)

        self.conv1a = self.vgg16.features[0]   #64
        self.bn1a = self.vgg16.features[1]
        self.conv1b = self.vgg16.features[3]   #64
        self.bn1b = self.vgg16.features[4]

        self.conv2a = self.vgg16.features[7]  #128
        self.bn2a = self.vgg16.features[8]
        self.conv2b = self.vgg16.features[10]  #128
        self.bn2b = self.vgg16.features[11]

        self.conv3a = self.vgg16.features[14]  #256
        self.bn3a = self.vgg16.features[15]
        self.conv3b = self.vgg16.features[17]  #256
        self.bn3b = self.vgg16.features[18]
        self.conv3c = self.vgg16.features[20]  #256
        self.bn3c = self.vgg16.features[21]

        self.conv4a = self.vgg16.features[24]  #512
        self.bn4a = self.vgg16.features[25]
        self.conv4b = self.vgg16.features[27]  #512
        self.bn4b = self.vgg16.features[28]
        self.conv4c = self.vgg16.features[30]  #512
        self.bn4c = self.vgg16.features[31]

        self.conv5a = self.vgg16.features[34]  #512
        self.bn5a = self.vgg16.features[35]
        self.conv5b = self.vgg16.features[37]  #512
        self.bn5b = self.vgg16.features[38]
        self.conv5c = self.vgg16.features[40]  #512
        self.bn5c = self.vgg16.features[41]

        self.deconv1 = DeConvBlk(512, 512)
        self.deconv2 = DeConvBlk(512, 256)
        self.deconv3 = DeConvBlk(256, 128)
        self.deconv4 = DeConvBlk(128, 64)
        self.outc = outConv(64, n_classes)
        if fixed_vgg:
            for param in self.vgg16.parameters():
                param.requires_grad = False

    def forward(self, x):
        t = self.relu(self.bn1a(self.conv1a(x)))
        x1 = self.relu(self.bn1b(self.conv1b(t)))
        t = self.maxpool(x1)
        t = self.relu(self.bn2a(self.conv2a(t)))
        x2 = self.relu(self.bn2b(self.conv2b(t)))
        t = self.maxpool(x2)
        t = self.relu(self.bn3a(self.conv3a(t)))
        t = self.relu(self.bn3b(self.conv3b(t)))
        x3 = self.relu(self.bn3c(self.conv3c(t)))
        t = self.maxpool(x3)
        t = self.relu(self.bn4a(self.conv4a(t)))
        t = self.relu(self.bn4b(self.conv4b(t)))
        x4 = self.relu(self.bn4c(self.conv4c(t)))
        t = self.maxpool(x4)
        t = self.relu(self.bn5a(self.conv5a(t)))
        t = self.relu(self.bn5b(self.conv5b(t)))
        x5 = self.relu(self.bn5c(self.conv5c(t)))
        t = self.deconv1(x5, x4)
        t = self.deconv2(t, x3)
        t = self.deconv3(t, x2)
        t = self.deconv4(t, x1)
        t = self.outc(t)
        t = F.sigmoid(t)
        return t


# Deep Contour Aware Network (DCAN)
class dcanConv(nn.Module):
    def __init__(self, in_ch, out_ch, dropout_ratio=0.2):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1),
            nn.ReLU(inplace=True),
            nn.BatchNorm2d(out_ch),
            nn.Dropout2d(p=dropout_ratio),
        )

    def forward(self, x):
        x = self.conv(x)
        return x

class dcanDeConv(nn.Module):
    def __init__(self, in_ch, out_ch, upscale_factor, dropout_ratio=0.2):
        super().__init__()
        self.upscaling = nn.ConvTranspose2d(
            in_ch, out_ch, kernel_size=upscale_factor, stride=upscale_factor)
        self.conv = dcanConv(out_ch, out_ch, dropout_ratio)

    def forward(self, x):
        x = self.upscaling(x)
        x = self.conv(x)
        return x

class DCAN(nn.Module):
    def __init__(self, n_channels, n_classes):
        super().__init__()
        self.maxpool = nn.MaxPool2d(2, 2)
        self.conv1 = dcanConv(n_channels, 64)
        self.conv2 = dcanConv(64, 128)
        self.conv3 = dcanConv(128, 256)
        self.conv4 = dcanConv(256, 512)
        self.conv5 = dcanConv(512, 512)
        self.conv6 = dcanConv(512, 1024)
        self.deconv3s = dcanDeConv(512, n_classes, 8) # 8 = 2^3 (3 maxpooling)
        self.deconv3c = dcanDeConv(512, n_classes, 8)
        self.deconv2s = dcanDeConv(512, n_classes, 16) # 16 = 2^4 (4 maxpooling)
        self.deconv2c = dcanDeConv(512, n_classes, 16)
        self.deconv1s = dcanDeConv(1024, n_classes, 32) # 32 = 2^5 (5 maxpooling)
        self.deconv1c = dcanDeConv(1024, n_classes, 32)

    def forward(self, x):
        c1 = self.conv1(x)
        c2 = self.conv2(self.maxpool(c1))
        c3 = self.conv3(self.maxpool(c2))
        c4 = self.conv4(self.maxpool(c3))
        # s for segment branch, c for contour branch
        u3s = self.deconv3s(c4)
        u3c = self.deconv3c(c4)
        c5 = self.conv5(self.maxpool(c4))
        u2s = self.deconv2s(c5)
        u2c = self.deconv2c(c5)
        c6 = self.conv6(self.maxpool(c5))
        u1s = self.deconv1s(c6)
        u1c = self.deconv1c(c6)
        outs = F.sigmoid(u1s + u2s + u3s)
        outc = F.sigmoid(u1c + u2c + u3c)
        # print('x: ', x.size())
        # print('c1: ', c1.size())
        # print('c2: ', c2.size())
        # print('c3: ', c3.size())
        # print('c4: ', c4.size())
        # print('c5: ', c5.size())
        # print('c6: ', c6.size())
        # print('u3s: ', u3s.size())
        # print('u3c: ', u3c.size())
        # print('u2s: ', u2s.size())
        # print('u2c: ', u2c.size())
        # print('u1s: ', u1s.size())
        # print('u1c: ', u1c.size())
        # print('outs: ', outs.size())
        # print('outc: ', outc.size())
        return outs, outc

def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

def build_model(model_name='unet'):
    # initialize model
    if model_name == 'unet_vgg16':
        model = UNetVgg16(3, 1, fixed_vgg=True)
    elif model_name == 'dcan':
        model = DCAN(3, 1)
    elif model_name == 'caunet':
        model = CAUNet()
    elif model_name == 'camunet':
        model = CAMUNet()
    elif model_name == 'dunet':
        model = DUNet()
    elif model_name == 'cadunet':
        model = CAMDUNet()
    elif model_name == 'camdunet':
        model = CAMDUNet()
    else:
        model = UNet()
    return model


if __name__ == '__main__':
    net = UNet()
    #print(net)
    print('Total number of Unet model parameters is', count_parameters(net))
    del net

    net = CAUNet()
    #print(net)
    print('Total number of CAUNet model parameters is', count_parameters(net))
    del net

    net = CAMUNet()
    #print(net)
    print('Total number of CAMUNet model parameters is', count_parameters(net))
    del net

    net = DUNet()
    #print(net)
    print('Total number of DUNet model parameters is', count_parameters(net))
    del net

    net = CADUNet()
    #print(net)
    print('Total number of CADUNet model parameters is', count_parameters(net))
    del net

    net = CAMDUNet()
    #print(net)
    print('Total number of CAMDUNet model parameters is', count_parameters(net))
    # x = torch.randn(10, 3, 128, 128)
    # x = Variable(x)
    # y, _, _ = net(x)
    # print(y.shape)
    del net

    # net = UNetVgg16(3, 1)
    # print(net)
    # del net
    # net = DCAN(3, 1)
    # print(net)
    # del net

    # x = torch.randn(10, 3, 256, 256)
    # x = Variable(x)
    # b = ConvBlock(3, 16)
    # p, y = b(x)
    # print(p.shape, y.shape)