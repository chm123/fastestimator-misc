# Copyright 2019 The FastEstimator Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
import os
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import wget

from fastestimator.dataset.dir_dataset import DirDataset
from fastestimator.util.util import Suppressor
from fastestimator.util.wget_util import bar_custom, callback_progress
from pycocotools.coco import COCO

wget.callback_progress = callback_progress


class MSCOCODataset(DirDataset):
    instances: Optional[COCO]
    captions: Optional[COCO]

    def __init__(self,
                 image_dir: str,
                 annotation_file: str,
                 caption_file: str,
                 include_bboxes: bool = True,
                 include_masks: bool = False,
                 include_captions: bool = False):
        super().__init__(root_dir=image_dir,
                         data_key="image",
                         recursive_search=False)
        if include_masks:
            assert include_bboxes, "must include bboxes with mask data"
        self.include_bboxes = include_bboxes
        self.include_masks = include_masks
        with Suppressor():
            self.instances = COCO(annotation_file)
            self.captions = COCO(caption_file) if include_captions else None

    def __getitem__(self, index: Union[int, str]):
        has_data = False
        while not has_data:
            has_box, has_mask, has_caption = True, True, True
            response = self._get_single_item(index)
            if self.include_bboxes and not response["bbox"]:
                has_box = False
            if self.include_masks and not response["mask"]:
                has_mask = False
            if self.captions and not response["caption"]:
                has_caption = False
            has_data = has_box and has_mask and has_caption
            index = np.random.randint(len(self))
        return response

    def _get_single_item(self, index: Union[int, str]):
        response = super().__getitem__(index)
        if isinstance(index, str):
            return response
        else:
            response = deepcopy(response)
        image = response["image"]
        image_id = int(os.path.splitext(os.path.basename(image))[0])
        response["image_id"] = image_id
        if self.include_bboxes:
            self._populate_instance_data(response, image_id)
        if self.captions:
            self._populate_caption_data(response, image_id)
        return response

    def _populate_instance_data(self, data: Dict[str, Any], image_id: int):
        data["bbox"] = []
        if self.include_masks:
            data["mask"] = []
        annotation_ids = self.instances.getAnnIds(imgIds=image_id,
                                                  iscrowd=False)
        if annotation_ids:
            annotations = self.instances.loadAnns(annotation_ids)
            for annotation in annotations:
                data["bbox"].append(
                    tuple(annotation['bbox'] + [annotation['category_id']]))
                if self.include_masks:
                    data["mask"].append(self.instances.annToMask(annotation))

    def _populate_caption_data(self, data: Dict[str, Any], image_id: int):
        data["caption"] = []
        annotation_ids = self.captions.getAnnIds(imgIds=image_id)
        if annotation_ids:
            annotations = self.captions.loadAnns(annotation_ids)
            for annotation in annotations:
                data["caption"].append(annotation['caption'])


def load_data(
        root_dir: Optional[str] = None,
        sample_num = 1000,
        load_bboxes: bool = True,
        load_masks: bool = False,
        load_captions: bool = False,) -> Tuple[MSCOCODataset, MSCOCODataset]:
    """Download the COCO dataset to local storage, if not already downloaded.

    Args:
        root_dir: The path to store the COCO data. When `path` is not provided, will save at
            `fastestimator_data` under home directory.
        load_bboxes: whether to get bbox-related data
        load_masks: whether to serve mask data (in the form of an array of 1-hot images)
        load_captions: whether to get caption-related data

    Returns:
        TrainData, EvalData
    """
    if root_dir is None:
        root_dir = os.path.join(str(Path.home()), 'fastestimator_data',
                                'MSCOCO2017')
    else:
        root_dir = os.path.join(os.path.abspath(root_dir), 'MSCOCO2017')
    os.makedirs(root_dir, exist_ok=True)

    train_data = os.path.join(root_dir, "train2017")
    eval_data = os.path.join(root_dir, "val2017")
    annotation_data = os.path.join(root_dir, "annotations")

    data_subsample(train_data, sample_num)
    data_subsample(eval_data, sample_num)

    files = [
        (train_data, "train2017.zip",
         'http://images.cocodataset.org/zips/train2017.zip'),
        (eval_data, "val2017.zip",
         'http://images.cocodataset.org/zips/val2017.zip'),
        (annotation_data, "annotations_trainval2017.zip",
         'http://images.cocodataset.org/annotations/annotations_trainval2017.zip'
         )
    ]

    for data_dir, zip_name, download_url in files:
        if not os.path.exists(data_dir):
            zip_path = os.path.join(root_dir, zip_name)
            # Download
            if not os.path.exists(zip_path):
                print("Downloading {} to {}".format(zip_name, root_dir))
                wget.download(download_url, zip_path, bar=bar_custom)
            # Extract
            print("Extracting {}".format(zip_name))
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                zip_file.extractall(os.path.dirname(zip_path))

    train_annotation = os.path.join(annotation_data,
                                    "instances_train2017.json")
    eval_annotation = os.path.join(annotation_data, "instances_val2017.json")
    train_captions = os.path.join(annotation_data, "captions_train2017.json")
    eval_captions = os.path.join(annotation_data, "captions_val2017.json")
    train_ds = MSCOCODataset(train_data,
                             train_annotation,
                             train_captions,
                             include_bboxes=load_bboxes,
                             include_masks=load_masks,
                             include_captions=load_captions)
    eval_ds = MSCOCODataset(eval_data,
                            eval_annotation,
                            eval_captions,
                            include_bboxes=load_bboxes,
                            include_masks=load_masks,
                            include_captions=load_captions)
    return train_ds, eval_ds


def data_subsample(source_dir, sample_num):
    # subsample the image
    img_count = 0
    for dirpath, _, filenames in os.walk(source_dir):
        for f in filenames:
            if img_count < sample_num:
                img_count += 1
            else:
                os.remove(os.path.join(dirpath, f))

if __name__ == "__main__":
    load_data()