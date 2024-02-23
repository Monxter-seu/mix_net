# Created on 2023/10
# Author: Kaituo XU,Minxu Hua
# Based On the structure of Conv-tas-net,using g-mlp and classifier to make an end-to-end classifier
# the value of C must be 2 in this case

from collections import OrderedDict
import torch
import torch.nn as nn
import torch.nn.functional as F
import time
import random

from torchviz import make_dot
from conv_tasnet import TemporalConvNet
from utils import overlap_and_add

EPS = 1e-8
NET = 'transformer'

#
class dayShiftNet(nn.Module):
    def __init__(self):
        super(dayShiftNet, self).__init__()
        self.net = mlpNet()
        self.classifier0 = BinaryClassifier(128)
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_normal_(p)
    
    def forward(self, mixture):
        output = self.net(mixture)
        classifier_output = self.classifier0(output)
        return output,classifier_output

class testMixNet(nn.Module):
    def __init__(self):
        super(testMixNet, self).__init__()
        self.mixstyle = MixStyle(p=0.5, alpha=0.1)
        self.classifier0 = MultiClassifier(0, 128,10)
    
    def forward(self, mixture):
        #print('mixture_shape',mixture.shape)
        output = self.mixstyle(mixture)
        classifier_output = self.classifier0(output)
        return classifier_output


class testLSTMNet(nn.Module):
    def __init__(self):
        super(testLSTMNet, self).__init__()
        self.net = nn.LSTM(128, 128, 2, batch_first=True)
        self.classifier0 = MultiClassifier(0, 128,10)
    
    def forward(self, mixture):
        #print('mixture_shape',mixture.shape)
        output,( hn,cn) = self.net(mixture)
        classifier_output = self.classifier0(output)
        return classifier_output
        
class end2end_test_B(nn.Module):
    def __init__(self, N, B, H, P, X, R, C, K, norm_type="gLN", causal=False,
                 mask_nonlinear='relu'):
        super(end2end_test_B, self).__init__()    
        self.norm_type = norm_type
        self.causal = causal
        self.mask_nonlinear = mask_nonlinear
        self.representation = mlpNet1()
        self.contextExtraction = mlpNet()
        self.confounderNet = mlpNet()
        self.fingerprintExtraction = mlpNet()
        
        #self.net = TemporalConvNet(N, B, H, P, X, R, C, norm_type, causal, mask_nonlinear)
        #self.net = mlpNet()
        self.classifier0 = MultiClassifier(0, 128,10)
        self.classifier1 = MultiClassifier(0, 128,6)
        self.confounderClassifier = MultiClassifier(0, 128,10)
        # init
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_normal_(p)

    def forward(self, mixture, confounder):
        feature = self.representation(mixture)
        fingerFeature = self.fingerprintExtraction(feature)
        contextFeature =self.contextExtraction(feature)
        confounderFeature = fingerFeature + confounder
        classifier_output_confounder = self.confounderClassifier(confounderFeature)
        classifier_output0 = self.classifier0(fingerFeature)
        classifier_output1 = self.classifier1(contextFeature)
        return classifier_output0, classifier_output1,classifier_output_confounder, feature
        
    def case_study(self, mixture):
        mixture_1 = self.representation(mixture)
        return mixture_1
        
    def cal_confounder(self, mixture):
        mixture_1 = self.representation(mixture)
        #print(mixture_1.shape)
        #[bs,2,1,128]
        confounder = self.contextExtraction(mixture_1)
        return confounder
        
#end2end训练模型(只输出confounder，不加入coufounder)
class end2end_train(nn.Module):
    def __init__(self, N, B, H, P, X, R, C, K, norm_type="gLN", causal=False,
                 mask_nonlinear='relu'):
        super(end2end_train, self).__init__()    
        self.norm_type = norm_type
        self.causal = causal
        self.mask_nonlinear = mask_nonlinear
        self.representation = mlpNet()
        self.contextExtraction = mlpNet()
        self.fingerprintExtraction = mlpNet()
        #self.net = TemporalConvNet(N, B, H, P, X, R, C, norm_type, causal, mask_nonlinear)
        #self.net = mlpNet()
        self.classifier0 = BinaryClassifier(128)
        self.classifier1 = MultiClassifier(0, 128,6)
        # init
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_normal_(p)

    def forward(self, mixture):
        feature = self.representation(mixture)
        fingerFeature = self.fingerprintExtraction(feature)
        contextFeature =self.contextExtraction(feature)
        classifier_output0 = self.classifier0(fingerFeature)
        classifier_output1 = self.classifier1(contextFeature)
        return classifier_output0, classifier_output1, feature
        
    def cal_confounder(self, mixture):
        mixture_1 = self.representation(mixture)
        #print(mixture_1.shape)
        #[bs,2,1,128]
        confounder = self.contextExtraction(mixture_1)
        return confounder
        
