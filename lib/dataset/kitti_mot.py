"""
KITTI Object Detection Database
Image list and annotation format follow the multicustom format.
"""

import cv2
import os
import numpy as np
import cPickle
from imdb import IMDB
from kitti_mot_eval import kitti_mot_eval

class KittiMOT(IMDB):
    def __init__(self, image_set, root_path, dataset_path, result_path=None):
        """
        fill basic information to initialize imdb
        :param image_set: train or val or trainval or test
        :param root_path: 'cache' and 'rpn_data'
        :param dataset_path: data and results
        :return: imdb object
        """
        super(KittiMOT, self).__init__('KittiMOT', image_set, root_path, dataset_path)
        self.image_set = image_set
        self.root_path = root_path
        self.data_path = dataset_path

        self.classes = ['__background__', 'Car', 'Pedestrian', 'Cyclist']
        self.num_classes = len(self.classes)
        self.load_image_set_index()
        self.num_images = len(self.image_set_index)
        print 'num_images', self.num_images

    def load_image_set_index(self):
        """
        Edited for kitti mot for Deep-Feature-Flow
        find out which indexes correspond to given image set (train or val)
        :return:
        """
        image_set_index_file = os.path.join(self.data_path, self.image_set + '.txt')
        assert os.path.exists(image_set_index_file), "Path does not exist: {}".format(image_set_index_file)

        with open(image_set_index_file) as f:
            lines = [x.strip().split(' ') for x in f.readlines()]

        if len(lines[0]) == 2:
            self.image_set_index = [x[0] for x in lines]
            self.frame_id = [int(x[1]) for x in lines]
        else:
            # for get pair iamge path
            # 'data/%06d' % 123   ---> 'data/000123'
            self.image_set_index = ['%s/%06d' % (x[0], int(x[2])) for x in lines]
            self.pattern = [x[0]+'/%06d' for x in lines]
            self.frame_id = [int(x[1]) for x in lines]
            self.frame_seg_id = [int(x[2]) for x in lines]
            self.frame_seg_len = [int(x[3]) for x in lines]

    def image_path_from_index(self, index):
        """
        given image index, find out full path
        :param index: index of a specific image
        :return: full path of this image
        """
        image_file = index+'.png'
        # assert os.path.exists(image_file), 'Path does not exist: {}'.format(image_file)
        return image_file

    def gt_roidb(self):
        """
        return ground truth image regions database
        :return: imdb[image_index]['boxes', 'gt_classes', 'gt_overlaps', 'flipped']
        """
        cache_file = os.path.join(self.cache_path, self.name + '_gt_roidb.pkl')
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as fid:
                roidb = cPickle.load(fid)
            print '{} gt roidb loaded from {}'.format(self.name, cache_file)
            return roidb
        gt_roidb = [self.load_kitti_mot_annotations(index) for index in range(0, len(self.image_set_index))]
        with open(cache_file, 'wb') as fid:
            cPickle.dump(gt_roidb, fid, cPickle.HIGHEST_PROTOCOL)
        print "wrote gt roidb to {}".format(cache_file)

        return gt_roidb

    def load_kitti_mot_annotations(self, iindex):
        """
        Edited for kitti mot for Deep-Feature-Flow
        for a given index, load image and bounding boxes info from a single image list
        :return: list of record['boxes', 'gt_classes', 'gt_overlaps', 'flipped']
        """
        index = self.image_set_index[iindex]
        print 'Current {} th file'.format(iindex)
        roi_rec = dict()
        roi_rec['image'] = self.image_path_from_index(index)
        roi_rec['frame_id'] = self.frame_id[iindex]

        if hasattr(self,'frame_seg_id'):
            roi_rec['pattern'] = self.image_path_from_index(self.pattern[iindex])
            roi_rec['frame_seg_id'] = self.frame_seg_id[iindex]
            roi_rec['frame_seg_len'] = self.frame_seg_len[iindex]


        image_size = cv2.imread(roi_rec['image']).shape
        roi_rec['height'] = image_size[0]
        roi_rec['width'] = image_size[1]

        # load bbox
        annotation_file_path = index.replace("image_02", 'label_new')+'.txt'
        assert os.path.exists(annotation_file_path), "Path does not exist:{}".format(annotation_file_path)

        with open(annotation_file_path, 'r') as f:
            annotation_list = f.readlines()

        num_objs = len(annotation_list)

        boxes = np.zeros((num_objs, 4), dtype=np.uint16)
        gt_classes = np.zeros((num_objs), dtype=np.int32)
        overlaps = np.zeros((num_objs, self.num_classes), dtype=np.float32)
        valid_objs = np.zeros((num_objs), dtype=np.bool)
        class_to_index = dict(zip(self.classes, range(self.num_classes)))

        for ix, line in enumerate(annotation_list):
            label = line.strip().split(' ')
            x1 = np.maximum(float(label[6]), 0)
            y1 = np.maximum(float(label[7]), 0)
            x2 = np.minimum(float(label[8]), roi_rec['width'] - 1)
            y2 = np.minimum(float(label[9]), roi_rec['height'] - 1)

            valid_objs[ix] = True
            cls = class_to_index[label[2]]
            boxes[ix, :] = [x1, y1, x2, y2]
            gt_classes[ix] = cls
            overlaps[ix, cls] = 1.0
        boxes = boxes[valid_objs, :]
        gt_classes = gt_classes[valid_objs]
        overlaps = overlaps[valid_objs, :]

        assert (boxes[:, 2] >= boxes[:, 0]).all()

        roi_rec.update({'boxes': boxes,
                        'gt_classes': gt_classes,
                        'gt_overlaps': overlaps,
                        'max_classes': overlaps.argmax(axis=1),
                        'max_overlaps': overlaps.max(axis=1),
                        'flipped': False})
        return roi_rec


    def evaluate_detections(self, detections):
        """
        write to cache and generate kitti format
        :param detections: result matrix, [bbox, confidence]
        :return:
        """
        result_dir = os.path.join(self.result_path, 'results')
        if not os.path.exists(result_dir):
            os.mkdir(result_dir)
        self.write_kitti_mot_results(detections)
        info = self.do_python_eval()
        return info

        # res_folder = os.path.join(self.cache_path, 'results')
        # if not os.path.exists(res_folder):
        #     os.makedirs(res_folder)
        # # write out all results
        # for cls_ind, cls in enumerate(self.classes):
        #     if cls == '__background__':
        #         continue
        #     print 'Writing preliminary {} results'.format(cls)
        #     filename = os.path.join(self.cache_path, 'results', self.image_set + '_' + cls + '.txt')
        #     with open(filename, 'w') as f:
        #         for im_ind, index in enumerate(self.image_set_index):
        #             dets = detections[cls_ind][im_ind]
        #             if len(dets) == 0:
        #                 continue
        #             for k in range(dets.shape[0]):
        #                 f.write('{:s} {:.8f} {:.2f} {:.2f} {:.2f} {:.2f}\n'.
        #                         format(index, dets[k, -1],
        #                                dets[k, 0], dets[k, 1], dets[k, 2], dets[k, 3]))
        # # write kitti format
        # self.gen_eval()
    def evaluate_detections_multiprocess(self, detections):
        result_dir = os.path.join(self.result_path, 'results')
        if not os.path.exists(result_dir):
            os.mkdir(result_dir)

        self.write_kitti_mot_results_multiprocess(detections)
        info = self.do_python_eval_gen()
        return info

    def get_result_file_template(self):
        """
        :return: a string template
        """
        res_file_folder = os.path.join(self.result_path, 'results')
        filename = 'det_' + self.image_set + '_{:s}.txt'
        path = os.path.join(res_file_folder, filename)
        return path
    def write_kitti_mot_results(self, all_boxes):
        print "Writing {} Kitti MOT results file".format('all')
        filename = self.get_result_file_template().format('all')

        with open(filename, 'wt') as f:
            for im_ind, index in enumerate(self.image_set_index):
                for cls_ind, cls in enumerate(self.classes):
                    if cls == '__background__':
                        continue
                    dets = all_boxes[cls_ind][im_ind]
                    if len(dets) == 0:
                        continue

                    for k in range(dets.shape[0]):
                        f.write('{:d} {:d} {:.4f} {:.2f} {:.2f} {:.2f} {:.2f}\n'.
                                format(self.frame_id[im_ind], cls_ind, dets[k, -1],
                                dets[k, 0], dets[k, 1], dets[k, 2], dets[k, 3]))

    def write_kitti_mot_results_multiprocess(self, detections):
        print "Writing {} Kitti MOT results file".format('all')
        filename = self.get_result_file_template().format('all')
        with open(filename, 'wt') as f:
            for detection in detections:
                all_boxes = detection[0]
                frame_ids = detection[1]
                for im_ind in range(len(frame_ids)):
                    for cls_ind, cls in enumerate(self.classes):
                        if cls == '__background__':
                            continue
                        dets = all_boxes[cls_ind][im_ind]

                        if len(dets) == 0:
                            continue
                        for k in range(dets.shape[0]):
                            f.write('{:d} {:d} {:.4f} {:.2f} {:.2f} {:.2f} {:.2f}\n'.
                                    format(frame_ids[im_ind], cls_ind, dets[k, -1],
                                    dets[k, 0], dets[k, 1], dets[k, 2], dets[k, 3]))
    def do_python_eval(self):
        """
        python evaluation wrapper
        :return: info_str
        """
        info_str = ''
        imageset_file = os.path.join(self.data_path, self.image_set + '.txt')
        annocache = os.path.join(self.cache_path, self.name + '_annotations.pkl')

        filename = self.get_result_file_template().format('all')
        ap = kitti_mot_eval(filename, imageset_file, self.classes, annocache, ovthresh=0.5)

        for cls_ind, cls in enumerate(self.classes):
            if cls == '__background__':
                continue
            print('AP for {} = {:.4f}'.format(cls, ap[cls_ind-1]))
            info_str += 'AP for {} = {:.4f}\n'.format(cls, ap[cls_ind-1])
        print('Mean AP@0.5 = {:.4f}'.format(np.mean(ap)))
        info_str += 'Mean AP@0.5 = {:.4f}\n\n'.format(np.mean(ap))
        return info_str

    def do_python_eval_gen(self):
        """
        python evaluation wrapper
        :return: info_str
        """
        info_str = ''
        imageset_file = os.path.join(self.data_path, self.image_set + '_eval.txt')
        annocache = os.path.join(self.cache_path, self.name + '_annotations.pkl')

        with open(imageset_file, 'w') as f:
            for i in range(len(self.pattern)):
                for j in range(self.frame_seg_len[i]):
                    f.write((self.pattern[i] % (self.frame_seg_id[i] + j)) + ' ' + str(self.frame_id[i] + j) + '\n')

        filename = self.get_result_file_template().format('all')
        ap = kitti_mot_eval(filename, imageset_file, self.classes, annocache, ovthresh=0.5)
        for cls_ind, cls in enumerate(self.classes):
            if cls == '__background__':
                continue
            print('AP for {} = {:.4f}'.format(cls, ap[cls_ind-1]))
            info_str += 'AP for {} = {:.4f}\n'.format(cls, ap[cls_ind-1])
        print('Mean AP@0.5 = {:.4f}'.format(np.mean(ap)))
        info_str += 'Mean AP@0.5 = {:.4f}\n\n'.format(np.mean(ap))
        return info_str

    # def gen_eval(self):
    #     """
    #     save to kitti format
    #     :return:
    #     """
    #     import shutil
    #     res_dir = os.path.join(self.data_path, 'results/')
    #     if os.path.exists(res_dir):
    #         shutil.rmtree(res_dir)
    #     if not os.path.exists(res_dir):
    #         os.mkdir(res_dir)
    #
    #     for cls_ind, cls in enumerate(self.classes):
    #         if cls == '__background__':
    #             continue
    #         print 'Writing final {} results'.format(cls)
    #         filename = os.path.join(self.cache_path, 'results', self.image_set + '_' + cls + '.txt')
    #         with open(filename, 'r') as f:
    #             dets = f.readlines()
    #         for l in dets:
    #             im_ind = l.split(' ')[0]
    #             det = map(float, l.split(' ')[1:])
    #             res_dir_det = os.path.dirname(res_dir + im_ind)
    #             if not os.path.exists(res_dir_det):
    #                 os.makedirs(res_dir_det)
    #             with open(os.path.join(res_dir_det, os.path.basename(im_ind).split('.')[0] + '.txt'), 'a') as fo:
    #                 fo.write('%s -1 -1 -10 ' % cls)
    #                 fo.write('%.2f ' % det[1])
    #                 fo.write('%.2f ' % det[2])
    #                 fo.write('%.2f ' % det[3])
    #                 fo.write('%.2f ' % det[4])
    #                 fo.write('-1 -1 -1 -1000 -1000 -1000 -10 ')
    #                 fo.write('%.8f\n' % det[0])
    #
    #     with open(os.path.join(self.data_path, 'imglists', self.image_set + '.lst')) as f:
    #         img_list = f.readlines()
    #     img_list = [item.split(':')[0] for item in img_list]
    #     for im_ind in img_list:
    #         res_dir_det = os.path.dirname(res_dir + im_ind)
    #         if not os.path.exists(res_dir_det):
    #             os.makedirs(res_dir_det)
    #         filename = os.path.join(res_dir_det, os.path.basename(im_ind).split('.')[0] + '.txt')
    #         if not os.path.exists(filename):
    #             print 'creating', filename
    #             open(filename, 'a').close()
