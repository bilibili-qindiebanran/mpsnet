import os
import pathlib
import numpy as np
import cv2
from keras.utils import img_to_array
from sklearn.model_selection import StratifiedKFold
from sklearn.utils import shuffle, class_weight


def _iter_class_dirs(root, extension):
    """按 Palm_ID 目录名排序，返回 [(class_name, [image_path, ...]), ...]。

    显式按目录名分组，避免依赖文件系统遍历顺序来推断标签（Windows 之外
    该顺序不保证），因此路径分隔符也不再需要解析。
    """
    root = pathlib.Path(root)
    if not root.is_dir():
        raise FileNotFoundError('数据目录不存在: ' + str(root))

    classes = []
    for class_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name):
        files = sorted(p for p in class_dir.rglob('*' + extension))
        if files:
            classes.append((class_dir.name, files))

    return classes


class DataLoader:

    def __init__(self, config):

        self.data_folder = config.data_folder
        self.image_extension = config.image_extension
        self.train_data = []
        self.train_labels = []
        label = -1
        i = 0
        print('Load training databases.')

        for folder in config.train_folders:
            folder = folder.strip()
            if not folder:
                continue
            path = os.path.join(self.data_folder, folder)
            n_before = i

            for class_name, paths in _iter_class_dirs(path, self.image_extension):
                label += 1
                for p in paths:
                    img = cv2.imread(str(p), 0)
                    if img is None:
                        raise FileNotFoundError('无法读取图像: ' + str(p))
                    self.train_data.append(img_to_array(img)/255.0)
                    self.train_labels.append(label)
                    i += 1
                    if(i%1000==0):
                        print('Processed: ', i, end='\r')
            print('Database:', folder, '- total images:', i - n_before)

        print('Total training images: ', i)
        self.train_data = np.asarray(self.train_data)
        self.train_labels = np.asarray(self.train_labels)
        self.sample_shape = self.train_data.shape[1:]
        self.n_train_classes = len(np.unique(self.train_labels))

        self.folds = list(StratifiedKFold(n_splits=config.n_folds, shuffle=True, random_state=config.random_state).split(self.train_data, self.train_labels))

        class_weights = class_weight.compute_class_weight(class_weight='balanced', classes=np.unique(self.train_labels), y=self.train_labels)
        self.class_weights = {int(l):float(c) for l,c in zip(np.unique(self.train_labels), class_weights)}

    def load_test_data(self, test_folder):
        self.test_data = []
        self.test_labels = []
        label = -1
        i = 0
        print('Load test databases.')

        for class_name, paths in _iter_class_dirs(os.path.join(self.data_folder, test_folder), self.image_extension):
            label += 1
            for p in paths:
                img = cv2.imread(str(p), 0)
                if img is None:
                    raise FileNotFoundError('无法读取图像: ' + str(p))
                self.test_data.append(img_to_array(img)/255.0)
                self.test_labels.append(label)
                i+=1

                if(i%100==0):
                    print('Processed: ', i, end='\r')

        print('Total test images: ', i)
        self.test_data = np.asarray(self.test_data)
        self.test_labels = np.asarray(self.test_labels)
        self.test_name = test_folder
        self.n_test_samples = self.test_data.shape[0]
        self.n_test_classes = len(np.unique(self.test_labels))
        self.test_class_size = self.n_test_samples//self.n_test_classes

    def get_fold_data(self, fold_id):
        train_ids, test_ids = self.folds[fold_id]
        return self.train_data[train_ids], self.train_labels[train_ids], self.test_data[test_ids], self.test_labels[test_ids]