#新网络用来计算confounder以及进行推理
class confounderNet(nn.Module):
    def __init__(self, N, B, H, P, X, R, C, K, norm_type="gLN", causal=False,
                 mask_nonlinear='relu'):
        super(confounderNet, self).__init__()
        self.N, self.B, self.H, self.P, self.X, self.R, self.C, self.K = N, B, H, P, X, R, C, K
        self.norm_type = norm_type
        self.causal = causal
        self.mask_nonlinear = mask_nonlinear
        self.net = RepresentLayer('mlp','mlp')
        #self.net = TemporalConvNet(N, B, H, P, X, R, C, norm_type, causal, mask_nonlinear)
        #self.net = mlpNet()
        self.classifier0 = BinaryClassifier(128)
        self.classifier1 = MultiClassifier(0, 128,6)
        self.classifier2 = BinaryClassifier(128)
        # init
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_normal_(p)


    def forward(self, mixture, confounder):
        #mixture = mixture.unsqueeze(1)
        mixture_1 = self.net(mixture)
        #print(mixture_1.shape)
        #[bs,2,1,128]
        mixture_2 = mixture_1.squeeze(dim=2)
        channel_0 = mixture_2[:, 0, :]
        channel_1 = mixture_2[:, 1, :]
        classifier_output0 = self.classifier0(channel_0)
        #classifier_output0 = self.classifier0(mixture_1)
        #self.confounder = channel_1
        channel_2 = channel_0 + torch.unsqueeze(confounder, 0).expand(channel_0.size(0), -1)
        classifier_output1 = self.classifier1(channel_1)
        classifier_output2 = self.classifier2(channel_2)
        #classifier_output0 = self.classifier0(mixture)
        #classifier_output1 = self.classifier1(mixture)
        #combined_classifier_output = torch.cat((classifier_output0, classifier_output1), dim=1)
        #return combined_classifier_output
        return classifier_output0, classifier_output1, classifier_output2
        
        
class maskNet(nn.Module):
    def __init__(self, N, B, H, P, X, R, C, K, norm_type="gLN", causal=False,
                 mask_nonlinear='relu'):
        super(maskNet, self).__init__()
        self.N, self.B, self.H, self.P, self.X, self.R, self.C, self.K = N, B, H, P, X, R, C, K
        self.norm_type = norm_type
        self.causal = causal
        self.mask_nonlinear = mask_nonlinear
        self.net = mlpNet()
        self.sigmoid = nn.Sigmoid()
        #self.net = TemporalConvNet(N, B, H, P, X, R, C, norm_type, causal, mask_nonlinear)
        #self.net = mlpNet()
        self.classifier0 = BinaryClassifier(128)
        self.classifier1 = MultiClassifier(0, 128,6)
        # init
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_normal_(p)


    def forward(self, mixture):
        #mixture = mixture.unsqueeze(1)
        mixture_1 = self.net(mixture)
        #print(mixture_1.shape)
        #[bs,2,1,128]
        channel_0_mask = self.sigmoid(mixture_1)
        channel_1_mask = torch.ones(channel_0_mask.size(0),channel_0_mask.size(1)).cuda()-channel_0_mask
        channel_0 = mixture*channel_0_mask
        channel_1 = mixture*channel_1_mask
        classifier_output0 = self.classifier0(channel_0)
        #classifier_output0 = self.classifier0(mixture_1)
        classifier_output1 = self.classifier1(channel_1)
        #classifier_output0 = self.classifier0(mixture)
        #classifier_output1 = self.classifier1(mixture)
        #combined_classifier_output = torch.cat((classifier_output0, classifier_output1), dim=1)
        #return combined_classifier_output
        return classifier_output0,classifier_output1

