# Adapted to tecorigin hardware。
import os

from PIL import Image
import numpy as np

from torchvision.transforms import functional as F
import torchvision.transforms as transforms
import torch
import torch_sdaa
from torch.autograd import Variable
# [修改] 移除对cudnn的引用，并改用sdaa
# import torch.backends.cudnn as cudnn
# cudnn.benchmark = True

import net

# [修改] 指定设备为 sdaa
device = torch.device('sdaa')


def extractDeepFeature(img, model, is_gray):
    if is_gray:
        transform = transforms.Compose([
            transforms.Grayscale(),
            transforms.ToTensor(),  # range [0, 255] -> [0.0,1.0]
            transforms.Normalize(mean=(0.5,), std=(0.5,))  # range [0.0, 1.0] -> [-1.0,1.0]
        ])
    else:
        transform = transforms.Compose([
            transforms.ToTensor(),  # range [0, 255] -> [0.0,1.0]
            transforms.Normalize(mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5))  # range [0.0, 1.0] -> [-1.0,1.0]
        ])
    img, img_ = transform(img), transform(F.hflip(img))
    # [修改] 将 'cuda' 改为 sdaa
    img, img_ = img.unsqueeze(0).to(device), img_.unsqueeze(0).to(device)
    ft = torch.cat((model(img), model(img_)), 1)[0].to('cpu')
    return ft


def KFold(n=6000, n_folds=10):
    folds = []
    base = list(range(n))
    for i in range(n_folds):
        # [修改] Python3.10 需要使用整除
        test = base[i * n // n_folds: (i + 1) * n // n_folds]
        train = list(set(base) - set(test))
        folds.append([train, test])
    return folds


def eval_acc(threshold, diff):
    y_true = []
    y_predict = []
    for d in diff:
        same = 1 if float(d[2]) > threshold else 0
        y_predict.append(same)
        y_true.append(int(d[3]))
    y_true = np.array(y_true)
    y_predict = np.array(y_predict)
    accuracy = 1.0 * np.count_nonzero(y_true == y_predict) / len(y_true)
    return accuracy


def find_best_threshold(thresholds, predicts):
    best_threshold = best_acc = 0
    for threshold in thresholds:
        accuracy = eval_acc(threshold, predicts)
        if accuracy >= best_acc:
            best_acc = accuracy
            best_threshold = threshold
    return best_threshold


def eval(model, model_path=None, is_gray=False):
    predicts = []
    # [修改] 使用 map_location=device 将权重加载到 sdaa 上
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()
    root = '/data/datasets/CosFace/result/lfw-112X96/'
    # [修改] 获取 lfw_pairs.txt 文件路径
    lfw_pairs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lfw_pairs.txt")
    with open(lfw_pairs_path) as f:
        pairs_lines = f.readlines()[1:]

    with torch.no_grad():
        for i in range(6000):
            p = pairs_lines[i].replace('\n', '').split('\t')

            if 3 == len(p):
                sameflag = 1
                name1 = p[0] + '/' + p[0] + '_' + '{:04}.jpg'.format(int(p[1]))
                name2 = p[0] + '/' + p[0] + '_' + '{:04}.jpg'.format(int(p[2]))
            elif 4 == len(p):
                sameflag = 0
                name1 = p[0] + '/' + p[0] + '_' + '{:04}.jpg'.format(int(p[1]))
                name2 = p[2] + '/' + p[2] + '_' + '{:04}.jpg'.format(int(p[3]))
            else:
                raise ValueError("WRONG LINE IN 'pairs.txt! ")

            with open(root + name1, 'rb') as f:
                img1 =  Image.open(f).convert('RGB')
            with open(root + name2, 'rb') as f:
                img2 =  Image.open(f).convert('RGB')
            f1 = extractDeepFeature(img1, model, is_gray)
            f2 = extractDeepFeature(img2, model, is_gray)

            distance = f1.dot(f2) / (f1.norm() * f2.norm() + 1e-5)
            predicts.append('{}\t{}\t{}\t{}\n'.format(name1, name2, distance, sameflag))

    accuracy = []
    thd = []
    folds = KFold(n=6000, n_folds=10)
    thresholds = np.arange(-1.0, 1.0, 0.005)
    # [修改] Python3.10，替换掉 map(...) 用列表推导
    predicts = np.array([line.strip('\n').split() for line in predicts])

    for idx, (train, test) in enumerate(folds):
        best_thresh = find_best_threshold(thresholds, predicts[train])
        accuracy.append(eval_acc(best_thresh, predicts[test]))
        thd.append(best_thresh)
    print('LFWACC={:.4f} std={:.4f} thd={:.4f}'.format(np.mean(accuracy), np.std(accuracy), np.mean(thd)))

    return np.mean(accuracy), predicts


if __name__ == '__main__':
    # [修改] 如果单独执行，可以这样测试
    _, result = eval(net.sphere().to(device), model_path='checkpoint/CosFace_24_checkpoint.pth')
    np.savetxt("result.txt", result, '%s')