class mixNet(nn.Module):
    def __init__(self, N, B, H, P, X, R, C, K, norm_type="gLN", causal=False,
                 mask_nonlinear='relu'):
        super(mixNet, self).__init__()
        self.N, self.B, self.H, self.P, self.X, self.R, self.C, self.K = N, B, H, P, X, R, C, K
        self.norm_type = norm_type
        self.causal = causal
        self.mask_nonlinear = mask_nonlinear
        self.net = RepresentLayer('mlp','mlp')
        #self.net = TemporalConvNet(N, B, H, P, X, R, C, norm_type, causal, mask_nonlinear)
        #self.net = mlpNet()
        self.classifier0 = BinaryClassifier(128)
        self.classifier1 = MultiClassifier(0, 128,6)
        # init
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_normal_(p)


    def forward(self, mixture):
        #mixture = mixture.unsqueeze(1)
        mixture_1 = self.net(mixture)
        #print(mixture_1.shape)
        #[bs,2,1,128]
        mixture_2 = mixture_1.squeeze(dim=2)
        channel_0 = mixture_2[:, 0, :]
        channel_1 = mixture_2[:, 1, :]
        classifier_output0 = self.classifier0(channel_0)
        #classifier_output0 = self.classifier0(mixture_1)
        #self.confounder = channel_1
        classifier_output1 = self.classifier1(channel_1)
        #classifier_output0 = self.classifier0(mixture)
        #classifier_output1 = self.classifier1(mixture)
        #combined_classifier_output = torch.cat((classifier_output0, classifier_output1), dim=1)
        #return combined_classifier_output
        return classifier_output0,classifier_output1
    
    def cal_confounder(self, mixture):
        mixture_1 = self.net(mixture)
        #print(mixture_1.shape)
        #[bs,2,1,128]
        mixture_2 = mixture_1.squeeze(dim=2)
        channel_0 = mixture_2[:, 0, :]
        channel_1 = mixture_2[:, 1, :]
        return channel_1

class mlpNet(nn.Module):
    def __init__(self):
        super(mlpNet,self).__init__()
        self.fc1 = nn.Linear(128, 2048)
        self.fc2 = nn.Linear(2048, 128)
        self.relu = nn.ReLU()
        
    def forward(self,input):
        output = self.fc1(input)
        output = self.relu(output)
        output = self.fc2(output)
        output = self.relu(output)
        return output

class mlpNet1(nn.Module):
    def __init__(self):
        super(mlpNet1,self).__init__()
        self.fc1 = nn.Linear(120000, 2048)
        self.fc2 = nn.Linear(2048, 128)
        self.relu = nn.ReLU()
        
    def forward(self,input):
        output = self.fc1(input)
        output = self.relu(output)
        output = self.fc2(output)
        output = self.relu(output)
        return output

#整个表示层     
class RepresentLayer(nn.Module):
    def __init__(self, type1, type2):
        super(RepresentLayer, self).__init__()
        self.type1 = type1
        self.type2 = type2
        self.mlp1 = mlpNet()
        self.mlp2 = mlpNet()
        self.transformer = TransformerLayer(d_model=128,nhead=8)
        self.cnn = Simple1DCNN()
    def forward(self, input):
        if self.type1 == 'mlp':
            output1 = self.mlp1(input)
        elif self.type1 == 'transformer':
            output1 = self.transformer(input)
        elif self.type1 == 'cnn':
            output1 = self.cnn(input)
        
        if self.type2 == 'mlp':
            output_channel1 = self.mlp2(output1)
            output_channel2 = self.mlp2(output1)
        elif self.type2 == 'transformer':
            output_channel1 = self.transformer(output1)
            output_channel2 = self.transformer(output1)
        elif self.type2 == 'cnn':
            output_channel1 = self.cnn(output1)
            output_channel2 = self.cnn(output1)
        
        output = torch.cat((output_channel1.unsqueeze(dim=1),
                            output_channel2.unsqueeze(dim=1)),dim=1)
                            
        return output
            
class Simple1DCNN(nn.Module):
    def __init__(self):
        super(Simple1DCNN, self).__init__()
        
        # 第一个卷积层，输入通道数为1，输出通道数为32，卷积核大小为3
        self.conv1 = nn.Conv1d(in_channels=16, out_channels=32, kernel_size=16)
        
        # 第二个卷积层，输入通道数为32，输出通道数为64，卷积核大小为3
        self.conv2 = nn.Conv1d(in_channels=32, out_channels=64, kernel_size=16)
        
        # 池化层，池化窗口大小为2
        self.pool = nn.MaxPool1d(kernel_size=32, stride=2)
        
        # 全连接层，输入特征数为64*4（经过两次池化层），输出特征数为128
        self.fc1 = nn.Linear(1312, 128)
        
        #self.fc2 = nn.Linear(128, 128)
        

    def forward(self, x):
        #[bs,128] bs=16
        
        x = x.unsqueeze(dim=2)
        #print('x.shape',
        x = x.permute(1, 0, 2)
        #[128,bs,1]
        #x = self.conv1(x)
        #print('x.shape',x.shape)
        print('x.shape',x.shape)
        x = self.conv1(x)
        x = F.relu(x)
        x = self.pool(x)
        #x = self.pool(F.relu(self.conv1(x)))
        x = x.permute(1, 0, 2)
        #x = self.pool(F.relu(self.conv2(x)))
        x = x.view(-1, 1312)
        #print('x.shape',x.shape)
        #print('x.shape',x.shape)
        x = F.relu(self.fc1(x))        
        return x
        
class OneDimCNNLayer(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride=1, padding=0):
        super(OneDimCNNLayer, self).__init__()
        
        # 一维卷积层
        self.conv1d = nn.Conv1d(in_channels, out_channels, kernel_size, stride=stride, padding=padding)
        
        # 非线性激活函数（ReLU）
        self.relu = nn.ReLU()

    def forward(self, x):
        # 前向传播
        x = self.conv1d(x)
        x = self.relu(x)
        return x

class TransformerLayer(nn.Module):
    def __init__(self, d_model, nhead, dim_feedforward=2048, dropout=0.1):
        super(TransformerLayer, self).__init__()
        
        # Self-Attention 层
        self.self_attn = nn.MultiheadAttention(d_model, nhead, dropout=dropout)
        
        # Layer Normalization
        self.norm1 = nn.LayerNorm(d_model)
        
        # 前馈神经网络层
        self.feedforward = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, d_model)
        )
        
        # Layer Normalization
        self.norm2 = nn.LayerNorm(d_model)
        
        # Dropout
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        # Self-Attention 层
        attn_output, _ = self.self_attn(x, x, x)
        
        # 残差连接和 Layer Normalization
        x = x + self.dropout(attn_output)
        x = self.norm1(x)
        
        # 前馈神经网络层
        ff_output = self.feedforward(x)
        
        # 残差连接和 Layer Normalization
        x = x + self.dropout(ff_output)
        x = self.norm2(x)
        
        return x      
        
class gMLP(nn.Module):
    def __init__(self, N, L, B, H, P, X, R, C, norm_type="gLN", causal=False,
                 mask_nonlinear='relu'):
        """
        Args:
            N: Number of filters in autoencoder
            L: Length of the filters (in samples)
            B: Number of channels in bottleneck 1 × 1-conv block
            H: Number of channels in convolutional blocks
            P: Kernel size in convolutional blocks
            X: Number of convolutional blocks in each repeat
            R: Number of repeats
            C: Number of speakers
            norm_type: BN, gLN, cLN
            causal: causal or non-causal
            mask_nonlinear: use which non-linear function to generate mask
        """
        super(gMLP, self).__init__()
        # Hyper-parameter
        self.N, self.L, self.B, self.H, self.P, self.X, self.R, self.C = N, L, B, H, P, X, R, C
        self.norm_type = norm_type
        self.causal = causal
        self.mask_nonlinear = mask_nonlinear
        K = 2*64000//L-1
        # Components
        """encoder组件
        """
        self.encoder = Encoder(L, N)
            
        """分离部分组件，为TemporalConvNet网络
        """
        self.separator = EditedNet(N, B, H, P, X, R, C, K,norm_type, causal, mask_nonlinear)
        """decoder组件
        """
        self.decoder = Decoder(N, L)

        """（中间是否要转化为频域？？）分类器组件
        """
        self.classifier0 = BinaryClassifier(128)
        self.classifier1 = MultiClassifier(64000, 128,6)

        # init
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_normal_(p)

    def forward(self, mixture):

        """
        Args:
            mixture: [M, T], M is batch size, T is #samples
        Returns:
            est_source: [M, C, T]
        """

        """通过encoder，mixture_w即混合信号的权重，被编码过的源信号
        """

        mixture_w = self.encoder(mixture)
        """通过separation网络计算mask
        """
        print('mixture_w.shape======',mixture_w.shape)
        est_mask = self.separator(mixture_w)
        print('est_mask.shape=====',est_mask.shape)
        """经过decoder得到原信号
        """

        M, N, K = mixture_w.size()
        est_mask = est_mask.view(M, self.C, N, K)

        est_source = self.decoder(mixture_w, est_mask)

        

        # T changed after conv1d in encoder, fix it here
        """保存T的值
        """
        T_origin = mixture.size(-1)
        T_conv = est_source.size(-1)
        """对原信号进行填充
        """
        est_source = F.pad(est_source, (0, T_origin - T_conv))
        """est_source是[M,C,T]的格式
        """
        channel_0 = est_source[:, 0, :]
        channel_1 = est_source[:, 1, :]
        classifier_output0 = self.classifier0(channel_0)
        classifier_output1 = self.classifier1(channel_1)

        combined_classifier_output = torch.cat((classifier_output0, classifier_output1), dim=1)
        return combined_classifier_output

    @classmethod
    def load_model(cls, path):
        # Load to CPU
        package = torch.load(path, map_location=lambda storage, loc: storage)
        model = cls.load_model_from_package(package)
        return model

    @classmethod
    def load_model_from_package(cls, package):
        model = cls(package['N'], package['L'], package['B'], package['H'],
                    package['P'], package['X'], package['R'], package['C'],
                    norm_type=package['norm_type'], causal=package['causal'],
                    mask_nonlinear=package['mask_nonlinear'])
        model.load_state_dict(package['state_dict'])
        return model
    """序列化，得到一个package，包含网络的超参数和模型的参数，优化器的参数
    """
    @staticmethod
    def serialize(model, optimizer, epoch, tr_loss=None, cv_loss=None):
        package = {
            # hyper-parameter
            'N': model.N, 'L': model.L, 'B': model.B, 'H': model.H,
            'P': model.P, 'X': model.X, 'R': model.R, 'C': model.C,
            'norm_type': model.norm_type, 'causal': model.causal,
            'mask_nonlinear': model.mask_nonlinear,
            # state
            'state_dict': model.state_dict(),
            'optim_dict': optimizer.state_dict(),
            'epoch': epoch
        }
        if tr_loss is not None:
            package['tr_loss'] = tr_loss
            package['cv_loss'] = cv_loss
        return package
        
        
class MixStyle(nn.Module):
    """MixStyle.
    Reference:
      Zhou et al. Domain Generalization with MixStyle. ICLR 2021.
    """

    def __init__(self, p=0.5, alpha=0.1, eps=1e-6, mix='random'):
        """
        Args:
          p (float): probability of using MixStyle.
          alpha (float): parameter of the Beta distribution.
          eps (float): scaling parameter to avoid numerical issues.
          mix (str): how to mix.
        """
        super().__init__()
        self.p = p
        self.beta = torch.distributions.Beta(alpha, alpha)
        self.eps = eps
        self.alpha = alpha
        self.mix = mix
        self._activated = True

    def __repr__(self):
        return f'MixStyle(p={self.p}, alpha={self.alpha}, eps={self.eps}, mix={self.mix})'

    def set_activation_status(self, status=True):
        self._activated = status

    def update_mix_method(self, mix='random'):
        self.mix = mix

    def forward(self, x):
        if not self.training or not self._activated:
            return x

        if random.random() > self.p:
            return x

        B = x.size(0)

        mu = x.mean(dim=1, keepdim=True)
        var = x.var(dim=1, keepdim=True)
        sig = (var + self.eps).sqrt()
        mu, sig = mu.detach(), sig.detach()
        x_normed = (x-mu) / sig

        lmda = self.beta.sample((B, 1, 1, 1))
        lmda = lmda.to(x.device)

        if self.mix == 'random':
            # random shuffle
            perm = torch.randperm(B)
            #print('perm',perm.shape)

        elif self.mix == 'crossdomain':
            # split into two halves and swap the order
            perm = torch.arange(B - 1, -1, -1) # inverse index
            perm_b, perm_a = perm.chunk(2)
            perm_b = perm_b[torch.randperm(B // 2)]
            perm_a = perm_a[torch.randperm(B // 2)]
            #print('perm_a',perm_a.shape)
            perm = torch.cat([perm_b, perm_a], 0)

        else:
            raise NotImplementedError

        mu2, sig2 = mu[perm], sig[perm]
        mu_mix = mu*lmda + mu2 * (1-lmda)
        sig_mix = sig*lmda + sig2 * (1-lmda)
        output = x_normed*sig_mix + mu_mix
        #print('out.shape',output.shape)
        output1 = output[0,:,:]
        output2 = output1.squeeze(dim=0)
        return output2
        
        
class Encoder(nn.Module):
    """Estimation of the nonnegative mixture weight by a 1-D conv layer.
    """
    def __init__(self, L, N):
        """继承pytorch中的nn.module类
        """
        super(Encoder, self).__init__()
        # Hyper-parameter
        """传入超参数L，N
        """
        self.L, self.N = L, N
        # Components
        # 50% overlap
        """创建一个一维卷积模块，其中输入信号的通道为1，因为时域信号是一维的；卷积输出的通道为N，即需要N个卷积核，卷积核的大小为L，步长为L/2
        class torch.nn.Conv1d(in_channels, out_channels, kernel_size, stride=1, padding=0, dilation=1, groups=1, bias=True)
        in_channels(int) – 输入信号的通道。在文本分类中，即为词向量的维度
        out_channels(int) – 卷积产生的通道。有多少个out_channels，就需要多少个1维卷积
        kernel_size(int or tuple) - 卷积核的尺寸，卷积核的大小为(k,)，第二个维度是由in_channels来决定的，所以实际上卷积大小为kernel_size*in_channels
        stride(int or tuple, optional) - 卷积步长
        padding (int or tuple, optional)- 输入的每一条边补充0的层数
        dilation(int or tuple, `optional``) – 卷积核元素之间的间距
        groups(int, optional) – 从输入通道到输出通道的阻塞连接数
        bias(bool, optional) - 如果bias=True，添加偏置

        """
        self.conv1d_U = nn.Conv1d(1, N, kernel_size=L, stride=L // 2, bias=False)

    def forward(self, mixture):
        """
        Args:
            mixture: [M, T], M is batch size, T is #samples
        Returns:
            mixture_w: [M, N, K], where K = (T-L)/(L/2)+1 = 2T/L-1
        """
        """为数据增加一个维度1，现在数据的结构为[M,1,T]
        """
        mixture = torch.unsqueeze(mixture, 1)  # [M, 1, T]
        """经过网络得到信号的权重,最终数据为[M,N,K], K = (T-L)/(L/2)+1 = 2T/L-1，再经过一个非线性函数relu得到mixture的权重mixture_w
        """
        mixture_w = F.relu(self.conv1d_U(mixture))  # [M, N, K]
        return mixture_w
        
class Decoder(nn.Module):
    def __init__(self, N, L):
        super(Decoder, self).__init__()
        # Hyper-parameter
        self.N, self.L = N, L
        # Components
        self.basis_signals = nn.Linear(N, L, bias=False)

    def forward(self, mixture_w, est_mask):
        """
        Args:
            mixture_w: [M, N, K]
            est_mask: [M, C, N, K]
        Returns:
            est_source: [M, C, T]
        """
        # D = W * M
        source_w = torch.unsqueeze(mixture_w, 1) * est_mask  # [M, C, N, K]
        source_w = torch.transpose(source_w, 2, 3) # [M, C, K, N]
        # S = DV
        est_source = self.basis_signals(source_w)  # [M, C, K, L]
        est_source = overlap_and_add(est_source, self.L//2) # M x C x T
        return est_source
    
def exist(x):
    return x is not None

class Residual(nn.Module):
    def __init__(self,fn):
        super().__init__()
        self.fn=fn
    
    def forward(self,x):
        return self.fn(x)+x

class SpatialGatingUnit(nn.Module):
    def __init__(self,dim,len_sen):
        super().__init__()
        self.ln=nn.LayerNorm(dim)
        self.proj=nn.Conv1d(len_sen,len_sen,1)

        nn.init.zeros_(self.proj.weight)
        nn.init.ones_(self.proj.bias)
    
    def forward(self,x):
        res,gate=torch.chunk(x,2,-1) #bs,n,d_ff
        ###Norm
        gate=self.ln(gate) #bs,n,d_ff
        ###Spatial Proj
        gate=self.proj(gate) #bs,n,d_ff

        return res*gate
        
class EditedNet(nn.Module):
    def __init__(self, N, B, H, P, X, R, C, K, norm_type="gLN", causal=False,
                 mask_nonlinear='relu'):
        """
        Args:
            N: Number of filters in autoencoder
            B: Number of channels in bottleneck 1 × 1-conv block
            H: Number of channels in convolutional blocks
            P: Kernel size in convolutional blocks
            X: Number of convolutional blocks in each repeat
            R: Number of repeats
            C: Number of speakers
            norm_type: BN, gLN, cLN
            causal: causal or non-causal
            mask_nonlinear: use which non-linear function to generate mask
        """
        super(EditedNet, self).__init__()
        # Hyper-parameter
        self.N = N
        self.B = B
        self.H = H
        self.P = P
        self.X = X
        self.R = R
        self.C = C
        self.mask_nonlinear = mask_nonlinear
        self.K=K
        # Components
        # [M, N, K] -> [M, N, K]
        self.layer_norm = ChannelwiseLayerNorm(N)
        # [M, N, K] -> [M, B, K]
        self.bottleneck_conv1x1 = nn.Conv1d(N, B, 1, bias=False)
        # [M, B, K] -> [M, B, K]
        
        
        self.coreNet = gMLP_core(num_tokens=N,len_sen=B,dim=K,d_ff=1024,num_layers=0)

        # [M, B, K] -> [M, C*N, K]
        self.mask_conv1x1 = nn.Conv1d(B, C*N, 1, bias=False)
        # Put together
        self.network = nn.Sequential(self.layer_norm,
                                     self.bottleneck_conv1x1,
                                     self.coreNet,
                                     self.mask_conv1x1)

    def forward(self, mixture_w):
        """
        Keep this API same with TasNet
        Args:
            mixture_w: [M, N, K], M is batch size
        returns:
            est_mask: [M, C, N, K]
        """
        M, N, K = mixture_w.size()
        score = self.network(mixture_w)
        #score = self.network(mixture_w)  # [M, N, K] -> [M, C*N, K]
        score = score.view(M, self.C, N, K) # [M, C*N, K] -> [M, C, N, K]
        if self.mask_nonlinear == 'softmax':
            est_mask = F.softmax(score, dim=1)
        elif self.mask_nonlinear == 'relu':
            est_mask = F.relu(score)
        else:
            raise ValueError("Unsupported mask non-linear function")
        return est_mask

class gMLP_core(nn.Module):
    def __init__(self,num_tokens=None,len_sen=49,dim=512,d_ff=1024,num_layers=6):
        super().__init__()
        self.num_layers=num_layers
        #self.embedding=nn.Embedding(num_tokens,dim) if exist(num_tokens) else nn.Identity()

        self.gmlp=nn.ModuleList([Residual(nn.Sequential(OrderedDict([
            ('ln1_%d'%i,nn.LayerNorm(dim)),
            ('fc1_%d'%i,nn.Linear(dim,d_ff*2)),
            ('gelu_%d'%i,nn.GELU()),
            ('sgu_%d'%i,SpatialGatingUnit(d_ff,len_sen)),
            ('fc2_%d'%i,nn.Linear(d_ff,dim)),
        ])))  for i in range(num_layers)])


        #删除这部分
        #self.to_logits=nn.Sequential(
        #    nn.LayerNorm(dim),
         #   nn.Linear(dim,num_tokens),
        #    nn.Softmax(-1)
        #)


    def forward(self,x):
        #embedding
        #embeded=self.embedding(x)

        #gMLP
        y=nn.Sequential(*self.gmlp)(x)



        #to logits
        #logits=self.to_logits(y)


        return y

# TODO: Use nn.LayerNorm to impl cLN to speed up
class ChannelwiseLayerNorm(nn.Module):
    """Channel-wise Layer Normalization (cLN)"""
    def __init__(self, channel_size):
        super(ChannelwiseLayerNorm, self).__init__()
        self.gamma = nn.Parameter(torch.Tensor(1, channel_size, 1))  # [1, N, 1]
        self.beta = nn.Parameter(torch.Tensor(1, channel_size,1 ))  # [1, N, 1]
        self.reset_parameters()

    def reset_parameters(self):
        self.gamma.data.fill_(1)
        self.beta.data.zero_()

    def forward(self, y):
        """
        Args:
            y: [M, N, K], M is batch size, N is channel size, K is length
        Returns:
            cLN_y: [M, N, K]
        """
        mean = torch.mean(y, dim=1, keepdim=True)  # [M, 1, K]
        var = torch.var(y, dim=1, keepdim=True, unbiased=False)  # [M, 1, K]
        cLN_y = self.gamma * (y - mean) / torch.pow(var + EPS, 0.5) + self.beta
        return cLN_y


# define Biclassifier
class BinaryClassifier(nn.Module):
    def __init__(self,length):
        super(BinaryClassifier, self).__init__()
        # 定义三个全连接层
        # self.fc1 = nn.Linear(2048, 256)
        self.fc1 = nn.Linear(length, 1024)
        self.fc2 = nn.Linear(1024, 2048)
        # self.fc2 = nn.Linear(256, 256)
        # self.fc3 = nn.Linear(256, 1)
        # self.fc2_1 = nn.Linear(256, 256)
        #self.fc3 = nn.Linear(2048, 2048)
        self.fc3 = nn.Linear(2048, 2048)
        self.fc4 = nn.Linear(2048,1)


        # 定义ReLU和Sigmoid激活函数
        self.relu = nn.ReLU()
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        # group_s = 500
        # x = x.reshape(x.size(0), group_s, -1)
        # # 对第二个维度执行FFT
        # x = torch.fft.fftn(x, dim=2)
        # x = torch.abs(x)
        # # 计算形状为[B,n, 128]的张量的平均值
        # x = torch.mean(x, dim=1)
        # 应用第一个全连接层和ReLU激活函数
        x = self.fc1(x)
        x = self.relu(x)
        # 应用第二个全连接层和ReLU激活函数
        x = self.fc2(x)
        x = self.relu(x)
        # 应用第三个全连接层和ReLU激活函数
        x = self.fc3(x)
        x = self.relu(x)
        x = self.fc4(x)
        x = self.sigmoid(x)
        return x


# define Multiclassifier
class MultiClassifier(nn.Module):
    def __init__(self, length, fft_length,classNum):
        super(MultiClassifier, self).__init__()
        self.fft_length = fft_length
        self.length = length
        self.group_size = 128
        # 定义三个全连接层
        # self.fc1 = nn.Linear(fft_length, 256)
        self.fc1 = nn.Linear(fft_length, 1024)
        self.fc2 = nn.Linear(1024, 2048)
        self.fc3 = nn.Linear(2048, classNum)
        self.relu = nn.ReLU()
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        # # 应用第一个全连接层和ReLU激活函数
        # group_num = self.length // self.group_size
        # num_elements = group_num * self.group_size
        #
        # # 将张量重塑为形状为[B,n, 128]的张量
        # x = x.reshape(x.size(0), group_num, -1)
        #
        # # 对第二个维度执行FFT
        # x = torch.fft.fftn(x, dim=2)
        # x = torch.abs(x)
        # # 计算形状为[B,n, 128]的张量的平均值
        # x = torch.mean(x, dim=1)
        x = self.fc1(x)
        x = self.relu(x)
        # 应用第二个全连接层和ReLU激活函数
        x = self.fc2(x)
        x = self.relu(x)
        # 应用第三个全连接层和ReLU激活函数
        x = self.fc3(x)
        return x


if __name__ == '__main__':
    
    torch.manual_seed(123)
    M, N, L, T = 16, 1, 4, 12
    K = 2*T//L-1
    B, H, P, X, R, C, norm_type, causal = 1, 3, 3, 3, 2, 2, "gLN", False
    # mixture = torch.randint(3, (M, T), dtype=torch.float)
    # # test Encoder
    # encoder = Encoder(L, N)
    # encoder.conv1d_U.weight.data = torch.randint(2, encoder.conv1d_U.weight.size(), dtype=torch.float)
    # with torch.no_grad():
        # mixture_w = encoder(mixture)
    # print('mixture', mixture)
    # print('U', encoder.conv1d_U.weight)
    # print('mixture_w', mixture_w)
    # print('mixture_w size', mixture_w.size())

    num_tokens=100
    bs=16
    #test
    len_sen=64000
    num_layers=6
    input = torch.randint(num_tokens, (bs, len_sen), dtype=torch.float).cuda() #bs,len_sen

    # g = make_dot(output.mean(), params=dict(gmlp.named_parameters()), show_attrs=True, show_saved=True)
    # g = make_dot(output.mean())
    # g.view()
    se_input = torch.randint(100, (bs,128),dtype=torch.float).cuda()
    print(se_input.shape)
    separator = mixNet(N, B, H, P, X, R, C, 128).cuda()
    out = separator(se_input)
    print('out.shape====',out)